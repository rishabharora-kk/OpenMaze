"""Small shared protocol; exact paths and no request bodies in this prototype."""

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import threading
import time

RESOURCE = re.compile(r"/v1/tenants/(alpha|beta)/records(?:/(item-[1-3]))?\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
MAX_RESPONSE = 8192


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))


@dataclass
class Request:
    method: str
    target: str
    headers: list[tuple[str, str]] = field(default_factory=list)

    def values(self, name):
        return [v for k, v in self.headers if k.lower() == name.lower()]

    def get(self, name, default=""):
        values = self.values(name)
        return values[0] if len(values) == 1 else default


@dataclass
class Response:
    status: int
    body: bytes


def response(status, data):
    return Response(status, encode(data))


def error(status, code):
    return response(status, {"error": code})


def validate(request):
    """Reject aliases, ambiguous headers and bodies before routing or forwarding."""
    if len(request.target) > 1024 or not request.target.startswith("/"):
        return error(400, "invalid_target")
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/-_" for c in request.target):
        return error(400, "invalid_target")
    if "//" in request.target:
        return error(400, "invalid_target")
    if len(request.headers) > 32 or sum(len(k) + len(v) for k, v in request.headers) > 8192:
        return error(431, "headers_too_large")
    for name in ("authorization", "x-openmaze-nonce", "content-length", "host"):
        if len(request.values(name)) > 1:
            return error(400, "ambiguous_headers")
    if request.values("transfer-encoding") or request.values("expect"):
        return error(400, "unsupported_framing")
    if request.get("content-length", "0") != "0":
        return error(400, "bodies_not_supported")
    if request.method != "GET":
        return error(405, "method_not_allowed")
    return None


class Policy:
    def __init__(self, credentials):
        if set(credentials) != {"alpha", "beta"}:
            raise ValueError("expected two demo tenants")
        tokens = list(credentials.values())
        if any(not isinstance(t, str) or len(t) < 32 for t in tokens) or len(set(tokens)) != 2:
            raise ValueError("distinct strong credentials required")
        self.credentials = credentials

    def principal(self, request):
        value = request.get("authorization")
        if not value.startswith("Bearer "):
            return None
        supplied = hashlib.sha256(value[7:].encode()).digest()
        for tenant, token in self.credentials.items():
            if hmac.compare_digest(supplied, hashlib.sha256(token.encode()).digest()):
                return tenant
        return None

    def check(self, request):
        principal = self.principal(request)
        if principal is None:
            return error(401, "unauthorized")
        match = RESOURCE.fullmatch(request.target)
        if match is None:
            return error(404, "not_found")
        if match[1] != principal:
            return error(403, "forbidden")
        return None


class Bucket:
    """Process-wide admission: no per-IP or per-session allocation."""
    def __init__(self, rate=50, burst=100, clock=time.monotonic):
        self.rate, self.capacity, self.clock = rate, burst, clock
        self.tokens, self.updated = burst, clock()
        self.lock = threading.Lock()

    def take(self):
        with self.lock:
            now = self.clock()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True
