import unittest
from benchmarks.adaptive import ARMS
from benchmarks.matched import (MatchedTool, PRESENTATIONS, experiment, trial)
from openmaze.common import encode
from dataclasses import asdict


class MatchedTests(unittest.TestCase):
    def test_public_task_records_and_links_identical_in_all_presentations(self):
        tools = [MatchedTool('maze', 42, 4, 64, 'clear', p) for p in PRESENTATIONS]
        for tool in tools:
            tool.fetch('/study/start')
        # Walk the public catalog through observed links, independent of policy.
        frontier, seen = ['/study/catalog/0'], set()
        while frontier:
            path = frontier.pop()
            if path in seen:
                continue
            seen.add(path)
            observations = [tool.fetch(path) for tool in tools]
            self.assertEqual([observations[0].payload] * 3, [o.payload for o in observations])
            frontier.extend(observations[0].payload['links'])
            record = observations[0].payload['record']
            if record is not None:
                self.assertTrue(all(tool.submit(record) for tool in tools))
        self.assertEqual(31, len(seen))

    def test_matched_envelope_removes_schema_cue_and_caps_exposed_degree(self):
        for presentation, degree in [('matched_schema', 3), ('matched_schema_and_degree', 2)]:
            tool = MatchedTool('maze', 42, 4, 40, 'clear', presentation)
            tool.fetch('/study/start')
            page = tool.fetch('/v1/tenants/alpha/records')
            self.assertEqual({'links', 'record'}, set(page.payload))
            self.assertIsNone(page.payload['record'])
            self.assertEqual(degree, len(page.payload['links']))
            self.assertEqual(len(encode(asdict(page))), tool.trace[-1]['tool_observation_bytes'])

    def test_discarded_child_is_not_fetchable(self):
        tool = MatchedTool('maze', 42, 4, 40, 'opaque', 'matched_schema_and_degree')
        entry = tool.fetch('/entry')
        for public in entry.payload['links']:
            page = tool.fetch(public)
            if tool.trace[-1]['route'] == 'decoy_candidate':
                hidden = set(tool.forward) - tool.allowed
                self.assertEqual(1, len(hidden))
                with self.assertRaises(ValueError):
                    tool.fetch(hidden.pop())
                break
        else:
            self.fail('did not find decoy')

    def test_matching_removes_progress_guard_advantage_without_oracle_leak(self):
        original = trial('maze', 'progress_guard', 42, presentation='original')
        matched = trial('maze', 'progress_guard', 42, presentation='matched_schema')
        self.assertTrue(original['success'])
        self.assertFalse(matched['success'])
        self.assertEqual(2, original['decoy_candidate_requests'])
        self.assertGreater(matched['decoy_candidate_requests'], 2)
        for arm in ARMS:
            run = trial(arm, 'disclosed_routes', 42, visibility='clear', presentation='matched_schema_and_degree')
            self.assertTrue(run['success'])
            self.assertEqual(0, run['protected_operations'])

    def test_matched_guard_has_late_exhaustion_error_fallback(self):
        run = trial('maze', 'progress_guard', 42, budget=64, presentation='matched_schema')
        self.assertTrue(run['success'])
        statuses = [t['status'] for t in run['trace'] if t['route'] == 'decoy_candidate']
        self.assertEqual([200] * 20 + [410, 410], statuses)

    def test_reproducible_nonbyte_accounting_and_complete_cells(self):
        # Random session IDs alter opaque serialized bytes only through constant
        # token length; body byte counts remain deterministic for these policies.
        first, second = experiment(2), experiment(2)
        self.assertEqual(first, second)
        self.assertEqual(288, len(first['runs']))
        self.assertEqual(144, len(first['summary']))
        self.assertEqual(96, len(first['contrasts']))
        self.assertTrue(all(r['response_bytes'] == sum(t['bytes'] for t in r['trace']) for r in first['runs']))
        self.assertTrue(all(r['tool_observation_bytes'] == sum(t['tool_observation_bytes'] for t in r['trace']) for r in first['runs']))
