import json
import subprocess
from pathlib import Path

root = Path('/home/alice/ndn-sync-eval/mini-ndn-svs-compare')
cmd_base = [
    'python3', str(root / 'run_compare.py'),
    '--rows', '8', '--cols', '8',
    '--duration-s', '10',
    '--slow-ms', '1000', '--fast-ms', '100',
    '--fast-producers', '16',
    '--distribution', 'zipf',
    '--seed', '7',
    '--nfd-ready-timeout', '120',
    '--route-retries', '15',
]
variants = {
    'no-partial': '/home/alice/ndn-sync-eval/variants/no-partial',
    'no-partial-no-event': '/home/alice/ndn-sync-eval/variants/no-partial-no-event',
}
results = []
for topology in ('grid', 'hierarchical'):
    for name, variant_dir in variants.items():
        cmd = cmd_base + ['--topology', topology, '--variant-dir', variant_dir]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        text = proc.stdout
        end = text.rfind('}')
        start = text.rfind('{', 0, end + 1)
        summary = json.loads(text[start:end + 1])
        summary['variant'] = name
        results.append(summary)
print(json.dumps(results, indent=2, ensure_ascii=False))
