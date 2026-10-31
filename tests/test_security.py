import copy
import errno
import logging
from pathlib import Path
import secrets
import socket
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from openmaze.common import Bucket, Policy, Request, decode, encode
from openmaze.decoy import Decoy
from openmaze.gateway import Gateway
from openmaze.protected import Protected
from openmaze.receipts import Verifier, VerificationError, sign
from openmaze.receipts import DOMAIN
from openmaze.setup import initialize
from openmaze.transport import ProtocolError, make_server, read_request, tcp_call, unix_call

TARGET = "/v1/tenants/alpha/records"
CREDS = {"alpha": "a" * 40, "beta": "b" * 40}


def authorized(target=TARGET, token=CREDS["alpha"], nonce="1" * 32, **kwargs):
    return Request("GET", target, [("Authorization", "Bearer " + token),
                                    ("X-OpenMaze-Nonce", nonce)], **kwargs)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.backend = Protected(Policy(CREDS), self.key)
        self.decoy = Decoy(b"d" * 32)
        self.forwarded = []

        def call(request):
            self.forwarded.append(request)
            return self.backend(request)

        self.gateway = Gateway(Policy(CREDS), call, self.decoy, "maze",
                               logging.getLogger("test.events"))

    def test_default_mode_denies_without_backend(self):
        gateway = Gateway(Policy(CREDS), self.backend, self.decoy)
        self.assertEqual(401, gateway(Request("GET", TARGET)).status)
        self.assertEqual(0, self.backend.operations)

    def test_probe_is_synthetic_and_cannot_reach_backend(self):
        result = self.gateway(Request("GET", TARGET))
        self.assertEqual(200, result.status)
        self.assertIn("links", decode(result.body))
        self.assertNotIn(b"Protected synthetic", result.body)
        self.assertEqual([], self.forwarded)

    def test_cross_tenant_is_forbidden_at_both_boundaries(self):
        request = authorized("/v1/tenants/beta/records")
        self.assertEqual(403, self.gateway(request).status)
        self.assertEqual([], self.forwarded)
        self.assertEqual(403, self.backend(request).status)
        self.assertEqual(0, self.backend.operations)

    def test_forged_identity_headers_do_not_grant_authority(self):
        request = Request("GET", TARGET, [("X-Tenant", "alpha"), ("X-Internal-Token", "admin")])
        self.gateway(request)
        self.assertEqual([], self.forwarded)
        request = authorized()
        request.headers.append(("X-Tenant", "beta"))
        self.assertEqual(200, self.gateway(request).status)
        self.assertEqual(["Authorization", "X-OpenMaze-Nonce"], [k for k, _ in self.forwarded[0].headers])

    def test_invalid_credential_never_receives_decoy_or_protected_result(self):
        result = self.gateway(authorized(token="wrong"))
        self.assertEqual(401, result.status)
        self.assertNotIn("links", decode(result.body))
        self.assertEqual([], self.forwarded)

    def test_path_aliases_and_methods_fail_before_backend(self):
        for target in [TARGET + "?x=1", TARGET + "/", "/v1/tenants/%61lpha/records",
                       "/v1/tenants/alpha/../beta/records", "//v1/tenants/alpha/records",
                       "http://localhost" + TARGET, TARGET + "#fragment"]:
            with self.subTest(target=target):
                self.assertGreaterEqual(self.gateway(authorized(target)).status, 400)
        request = authorized()
        request.method = "POST"
        self.assertEqual(405, self.gateway(request).status)
        self.assertEqual([], self.forwarded)

    def test_ambiguous_headers_and_bodies_are_rejected(self):
        for header in [("Authorization", "Bearer " + CREDS["alpha"]),
                       ("X-OpenMaze-Nonce", "1" * 32), ("Transfer-Encoding", "chunked"),
                       ("Content-Length", "1"), ("Expect", "100-continue")]:
            request = authorized()
            request.headers.append(header)
            self.assertEqual(400, self.gateway(request).status)
        self.assertEqual([], self.forwarded)

    def test_nonce_required_before_protected_operation(self):
        self.assertEqual(400, self.gateway(authorized(nonce="not-a-nonce")).status)
        self.assertEqual(0, self.backend.operations)

    def test_backend_or_decoy_failure_fails_closed(self):
        def failed(_):
            raise OSError("offline")
        self.gateway.backend = failed
        self.assertEqual(503, self.gateway(authorized()).status)
        self.gateway.decoy = failed
        self.assertEqual(503, self.gateway(Request("GET", TARGET)).status)
        self.assertEqual(0, self.backend.operations)

    def test_global_budget_survives_identity_rotation(self):
        self.gateway.probes = Bucket(rate=0, burst=3)
        for i in range(3):
            self.assertEqual(200, self.gateway(Request("GET", f"/probe-{i}")).status)
        self.assertEqual(429, self.gateway(Request("GET", "/another-identity")).status)
        self.assertEqual(200, self.gateway(authorized()).status)
        self.assertEqual(1, self.backend.operations)

    def test_logs_exclude_tokens_paths_and_nonces(self):
        with self.assertLogs("test.events", level="INFO") as logs:
            self.gateway(authorized())
        output = " ".join(logs.output)
        for sensitive in [CREDS["alpha"], TARGET, "1" * 32]:
            self.assertNotIn(sensitive, output)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.key = Ed25519PrivateKey.generate()
        self.verifier = Verifier(self.key.public_key(), lambda: self.now)
        self.nonce = self.verifier.begin("GET", TARGET)
        self.request = authorized(nonce=self.nonce)
        self.raw = sign(self.key, self.request, 200, {"records": []}, self.now)

    def test_valid_receipt_then_replay_rejection(self):
        self.assertEqual({"records": []}, self.verifier.verify(self.raw, 200, self.nonce))
        with self.assertRaises(VerificationError):
            self.verifier.verify(self.raw, 200, self.nonce)

    def test_every_signed_field_is_bound(self):
        envelope = decode(self.raw)
        for field in envelope["receipt"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(envelope)
                value = changed["receipt"][field]
                changed["receipt"][field] = value + 1 if type(value) is int else value + "x"
                with self.assertRaises(VerificationError):
                    self.verifier.verify(encode(changed), 200, self.nonce)

    def test_wrong_http_status_is_rejected(self):
        with self.assertRaises(VerificationError):
            self.verifier.verify(self.raw, 201, self.nonce)

    def test_other_request_nonce_is_rejected(self):
        nonce = self.verifier.begin("GET", TARGET)
        with self.assertRaises(VerificationError):
            self.verifier.verify(self.raw, 200, nonce)

    def test_foreign_key_is_rejected(self):
        raw = sign(Ed25519PrivateKey.generate(), self.request, 200, {}, self.now)
        with self.assertRaises(VerificationError):
            self.verifier.verify(raw, 200, self.nonce)

    def test_expired_future_and_overlong_lifetimes_are_rejected(self):
        for issued in [self.now - 100, self.now + 31]:
            raw = sign(self.key, self.request, 200, {}, issued)
            with self.assertRaises(VerificationError):
                self.verifier.verify(raw, 200, self.nonce)
        import base64
        envelope = decode(self.raw)
        envelope["receipt"]["expires"] = self.now + 600
        envelope["signature"] = base64.b64encode(self.key.sign(DOMAIN + encode(envelope["receipt"]))).decode()
        with self.assertRaises(VerificationError):
            self.verifier.verify(encode(envelope), 200, self.nonce)

    def test_missing_and_additional_coverage_is_rejected(self):
        for change in ["remove", "add"]:
            envelope = decode(self.raw)
            if change == "remove":
                del envelope["receipt"]["nonce"]
            else:
                envelope["receipt"]["uncovered"] = "x"
            with self.assertRaises(VerificationError):
                self.verifier.verify(encode(envelope), 200, self.nonce)

    def test_malformed_and_unsigned_decoys_are_rejected(self):
        for raw in [b"{}", b"[]", b"null", b"not-json", b"{\"a\":1,\"a\":2}", b"x" * 8193,
                    Decoy(b"d" * 32)(Request("GET", TARGET)).body]:
            with self.subTest(raw=raw[:32]), self.assertRaises(VerificationError):
                self.verifier.verify(raw, 200, self.nonce)

    def test_pending_state_is_bounded_and_expired(self):
        for _ in range(127):
            self.verifier.begin("GET", TARGET)
        with self.assertRaises(VerificationError):
            self.verifier.begin("GET", TARGET)
        self.now += 91
        self.verifier.begin("GET", TARGET)
        self.assertEqual(1, len(self.verifier.pending))

    def test_concurrent_replay_only_one_verification_succeeds(self):
        results = []
        def verify():
            try:
                self.verifier.verify(self.raw, 200, self.nonce)
                results.append(True)
            except VerificationError:
                results.append(False)
        threads = [threading.Thread(target=verify) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, sum(results))


class MazeTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.decoy = Decoy(b"d" * 32, lambda: self.now, max_sessions=2)

    def enter(self):
        return decode(self.decoy(Request("GET", TARGET)).body)

    def test_links_are_same_origin_and_records_stay_consistent(self):
        link = self.enter()["links"][0]
        first = self.decoy(Request("GET", link))
        second = self.decoy(Request("GET", link))
        self.assertEqual(first.body, second.body)
        self.assertTrue(all(l.startswith("/maze/") for l in decode(first.body)["links"]))

    def test_replaying_continuation_consumes_budget(self):
        link = self.enter()["links"][0]
        for _ in range(19):
            self.assertEqual(200, self.decoy(Request("GET", link)).status)
        self.assertEqual(410, self.decoy(Request("GET", link)).status)

    def test_forged_continuation_rejected(self):
        link = self.enter()["links"][0]
        self.assertEqual(404, self.decoy(Request("GET", link[:-1] + ("0" if link[-1] != "0" else "1"))).status)

    def test_capacity_and_absolute_expiry(self):
        link = self.enter()["links"][0]
        self.enter()
        self.assertEqual(429, self.decoy(Request("GET", TARGET)).status)
        self.now += 121
        self.assertEqual(410, self.decoy(Request("GET", link)).status)
        self.assertEqual(200, self.decoy(Request("GET", TARGET)).status)
        self.assertEqual(1, len(self.decoy.sessions))


class TransportTests(unittest.TestCase):
    def parse(self, raw):
        client, server = socket.socketpair()
        try:
            client.sendall(raw)
            client.shutdown(socket.SHUT_WR)
            return read_request(server)
        finally:
            client.close()
            server.close()

    def test_wire_parsing_rejects_oversize_obsolete_folding_and_pipelining(self):
        for raw in [b"GET / HTTP/1.1\r\nX: " + b"a" * 8200 + b"\r\n\r\n",
                    b"GET / HTTP/1.1\r\n X: y\r\n\r\n",
                    b"GET / HTTP/1.1\r\n\r\nGET / HTTP/1.1\r\n\r\n",
                    b"GET / HTTP/2\r\n\r\n", b"GET / HTTP/1.1\r\nX: \x7f\r\n\r\n"]:
            with self.subTest(raw=raw[:30]), self.assertRaises(ProtocolError):
                self.parse(raw)

    def test_unix_transport_rechecks_backend_authority_and_signs(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM):
                pass
        except OSError as exc:
            if exc.errno in (errno.EPERM, errno.EAFNOSUPPORT):
                self.skipTest("runner does not permit filesystem Unix sockets")
            raise
        with tempfile.TemporaryDirectory() as directory:
            key = Ed25519PrivateKey.generate()
            backend = Protected(Policy(CREDS), key)
            path = Path(directory) / "api.sock"
            server = make_server(str(path), backend, unix=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                self.assertEqual(403, unix_call(path, authorized("/v1/tenants/beta/records")).status)
                verifier = Verifier(key.public_key())
                nonce = verifier.begin("GET", TARGET)
                result = unix_call(path, authorized(nonce=nonce))
                data = verifier.verify(result.body, result.status, nonce)
                self.assertEqual({"alpha"}, {r["tenant"] for r in data["records"]})
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_tcp_transport_rechecks_backend_authority_and_signs(self):
        key = Ed25519PrivateKey.generate()
        backend = Protected(Policy(CREDS), key)
        server = make_server(("127.0.0.1", 0), backend)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            self.assertEqual(403, tcp_call(port, authorized("/v1/tenants/beta/records")).status)
            verifier = Verifier(key.public_key())
            nonce = verifier.begin("GET", TARGET)
            result = tcp_call(port, authorized(nonce=nonce))
            self.assertEqual(3, len(verifier.verify(result.body, result.status, nonce)["records"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class SetupTests(unittest.TestCase):
    def test_fresh_secrets_permissions_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "state"
            initialize(state)
            credentials = decode((state / "auth.json").read_bytes())
            self.assertNotEqual(credentials["alpha"], credentials["beta"])
            self.assertEqual(0o600, (state / "signing.key").stat().st_mode & 0o777)
            with self.assertRaises(FileExistsError):
                initialize(state)


if __name__ == "__main__":
    unittest.main()
