"""Independent accounting checks for adaptive-script and finite HTTP artifacts.

These checks validate recorded evidence, not hidden oracle internals. With retained
/proc endpoints CPU deltas and sampled maxima are recomputed; legacy artifacts
without endpoints receive only nonnegative and recorded-sample consistency checks.
"""
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from scripts.check_artifacts import bootstrap_interval, close, finite_values, integer, unique_pairs

ARMS = {'deny', 'static', 'maze'}
POLICIES = {'breadth_first', 'progress_guard', 'branch_quota', 'disclosed_routes'}
SPLIT_SEEDS = {'development': 20000, 'evaluation': 50000}
ROLES = {'protected', 'decoy', 'gateway'}
LATENCY_POPULATION = 'all completed legitimate HTTP responses, including HTTP errors'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, minimum=0):
    return type(value) in (float, int) and math.isfinite(value) and value >= minimum


def source_identity(artifact):
    import re
    hashes = artifact.get('provenance', {}).get('source_sha256')
    require(isinstance(hashes, dict) and bool(hashes), 'missing source hashes')
    require(all(isinstance(name, str) and isinstance(digest, str) and
                re.fullmatch('[0-9a-f]{64}', digest) for name, digest in hashes.items()),
            'malformed source hash')


@lru_cache(maxsize=512)
def interval(differences, seed):
    if len(set(differences)) == 1:
        return [differences[0], differences[0]]
    return bootstrap_interval(differences, seed)


