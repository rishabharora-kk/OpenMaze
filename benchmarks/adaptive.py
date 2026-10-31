"""Adaptive scripted catalog controls with an observation/action interface.

This is an in-process synthetic experiment, not an LLM-agent efficacy study.
"""
import argparse
import copy
import hashlib
import hmac
import json
import random
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from benchmarks.objective import ARMS, TaskWorld, paired_interval
from benchmarks.provenance import provenance
from openmaze.common import decode

POLICIES = ('breadth_first', 'progress_guard', 'branch_quota', 'disclosed_routes')
# Evaluation seeds are fixed only after the policy/rules and configurations below.
# They represent new target locations/order, not new world-generator families.
SPLITS = {'development': 20000, 'evaluation': 50000}
DEFAULT_CONFIGS = tuple((depth, budget) for depth in (3, 4, 5) for budget in (24, 40, 64))
TOOL_SCHEMA = {
    'fetch': {'path': 'same-origin path previously observed in links'},
    'submit': {'record': {'item': 'string', 'value': 'string'}},
    'finish': {},
}


@dataclass(frozen=True)
class Observation:
    path: str
    status: int
    payload: dict
    remaining: int


@dataclass(frozen=True)
class Action:
    tool: str
    argument: object = None


class CatalogPolicy:
    """Policy state contains observations, never world seeds or the oracle.

    A branch is an initial entry link and its descendants. Progress guard stops
    a branch after two pages without any `record` field. Branch quota limits
    each initial branch to half the request budget. These deliberately simple
    rules are fixed in code and can be defeated by richer decoy schemas.
    """
    def __init__(self, name, budget, visibility):
        if name not in POLICIES:
            raise ValueError('unknown policy')
        self.name, self.budget, self.visibility = name, budget, visibility
        self.frontier = deque([('/entry' if visibility == 'opaque' else '/study/start', None)])
        self.visited, self.queued = set(), set()
        self.root_counts = defaultdict(int)
        self.no_record_counts = defaultdict(int)
        self.blocked = set()
        self.pending = None
        self.candidate = None

    def observe(self, observation):
        path, root = self.pending
        self.visited.add(path)
        if root is not None:
            self.root_counts[root] += 1
            if 'record' not in observation.payload:
                self.no_record_counts[root] += 1
            else:
                self.no_record_counts[root] = 0
            if self.name == 'progress_guard' and self.no_record_counts[root] >= 2:
                self.blocked.add(root)
        record = observation.payload.get('record')
        if isinstance(record, dict) and record.get('item') == 'requested-inventory-item':
            self.candidate = copy.deepcopy(record)
        for link in observation.payload.get('links', []):
            if not isinstance(link, str) or not link.startswith('/'):
                continue
            if self.name == 'disclosed_routes' and self.visibility == 'clear' and not link.startswith('/study/'):
                continue
            if link not in self.visited and link not in self.queued:
                self.frontier.append((link, link if root is None else root))
                self.queued.add(link)

    def act(self):
        if self.candidate is not None:
            candidate, self.candidate = self.candidate, None
            return Action('submit', candidate)
        while self.frontier:
            path, root = self.frontier.popleft()
            if path in self.visited or root in self.blocked:
                continue
            if self.name == 'branch_quota' and root is not None and self.root_counts[root] >= max(2, self.budget // 2):
                continue
            self.pending = path, root
            return Action('fetch', path)
        return Action('finish')


class ObservationTool:
    """Owned-world tool adapter. Policy API never receives this object.

    Path allowlisting is an experimental tool constraint, not a deployment
    security boundary. Opaque URLs remove the obvious prefix signal; they do
    not hide response-shape clues or create a new security mechanism.
    """
    def __init__(self, arm, seed, depth, budget, visibility):
        if visibility not in ('clear', 'opaque'):
            raise ValueError('invalid visibility')
        self.world = TaskWorld(arm, seed, depth)
        self.budget, self.visibility = budget, visibility
        self.forward, self.reverse = {}, {}
        self.alias_key = hashlib.sha256(f'aliases:{seed}'.encode()).digest()
        entry = self.public_path('/study/start')
        self.allowed = {entry}
        self.requests, self.trace = 0, []

    def public_path(self, internal):
        if self.visibility == 'clear':
            return internal
        if internal not in self.reverse:
            public = '/entry' if internal == '/study/start' else '/node/' + hmac.new(
                self.alias_key, internal.encode(), hashlib.sha256).hexdigest()[:24]
            self.reverse[internal], self.forward[public] = public, internal
        return self.reverse[internal]

    def fetch(self, public):
        if self.requests >= self.budget:
            raise ValueError('request budget exhausted')
        if not isinstance(public, str) or public not in self.allowed:
            raise ValueError('path was not exposed by the tool')
        internal = public if self.visibility == 'clear' else self.forward[public]
        result = self.world.fetch(internal)
        payload = decode(result.body)
        links = [self.public_path(link) for link in payload.get('links', [])]
        self.allowed.update(links)
        payload['links'] = links
        self.requests += 1
        self.trace.append({'step': self.requests - 1, 'status': result.status,
                           'route': 'task' if internal.startswith('/study/') else 'decoy_candidate',
                           'bytes': len(result.body)})
        return Observation(public, result.status, payload, self.budget - self.requests)

    def submit(self, candidate):
        return self.world.accepts(candidate)


def trial(arm, policy, seed, budget=40, depth=4, visibility='clear'):
    if arm not in ARMS or policy not in POLICIES or not 1 <= budget <= 80 or not 1 <= depth <= 6:
        raise ValueError('invalid trial configuration')
    tool, actor = ObservationTool(arm, seed, depth, budget, visibility), CatalogPolicy(policy, budget, visibility)
    success, submitted, stop = False, 0, 'budget'
    # Fetches and submissions are separate accounting categories. A pending
    # candidate may be submitted after the final allowed fetch, but submissions
    # cannot open a free oracle-query loop: one candidate submission ends a run.
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
            stop = 'budget'
            break
        actor.observe(tool.fetch(action.argument))
    return {'arm': arm, 'policy': policy, 'seed': seed, 'budget': budget, 'depth': depth,
            'visibility': visibility, 'success': success, 'stop': stop,
            'requests': tool.requests, 'submissions': submitted,
            'decoy_candidate_requests': sum(t['route'] == 'decoy_candidate' for t in tool.trace),
            'response_bytes': sum(t['bytes'] for t in tool.trace),
            'protected_operations': tool.world.backend.operations, 'trace': tool.trace}


def experiment(trials=30, split='evaluation', configs=DEFAULT_CONFIGS, visibilities=('clear', 'opaque')):
    if split not in SPLITS or not 2 <= trials <= 1000 or not configs or not visibilities:
        raise ValueError('invalid experiment configuration')
    if len(set(configs)) != len(configs) or len(set(visibilities)) != len(visibilities):
        raise ValueError('duplicate experimental conditions')
    seed_base = SPLITS[split]
    rng, runs = random.Random(seed_base), []
    for depth, budget in configs:
        for visibility in visibilities:
            for block in range(trials):
                for policy in POLICIES:
                    arms = list(ARMS)
                    rng.shuffle(arms)
                    for arm in arms:
                        runs.append(trial(arm, policy, seed_base + block, budget, depth, visibility))
    summary, contrasts = [], []
    for depth, budget in configs:
        for visibility in visibilities:
            for policy in POLICIES:
                subset = [r for r in runs if (r['depth'], r['budget'], r['visibility'], r['policy']) == (depth, budget, visibility, policy)]
                identity = {'depth': depth, 'budget': budget, 'visibility': visibility, 'policy': policy}
                by_arm = {}
                for arm in ARMS:
                    arm_runs = [r for r in subset if r['arm'] == arm]
                    by_arm[arm] = {r['seed']: r for r in arm_runs}
                    summary.append({**identity, 'arm': arm, 'n': len(arm_runs),
                                    'success_rate': statistics.mean(r['success'] for r in arm_runs),
                                    'mean_requests': statistics.mean(r['requests'] for r in arm_runs),
                                    'mean_decoy_candidate_requests': statistics.mean(r['decoy_candidate_requests'] for r in arm_runs)})
                for control in ('deny', 'static'):
                    differences = [int(by_arm['maze'][seed]['success']) - int(by_arm[control][seed]['success']) for seed in sorted(by_arm['maze'])]
                    contrasts.append({**identity, 'comparison': 'maze_minus_' + control,
                                      'success_rate_difference': statistics.mean(differences),
                                      'paired_world_bootstrap_95_interval': paired_interval(differences, seed_base)})
    return {'schema_version': 1, 'scope': 'adaptive scripted synthetic controls; not model-agent or security efficacy',
            'protocol': 'adaptive-controls-v1',
            'config': {'trials': trials, 'split': split, 'seed_base': seed_base,
                       'configs': [list(c) for c in configs], 'visibilities': list(visibilities)},
            'tool_schema': TOOL_SCHEMA, 'summary': summary, 'contrasts': contrasts, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials', type=int, default=30)
    parser.add_argument('--split', choices=SPLITS, default='evaluation')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = experiment(args.trials, args.split)
    result['provenance'] = provenance()
    result['protocol_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'runs': len(result['runs']), 'summary': result['summary'], 'contrasts': result['contrasts']}, indent=2))


if __name__ == '__main__':
    main()
