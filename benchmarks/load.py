"""Finite open-loop localhost HTTP cost experiment; never an AI efficacy result."""
import argparse
import concurrent.futures
import http.client
import json
import math
import os
import random
import select
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from benchmarks.provenance import provenance
from openmaze.common import decode
from openmaze.receipts import Verifier, VerificationError
from openmaze.setup import initialize

ROOT = Path(__file__).resolve().parents[1]
TARGET = '/v1/tenants/alpha/records'


def percentile(values, quantile):
    """Nearest-rank sample quantile; no interpolation or distribution assumption."""
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(quantile * len(values)) - 1)]


def process_sample(pid):
    """Linux /proc process CPU (user+system seconds), RSS and thread count."""
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
        status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
        return {'cpu_seconds': (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK'),
                'rss_bytes': int(status['VmRSS'].split()[0]) * 1024,
                'threads': int(status['Threads'])}
    except (OSError, KeyError, ValueError):
        return None


def measurement_metadata():
    """Non-secret CPU/sampling context; visible cgroup files are not host guarantees."""
    def optional_text(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None

    cpu_model = None
    cpu_info = optional_text('/proc/cpuinfo')
    if cpu_info:
        for line in cpu_info.splitlines():
            key, separator, value = line.partition(':')
            if separator and key.strip() in ('model name', 'Hardware'):
                cpu_model = value.strip()
                break
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    try:
        clock_ticks = os.sysconf('SC_CLK_TCK')
    except (AttributeError, OSError, ValueError):
        clock_ticks = None
    system = os.uname()
    return {'system': system.sysname, 'kernel_release': system.release,
            'architecture': system.machine, 'cpu_model': cpu_model,
            'os_cpu_count': os.cpu_count(), 'client_cpu_affinity_count': affinity,
            'clock_ticks_per_second': clock_ticks,
            'visible_cgroup_cpu_max': optional_text('/sys/fs/cgroup/cpu.max'),
            'visible_cgroup_memory_max': optional_text('/sys/fs/cgroup/memory.max'),
            'visible_cgroup_v1_cpu_quota_us': optional_text('/sys/fs/cgroup/cpu/cpu.cfs_quota_us'),
            'visible_cgroup_v1_cpu_period_us': optional_text('/sys/fs/cgroup/cpu/cpu.cfs_period_us'),
            'context_scope': 'client-visible CPU/cgroup context; server subprocesses inherit placement; not exhaustive host or ancestor-quota accounting',
            'resource_sampler': 'per-role Linux /proc; non-atomic sequential reads; endpoints plus opportunistic approximately 10Hz samples',
            'quantile_method': 'nearest_rank', 'http_timeout_seconds': 2}


class Deployment:
    """Three fresh subprocesses, private temporary state, Unix-socket upstreams."""
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='openmaze-load-')
        self.state = Path(self.directory.name) / 'state'
        initialize(self.state)
        self.processes = {}
        self.output = tempfile.TemporaryFile()
        self.credentials = decode((self.state / 'auth.json').read_bytes())
        self.key = Ed25519PublicKey.from_public_bytes((self.state / 'verify.key').read_bytes())
        return self

    def start(self, mode):
        import socket
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        try:
            for role in ('protected', 'decoy', 'gateway'):
                command = [sys.executable, '-m', 'openmaze', 'serve', role,
                           '--state', str(self.state), '--transport', 'unix',
                           '--port', str(self.port), '--mode', mode]
                process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                           stderr=self.output, text=True)
                self.processes[role] = process
                if not select.select([process.stdout], [], [], 10)[0]:
                    raise RuntimeError(f'{role} readiness timeout')
                if not process.stdout.readline().startswith(f'{role} listening on '):
                    raise RuntimeError(f'{role} failed before bind')
            warmup = self.request('legitimate')
            if not warmup['verified']:
                raise RuntimeError('protected HTTP warmup verification failed')
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def request(self, kind):
        path, headers, verifier, nonce = TARGET, {}, None, None
        if kind in ('legitimate', 'cross_tenant'):
            if kind == 'cross_tenant':
                path = '/v1/tenants/beta/records'
            verifier = Verifier(self.key)
            nonce = verifier.begin('GET', path)
            headers = {'Authorization': 'Bearer ' + self.credentials['alpha'], 'X-OpenMaze-Nonce': nonce}
        elif kind == 'invalid_credential':
            headers = {'Authorization': 'Bearer invalid-load-probe'}
        started = time.perf_counter()
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=2)
        record = {'kind': kind, 'status': None, 'bytes': 0, 'verified': False,
                  'outcome': 'transport_error', 'http_ms': None}
        try:
            connection.request('GET', path, headers=headers)
            result = connection.getresponse()
            body = result.read(8193)
            record.update(status=result.status, bytes=len(body),
                          http_ms=(time.perf_counter() - started) * 1000, outcome='response')
            if kind == 'legitimate':
                if result.status == 200:
                    payload = verifier.verify(body, result.status, nonce)
                    records = payload.get('records', [])
                    record['verified'] = len(records) == 3 and all(item.get('tenant') == 'alpha' for item in records)
                    record['outcome'] = 'verified' if record['verified'] else 'invalid_protected_payload'
                else:
                    record['outcome'] = 'legitimate_http_error'
            elif kind in ('invalid_credential', 'cross_tenant'):
                expected = 401 if kind == 'invalid_credential' else 403
                record['outcome'] = 'expected_rejection' if result.status == expected else 'unexpected_rejection_status'
        except TimeoutError:
            record['outcome'] = 'timeout'
        except VerificationError:
            record['outcome'] = 'verification_failure'
        except (OSError, http.client.HTTPException, ValueError, TypeError, KeyError):
            record['outcome'] = 'transport_or_parse_error'
        finally:
            connection.close()
        record['total_ms'] = (time.perf_counter() - started) * 1000
        return record

    def sample(self):
        return {role: process_sample(process.pid) for role, process in self.processes.items()}

    def __exit__(self, *_):
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        for process in self.processes.values():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
        self.output.close()
        self.directory.cleanup()