def validate_adaptive(artifact):
    matched = artifact.get('protocol') == 'matched-presentation-v1'
    require(artifact.get('protocol') in {'adaptive-controls-v1', 'matched-presentation-v1'}, 'unknown scripted protocol')
    config, runs = artifact['config'], artifact['runs']
    trials = config['trials']
    require(integer(trials, 2) and trials <= 1000, 'invalid scripted trials')
    if matched:
        require(type(config['seed_base']) is int and config['seed_base'] == 60000 and
                type(config['depth']) is int and config['depth'] == 4, 'matched seed/depth mismatch')
        require(config['budgets'] == [40, 64] and all(type(v) is int for v in config['budgets']), 'matched budget mismatch')
        presentations = config['presentations']
        require(isinstance(presentations, list) and len(presentations) == 3 and
                set(presentations) == {'original', 'matched_schema', 'matched_schema_and_degree'}, 'matched presentation mismatch')
        require(config['visibilities'] == ['clear', 'opaque'], 'matched visibility mismatch')
        identity_fields = ('presentation', 'budget', 'visibility', 'policy')
        identities = {(presentation, budget, visibility, policy)
                      for presentation in presentations for budget in config['budgets']
                      for visibility in config['visibilities'] for policy in POLICIES}
    else:
        split = config['split']
        require(split in SPLIT_SEEDS and type(config['seed_base']) is int and config['seed_base'] == SPLIT_SEEDS[split], 'split seed mismatch')
        configs = config['configs']
        require(isinstance(configs, list) and bool(configs), 'empty experimental configurations')
        conditions = set()
        for condition in configs:
            require(isinstance(condition, list) and len(condition) == 2, 'invalid factorial configuration')
            depth, budget = condition
            require(integer(depth, 1) and depth <= 6 and integer(budget, 1) and budget <= 80, 'unbounded adaptive configuration')
            conditions.add((depth, budget))
        require(len(conditions) == len(configs), 'duplicate adaptive configuration')
        visibilities = config['visibilities']
        require(isinstance(visibilities, list) and bool(visibilities) and
                set(visibilities) <= {'clear', 'opaque'} and len(set(visibilities)) == len(visibilities), 'invalid or duplicate visibility')
        identity_fields = ('depth', 'budget', 'visibility', 'policy')
        identities = {(depth, budget, visibility, policy)
                      for depth, budget in conditions for visibility in visibilities for policy in POLICIES}
    seeds = set(range(config['seed_base'], config['seed_base'] + trials))
    expected = {identity + (seed, arm) for identity in identities for seed in seeds for arm in ARMS}
    observed, groups = Counter(), defaultdict(list)
    for run in runs:
        key = tuple(run[field] for field in identity_fields) + (run['seed'], run['arm'])
        require(type(run['depth']) is int and type(run['budget']) is int and type(run['seed']) is int and key in expected,
                'run outside configured scripted factorial')
        if matched:
            require(run['depth'] == config['depth'], 'matched run depth mismatch')
        observed[key] += 1
        trace = run['trace']
        require(integer(run['requests'], 1) and run['requests'] <= run['budget'] and len(trace) == run['requests'],
                'adaptive request budget/accounting mismatch')
        for step, event in enumerate(trace):
            require(type(event['step']) is int and event['step'] == step and event['route'] in {'task', 'decoy_candidate'},
                    'invalid adaptive trace step/route')
            require(type(event['status']) is int and 100 <= event['status'] <= 599 and integer(event['bytes']),
                    'invalid adaptive trace status/bytes')
        require(integer(run['response_bytes']) and run['response_bytes'] == sum(t['bytes'] for t in trace), 'adaptive byte accounting mismatch')
        if matched:
            require(all(integer(t['tool_observation_bytes'], 1) for t in trace) and integer(run['tool_observation_bytes'], 1) and
                    run['tool_observation_bytes'] == sum(t['tool_observation_bytes'] for t in trace),
                    'normalized tool-observation byte accounting mismatch')
        require(integer(run['decoy_candidate_requests']) and run['decoy_candidate_requests'] == sum(t['route'] == 'decoy_candidate' for t in trace),
                'adaptive decoy request accounting mismatch')
        require(type(run['protected_operations']) is int and run['protected_operations'] == 0,
                'recorded unauthorized protected operation')
        require(type(run['success']) is bool and type(run['submissions']) is int and run['submissions'] in (0, 1),
                'invalid adaptive success/submission value')
        require(run['stop'] in {'budget', 'objective_completed', 'incorrect_submission', 'policy_abandoned', 'no_action'},
                'invalid adaptive stop reason')
        require((run['stop'] == 'objective_completed') == run['success'], 'adaptive success/stop mismatch')
        require((run['stop'] in {'objective_completed', 'incorrect_submission'}) == (run['submissions'] == 1),
                'adaptive submission/stop mismatch')
        if run['stop'] == 'budget':
            require(run['requests'] == run['budget'], 'budget stop without exhausted fetch budget')
        if run['policy'] == 'disclosed_routes' and run['visibility'] == 'clear':
            require(run['decoy_candidate_requests'] == 0, 'disclosed-route control followed decoy')
        groups[key[:4] + (run['arm'],)].append(run)
    require(set(observed) == expected and set(observed.values()) == {1}, 'missing or duplicate adaptive factorial cell')
    summary = artifact['summary']
    summary_keys = [tuple(row[field] for field in identity_fields) + (row['arm'],) for row in summary]
    require(Counter(summary_keys) == Counter({key: 1 for key in groups}), 'missing or duplicate adaptive summary')
    for key, row in zip(summary_keys, summary):
        subset = groups[key]
        require(type(row['n']) is int and row['n'] == trials, 'adaptive aggregate sample mismatch')
        close(row['success_rate'], statistics.mean(r['success'] for r in subset))
        for metric in ('requests', 'decoy_candidate_requests'):
            close(row['mean_' + metric], statistics.mean(r[metric] for r in subset))
        if matched:
            close(row['mean_original_body_bytes'], statistics.mean(r['response_bytes'] for r in subset))
            close(row['mean_tool_observation_bytes'], statistics.mean(r['tool_observation_bytes'] for r in subset))
    expected_contrasts = {identity + ('maze_minus_' + control,) for identity in identities for control in ('deny', 'static')}
    contrasts = artifact['contrasts']
    contrast_keys = [tuple(c[field] for field in identity_fields) + (c['comparison'],) for c in contrasts]
    require(Counter(contrast_keys) == Counter({key: 1 for key in expected_contrasts}), 'missing or duplicate adaptive contrasts')
    by_key = {tuple(r[field] for field in identity_fields) + (r['seed'], r['arm']): r for r in runs}
    for key, contrast in zip(contrast_keys, contrasts):
        control = key[-1].removeprefix('maze_minus_')
        differences = tuple(int(by_key[key[:4] + (seed, 'maze')]['success']) -
                            int(by_key[key[:4] + (seed, control)]['success']) for seed in sorted(seeds))
        close(contrast['success_rate_difference'], statistics.mean(differences))
        reported = contrast['paired_world_bootstrap_95_interval']
        require(isinstance(reported, list) and len(reported) == 2, 'invalid adaptive paired interval')
        for actual, expected_endpoint in zip(reported, interval(differences, config['seed_base'])):
            close(actual, expected_endpoint)
    digest = artifact.get('protocol_sha256')
    if digest is not None:
        module = 'benchmarks/matched.py' if matched else 'benchmarks/adaptive.py'
        require(digest == artifact['provenance']['source_sha256'].get(module), 'protocol/source digest mismatch')
    return len(runs)


