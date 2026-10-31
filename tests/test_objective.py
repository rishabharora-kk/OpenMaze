import unittest
from benchmarks.objective import ARMS, TaskWorld, experiment, paired_interval, trial
from openmaze.common import decode


class ObjectiveTests(unittest.TestCase):
    def test_oracle_rejects_decoy_and_success_status_without_answer(self):
        world = TaskWorld('maze', 42)
        self.assertFalse(world.accepts(decode(world.fetch('/v1/tenants/alpha/records').body)))
        self.assertFalse(world.accepts({'item': world.objective, 'value': 'wrong'}))
        record = decode(world.fetch(f'/study/catalog/{world.leaf}').body)['record']
        self.assertTrue(world.accepts(record))
        self.assertEqual(0, world.backend.operations)

    def test_task_opportunity_is_identical_across_treatments(self):
        worlds = [TaskWorld(arm, 42) for arm in ARMS]
        for node in range(31):
            bodies = [world.fetch(f'/study/catalog/{node}').body for world in worlds]
            self.assertEqual([bodies[0]] * 3, bodies)
        self.assertEqual([worlds[0].initial] * 3, [w.initial for w in worlds])

    def test_aware_control_completes_task_and_budget_is_enforced(self):
        for arm in ARMS:
            run = trial(arm, 'source_aware', 42)
            self.assertTrue(run['success'])
            self.assertEqual(0, run['decoy_candidate_requests'])
            failed = trial(arm, 'breadth_first', 42, budget=1)
            self.assertFalse(failed['success'])
            self.assertEqual('budget', failed['stop'])

    def test_reproducible_paired_world_blocks(self):
        first, second = experiment(2, seed=42), experiment(2, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(18, len(first['runs']))
        self.assertEqual(6, len(first['contrasts']))
        self.assertTrue(all(r['protected_operations'] == 0 for r in first['runs']))
        self.assertEqual([0, 0], paired_interval([0, 0]))

    def test_invalid_configuration(self):
        for kwargs in ({'trials': 1}, {'depth': 7}, {'budget': 81}):
            with self.assertRaises(ValueError):
                experiment(**kwargs)
