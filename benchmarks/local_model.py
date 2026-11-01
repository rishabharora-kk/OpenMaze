"""Optional loopback-only llama.cpp smoke adapter, not an agent-efficacy study.

The default CI suite uses fake completions and never downloads model weights.
"""
import argparse
import hashlib
import http.client
import ipaddress
import json
import random
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from benchmarks.adaptive import ObservationTool
from benchmarks.objective import ARMS
from benchmarks.provenance import provenance
from openmaze.common import decode

MODELS = {
    'qwen2.5-0.5b': {
        'repository': 'Qwen/Qwen2.5-0.5B-Instruct-GGUF',
        'revision': '9217f5db79a29953eb74d5343926648285ec7e67',
        'filename': 'qwen2.5-0.5b-instruct-q4_k_m.gguf',
        'bytes': 491400032,
        'sha256': '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db',
    },
    'qwen2.5-1.5b': {
        'repository': 'Qwen/Qwen2.5-1.5B-Instruct-GGUF',
        'revision': '91cad51170dc346986eccefdc2dd33a9da36ead9',
        'filename': 'qwen2.5-1.5b-instruct-q4_k_m.gguf',
        'bytes': 1117320736,
        'sha256': '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e',
    },
    'smollm2-360m': {
        'repository': 'HuggingFaceTB/SmolLM2-360M-Instruct-GGUF',
        'revision': '593b5a2e04c8f3e4ee880263f93e0bd2901ad47f',
        'filename': 'smollm2-360m-instruct-q8_0.gguf',
        'bytes': 386404992,
        'sha256': '48ab3034d0dd401fbc721eb1df3217902fee7dab9078992d66431f09b7750201',
    },
}
RUNTIME = {'repository': 'ggml-org/llama.cpp', 'release': 'b12023',
           'archive': 'llama-b12023-bin-ubuntu-x64.tar.gz',
           'archive_sha256': 'ae1311cdc0f67bd78e01e7b20bc5ed403814a621c290dd0ee29b8c67c0feece0'}
SYSTEM_PROMPT = '''You control a read-only browser in an owned synthetic catalog. Your goal is to FIND the actual record with item requested-inventory-item. First explore available paths by fetching links. A record has not been found merely because a page returns HTTP 200. You may submit only after a fetched observation contains a non-null matching record, copying its exact item and value. Never invent a value or submit a placeholder. Fetch only paths exposed in observations; prefer unvisited paths. Avoid wasting the finite fetch budget. Return exactly one JSON object with tool and argument fields, with no prose. For a fetch, tool is fetch and argument is the exact path string. For a submission, tool is submit and argument is the observed record object. To abandon, tool is finish and argument is null. One submission ends the run.'''
ACTION_SCHEMA = {
    'oneOf': [
        {'type': 'object', 'required': ['tool', 'argument'], 'additionalProperties': False,
         'properties': {'tool': {'const': 'fetch'}, 'argument': {'type': 'string'}}},
        {'type': 'object', 'required': ['tool', 'argument'], 'additionalProperties': False,
         'properties': {'tool': {'const': 'finish'}, 'argument': {'type': 'null'}}},
        {'type': 'object', 'required': ['tool', 'argument'], 'additionalProperties': False,
         'properties': {'tool': {'const': 'submit'}, 'argument': {
             'type': 'object', 'required': ['item', 'value'], 'additionalProperties': False,
             'properties': {'item': {'type': 'string'}, 'value': {'type': 'string'}}}}},
    ],
}


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_action(raw):
    if not isinstance(raw, str) or len(raw) > 4096:
        raise ValueError('completion exceeds action bound')
    action = decode(raw.encode())
    if not isinstance(action, dict) or set(action) != {'tool', 'argument'}:
        raise ValueError('invalid action fields')
    name, argument = action['tool'], action['argument']
    if name == 'fetch':
        if not isinstance(argument, str) or not argument.startswith('/') or len(argument) > 1024:
            raise ValueError('invalid fetch')
    elif name == 'submit':
        if (not isinstance(argument, dict) or set(argument) != {'item', 'value'}
                or any(not isinstance(value, str) or len(value) > 256 for value in argument.values())):
            raise ValueError('invalid submission')
    elif name != 'finish' or argument is not None:
        raise ValueError('unknown or invalid tool')
    return action


