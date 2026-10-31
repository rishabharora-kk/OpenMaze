"""Enforce policy before backend calls. Decoy is optional and defaults to off."""

import logging
import time

from .common import Bucket, Request, error, validate


class Gateway:
    def __init__(self, policy, backend, decoy, mode="deny", logger=None):
        if mode not in ("deny", "maze"):
            raise ValueError("invalid mode")
        self.policy, self.backend, self.decoy = policy, backend, decoy
        self.mode, self.logger = mode, logger or logging.getLogger("openmaze.events")
        self.probes = Bucket()
        self.authorized = Bucket(rate=100, burst=200)

    def __call__(self, request):
        start = time.monotonic()
        result, route = self.dispatch(request)
        # Deliberately omit path, user-controlled content, tokens and nonce.
        self.logger.info("route=%s status=%d bytes=%d elapsed_ms=%.2f", route, result.status,
                         len(result.body), (time.monotonic() - start) * 1000)
        return result

    def dispatch(self, request):
        failure = validate(request)
        if failure:
            return failure, "reject"
        if request.values("authorization"):
            failure = self.policy.check(request)
            if failure:
                return failure, "reject"
            if not self.authorized.take():
                return error(429, "authorized_budget_exhausted"), "reject"
            # Rebuild the request: never forward arbitrary client identity/routing headers.
            forwarded = Request("GET", request.target, [
                ("Authorization", request.get("authorization")),
                ("X-OpenMaze-Nonce", request.get("x-openmaze-nonce")),
            ])
            try:
                return self.backend(forwarded), "protected"
            except (OSError, TimeoutError, ValueError):
                return error(503, "backend_unavailable"), "reject"
        if not self.probes.take():
            return error(429, "probe_budget_exhausted"), "reject"
        if self.mode == "deny":
            return error(401, "unauthorized"), "reject"
        try:
            # Decoy never receives authorization, nonce or arbitrary client headers.
            return self.decoy(Request("GET", request.target)), "decoy"
        except (OSError, TimeoutError, ValueError):
            return error(503, "decoy_unavailable"), "reject"