def offered_events(duration, legitimate_rate, probe_rate):
    """Independent reconstruction of the registered deterministic offered schedule."""
    events = [(index / legitimate_rate, 'legitimate') for index in range(math.floor(duration * legitimate_rate))]
    if probe_rate:
        for index in range(math.floor(duration * probe_rate)):
            kind = {8: 'invalid_credential', 9: 'cross_tenant'}.get(index % 10, 'entry_probe')
            events.append((index / probe_rate, kind))
    return sorted(events)


def validate_load(artifact):
    config, runs = artifact['config'], artifact['runs']
    repetitions = config['repetitions']
    require(integer(repetitions, 1) and repetitions <= 30 and type(config['seed']) is int, 'invalid load repetitions/seed')
    duration, legitimate_rate, probe_rate, workers = (config.get('duration', 5), config.get('legitimate_rate', 10),
                                                    config.get('probe_rate', 50), config.get('workers', 16))
    require(number(duration, .1) and duration <= 60 and number(legitimate_rate) and 0 < legitimate_rate <= 100 and
            number(probe_rate) and probe_rate <= 1000 and integer(workers, 1) and workers <= 32, 'invalid load configuration')
    events = offered_events(duration, legitimate_rate, probe_rate)
    require(any(kind == 'legitimate' for _, kind in events) and len(events) <= 10000, 'invalid offered load count')
    expected = {(block, mode) for block in range(repetitions) for mode in ('deny', 'maze')}
    observed = Counter()
    for run in runs:
        require(type(run['block']) is int and (run['block'], run['mode']) in expected, 'run outside load blocks')
        observed[run['block'], run['mode']] += 1
        for field, expected_value in [('duration_seconds', duration), ('legitimate_rate', legitimate_rate),
                                      ('probe_rate', probe_rate), ('client_workers', workers)]:
            close(run[field], expected_value)
        require(number(run['elapsed_with_drain_seconds'], duration), 'load elapsed time shorter than offered window')
        requests = run['requests']
        require(integer(run['offered_requests']) and run['offered_requests'] == len(events) == len(requests), 'offered request count mismatch')
        require(Counter(r['index'] for r in requests) == Counter(range(len(events))) and
                all(type(r['index']) is int for r in requests), 'missing or duplicate offered request index')
        outcomes = Counter()
        legitimate = []
        latencies = []
        for request in requests:
            require(request['kind'] == events[request['index']][1], 'offered request kind mismatch')
            require(integer(request['bytes']) and type(request['verified']) is bool and number(request['scheduled_lag_ms']),
                    'invalid request byte/verified/lag measurement')
            outcome, status = request['outcome'], request['status']
            require(outcome in {'client_capacity_drop', 'response', 'verified', 'expected_rejection', 'unexpected_rejection_status',
                                'legitimate_http_error', 'invalid_protected_payload', 'verification_failure',
                                'timeout', 'transport_error', 'transport_or_parse_error'}, 'unknown request outcome')
            outcomes[outcome] += 1
            require(status is None or (type(status) is int and 100 <= status <= 599), 'invalid HTTP status')
            require(request['http_ms'] is None or number(request['http_ms']), 'invalid HTTP latency')
            require((status is None) == (request['http_ms'] is None), 'HTTP status/latency population mismatch')
            if status is None:
                require(request['bytes'] == 0, 'body bytes credited without a completed response')
            if outcome in {'response', 'verified', 'expected_rejection', 'unexpected_rejection_status',
                           'legitimate_http_error', 'invalid_protected_payload', 'verification_failure'}:
                require(status is not None, 'completed outcome without completed HTTP response')
            if outcome in {'timeout', 'transport_error'}:
                require(status is None, 'failed transport credited as completed HTTP response')
            if outcome in {'invalid_protected_payload', 'verification_failure'}:
                require(status == 200, 'protected verification error without HTTP 200')
            if outcome == 'legitimate_http_error':
                require(status != 200, 'HTTP error outcome incorrectly assigned to 200')
            if outcome == 'client_capacity_drop':
                require(status is None and request['bytes'] == 0 and request['total_ms'] is None and not request['verified'],
                        'client capacity drop incorrectly marked attempted/completed')
            else:
                require(number(request['total_ms']), 'missing attempted-request duration')
                if request['http_ms'] is not None:
                    require(request['total_ms'] + 1e-9 >= request['http_ms'], 'HTTP duration exceeds total duration')
            require(request['verified'] == (outcome == 'verified'), 'verified outcome/flag mismatch')
            if request['verified']:
                require(request['kind'] == 'legitimate' and status == 200, 'verification credited to nonlegitimate/non200 response')
            if request['kind'] == 'legitimate':
                legitimate.append(request)
                require(outcome not in {'response', 'expected_rejection', 'unexpected_rejection_status'}, 'legitimate classification mismatch')
                if request['http_ms'] is not None:
                    latencies.append(request['http_ms'])
            elif request['kind'] in ('invalid_credential', 'cross_tenant'):
                expected_status = 401 if request['kind'] == 'invalid_credential' else 403
                if outcome == 'expected_rejection':
                    require(status == expected_status, 'incorrect expected-rejection status')
                elif outcome == 'unexpected_rejection_status':
                    require(status is not None and status != expected_status, 'incorrect unexpected-rejection classification')
                require(outcome not in {'verified', 'response', 'legitimate_http_error', 'invalid_protected_payload', 'verification_failure'},
                        'security probe classification mismatch')
            else:
                require(outcome not in {'verified', 'expected_rejection', 'unexpected_rejection_status', 'legitimate_http_error',
                                       'invalid_protected_payload', 'verification_failure'}, 'entry probe classification mismatch')
        require(run['outcomes'] == dict(outcomes) and all(integer(value, 1) for value in run['outcomes'].values()), 'outcome count mismatch')
        for field, expected_value in [('attempted_requests', sum(r['outcome'] != 'client_capacity_drop' for r in requests)),
                                      ('http_completed_requests', sum(r['status'] is not None for r in requests)),
                                      ('response_body_bytes', sum(r['bytes'] for r in requests))]:
            require(integer(run[field]) and run[field] == expected_value, 'load ' + field + ' mismatch')
        aggregate = run['legitimate']
        verified = sum(r['verified'] for r in legitimate)
        require(integer(aggregate['offered']) and aggregate['offered'] == len(legitimate) and
                integer(aggregate['verified']) and aggregate['verified'] == verified, 'legitimate completion count mismatch')
        close(aggregate['error_fraction'], (len(legitimate) - verified) / len(legitimate))
        require(aggregate['http_latency_population'] == LATENCY_POPULATION, 'wrong latency population label')
        require(set(aggregate['http_latency_ms']) == {'p50', 'p95', 'p99'}, 'missing latency quantiles')
        for q in (50, 95, 99):
            actual = aggregate['http_latency_ms']['p' + str(q)]
            if latencies:
                close(actual, sorted(latencies)[max(0, math.ceil(q / 100 * len(latencies)) - 1)])
            else:
                require(actual is None, 'latency quantile invented without completed responses')
        validate_resources(run)
    require(set(observed) == expected and set(observed.values()) == {1}, 'missing or duplicate paired load block')
    return len(runs)