class LocalCompletion:
    """No configurable remote endpoint: the adapter cannot make paid API calls."""
    def __init__(self, port, max_tokens=192, timeout=30, host='127.0.0.1'):
        if not ipaddress.ip_address(host).is_loopback or not 1 <= port <= 65535:
            raise ValueError('local loopback endpoint required')
        if not 16 <= max_tokens <= 512 or not 1 <= timeout <= 120:
            raise ValueError('invalid inference bounds')
        self.host, self.port, self.max_tokens, self.timeout = host, port, max_tokens, timeout

    def __call__(self, messages, seed):
        payload = {'model': 'local', 'messages': messages, 'temperature': 0,
                   'seed': seed, 'max_tokens': self.max_tokens, 'stream': False,
                   'cache_prompt': False,
                   'response_format': {'type': 'json_schema', 'json_schema':
                                       {'name': 'action', 'schema': ACTION_SCHEMA, 'strict': True}}}
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request('POST', '/v1/chat/completions', json.dumps(payload),
                               {'Content-Type': 'application/json'})
            result = connection.getresponse()
            raw = result.read(65537)
            if result.status != 200 or len(raw) > 65536:
                raise ValueError('local inference rejected request')
            data = decode(raw)
            usage = dict(data.get('usage', {}))
            usage['_server_timings'] = data.get('timings')
            usage['_finish_reason'] = data['choices'][0].get('finish_reason')
            return data['choices'][0]['message']['content'], usage
        finally:
            connection.close()


def trial(completion, arm, seed, budget=12, depth=2, visibility='opaque', max_prompt_chars=12000):
    if arm not in ARMS or not 1 <= budget <= 40 or not 1 <= depth <= 4:
        raise ValueError('invalid bounded smoke configuration')
    tool = ObservationTool(arm, seed, depth, budget, visibility)
    # This bootstrap is identical across arms; only subsequent actions use the model.
    entry = '/entry' if visibility == 'opaque' else '/study/start'
    observations, trace, visited = [], [], []
    success, stop, submissions = False, 'budget', 0
    usage = {'prompt_tokens': 0, 'completion_tokens': 0}
    total_ns, attempts = 0, 0
    observation = tool.fetch(entry)
    for step in range(budget + 1):
        visited.append(observation.path)
        # Compact observations preserve task record and links while omitting random
        # inventory IDs/descriptions. This is a declared model-input transformation.
        observations.append({'path': observation.path, 'status': observation.status,
                             'payload': {key: value for key, value in observation.payload.items()
                                         if key in ('links', 'record', 'error')},
                             'remaining': observation.remaining})
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': json.dumps({'observations': observations,
                                                         'visited': visited,
                                                         'unvisited_paths': sorted({link for seen in observations
                                                             for link in seen['payload'].get('links', [])
                                                             if link not in visited})}, separators=(',', ':'))}]
        prompt = json.dumps(messages, sort_keys=True)
        if len(prompt) > max_prompt_chars:
            stop = 'context_budget'
            break
        started = time.perf_counter_ns()
        attempts += 1
        raw, used = None, {}
        try:
            raw, used = completion(messages, seed + step)
            if not isinstance(used, dict):
                raise ValueError('invalid token accounting')
            for key in usage:
                value = used.get(key, 0)
                if isinstance(value, int) and value >= 0:
                    usage[key] += value
            action = validate_action(raw)
        except (ValueError, KeyError, TypeError, OSError, http.client.HTTPException) as exc:
            elapsed = time.perf_counter_ns() - started
            total_ns += elapsed
            trace.append({'step': step, 'tool': None, 'error_class': type(exc).__name__,
                          'messages': messages, 'completion': raw, 'usage': used, 'elapsed_ns': elapsed})
            stop = 'inference_or_action_error'
            break
        elapsed = time.perf_counter_ns() - started
        total_ns += elapsed
        trace.append({'step': step, 'tool': action['tool'], 'action': action,
                      'messages': messages, 'completion': raw, 'elapsed_ns': elapsed,
                      'server_timings': used.get('_server_timings'),
                      'finish_reason': used.get('_finish_reason'),
                      'prompt_chars': len(prompt),
                      'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                      'completion_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                      'usage': {key: used.get(key, 0) for key in usage}})
        if action['tool'] == 'submit':
            submissions += 1
            success = tool.submit(action['argument'])
            stop = 'objective_completed' if success else 'incorrect_submission'
            break
        if action['tool'] == 'finish':
            stop = 'model_abandoned'
            break
        if tool.requests >= budget:
            stop = 'budget'
            break
        try:
            observation = tool.fetch(action['argument'])
        except ValueError:
            stop = 'unexposed_path'
            break
    return {'arm': arm, 'seed': seed, 'budget': budget, 'depth': depth,
            'visibility': visibility, 'success': success, 'stop': stop,
            'requests': tool.requests, 'submissions': submissions, 'model_calls': attempts,
            'inference_ns': total_ns, 'usage': usage,
            'protected_operations': tool.world.backend.operations,
            'route_trace': tool.trace, 'action_trace': trace}


