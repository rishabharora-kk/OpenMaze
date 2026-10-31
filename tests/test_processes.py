"""Real three-process HTTP/Unix-socket smoke test, without container claims."""

import http.client
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from openmaze.common import decode
from openmaze.receipts import Verifier
from openmaze.setup import initialize


class ProcessTests(unittest.TestCase):
    def test_three_process_demo(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state"
            initialize(state)
            ports = []
            reservations = []
            for _ in range(3):
                probe = socket.socket()
                probe.bind(("127.0.0.1", 0))
                ports.append(probe.getsockname()[1])
                reservations.append(probe)
            for probe in reservations:
                probe.close()
            port, backend_port, decoy_port = ports
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen([sys.executable, "-m", "openmaze", "demo", "--state", str(state),
                                            "--port", str(port), "--mode", "maze", "--transport", "tcp",
                                            "--backend-port", str(backend_port), "--decoy-port", str(decoy_port)],
                                           stdout=output, stderr=output, start_new_session=True)
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                                break
                        except OSError:
                            if process.poll() is not None or time.monotonic() > deadline:
                                output.seek(0)
                                self.fail(output.read().decode())
                            time.sleep(0.02)
                    target = "/v1/tenants/alpha/records"

                    def request(path, headers=None):
                        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                        try:
                            connection.request("GET", path, headers=headers or {})
                            result = connection.getresponse()
                            return result.status, result.read()
                        finally:
                            connection.close()

                    status, raw = request(target)
                    self.assertEqual(200, status)
                    self.assertIn("links", decode(raw))
                    credentials = decode((state / "auth.json").read_bytes())
                    verifier = Verifier(Ed25519PublicKey.from_public_bytes((state / "verify.key").read_bytes()))
                    nonce = verifier.begin("GET", target)
                    headers = {"Authorization": "Bearer " + credentials["alpha"], "X-OpenMaze-Nonce": nonce}
                    status, raw = request(target, headers)
                    self.assertEqual(200, status)
                    self.assertEqual(3, len(verifier.verify(raw, status, nonce)["records"]))
                    status, _ = request("/v1/tenants/beta/records", headers)
                    self.assertEqual(403, status)
                    client = subprocess.run([sys.executable, "-m", "openmaze", "client", "--state", str(state),
                                             "--port", str(port)], capture_output=True, text=True, timeout=5)
                    self.assertEqual(0, client.returncode, client.stderr)
                    self.assertIn("Verified protected response", client.stdout)
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                self.assertEqual(0, process.returncode)
                self.assertFalse((state / "backend/api.sock").exists())
                self.assertFalse((state / "decoy/api.sock").exists())


if __name__ == "__main__":
    unittest.main()
