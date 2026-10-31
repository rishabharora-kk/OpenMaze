import unittest
from benchmarks.pilot import ARMS, StaticDecoy, TARGET, experiment, trial
from openmaze.common import Request, decode
from openmaze.decoy import Decoy


class PilotTests(unittest.TestCase):
    def test_static_matches_initial_bytes_without_links(self):
        template = Decoy(b'd' * 32)(Request('GET', TARGET))
        static = StaticDecoy(template)(Request('GET', TARGET))
        self.assertEqual(len(template.body), len(static.body))
        self.assertEqual([], decode(static.body)['links'])

    def test_controls_expose_restart_and_source_awareness(self):
        self.assertEqual(21, trial('maze', 'follow', 0)['requests'])
        self.assertEqual('recognized_maze', trial('maze', 'source_aware', 0)['stop'])
        for arm in ARMS:
            run = trial(arm, 'restart', 0)
            self.assertEqual(25, run['requests'])
            self.assertEqual(0, run['protected_operations'])

    def test_complete_blocks_and_reproducible_non_timing_metrics(self):
        first, second = experiment(2, 42), experiment(2, 42)
        self.assertEqual(18, len(first['runs']))
        for a, b in zip(first['runs'], second['runs']):
            for key in a.keys() - {'elapsed_ns', 'cpu_ns'}:
                self.assertEqual(a[key], b[key])
            self.assertEqual(0, a['protected_operations'])

    def test_invalid_budgets_rejected(self):
        for trials, budget in [(0, 25), (1, 0), (1, 51)]:
            with self.assertRaises(ValueError):
                experiment(trials, budget=budget)
