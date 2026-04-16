#!/usr/bin/env python3
import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from mininet.log import info, setLogLevel

from analyze_logs import analyze_directory

ROOT = Path(__file__).resolve().parents[1]
MSVS_ROOT = ROOT.parent / "m-svs"
DEFAULT_BINARY = MSVS_ROOT / "build/examples/mini_ndn_svs_eval"
DEFAULT_PREFIX = "/ndn/svs-eval"


def load_env_file(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def write_grid_topology(path, rows, cols, delay_ms, loss):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        handle.write("[nodes]\n")
        for r in range(rows):
            for c in range(cols):
                handle.write(f"n{r}_{c}: _\n")
        handle.write("[links]\n")
        for r in range(rows):
            for c in range(cols):
                node = f"n{r}_{c}"
                if c + 1 < cols:
                    handle.write(f"{node}:n{r}_{c+1} delay={delay_ms}ms loss={loss}\n")
                if r + 1 < rows:
                    handle.write(f"{node}:n{r+1}_{c} delay={delay_ms}ms loss={loss}\n")


def choose_fast_nodes(host_names, count, seed, distribution, alpha):
    rng = random.Random(seed)
    ordered = sorted(host_names)
    count = min(count, len(ordered))

    if distribution == "zipf":
        available = ordered[:]
        weights = [1.0 / ((i + 1) ** alpha) for i in range(len(available))]
        selected = []
        while available and len(selected) < count:
            pick = rng.choices(available, weights=weights, k=1)[0]
            idx = available.index(pick)
            selected.append(pick)
            available.pop(idx)
            weights.pop(idx)
        return set(selected)

    return set(rng.sample(ordered, count))


def wait_for_completion(ndn, pid_map, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        running = 0
        for node, pid in pid_map:
            status = node.cmd(f"kill -0 {pid} >/dev/null 2>&1; echo $?").strip().splitlines()[-1]
            if status == "0":
                running += 1
        if running == 0:
            return
        info(f"Waiting for {running} application processes to finish\n")
        time.sleep(2)


def wait_for_nfd_ready(hosts, timeout_s):
    deadline = time.time() + timeout_s
    pending = {host.name for host in hosts}

    while pending and time.time() < deadline:
        ready = set()
        for host in hosts:
            if host.name not in pending:
                continue

            sock = f"/run/nfd/{host.name}.sock"
            status = host.cmd(
                f"test -S {sock} && pgrep -x nfd >/dev/null 2>&1; echo $?"
            ).strip().splitlines()[-1]
            if status == "0":
                ready.add(host.name)

        pending -= ready
        if pending:
            info(f"Waiting for NFD readiness on {len(pending)} nodes\n")
            time.sleep(2)

    if pending:
        raise RuntimeError(f"NFD did not become ready on nodes: {', '.join(sorted(pending))}")


def get_neighbor_ip_map(node):
    neighbor_ips = {}
    for intf in node.intfList():
        link = getattr(intf, "link", None)
        if not link:
            continue

        node1, node2 = link.intf1.node, link.intf2.node
        if node1 == node:
            other = node2
            ip = other.IP(str(link.intf2))
        else:
            other = node1
            ip = other.IP(str(link.intf1))

        if other.name != node.name:
            neighbor_ips[other.name] = ip

    return neighbor_ips


def setup_sync_faces_and_routes(hosts, sync_prefix, nfdc, retries=8):
    info("Creating faces and adding routes to FIB\n")
    for node in hosts:
        neighbor_ips = get_neighbor_ip_map(node)
        for neighbor_name, ip in sorted(neighbor_ips.items()):
            face_id = -1
            for _ in range(retries):
                face_id = nfdc.createFace(node, ip, nfdc.PROTOCOL_UDP)
                if isinstance(face_id, str):
                    break
                time.sleep(1)

            if not isinstance(face_id, str):
                raise RuntimeError(
                    f"Failed to create face from {node.name} to {neighbor_name} at {ip}"
                )

            nfdc.registerRoute(node, sync_prefix, face_id, cost=0)

    info("Processed all the routes to NFD\n")


def run_experiment(args):
    saved_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    from mininet.node import OVSController
    from minindn.apps.app_manager import AppManager
    from minindn.apps.nfd import Nfd
    from minindn.helpers.nfdc import Nfdc
    from minindn.minindn import Minindn
    sys.argv = saved_argv

    variant_dir = Path(args.variant_dir).resolve()
    env = load_env_file(variant_dir / "variant.env")
    variant_name = variant_dir.name

    binary = Path(args.binary or DEFAULT_BINARY)
    if not binary.exists():
        raise FileNotFoundError(f"Evaluation binary not found: {binary}")

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = ROOT / "results" / variant_name / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    work_dir = log_dir / "minindn-work"
    work_dir.mkdir(parents=True, exist_ok=True)

    topo_path = log_dir / f"grid-{args.rows}x{args.cols}.conf"
    write_grid_topology(topo_path, args.rows, args.cols, args.delay_ms, args.loss)

    Minindn.cleanUp()
    Minindn.verifyDependencies()

    minindn_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        ndn = Minindn(topoFile=str(topo_path), controller=OVSController, workDir=str(work_dir))
    finally:
        sys.argv = minindn_argv
    ndn.start()

    try:
        info("Starting NFD on all nodes\n")
        AppManager(ndn, ndn.net.hosts, Nfd)
        wait_for_nfd_ready(ndn.net.hosts, args.nfd_ready_timeout)

        info("Configuring multicast sync strategy and routes\n")
        for node in ndn.net.hosts:
            Nfdc.setStrategy(node, args.sync_prefix, Nfdc.STRATEGY_MULTICAST)

        setup_sync_faces_and_routes(ndn.net.hosts, args.sync_prefix, Nfdc, args.route_retries)
        time.sleep(2)

        fast_nodes = choose_fast_nodes([host.name for host in ndn.net.hosts],
                                       args.fast_producers,
                                       args.seed,
                                       args.distribution,
                                       args.zipf_alpha)
        (log_dir / "fast_nodes.json").write_text(json.dumps(sorted(fast_nodes), indent=2) + "\n")

        info(f"Selected {len(fast_nodes)} fast producers for {variant_name}\n")
        pid_map = []
        local_lib_dir = str((MSVS_ROOT / "build").resolve())
        for host in ndn.net.hosts:
            host_env = dict(env)
            host_env["SVS_PUB_INTERVAL_MS"] = str(args.fast_ms if host.name in fast_nodes else args.slow_ms)
            host_env["SVS_NODE_ROLE"] = "fast" if host.name in fast_nodes else "slow"
            host_env["SVS_RUN_DURATION_SEC"] = str(args.duration_s)
            host_env["SVS_START_DELAY_MS"] = str(args.start_delay_ms)
            host_env["SVS_COOLDOWN_MS"] = str(args.cooldown_ms)
            host_env["SVS_SYNC_PREFIX"] = args.sync_prefix
            host_env["LD_LIBRARY_PATH"] = (
                local_lib_dir
                if not host_env.get("LD_LIBRARY_PATH")
                else f"{local_lib_dir}:{host_env['LD_LIBRARY_PATH']}"
            )

            exports = " ".join(f'{k}="{v}"' for k, v in sorted(host_env.items()))
            log_file = log_dir / f"{host.name}.log"
            cmd = f"env {exports} {binary} /{host.name} {args.sync_prefix} > {log_file} 2>&1 & echo $!"
            pid = host.cmd(cmd).strip().splitlines()[-1]
            pid_map.append((host, pid))

        wait_for_completion(ndn,
                            pid_map,
                            args.start_delay_ms / 1000 + args.duration_s + args.cooldown_ms / 1000 + 20)
    finally:
        ndn.stop()

    summary = analyze_directory(log_dir)
    summary.update({
        "variant": variant_name,
        "rows": args.rows,
        "cols": args.cols,
        "fast_producers": args.fast_producers,
        "distribution": args.distribution,
        "sync_prefix": args.sync_prefix,
    })
    summary_path = log_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary_path


def main():
    parser = argparse.ArgumentParser(description="Run SVS comparison variants on Mini-NDN")
    parser.add_argument("--variant-dir", required=True, help="folder containing variant.env")
    parser.add_argument("--binary", help="path to the built evaluation executable")
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--fast-ms", type=int, default=100)
    parser.add_argument("--fast-producers", type=int, default=8)
    parser.add_argument("--delay-ms", type=int, default=10)
    parser.add_argument("--loss", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="uniform")
    parser.add_argument("--zipf-alpha", type=float, default=1.2)
    parser.add_argument("--start-delay-ms", type=int, default=2000)
    parser.add_argument("--cooldown-ms", type=int, default=3000)
    parser.add_argument("--nfd-ready-timeout", type=int, default=60)
    parser.add_argument("--route-retries", type=int, default=8)
    parser.add_argument("--sync-prefix", default=DEFAULT_PREFIX)
    args = parser.parse_args()

    setLogLevel("info")
    run_experiment(args)


if __name__ == "__main__":
    main()