def schedule(duration, legitimate_rate, probe_rate):
    events = []
    for prefix, rate in (('legitimate', legitimate_rate), ('probe', probe_rate)):
        if rate == 0:
            continue
        for index in range(math.floor(duration * rate)):
            kind = prefix
            if prefix == 'probe':
                kind = ('invalid_credential' if index % 10 == 8 else
                        'cross_tenant' if index % 10 == 9 else 'entry_probe')
            events.append((index / rate, kind))
    return sorted(events)


def trial(mode, duration=5, legitimate_rate=10, probe_rate=50, workers=16):
    validate(duration, legitimate_rate, probe_rate, workers)
    if mode not in ('deny', 'maze'):
        raise ValueError('deny or maze required')
    events = schedule(duration, legitimate_rate, probe_rate)
    records, measurements, pending = [], [], set()
    with Deployment() as deployment:
        deployment.start(mode)
        before = deployment.sample()
        start = time.perf_counter()
        next_sample = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for index, (offset, kind) in enumerate(events):
                remaining = start + offset - time.perf_counter()
                if remaining > 0:
                    time.sleep(remaining)
                now = time.perf_counter() - start
                if now >= next_sample:
                    measurements.append({'offset_seconds': now, 'roles': deployment.sample()})
                    next_sample = now + .1
                completed = {future for future in pending if future.done()}
                for future in completed:
                    records.append(future.result())
                pending -= completed
                lag_ms = max(0, (time.perf_counter() - start - offset) * 1000)
                if len(pending) >= workers:
                    records.append({'index': index, 'kind': kind, 'outcome': 'client_capacity_drop',
                                    'scheduled_lag_ms': lag_ms, 'status': None, 'bytes': 0,
                                    'verified': False, 'http_ms': None, 'total_ms': None})
                else:
                    def request(index=index, kind=kind, lag_ms=lag_ms):
                        result = deployment.request(kind)
                        result.update(index=index, scheduled_lag_ms=lag_ms)
                        return result
                    pending.add(pool.submit(request))
            for future in concurrent.futures.as_completed(pending):
                records.append(future.result())
        remaining = start + duration - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)
        elapsed = time.perf_counter() - start
        after = deployment.sample()
    records.sort(key=lambda item: item['index'])
    legitimate = [r for r in records if r['kind'] == 'legitimate']
    latencies = [r['http_ms'] for r in legitimate if r['http_ms'] is not None]
    resources = {}
    for role in before:
        if before[role] is not None and after[role] is not None:
            snapshots = [sample['roles'][role] for sample in measurements if sample['roles'][role] is not None]
            snapshots += [before[role], after[role]]
            resources[role] = {'cpu_seconds': after[role]['cpu_seconds'] - before[role]['cpu_seconds'],
                               'max_sampled_rss_bytes': max(s['rss_bytes'] for s in snapshots),
                               'max_sampled_threads': max(s['threads'] for s in snapshots)}
        else:
            resources[role] = None
    return {'mode': mode, 'duration_seconds': duration, 'elapsed_with_drain_seconds': elapsed,
            'legitimate_rate': legitimate_rate, 'probe_rate': probe_rate, 'client_workers': workers,
            'offered_requests': len(events), 'attempted_requests': sum(r['outcome'] != 'client_capacity_drop' for r in records),
            'http_completed_requests': sum(r['status'] is not None for r in records),
            'response_body_bytes': sum(r['bytes'] for r in records),
            'response_byte_scope': 'fully read response bodies only; partial failed reads and transport framing excluded',
            'outcomes': dict(Counter(r['outcome'] for r in records)),
            'legitimate': {'offered': len(legitimate), 'verified': sum(r['verified'] for r in legitimate),
                           'error_fraction': (sum(not r['verified'] for r in legitimate) / len(legitimate)) if legitimate else None,
                           'http_latency_population': 'all completed legitimate HTTP responses, including HTTP errors',
                           'http_latency_ms': {f'p{q}': percentile(latencies, q / 100) for q in (50, 95, 99)}},
            'server_resources': resources,
            'server_resource_endpoints': {'before': before, 'after': after},
            'resource_samples': measurements, 'requests': records}


