"""Post-result scripted presentation ablation; no AI or HTTP efficacy claim."""
import argparse
import copy
import hashlib
import json
import random
import statistics
from dataclasses import asdict
from pathlib import Path

from benchmarks.adaptive import (ARMS, POLICIES, Action, CatalogPolicy, Observation,
                                 ObservationTool)
from benchmarks.objective import paired_interval
from benchmarks.provenance import provenance
from openmaze.common import encode

PRESENTATIONS = ('original', 'matched_schema', 'matched_schema_and_degree')
BUDGETS = (40, 64)
SEED_BASE = 60000
DEPTH = 4


class MatchedTool(ObservationTool):
    """Present successful observations through an optional common envelope.

    All task records/links stay intact. The degree ablation changes only the
    set of decoy links exposed to the caller; unexposed links are not allowed.
    """
    def __init__(self, arm, seed, depth, budget, visibility, presentation):
        if presentation not in PRESENTATIONS:
            raise ValueError('unknown presentation')
        super().__init__(arm, seed, depth, budget, visibility)
        self.presentation = presentation

    def fetch(self, public):
        previously_allowed = self.allowed.copy()
        observation = super().fetch(public)
        payload = copy.deepcopy(observation.payload)
        if self.presentation != 'original' and observation.status == 200:
            payload = {'links': payload.get('links', []), 'record': payload.get('record')}
            if self.presentation == 'matched_schema_and_degree':
                payload['links'] = payload['links'][:2]
        # The parent adapter discovers world links before presentation. Restore
        # the allowlist to exactly previously observed plus actually shown links.
        self.allowed = previously_allowed | set(payload.get('links', []))
        presented = Observation(observation.path, observation.status, payload, observation.remaining)
        self.trace[-1]['tool_observation_bytes'] = len(encode(asdict(presented)))
        return presented


def trial(arm, policy, seed, budget=40, visibility='opaque', presentation='matched_schema'):
    if arm not in ARMS or policy not in POLICIES or budget not in BUDGETS:
        raise ValueError('invalid trial configuration')
    tool = MatchedTool(arm, seed, DEPTH, budget, visibility, presentation)
    actor = CatalogPolicy(policy, budget, visibility)
    success, submitted, stop = False, 0, 'budget'
    for _ in range(budget + 2):
        action = actor.act()
        if action.tool == 'submit':
            submitted += 1
            success = tool.submit(action.argument)
            stop = 'objective_completed' if success else 'incorrect_submission'
            break
        if action.tool == 'finish':
            stop = 'policy_abandoned' if tool.requests else 'no_action'
            break
        if action.tool != 'fetch':
            raise ValueError('unknown tool')
        if tool.requests >= budget:
            break
        actor.observe(tool.fetch(action.argument))
    return {'arm': arm, 'policy': policy, 'seed': seed, 'depth': DEPTH,
            'budget': budget, 'visibility': visibility, 'presentation': presentation,
            'success': success, 'stop': stop, 'requests': tool.requests,
            'submissions': submitted,
            'decoy_candidate_requests': sum(t['route'] == 'decoy_candidate' for t in tool.trace),
            'response_bytes': sum(t['bytes'] for t in tool.trace),
            'tool_observation_bytes': sum(t['tool_observation_bytes'] for t in tool.trace),
            'protected_operations': tool.world.backend.operations, 'trace': tool.trace}


def experiment(trials=30):
    if not 2 <= trials <= 1000:
        raise ValueError('trials must be 2..1000')
    rng, runs = random.Random(SEED_BASE), []
    for presentation in PRESENTATIONS:
        for budget in BUDGETS:
            for visibility in ('clear', 'opaque'):
                for block in range(trials):
                    for policy in POLICIES:
                        arms = list(ARMS)
                        rng.shuffle(arms)
                        for arm in arms:
                            runs.append(trial(arm, policy, SEED_BASE + block, budget, visibility, presentation))
    summary, contrasts = [], []
    for presentation in PRESENTATIONS:
        for budget in BUDGETS:
            for visibility in ('clear', 'opaque'):
                for policy in POLICIES:
                    identity = {'presentation': presentation, 'budget': budget,
                                'visibility': visibility, 'policy': policy}
                    subset = [r for r in runs if all(r[k] == v for k, v in identity.items())]
                    by_arm = {}
                    for arm in ARMS:
                        arm_runs = [r for r in subset if r['arm'] == arm]
                        by_arm[arm] = {r['seed']: r for r in arm_runs}
                        summary.append({**identity, 'arm': arm, 'n': len(arm_runs),
                                        'success_rate': statistics.mean(r['success'] for r in arm_runs),
                                        'mean_requests': statistics.mean(r['requests'] for r in arm_runs),
                                        'mean_decoy_candidate_requests': statistics.mean(r['decoy_candidate_requests'] for r in arm_runs),
                                        'mean_original_body_bytes': statistics.mean(r['response_bytes'] for r in arm_runs),
                                        'mean_tool_observation_bytes': statistics.mean(r['tool_observation_bytes'] for r in arm_runs)})
                    for control in ('deny', 'static'):
                        differences = [int(by_arm['maze'][seed]['success']) - int(by_arm[control][seed]['success']) for seed in sorted(by_arm['maze'])]
                        contrasts.append({**identity, 'comparison': 'maze_minus_' + control,
                                          'success_rate_difference': statistics.mean(differences),
                                          'paired_world_bootstrap_95_interval': paired_interval(differences, SEED_BASE)})
    return {'schema_version': 1,
            'scope': 'post-result scripted matched-presentation follow-up; not AI or network evidence',
            'protocol': 'matched-presentation-v1',
            'config': {'trials': trials, 'seed_base': SEED_BASE, 'depth': DEPTH,
                       'budgets': list(BUDGETS), 'presentations': list(PRESENTATIONS),
                       'visibilities': ['clear', 'opaque']},
            'summary': summary, 'contrasts': contrasts, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials', type=int, default=30)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = experiment(args.trials)
    result['provenance'] = provenance()
    result['protocol_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'runs': len(result['runs']), 'summary': result['summary'], 'contrasts': result['contrasts']}, indent=2))


if __name__ == '__main__':
    main()
