import unittest
from benchmarks.adaptive import (ARMS, Action, CatalogPolicy, Observation, ObservationTool,
                                  POLICIES, SPLITS, experiment, trial)


class AdaptiveTests(unittest.TestCase):
    def test_tool_restricts_fetches_and_keeps_oracle_out_of_observation(self):
        tool = ObservationTool('maze', 42, 4, 2, 'opaque')
        with self.assertRaises(ValueError):
            tool.fetch('/study/catalog/1')
        observation = tool.fetch('/entry')
        self.assertEqual({'links'}, set(observation.payload))
        self.assertTrue(all(link.startswith('/node/') for link in observation.payload['links']))
        tool.fetch(observation.payload['links'][0])
        with self.assertRaises(ValueError):
            tool.fetch('/entry')
        self.assertFalse(tool.submit({'item': 'requested-inventory-item', 'value': 'wrong'}))

    def test_opaque_task_aliases_are_seeded_and_matched_across_arms(self):
        tools = [ObservationTool(arm, 42, 4, 40, 'opaque') for arm in ARMS]
        aliases = [t.public_path('/study/catalog/7') for t in tools]
        self.assertEqual([aliases[0]] * 3, aliases)
        other = ObservationTool('maze', 43, 4, 40, 'opaque')
        self.assertNotEqual(aliases[0], other.public_path('/study/catalog/7'))

    def test_policy_can_use_observations_without_world_object(self):
        policy = CatalogPolicy('progress_guard', 20, 'opaque')
        self.assertEqual(Action('fetch', '/entry'), policy.act())
        policy.observe(Observation('/entry', 200, {'links': ['/a', '/b']}, 19))
        self.assertEqual(Action('fetch', '/a'), policy.act())
        policy.observe(Observation('/a', 200, {'links': ['/a/1'], 'id': 'decoy'}, 18))
        self.assertEqual(Action('fetch', '/b'), policy.act())
        policy.observe(Observation('/b', 200, {'links': ['/b/1'], 'record': None}, 17))
        self.assertEqual(Action('fetch', '/a/1'), policy.act())
        policy.observe(Observation('/a/1', 200, {'links': ['/a/2'], 'id': 'other'}, 16))
        self.assertEqual(Action('fetch', '/b/1'), policy.act())
        self.assertNotIn('world', vars(policy))
        self.assertNotIn('seed', vars(policy))

    def test_final_fetch_candidate_can_be_submitted(self):
        full = trial('deny', 'disclosed_routes', 42, budget=40)
        exact = trial('deny', 'disclosed_routes', 42, budget=full['requests'])
        self.assertTrue(exact['success'])
        self.assertEqual(1, exact['submissions'])

    def test_source_aware_and_progress_controls_expose_maze_limits(self):
        for policy in ('progress_guard', 'disclosed_routes'):
            for arm in ARMS:
                run = trial(arm, policy, 42)
                self.assertTrue(run['success'])
                self.assertEqual(0, run['protected_operations'])
                if policy == 'disclosed_routes':
                    self.assertEqual(0, run['decoy_candidate_requests'])
        self.assertFalse(trial('maze', 'breadth_first', 42)['success'])
        self.assertFalse(trial('maze', 'disclosed_routes', 42, visibility='opaque')['success'])

    def test_experiment_is_reproducible_and_splits_do_not_overlap(self):
        args = {'trials': 2, 'configs': ((3, 24),), 'visibilities': ('opaque',)}
        first, second = experiment(**args), experiment(**args)
        self.assertEqual(first, second)
        self.assertEqual(24, len(first['runs']))
        self.assertEqual(12, len(first['summary']))
        self.assertEqual(8, len(first['contrasts']))
        self.assertLess(SPLITS['development'] + 1000, SPLITS['evaluation'])

    def test_invalid_configurations(self):
        for kwargs in ({'trials': 1}, {'split': 'unknown'}, {'configs': ((4, 40), (4, 40))}):
            with self.assertRaises(ValueError):
                experiment(**kwargs)
        with self.assertRaises(ValueError):
            trial('maze', POLICIES[0], 0, budget=81)