def validate(duration, legitimate_rate, probe_rate, workers):
    if not .1 <= duration <= 60 or not 0 < legitimate_rate <= 100 or not 0 <= probe_rate <= 1000 or not 1 <= workers <= 32:
        raise ValueError('duration .1..60, legitimate rate (0,100], probe rate 0..1000, workers 1..32 required')
    if math.floor(duration * legitimate_rate) < 1 or duration * (legitimate_rate + probe_rate) > 10000:
        raise ValueError('at least one legitimate event and at most 10000 offered requests per trial required')


def experiment(repetitions=3, seed=2026, **kwargs):
    if not 1 <= repetitions <= 30:
        raise ValueError('repetitions 1..30 required')
    rng, runs = random.Random(seed), []
    for block in range(repetitions):
        modes = ['deny', 'maze']
        rng.shuffle(modes)
        for mode in modes:
            run = trial(mode, **kwargs)
            run['block'] = block
            runs.append(run)
    return {'schema_version': 1, 'scope': 'localhost HTTP finite-load pilot; no AI efficacy or production availability claim',
            'config': {'repetitions': repetitions, 'seed': seed, **kwargs},
            'resource_scope': 'Linux per-role /proc CPU and sampled RSS; client process excluded; shared host scheduling remains a confound',
            'measurement_metadata': measurement_metadata(),
            'runs': runs, 'provenance': provenance()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--duration', type=float, default=5)
    parser.add_argument('--legitimate-rate', type=float, default=10)
    parser.add_argument('--probe-rate', type=float, default=50)
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    settings = vars(args).copy()
    output = settings.pop('output')
    if output.exists():
        raise FileExistsError('refusing to overwrite load artifact')
    artifact = experiment(**settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as handle:
        json.dump(artifact, handle, indent=2)
        handle.write('\n')
    print(json.dumps([{'block': r['block'], 'mode': r['mode'], 'legitimate': r['legitimate'],
                       'outcomes': r['outcomes'], 'server_resources': r['server_resources']} for r in artifact['runs']], indent=2))


if __name__ == '__main__':
    main()
