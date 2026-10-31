"""Run one finite crawler against deny-only and maze; never contact the network."""

import json
import logging
import time
from collections import Counter

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from openmaze.common import Policy, Request, decode
from openmaze.decoy import Decoy
from openmaze.gateway import Gateway
from openmaze.protected import Protected


def trial(mode):
    credentials = {"alpha": "a" * 40, "beta": "b" * 40}
    backend = Protected(Policy(credentials), Ed25519PrivateKey.generate())
    gateway = Gateway(Policy(credentials), backend, Decoy(b"d" * 32), mode,
                      logging.getLogger("benchmark.events"))
    path, statuses = "/v1/tenants/alpha/records", Counter()
    started = time.perf_counter()
    total_bytes = 0
    for _ in range(25):
        result = gateway(Request("GET", path))
        statuses[result.status] += 1
        total_bytes += len(result.body)
        links = decode(result.body).get("links", [])
        if not links:
            break
        path = links[0]
    return {"mode": mode, "requests": sum(statuses.values()), "statuses": dict(statuses),
            "response_bytes": total_bytes, "protected_operations": backend.operations,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)}


def main():
    print(json.dumps({"scope": "in-process scripted crawler; not AI efficacy or HTTP throughput",
                      "trials": [trial("deny"), trial("maze")]}, indent=2))


if __name__ == "__main__":
    main()
