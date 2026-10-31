"""Execute owned Compose smoke/boundary checks with disposable state."""
import argparse
import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from openmaze.common import decode
from openmaze.receipts import Verifier
from openmaze.setup import initialize

ROOT = Path(__file__).resolve().parents[1]
TARGET = '/v1/tenants/alpha/records'


def check(image):
    with tempfile.TemporaryDirectory(prefix='openmaze-container-') as directory:
        state = Path(directory) / '.openmaze'
        initialize(state)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = dict(os.environ, OPENMAZE_UID=str(os.getuid()), OPENMAZE_GID=str(os.getgid()),
                   OPENMAZE_IMAGE=image, OPENMAZE_PORT=str(port))
        base = ['docker', 'compose', '--project-directory', directory,
                '-f', str(ROOT / 'compose.yaml'), '-p', f'openmaze-check-{os.getpid()}']

        def compose(*args, capture=False):
            return subprocess.check_output(base + list(args), env=env, text=True) if capture else subprocess.run(base + list(args), env=env, check=True)

        def request(path=TARGET, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            try:
                connection.request('GET', path, headers=headers or {})
                result = connection.getresponse()
                return result.status, result.read(8193)
            finally:
                connection.close()

        def ready(expected, path=TARGET, headers=None):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    result = request(path, headers)
                    if result[0] == expected:
                        return result
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.2)
            raise RuntimeError(f'gateway did not reach expected status {expected}')

        try:
            for mode, expected in [('deny', 401), ('maze', 200)]:
                env['OPENMAZE_MODE'] = mode
                compose('up', '-d', '--no-build', '--force-recreate')
                ready(expected)
                credentials = decode((state / 'auth.json').read_bytes())
                verifier = Verifier(Ed25519PublicKey.from_public_bytes((state / 'verify.key').read_bytes()))
                nonce = verifier.begin('GET', TARGET)
                headers = {'Authorization': 'Bearer ' + credentials['alpha'], 'X-OpenMaze-Nonce': nonce}
                status, body = ready(200, headers=headers)
                assert len(verifier.verify(body, status, nonce)['records']) == 3
                assert request('/v1/tenants/beta/records', headers)[0] == 403
                for role in ('protected', 'decoy', 'gateway'):
                    cid = compose('ps', '-q', role, capture=True).strip()
                    config = json.loads(subprocess.check_output(['docker', 'inspect', cid], text=True))[0]
                    host = config['HostConfig']
                    assert config['Config']['User'] == f'{os.getuid()}:{os.getgid()}'
                    assert host['ReadonlyRootfs'] and 'ALL' in host['CapDrop']
                    assert host['Memory'] == 128 * 1024 * 1024 and host['PidsLimit'] == 32
                    assert host['NanoCpus'] == (500000000 if role == 'gateway' else 250000000)
                    assert any('no-new-privileges' in option for option in host['SecurityOpt'])
                    if role != 'gateway':
                        assert host['NetworkMode'] == 'none'
                    if role == 'decoy':
                        assert {m['Destination'] for m in config['Mounts'] if m['Type'] == 'bind'} == {'/state/decoy.seed', '/state/decoy'}
                compose('exec', '-T', 'decoy', 'python', '-c', '''
from pathlib import Path
import socket
for path in ['/state/auth.json', '/state/signing.key', '/state/backend/api.sock', '/var/run/docker.sock']:
    assert not Path(path).exists(), path
assert Path('/state/decoy.seed').is_file()
try:
    with socket.create_connection(('1.1.1.1', 443), timeout=1):
        raise AssertionError('unexpected outbound IPv4 access')
except OSError:
    pass
try:
    with socket.socket(socket.AF_INET6) as connection:
        connection.settimeout(1)
        connection.connect(('2606:4700:4700::1111', 443))
        raise AssertionError('unexpected outbound IPv6 access')
except OSError:
    pass
''')
                if mode == 'maze':
                    compose('stop', 'decoy')
                    ready(503)
                    compose('start', 'decoy')
                    ready(200)
                    compose('stop', 'protected')
                    assert request(headers=headers)[0] == 503
                    compose('start', 'protected')
                    ready(200, headers=headers)
                compose('down', '--timeout', '5')
                assert not (state / 'backend/api.sock').exists()
                assert not (state / 'decoy/api.sock').exists()
            print('PASS: deny/maze, signed client, tenant boundary, container settings, decoy mounts/egress, fail-closed upstreams, socket lifecycle')
        except Exception:
            compose('logs', '--no-color', '--tail', '30')
            raise
        finally:
            compose('down', '--timeout', '5', '--remove-orphans')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='openmaze:ci')
    check(parser.parse_args().image)
