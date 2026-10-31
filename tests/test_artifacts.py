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
        cls.artifact['provenance'] = {'source_sha256': {'fixture': 'fixture'}}

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