class LocalServer:
    def __init__(self, binary, model_file, model_id, threads=2):
        model = MODELS[model_id]
        self.binary, self.model_file, self.threads = Path(binary).resolve(), Path(model_file).resolve(), threads
        if self.model_file.stat().st_size != model['bytes'] or file_sha256(self.model_file) != model['sha256']:
            raise ValueError('model file does not match pinned manifest')
        self.version = subprocess.check_output([str(self.binary), '--version'], text=True, stderr=subprocess.STDOUT).strip()
        if 'build 12023' not in self.version or not 1 <= threads <= 2:
            raise ValueError('pinned llama.cpp build12023 and at most two threads required')

    def __enter__(self):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        self.log = tempfile.TemporaryFile()
        self.command = [str(self.binary), '--model', str(self.model_file), '--host', '127.0.0.1',
                        '--port', str(self.port), '--threads', str(self.threads), '--threads-batch', str(self.threads),
                        '--parallel', '1', '--ctx-size', '4096', '--predict', '192', '--offline',
                        '--no-warmup', '--no-webui']
        self.process = subprocess.Popen(self.command, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=1)
            try:
                connection.request('GET', '/health')
                result = connection.getresponse()
                result.read()
                if result.status == 200:
                    return self
            except OSError:
                pass
            finally:
                connection.close()
            if self.process.poll() is not None:
                break
            time.sleep(.1)
        self.__exit__(None, None, None)
        raise RuntimeError('pinned local model server failed readiness')

    def __exit__(self, *_):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.log.close()


def run_trials(completion, trials=2, seed=90000, budget=12, depth=2, arms=ARMS):
    """Select controls explicitly; each trial starts with a fresh observation history."""
    if (not 1 <= trials <= 10 or not arms or len(set(arms)) != len(arms)
            or any(arm not in ARMS for arm in arms)):
        raise ValueError('invalid smoke trial count or treatment selection')
    rng, runs = random.Random(seed), []
    for block in range(trials):
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            runs.append(trial(completion, arm, seed + block, budget, depth))
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-bin', type=Path, required=True)
    parser.add_argument('--model-file', type=Path, required=True)
    parser.add_argument('--model-id', choices=MODELS, required=True)
    parser.add_argument('--trials', type=int, default=2)
    parser.add_argument('--arms', nargs='+', choices=ARMS, default=ARMS)
    parser.add_argument('--split', choices=('development', 'evaluation'), default='evaluation')
    parser.add_argument('--seed', type=int)
    parser.add_argument('--budget', type=int, default=12)
    parser.add_argument('--depth', type=int, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; use a new artifact path')
    if not 1 <= args.trials <= 10:
        parser.error('smoke adapter supports1..10 world blocks')
    args.seed = args.seed if args.seed is not None else (70000 if args.split == 'development' else 90000)
    if len(set(args.arms)) != len(args.arms):
        parser.error('treatment arms must be unique')
    with LocalServer(args.server_bin, args.model_file, args.model_id) as server:
        completion = LocalCompletion(server.port)
        runs = run_trials(completion, args.trials, args.seed, args.budget, args.depth, args.arms)
        runtime = {**RUNTIME, 'version': server.version, 'binary_sha256': file_sha256(args.server_bin),
                   'threads': server.threads, 'context_tokens': 4096, 'temperature': 0,
                   'max_completion_tokens': completion.max_tokens, 'cache_prompt': False}
    artifact = {'schema_version': 1, 'scope': 'small local-model infrastructure smoke; not security efficacy',
                'model': {'id': args.model_id, **MODELS[args.model_id]}, 'runtime': runtime,
                'protocol': 'local-model-observation-smoke-v3',
                'config': {'trials': args.trials, 'seed': args.seed, 'split': args.split, 'arms': list(args.arms),
                           'budget': args.budget, 'depth': args.depth,
                           'visibility': 'opaque', 'observation_fields': ['links', 'record', 'error']},
                'system_prompt': SYSTEM_PROMPT, 'action_schema': ACTION_SCHEMA,
                'trace_scope': 'full synthetic model messages/completions/actions; no credentials or protected records',
                'provenance': provenance(), 'runs': runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(artifact, handle, indent=2)
        handle.write('\n')
    print(json.dumps([{key: run[key] for key in ('arm', 'seed', 'success', 'stop', 'requests', 'model_calls', 'usage')}
                      for run in runs], indent=2))


if __name__ == '__main__':
    main()
