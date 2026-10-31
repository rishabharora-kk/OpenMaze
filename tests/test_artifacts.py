import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from benchmarks.objective import experiment
from scripts.check_artifacts import check


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = experiment(2, seed=42)
        cls.artifact['provenance'] = {'source_sha256': {'fixture.py': '0' * 64}}

    def verify(self, artifact):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trial.json'
            path.write_text(json.dumps(artifact))
            with contextlib.redirect_stdout(io.StringIO()):
                check(path)

    def test_valid_artifact(self):
        self.verify(self.artifact)

    def test_rejects_security_and_accounting_corruption(self):
        for field, value in [('protected_operations', 1), ('requests', 81),
                             ('response_bytes', -1), ('success', False)]:
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.artifact)
                # The first fixture run completes the objective.
                run = next(r for r in artifact['runs'] if r['success'])
                run[field] = value
                with self.assertRaises(ValueError):
                    self.verify(artifact)

    def test_rejects_duplicate_arm_even_when_global_counts_match(self):
        artifact = copy.deepcopy(self.artifact)
        strategy = artifact['runs'][0]['strategy']
        first = next(r for r in artifact['runs'] if r['strategy'] == strategy and r['arm'] == 'deny')
        other = next(r for r in artifact['runs'] if r['strategy'] == strategy and r['arm'] == 'maze' and r['seed'] != first['seed'])
        first['arm'], other['arm'] = other['arm'], first['arm']
        with self.assertRaises(ValueError):
            self.verify(artifact)


    def test_rejects_impossible_or_corrupted_aggregate_results(self):
        for section, field, value in [('summary', 'success_rate', 123),
                                      ('summary', 'mean_requests', -1),
                                      ('summary', 'n', 123),
                                      ('contrasts', 'success_rate_difference', 123),
                                      ('contrasts', 'paired_world_bootstrap_95_interval', [-1, 1])]:
            with self.subTest(section=section, field=field):
                artifact = copy.deepcopy(self.artifact)
                artifact[section][0][field] = value
                with self.assertRaises(ValueError):
                    self.verify(artifact)

    def test_rejects_nonfinite_metrics_and_bad_source_digest(self):
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=value):
                artifact = copy.deepcopy(self.artifact)
                artifact['summary'][0]['mean_requests'] = value
                with self.assertRaises(ValueError):
                    self.verify(artifact)
        artifact = copy.deepcopy(self.artifact)
        artifact['provenance']['source_sha256']['fixture.py'] = 'not-a-digest'
        with self.assertRaises(ValueError):
            self.verify(artifact)

    def test_rejects_mismatched_seed_budget_and_depth(self):
        for field, value in [('seed', -100), ('budget', 39), ('depth', 3)]:
            with self.subTest(field=field):
                artifact = copy.deepcopy(self.artifact)
                artifact['runs'][0][field] = value
                with self.assertRaises(ValueError):
                    self.verify(artifact)

    def test_valid_pilot_and_corrupt_pilot_aggregate(self):
        from benchmarks.pilot import experiment as pilot
        artifact = pilot(2, seed=42)
        artifact['provenance'] = {'source_sha256': {'fixture.py': '0' * 64}}
        self.verify(artifact)
        artifact['summary'][0]['mean_cpu_ns'] += 1000
        with self.assertRaises(ValueError):
            self.verify(artifact)

    def test_short_budget_control_is_not_mislabeled_as_failure(self):
        artifact = experiment(2, seed=42, budget=1)
        artifact['provenance'] = {'source_sha256': {'fixture.py': '0' * 64}}
        self.verify(artifact)
