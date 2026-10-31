"""Check experiment structure and controls, without gating on a claimed effect."""
import json
import sys
from collections import Counter
from pathlib import Path


def check(path):
    artifact = json.loads(Path(path).read_text())
    config, runs = artifact['config'], artifact['runs']
    counts = Counter((r['strategy'], r['arm']) for r in runs)
    if len(counts) != 9 or set(counts.values()) != {config['trials']}:
        raise ValueError('incomplete experiment blocks')
    pairs = Counter((r['seed'], r['strategy']) for r in runs)
    if set(pairs.values()) != {3}:
        raise ValueError('unpaired world seeds')
    for pair in pairs:
        if {r['arm'] for r in runs if (r['seed'], r['strategy']) == pair} != {'deny', 'static', 'maze'}:
            raise ValueError('missing or duplicate arm in world block')
    for run in runs:
        if run['protected_operations'] != 0:
            raise ValueError('unauthorized protected operation')
        if not 1 <= run['requests'] <= config['budget'] or run['requests'] != len(run['trace']):
            raise ValueError('request accounting or budget violation')
        if run['response_bytes'] != sum(t['bytes'] for t in run['trace']):
            raise ValueError('byte accounting mismatch')
        if 'success' in run:
            if run['success'] != any(t['oracle_success'] for t in run['trace']):
                raise ValueError('oracle accounting mismatch')
            if run['strategy'] == 'source_aware' and (not run['success'] or run['decoy_candidate_requests']):
                raise ValueError('source-aware task-opportunity control failed')
    if not artifact['provenance']['source_sha256']:
        raise ValueError('missing source identity')
    print(f'{path}: {len(runs)} runs; budgets, oracle controls and protected boundary checked')


if __name__ == '__main__':
    for argument in sys.argv[1:]:
        check(argument)
