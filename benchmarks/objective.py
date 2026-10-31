"""Owned synthetic task opportunity beside a decoy; scripted construct check only."""
import argparse
import hashlib
import json
import random
import statistics
from collections import deque
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from openmaze.common import Policy, Request, decode, error, response
from openmaze.decoy import Decoy
from openmaze.gateway import Gateway
from openmaze.protected import Protected
from benchmarks.pilot import ARMS, StaticDecoy, TARGET
from benchmarks.provenance import provenance

STRATEGIES = ('breadth_first', 'random_frontier', 'source_aware')


class TaskWorld:
    """Public binary catalog, a designated leaf record, and a separate decoy API.

    The answer oracle never trusts HTTP status, decoy IDs or caller self-reports.
    This wrapper is benchmark-only: it does not expose protected records.
    """
    def __init__(self, arm, seed, depth=4):
        if arm not in ARMS or not 1 <= depth <= 6:
            raise ValueError('invalid arm or depth')
        self.depth = depth
        rng = random.Random(seed)
        self.leaf = rng.randrange(2 ** depth - 1, 2 ** (depth + 1) - 1)
        self.answer = hashlib.sha256(f'answer:{seed}'.encode()).hexdigest()
        self.objective = 'requested-inventory-item'
        self.initial = ['/study/catalog/0', TARGET]
        rng.shuffle(self.initial)
        credentials = {'alpha': 'a' * 40, 'beta': 'b' * 40}
        self.backend = Protected(Policy(credentials), Ed25519PrivateKey.generate())
        decoy = Decoy(hashlib.sha256(str(seed).encode()).digest(), clock=lambda: 1800000000)
        if arm == 'static':
            decoy = StaticDecoy(decoy(Request('GET', TARGET)))
        self.gateway = Gateway(Policy(credentials), self.backend, decoy,
                               'deny' if arm == 'deny' else 'maze')
        for bucket in (self.gateway.probes, decoy.bucket):
            bucket.clock = lambda: 0
            bucket.updated = 0

    def fetch(self, path):
        if path == '/study/start':
            return response(200, {'links': self.initial})
        prefix = '/study/catalog/'
        if path.startswith(prefix):
            raw = path[len(prefix):]
            if not raw.isascii() or not raw.isdigit() or len(raw) > 3:
                return error(404, 'not_found')
            node = int(raw)
            if raw != str(node) or node >= 2 ** (self.depth + 1) - 1:
                return error(404, 'not_found')
            links = [f'{prefix}{child}' for child in (2 * node + 1, 2 * node + 2)
                     if child < 2 ** (self.depth + 1) - 1]
            record = {'item': self.objective, 'value': self.answer} if node == self.leaf else None
            return response(200, {'links': links, 'record': record})
        return self.gateway(Request('GET', path))

    def accepts(self, record):
        return (isinstance(record, dict) and record.get('item') == self.objective
                and record.get('value') == self.answer)


def trial(arm, strategy, seed, budget=40, depth=4):
    if strategy not in STRATEGIES or not 1 <= budget <= 80:
        raise ValueError('invalid strategy or budget')
    world, rng = TaskWorld(arm, seed, depth), random.Random(seed)
    frontier, seen, trace = deque(['/study/start']), set(), []
    success, stop = False, 'budget'
    while frontier and len(trace) < budget:
        if strategy == 'random_frontier':
            frontier.rotate(-rng.randrange(len(frontier)))
        path = frontier.popleft()
        if path in seen:
            continue
        seen.add(path)
        result = world.fetch(path)
        payload = decode(result.body)
        success = world.accepts(payload.get('record'))
        trace.append({'step': len(trace), 'route': 'task' if path.startswith('/study/') else 'decoy_candidate',
                      'status': result.status, 'bytes': len(result.body), 'oracle_success': success})
        if success:
            stop = 'objective_completed'
            break
        for link in payload.get('links', []):
            # This baseline knows the world/decoy routing design by construction.
            if strategy == 'source_aware' and not link.startswith('/study/'):
                continue
            if link not in seen:
                frontier.append(link)
    else:
        if not frontier:
            stop = 'frontier_exhausted'
    return {'arm': arm, 'strategy': strategy, 'seed': seed, 'budget': budget,
            'depth': depth, 'success': success, 'stop': stop, 'requests': len(trace),
            'decoy_candidate_requests': sum(t['route'] == 'decoy_candidate' for t in trace),
            'response_bytes': sum(t['bytes'] for t in trace),
            'protected_operations': world.backend.operations, 'trace': trace}


def paired_interval(differences, seed=0, draws=2000):
    """Percentile bootstrap over paired world seeds, never individual requests."""
    rng = random.Random(seed)
    estimates = sorted(statistics.mean(rng.choices(differences, k=len(differences)))
                       for _ in range(draws))
    return [estimates[int(draws * .025)], estimates[int(draws * .975)]]


def experiment(trials=30, seed=10000, budget=40, depth=4):
    if trials < 2 or not 1 <= budget <= 80 or not 1 <= depth <= 6:
        raise ValueError('trials >= 2, budget 1..80, depth 1..6 required')
    rng, runs = random.Random(seed), []
    for block in range(trials):
        for strategy in STRATEGIES:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                runs.append(trial(arm, strategy, seed + block, budget, depth))
    summary, contrasts = [], []
    for strategy in STRATEGIES:
        by_arm = {}
        for arm in ARMS:
            subset = [r for r in runs if r['strategy'] == strategy and r['arm'] == arm]
            by_arm[arm] = {r['seed']: r for r in subset}
            summary.append({'strategy': strategy, 'arm': arm, 'n': len(subset),
                            'success_rate': statistics.mean(r['success'] for r in subset),
                            'mean_requests': statistics.mean(r['requests'] for r in subset),
                            'mean_decoy_candidate_requests': statistics.mean(r['decoy_candidate_requests'] for r in subset)})
        for control in ('deny', 'static'):
            differences = [int(by_arm['maze'][s]['success']) - int(by_arm[control][s]['success'])
                           for s in sorted(by_arm['maze'])]
            contrasts.append({'strategy': strategy, 'comparison': f'maze_minus_{control}',
                              'success_rate_difference': statistics.mean(differences),
                              'paired_world_bootstrap_95_interval': paired_interval(differences, seed)})
    return {'schema_version': 1, 'scope': 'scripted task construct check; not AI or security efficacy',
            'config': {'trials': trials, 'seed': seed, 'budget': budget, 'depth': depth},
            'summary': summary, 'contrasts': contrasts, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials', type=int, default=30)
    parser.add_argument('--seed', type=int, default=10000)
    parser.add_argument('--budget', type=int, default=40)
    parser.add_argument('--depth', type=int, default=4)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = experiment(args.trials, args.seed, args.budget, args.depth)
    result['provenance'] = provenance()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'summary': result['summary'], 'contrasts': result['contrasts']}, indent=2))


if __name__ == '__main__':
    main()
