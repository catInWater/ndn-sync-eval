import json
import subprocess
import os
import re

variants = [
    "/home/alice/ndn-sync-eval/variants/cluster-hybrid-fixed",
    "/home/alice/ndn-sync-eval/variants/cluster-score-fixed",
    "/home/alice/ndn-sync-eval/variants/age-score-fixed"
]
fast_producers_list = [0, 16, 38]
password = "123456"

recent_file = "/home/alice/ndn-sync-eval/results/paper-zh-fast-producer-strict-budget/all_results.json"
recent_data = {}
if os.path.exists(recent_file):
    with open(recent_file, 'r') as f:
        full_recent = json.load(f)
        for entry in full_recent:
            fp = entry.get('fast_producers')
            if fp in fast_producers_list:
                recent_data[fp] = entry

summary = {"new_runs": {}, "recent": recent_data}

for variant_path in variants:
    v_name = os.path.basename(variant_path)
    summary["new_runs"][v_name] = {}
    
    for fp in fast_producers_list:
        cmd = f"echo '{password}' | sudo -S python3 /home/alice/ndn-sync-eval/mini-ndn-svs-compare/run_compare.py " \
              f"--variant-dir {variant_path} " \
              f"--fast-producers {fp} --rows 8 --cols 8 --duration-s 10 " \
              f"--slow-ms 1000 --fast-ms 100 --distribution zipf --topology clustered " \
              f"--seed 7 --nfd-ready-timeout 120 --route-retries 15 " \
              f"--env NDN_SVS_STATE_VECTOR_RATIO=0.30 --env NDN_SVS_MAX_STATE_VECTOR_ENTRIES=32"
        
        print(f"Executing: {v_name} FP={fp}")
        # Use check_output and show progress
        try:
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
            match = re.search(r"Saved results to folder: (results/[\w-]+)", output)
            if match:
                res_dir = match.group(1)
                res_file = os.path.join(res_dir, "all_results.json")
                if os.path.exists(res_file):
                    with open(res_file, 'r') as f:
                        data = json.load(f)
                        summary["new_runs"][v_name][fp] = data[0] if isinstance(data, list) else data
                else:
                    print(f"Error: {res_file} not found")
            else:
                print(f"Error: Could not find result folder in output")
        except subprocess.CalledProcessError as e:
            print(f"Command failed: {e.output}")

print("FINAL_JSON_START")
print(json.dumps(summary, indent=2))
print("FINAL_JSON_END")
