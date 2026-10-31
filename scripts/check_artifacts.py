"""Independently validate paired runs and their published aggregate statistics."""
import json
import math
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ARMS = {'deny', 'static', 'maze'}
PILOT_STRATEGIES = {'follow', 'source_aware', 'restart'}
OBJECTIVE_STRATEGIES = {'breadth_first', 'random_frontier', 'source_aware'}


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def finite_values(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite measurement')
    if isinstance(value, dict):
        for item in value.values():
            finite_values(item)
    elif isinstance(value, list):
        for item in value:
            finite_values(item)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def close(actual, expected):
    if type(actual) not in (float, int) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(f'aggregate does not match runs: {actual!r} != {expected!r}')


def bootstrap_interval(values, seed):
    # Repeat the specified paired-world method independently of the benchmark.
    rng = random.Random(seed)
    estimates = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return [estimates[50], estimates[1950]]


def validate(artifact):
    finite_values(artifact)
    if artifact.get('schema_version') != 1:
        raise ValueError('unsupported artifact schema')
    config, runs = artifact['config'], artifact['runs']
    objective = 'depth' in config
    strategies = OBJECTIVE_STRATEGIES if objective else PILOT_STRATEGIES
    if not integer(config['trials'], 2 if objective else 1) or type(config['seed']) is not int:
        raise ValueError('invalid trial count or seed')
    if not integer(config['budget'], 1) or config['budget'] > (80 if objective else 50):
        raise ValueError('invalid configured budget')
    if objective and (not integer(config['depth'], 1) or config['depth'] > 6):
        raise ValueError('invalid configured depth')
    expected_seeds = set(range(config['seed'], config['seed'] + config['trials']))
    expected = {(seed, strategy, arm) for seed in expected_seeds for strategy in strategies for arm in ARMS}
    observed = Counter()
    for run in runs:
        if type(run['seed']) is not int or run['seed'] not in expected_seeds:
            raise ValueError('run seed outside configured world blocks')
        observed[(run['seed'], run['strategy'], run['arm'])] += 1
        if type(run['budget']) is not int or run['budget'] != config['budget']:
            raise ValueError('run/config budget mismatch')
        if run['protected_operations'] != 0 or type(run['protected_operations']) is not int:
            raise ValueError('unauthorized protected operation')
        trace = run['trace']
        if not integer(run['requests'], 1) or run['requests'] > config['budget'] or run['requests'] != len(trace):
            raise ValueError('request accounting or budget violation')
        allowed_routes = {'task', 'decoy_candidate'} if objective else {'entry', 'continuation'}
        for step, event in enumerate(trace):
            if event['step'] != step or type(event['step']) is not int or event['route'] not in allowed_routes:
                raise ValueError('invalid trace step or route')
            if not integer(event['bytes']) or type(event['status']) is not int or not 100 <= event['status'] <= 599:
                raise ValueError('invalid trace bytes or status')
        if not integer(run['response_bytes']) or run['response_bytes'] != sum(t['bytes'] for t in trace):
            raise ValueError('byte accounting mismatch')
        if objective:
            if type(run['depth']) is not int or run['depth'] != config['depth']:
                raise ValueError('run/config depth mismatch')
            if type(run['success']) is not bool or any(type(t['oracle_success']) is not bool for t in trace):
                raise ValueError('invalid oracle outcome')
            if sum(t['oracle_success'] for t in trace) != int(run['success']) or trace[-1]['oracle_success'] != run['success']:
                raise ValueError('oracle accounting mismatch')
            if run['stop'] not in {'budget', 'frontier_exhausted', 'objective_completed'} or (run['stop'] == 'objective_completed') != run['success']:
                raise ValueError('objective stop reason mismatch')
            candidate_requests = sum(t['route'] == 'decoy_candidate' for t in trace)
            if not integer(run['decoy_candidate_requests']) or run['decoy_candidate_requests'] != candidate_requests:
                raise ValueError('decoy request accounting mismatch')
            if run['strategy'] == 'source_aware':
                if candidate_requests:
                    raise ValueError('source-aware route control failed')
                # All catalog nodes plus the start page fit only at this budget.
                if config['budget'] >= 2 ** (config['depth'] + 1) and not run['success']:
                    raise ValueError('source-aware task-opportunity control failed')
        else:
            if not integer(run['continuation_requests']) or run['continuation_requests'] != sum(t['route'] == 'continuation' for t in trace):
                raise ValueError('continuation accounting mismatch')
            if any(not integer(run[key]) for key in ('cpu_ns', 'elapsed_ns')):
                raise ValueError('invalid timing measurement')
            if run['stop'] not in {'budget', 'recognized_maze', 'no_links'}:
                raise ValueError('invalid pilot stop reason')
    if set(observed) != expected or any(count != 1 for count in observed.values()):
        raise ValueError('missing or duplicate arm/strategy/world block')

    summary = artifact['summary']
    expected_groups = {(strategy, arm) for strategy in strategies for arm in ARMS}
    if Counter((s['strategy'], s['arm']) for s in summary) != Counter({group: 1 for group in expected_groups}):
        raise ValueError('incomplete or duplicate aggregate groups')
    for aggregate in summary:
        subset = [r for r in runs if (r['strategy'], r['arm']) == (aggregate['strategy'], aggregate['arm'])]
        if type(aggregate['n']) is not int or aggregate['n'] != len(subset):
            raise ValueError('aggregate sample count mismatch')
        metrics = ('requests', 'decoy_candidate_requests') if objective else ('requests', 'response_bytes', 'cpu_ns')
        for metric in metrics:
            close(aggregate[f'mean_{metric}'], statistics.mean(r[metric] for r in subset))
        if objective:
            close(aggregate['success_rate'], statistics.mean(r['success'] for r in subset))
        elif type(aggregate['protected_operations']) is not int or aggregate['protected_operations'] != sum(r['protected_operations'] for r in subset):
            raise ValueError('aggregate protected operation mismatch')
    if objective:
        contrasts = artifact['contrasts']
        expected_contrasts = {(strategy, f'maze_minus_{control}') for strategy in strategies for control in ('deny', 'static')}
        if Counter((c['strategy'], c['comparison']) for c in contrasts) != Counter({key: 1 for key in expected_contrasts}):
            raise ValueError('incomplete or duplicate paired contrasts')
        by_key = {(r['strategy'], r['arm'], r['seed']): r for r in runs}
        for contrast in contrasts:
            strategy, control = contrast['strategy'], contrast['comparison'].removeprefix('maze_minus_')
            differences = [int(by_key[strategy, 'maze', seed]['success']) - int(by_key[strategy, control, seed]['success']) for seed in sorted(expected_seeds)]
            close(contrast['success_rate_difference'], statistics.mean(differences))
            interval = contrast['paired_world_bootstrap_95_interval']
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError('invalid paired interval')
            for actual, expected_endpoint in zip(interval, bootstrap_interval(differences, config['seed'])):
                close(actual, expected_endpoint)
    hashes = artifact['provenance']['source_sha256']
    if not isinstance(hashes, dict) or not hashes or any(not isinstance(path, str) or not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None for path, digest in hashes.items()):
        raise ValueError('missing or malformed source identity')
    return len(runs)


def check(path):
    artifact = json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs)
    count = validate(artifact)
    print(f'{path}: {count} runs; accounting, paired aggregates, oracle controls and protected boundary checked')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: check_artifacts.py ARTIFACT [ARTIFACT ...]')
    for argument in sys.argv[1:]:
        check(argument)
