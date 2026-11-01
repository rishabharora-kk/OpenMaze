import json
import unittest
from benchmarks.local_model import LocalCompletion, run_trials, trial, validate_action


class LocalModelTests(unittest.TestCase):
    def test_only_local_endpoint(self):
        with self.assertRaises(ValueError):
            LocalCompletion(8080, host='1.1.1.1')

    def test_rejects_malformed_actions(self):
        for raw in ('null', '[]', '{"tool":"shell","argument":"id"}',
                    '{"tool":"finish","argument":"x"}',
                    '{"tool":"fetch","tool":"finish","argument":null}',
                    '{"tool":"submit","argument":{"item":"x","value":42}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_action(raw)

    def test_unexposed_fetch_and_single_submission_stop(self):
        def unknown(*_):
            return json.dumps({'tool': 'fetch', 'argument': '/not-exposed'}), {}
        result = trial(unknown, 'maze', 42)
        self.assertEqual('unexposed_path', result['stop'])
        self.assertEqual(1, result['requests'])
        def incorrect(*_):
            return json.dumps({'tool': 'submit', 'argument': {'item': 'x', 'value': 'wrong'}}), {}
        result = trial(incorrect, 'maze', 42)
        self.assertEqual('incorrect_submission', result['stop'])
        self.assertEqual(1, result['submissions'])
        self.assertEqual(0, result['protected_operations'])

    def test_observation_only_policy_can_complete(self):
        # Fake completion uses only serialized observations, never tool/world/oracle.
        def breadth_first(messages, seed):
            state = json.loads(messages[1]['content'])
            visited = set(state['visited'])
            for observation in state['observations']:
                record = observation['payload'].get('record')
                if record:
                    return json.dumps({'tool': 'submit', 'argument': record}), {'completion_tokens': 1}
            for observation in state['observations']:
                for link in observation['payload'].get('links', []):
                    if link not in visited:
                        return json.dumps({'tool': 'fetch', 'argument': link}), {'prompt_tokens': 1}
            return json.dumps({'tool': 'finish', 'argument': None}), {}
        result = trial(breadth_first, 'deny', 42)
        self.assertTrue(result['success'])
        self.assertEqual('objective_completed', result['stop'])
        self.assertGreater(result['usage']['prompt_tokens'], 0)
        self.assertNotIn('argument', result['action_trace'][0])

    def test_budget_and_context_bound(self):
        def repeat(messages, seed):
            return json.dumps({'tool': 'fetch', 'argument': '/entry'}), {}
        result = trial(repeat, 'maze', 42, budget=2)
        self.assertEqual('budget', result['stop'])
        self.assertEqual(2, result['requests'])
        result = trial(repeat, 'maze', 42, max_prompt_chars=1)
        self.assertEqual('context_budget', result['stop'])
        self.assertEqual(0, result['model_calls'])

    def test_invalid_action_still_accounts_inference(self):
        def invalid(*_):
            return '{"tool":"finish","argument":"null"}', {'prompt_tokens': 2, 'completion_tokens': 3}
        result = trial(invalid, 'deny', 42)
        self.assertEqual('inference_or_action_error', result['stop'])
        self.assertEqual(1, result['model_calls'])
        self.assertEqual(3, result['usage']['completion_tokens'])
        self.assertEqual('ValueError', result['action_trace'][0]['error_class'])

    def test_denial_only_capability_selection_is_fresh_and_complete(self):
        histories = []
        def finish(messages, seed):
            histories.append(json.loads(messages[1]['content']))
            return '{"tool":"finish","argument":null}', {}
        runs = run_trials(finish, trials=2, seed=100000, arms=('deny',))
        self.assertEqual(['deny', 'deny'], [run['arm'] for run in runs])
        self.assertEqual([100000, 100001], [run['seed'] for run in runs])
        self.assertEqual([1, 1], [len(state['observations']) for state in histories])
        self.assertTrue(all(run['protected_operations'] == 0 for run in runs))
        for arms in ((), ('deny', 'deny'), ('unknown',)):
            with self.subTest(arms=arms), self.assertRaises(ValueError):
                run_trials(finish, arms=arms)
