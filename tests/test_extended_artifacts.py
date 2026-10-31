import copy
import math
import unittest
from collections import Counter

from benchmarks.adaptive import experiment
from scripts.check_extended_artifacts import LATENCY_POPULATION, validate


def load_fixture():
    # Independently written deterministic records, no live network timing dependency.
    events = [(i / 4, 'legitimate') for i in range(2)]
    events += [(i / 20, {8: 'invalid_credential', 9: 'cross_tenant'}.get(i % 10, 'entry_probe')) for i in range(10)]
    requests = []
    for index, (_, kind) in enumerate(sorted(events)):
        status = {'invalid_credential': 401, 'cross_tenant': 403}.get(kind, 200)
        outcome = ('verified' if kind == 'legitimate' else 'response' if kind == 'entry_probe' else 'expected_rejection')
        requests.append({'index': index, 'kind': kind, 'outcome': outcome, 'status': status,
                         'verified': kind == 'legitimate', 'bytes': 10, 'http_ms': index + 1.,
                         'total_ms': index + 2., 'scheduled_lag_ms': .1})
    roles = ('protected', 'decoy', 'gateway')
    run = {'mode': 'deny', 'block': 0, 'duration_seconds': .5, 'elapsed_with_drain_seconds': .6,
           'legitimate_rate': 4, 'probe_rate': 20, 'client_workers': 4, 'requests': requests,
           'server_resource_endpoints': {
               'before': {role: {'cpu_seconds': .1, 'rss_bytes': 100, 'threads': 1} for role in roles},
               'after': {role: {'cpu_seconds': .4, 'rss_bytes': 120, 'threads': 1} for role in roles}},
           'resource_samples': [{'offset_seconds': .1, 'roles': {role: {'cpu_seconds': .2, 'rss_bytes': 110, 'threads': 2} for role in roles}}],
           'server_resources': {role: {'cpu_seconds': .3, 'max_sampled_rss_bytes': 120, 'max_sampled_threads': 2} for role in roles}}
    recount_load(run)
    second = copy.deepcopy(run)
    second['mode'] = 'maze'
    return {'schema_version': 1, 'config': {'repetitions': 1, 'seed': 2026, 'duration': .5,
                                          'legitimate_rate': 4, 'probe_rate': 20, 'workers': 4},
            'runs': [run, second], 'provenance': {'source_sha256': {'fixture.py': '0' * 64}}}


def recount_load(run):
    records = run['requests']
    legitimate = [r for r in records if r['kind'] == 'legitimate']
    values = sorted(r['http_ms'] for r in legitimate if r['http_ms'] is not None)
    run.update(offered_requests=len(records), attempted_requests=sum(r['outcome'] != 'client_capacity_drop' for r in records),
               http_completed_requests=sum(r['status'] is not None for r in records),
               response_body_bytes=sum(r['bytes'] for r in records), outcomes=dict(Counter(r['outcome'] for r in records)))
    verified = sum(r['verified'] for r in legitimate)
    run['legitimate'] = {'offered': len(legitimate), 'verified': verified,
                         'error_fraction': (len(legitimate) - verified) / len(legitimate),
                         'http_latency_population': LATENCY_POPULATION,
                         'http_latency_ms': {'p' + str(q): values[max(0, math.ceil(q / 100 * len(values)) - 1)] if values else None for q in (50, 95, 99)}}


class ExtendedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adaptive = experiment(trials=2, configs=((3, 24),), visibilities=('opaque',))
        cls.adaptive['provenance'] = {'source_sha256': {'fixture.py': '0' * 64}}

    def test_valid_adaptive_factorial(self):
        self.assertEqual(('adaptive', 24), validate(self.adaptive))

    def test_rejects_adaptive_duplicate_cell_and_tampered_success(self):
        artifact = copy.deepcopy(self.adaptive)
        artifact['runs'][0] = copy.deepcopy(artifact['runs'][1])
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = copy.deepcopy(self.adaptive)
        artifact['summary'][0]['success_rate'] = 123
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = copy.deepcopy(self.adaptive)
        artifact['runs'][0]['submissions'] = 2
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = copy.deepcopy(self.adaptive)
        artifact['contrasts'][0]['paired_world_bootstrap_95_interval'] = [-1, 1]
        with self.assertRaises(ValueError):
            validate(artifact)

    def test_valid_load_with_exact_resource_endpoint_audit(self):
        self.assertEqual(('load', 2), validate(load_fixture()))
        legacy = load_fixture()
        for run in legacy['runs']:
            del run['server_resource_endpoints']
        self.assertEqual(('load', 2), validate(legacy))

    def test_rejects_tampered_load_resources_and_bookkeeping(self):
        for field, value in [('offered_requests', 13), ('attempted_requests', 0), ('response_body_bytes', 0)]:
            with self.subTest(field=field):
                artifact = load_fixture()
                artifact['runs'][0][field] = value
                with self.assertRaises(ValueError):
                    validate(artifact)
        for field, value in [('cpu_seconds', -.1), ('cpu_seconds', 1), ('max_sampled_rss_bytes', 999), ('max_sampled_threads', 0)]:
            with self.subTest(field=field, value=value):
                artifact = load_fixture()
                artifact['runs'][0]['server_resources']['gateway'][field] = value
                with self.assertRaises(ValueError):
                    validate(artifact)
        artifact = load_fixture()
        artifact['runs'][1]['mode'] = 'deny'
        with self.assertRaises(ValueError):
            validate(artifact)

    def test_load_latency_population_includes_http_errors_and_has_no_fake_timeout_latency(self):
        artifact = load_fixture()
        run = artifact['runs'][0]
        record = next(r for r in run['requests'] if r['kind'] == 'legitimate')
        record.update(outcome='legitimate_http_error', status=503, verified=False, http_ms=100, total_ms=101)
        recount_load(run)
        self.assertEqual(('load', 2), validate(artifact))
        run['legitimate']['http_latency_ms']['p95'] = 1
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = load_fixture()
        for run in artifact['runs']:
            for record in run['requests']:
                if record['kind'] == 'legitimate':
                    record.update(outcome='timeout', status=None, http_ms=None, verified=False, bytes=0)
            recount_load(run)
        self.assertEqual(('load', 2), validate(artifact))
        artifact['runs'][0]['legitimate']['http_latency_ms']['p99'] = 0
        with self.assertRaises(ValueError):
            validate(artifact)

    def test_rejects_nonfinite_or_invented_verification(self):
        artifact = load_fixture()
        artifact['runs'][0]['server_resources']['gateway']['cpu_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = load_fixture()
        record = next(r for r in artifact['runs'][0]['requests'] if r['kind'] == 'entry_probe')
        record.update(outcome='verified', verified=True)
        recount_load(artifact['runs'][0])
        with self.assertRaises(ValueError):
            validate(artifact)


class MatchedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from benchmarks.matched import experiment as matched_experiment
        cls.artifact = matched_experiment(2)
        cls.artifact['provenance'] = {'source_sha256': {'fixture.py': '0' * 64}}

    def test_complete_matched_presentation_factorial(self):
        self.assertEqual(('matched', 288), validate(self.artifact))

    def test_rejects_duplicate_presentation_cell_and_wrong_frozen_configuration(self):
        artifact = copy.deepcopy(self.artifact)
        artifact['runs'][0] = copy.deepcopy(artifact['runs'][1])
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = copy.deepcopy(self.artifact)
        artifact['config']['seed_base'] += 1
        with self.assertRaises(ValueError):
            validate(artifact)
        artifact = copy.deepcopy(self.artifact)
        artifact['runs'][0]['depth'] = 3
        with self.assertRaises(ValueError):
            validate(artifact)

    def test_rejects_conflated_body_tool_bytes_and_corrupt_paired_statistics(self):
        for field in ('response_bytes', 'tool_observation_bytes'):
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.artifact)
                artifact['runs'][0][field] += 1
                with self.assertRaises(ValueError):
                    validate(artifact)
        for field in ('mean_original_body_bytes', 'mean_tool_observation_bytes'):
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.artifact)
                artifact['summary'][0][field] += 1
                with self.assertRaises(ValueError):
                    validate(artifact)
        artifact = copy.deepcopy(self.artifact)
        artifact['contrasts'][0]['success_rate_difference'] = 123
        with self.assertRaises(ValueError):
            validate(artifact)
