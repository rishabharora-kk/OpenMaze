"""Experimental Ed25519 envelope v1. NOT an RFC 9421 implementation."""

import base64
import secrets
import threading
import time

from cryptography.exceptions import InvalidSignature

from .common import MAX_RESPONSE, NONCE, decode, encode

PROFILE = "openmaze-envelope-v1"
AUDIENCE = "openmaze-local-demo"
KEY_ID = "demo-ed25519-v1"
FIELDS = {"profile", "audience", "kid", "method", "target", "nonce", "status",
          "issued", "expires", "payload"}
DOMAIN = b"OpenMaze response envelope v1\x00"


def sign(private_key, request, status, data, now=None):
    now = int(time.time()) if now is None else now
    receipt = {"profile": PROFILE, "audience": AUDIENCE, "kid": KEY_ID,
               "method": request.method, "target": request.target,
               "nonce": request.get("x-openmaze-nonce"), "status": status,
               "issued": now, "expires": now + 60,
               "payload": base64.b64encode(encode(data)).decode("ascii")}
    signature = private_key.sign(DOMAIN + encode(receipt))
    return encode({"receipt": receipt, "signature": base64.b64encode(signature).decode("ascii")})


class VerificationError(ValueError):
    pass


class Verifier:
    """Trust a locally pinned key. Consume a pending request exactly once."""
    def __init__(self, public_key, clock=time.time):
        self.key, self.clock = public_key, clock
        self.pending = {}
        self.lock = threading.Lock()

    def begin(self, method, target):
        with self.lock:
            now = int(self.clock())
            self.pending = {n: v for n, v in self.pending.items() if v[2] >= now}
            if len(self.pending) >= 128:
                raise VerificationError("too many outstanding requests")
            nonce = secrets.token_hex(16)
            self.pending[nonce] = (method, target, now + 90)
            return nonce

    def verify(self, raw, status, nonce):
        with self.lock:
            try:
                now = int(self.clock())
                expected = self.pending.get(nonce)
                if expected is None or expected[2] < now or len(raw) > MAX_RESPONSE:
                    raise ValueError("not pending")
                envelope = decode(raw)
                if set(envelope) != {"receipt", "signature"}:
                    raise ValueError("envelope")
                r = envelope["receipt"]
                if not isinstance(r, dict) or set(r) != FIELDS:
                    raise ValueError("coverage")
                if (r["profile"], r["audience"], r["kid"]) != (PROFILE, AUDIENCE, KEY_ID):
                    raise ValueError("trust profile")
                if (r["method"], r["target"], r["nonce"], r["status"]) != (*expected[:2], nonce, status):
                    raise ValueError("request binding")
                if any(type(r[k]) is not int for k in ("issued", "expires", "status")):
                    raise ValueError("integer metadata required")
                if not (0 < r["expires"] - r["issued"] <= 60 and r["issued"] <= now + 30
                        and r["expires"] >= now - 30):
                    raise ValueError("freshness")
                signature = base64.b64decode(envelope["signature"], validate=True)
                self.key.verify(signature, DOMAIN + encode(r))
                payload = decode(base64.b64decode(r["payload"], validate=True))
                if not isinstance(payload, dict):
                    raise ValueError("payload schema")
            except (ValueError, KeyError, TypeError, InvalidSignature, UnicodeError, RecursionError) as exc:
                raise VerificationError("untrusted or mismatched response") from exc
            del self.pending[nonce]
            return payload