def validate_resources(run):
    resources, samples = run['server_resources'], run['resource_samples']
    require(set(resources) == ROLES and isinstance(samples, list), 'missing resource roles/samples')
    prior_offset = -1
    per_role = defaultdict(list)
    for sample in samples:
        offset = sample['offset_seconds']
        require(number(offset) and prior_offset <= offset <= run['elapsed_with_drain_seconds'] and set(sample['roles']) == ROLES,
                'invalid resource sample schedule/roles')
        prior_offset = offset
        for role, values in sample['roles'].items():
            if values is None:
                continue
            require(number(values['cpu_seconds']) and integer(values['rss_bytes'], 1) and integer(values['threads'], 1), 'invalid /proc resource sample')
            if per_role[role]:
                require(values['cpu_seconds'] >= per_role[role][-1]['cpu_seconds'], 'process CPU samples decreased')
            per_role[role].append(values)
    endpoints = run.get('server_resource_endpoints')
    if endpoints is not None:
        require(set(endpoints) == {'before', 'after'} and
                all(set(endpoints[phase]) == ROLES for phase in endpoints), 'invalid resource endpoint roles')
    for role, values in resources.items():
        if endpoints is not None:
            before, after = endpoints['before'][role], endpoints['after'][role]
            for endpoint in (before, after):
                if endpoint is not None:
                    require(number(endpoint['cpu_seconds']) and integer(endpoint['rss_bytes'], 1) and
                            integer(endpoint['threads'], 1), 'invalid resource endpoint')
            if before is None or after is None:
                require(values is None, 'resource aggregate invented without both endpoints')
                continue
            require(values is not None, 'resource aggregate missing despite available endpoints')
            require(after['cpu_seconds'] >= before['cpu_seconds'], 'endpoint CPU counter decreased')
            close(values['cpu_seconds'], after['cpu_seconds'] - before['cpu_seconds'])
            retained = per_role[role] + [before, after]
            require(values['max_sampled_rss_bytes'] == max(s['rss_bytes'] for s in retained) and
                    values['max_sampled_threads'] == max(s['threads'] for s in retained),
                    'resource aggregate maximum does not match endpoints and samples')
            require(all(before['cpu_seconds'] <= s['cpu_seconds'] <= after['cpu_seconds'] for s in per_role[role]),
                    'resource sample lies outside endpoint CPU counters')
        if values is None:
            continue
        require(number(values['cpu_seconds']) and integer(values['max_sampled_rss_bytes'], 1) and integer(values['max_sampled_threads'], 1),
                'invalid aggregate server resource')
        observations = per_role[role]
        if observations:
            require(values['max_sampled_rss_bytes'] >= max(s['rss_bytes'] for s in observations) and
                    values['max_sampled_threads'] >= max(s['threads'] for s in observations), 'resource maximum misses recorded sample')
            require(values['cpu_seconds'] + 1e-12 >= observations[-1]['cpu_seconds'] - observations[0]['cpu_seconds'],
                    'aggregate CPU delta smaller than retained sample delta')


def validate(artifact):
    finite_values(artifact)
    require(artifact.get('schema_version') == 1, 'unsupported extended artifact schema')
    source_identity(artifact)
    if artifact.get('protocol') in {'adaptive-controls-v1', 'matched-presentation-v1'}:
        kind = 'matched' if artifact['protocol'] == 'matched-presentation-v1' else 'adaptive'
        return kind, validate_adaptive(artifact)
    if 'repetitions' in artifact.get('config', {}):
        return 'load', validate_load(artifact)
    raise ValueError('unknown extended artifact kind')


def check(path):
    artifact = json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs)
    kind, count = validate(artifact)
    print(f'{path}: {kind}, {count} runs; paired configuration and recorded aggregate accounting checked')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('usage: python -m scripts.check_extended_artifacts ARTIFACT [ARTIFACT ...]')
    for argument in sys.argv[1:]:
        check(argument)
