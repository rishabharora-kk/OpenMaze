"""Bounded consistent world; no credentials, signing keys, I/O or execution tools."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import OrderedDict

from .common import Bucket, error, response, validate


class Decoy:
    def __init__(self, seed, clock=time.time, max_sessions=1000):
        if len(seed) != 32:
            raise ValueError("32-byte deployment seed required")
        self.seed, self.clock, self.max_sessions = seed, clock, max_sessions
        self.sessions = OrderedDict()
        self.lock = threading.Lock()
        self.bucket = Bucket()

    def token(self, sid, node, expires):
        text = f"{sid}_{node}_{expires}"
        mac = hmac.new(self.seed, text.encode(), hashlib.sha256).hexdigest()
        return f"{text}_{mac}"

    def __call__(self, request):
        failure = validate(request)
        if failure:
            return failure
        if not self.bucket.take():
            return error(429, "decoy_budget_exhausted")
        with self.lock:
            now = int(self.clock())
            expired = [sid for sid, state in self.sessions.items() if state[0] < now]
            for sid in expired:
                del self.sessions[sid]
            if request.target.startswith("/maze/"):
                parts = request.target[6:].split("_")
                if len(parts) != 4:
                    return error(404, "not_found")
                sid, node, expiry, _ = parts
                try:
                    expires = int(expiry)
                    if not 0 <= int(node) < 1000000 or len(node) > 6 or len(expiry) > 12:
                        raise ValueError("bounds")
                except ValueError:
                    return error(404, "not_found")
                if not hmac.compare_digest(request.target[6:], self.token(sid, node, expires)):
                    return error(404, "not_found")
                state = self.sessions.get(sid)
                if state is None or state[0] != expires or state[1] >= 20:
                    return error(410, "session_exhausted")
            else:
                if len(self.sessions) >= self.max_sessions:
                    return error(429, "session_capacity")
                sid, node, expires = secrets.token_hex(16), "0", now + 120
                self.sessions[sid] = [expires, 0]
            self.sessions[sid][1] += 1
            digest = hmac.new(self.seed, f"record:{sid}:{node}".encode(), hashlib.sha256).hexdigest()
            children = [(int(node) * 3 + i) % 1000000 for i in (1, 2, 3)]
            return response(200, {"id": digest[:16], "description": f"Inventory batch {digest[16:24]}",
                                  "links": ["/maze/" + self.token(sid, str(n), expires) for n in children]})
