import unittest
from unittest.mock import patch
from benchmarks.load import Deployment, measurement_metadata, percentile, process_sample, schedule, trial, validate


class LoadTests(unittest.TestCase):
    def test_nearest_rank_and_empty_latency(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(5, percentile([1, 2, 3, 4, 5], .95))
        self.assertEqual(3, percentile([1, 2, 3, 4, 5], .5))

    def test_schedule_includes_security_probes_and_fixed_offered_counts(self):
        events = schedule(1, 10, 20)
        self.assertEqual(30, len(events))
        self.assertEqual(10, sum(kind == 'legitimate' for _, kind in events))
        self.assertEqual(2, sum(kind == 'invalid_credential' for _, kind in events))
        self.assertEqual(2, sum(kind == 'cross_tenant' for _, kind in events))
        self.assertTrue(all(0 <= offset < 1 for offset, _ in events))

    def test_invalid_or_unbounded_configuration(self):
        for values in [(0, 10, 50, 16), (1, 0, 50, 16), (60, 100, 1000, 16), (1, 10, 50, 100)]:
            with self.assertRaises(ValueError):
                validate(*values)
        self.assertIsNone(process_sample(999999999))

    def test_real_http_accounting_verification_and_cleanup(self):
        run = trial('maze', duration=.5, legitimate_rate=4, probe_rate=20, workers=4)
        self.assertEqual(12, run['offered_requests'])
        self.assertEqual(12, len(run['requests']))
        self.assertEqual(2, run['legitimate']['verified'])
        self.assertEqual(0, run['legitimate']['error_fraction'])
        self.assertEqual(2, run['outcomes']['expected_rejection'])
        self.assertEqual(12, run['http_completed_requests'])
        self.assertEqual(sum(item['bytes'] for item in run['requests']), run['response_body_bytes'])
        for role, resource in run['server_resources'].items():
            before = run['server_resource_endpoints']['before'][role]
            after = run['server_resource_endpoints']['after'][role]
            if resource:
                self.assertGreaterEqual(resource['cpu_seconds'], 0)
                self.assertEqual(after['cpu_seconds'] - before['cpu_seconds'], resource['cpu_seconds'])
                snapshots = [before, after] + [sample['roles'][role] for sample in run['resource_samples'] if sample['roles'][role] is not None]
                self.assertEqual(max(s['rss_bytes'] for s in snapshots), resource['max_sampled_rss_bytes'])
                self.assertEqual(max(s['threads'] for s in snapshots), resource['max_sampled_threads'])
            else:
                self.assertTrue(before is None or after is None)

    def test_metadata_survives_unavailable_proc_and_cgroup_files(self):
        with patch('benchmarks.load.Path.read_text', side_effect=OSError):
            metadata = measurement_metadata()
        self.assertEqual('nearest_rank', metadata['quantile_method'])
        self.assertIsNone(metadata['visible_cgroup_cpu_max'])
        self.assertIsNone(metadata['cpu_model'])

