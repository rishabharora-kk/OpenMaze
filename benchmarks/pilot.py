"""Finite in-process ablation pilot. No AI models or external requests."""
import argparse
import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from openmaze.common import Bucket, Policy, Request, decode, error, response, validate
from openmaze.decoy import Decoy
from openmaze.gateway import Gateway
from openmaze.protected import Protected
from benchmarks.provenance import provenance

TARGET = "/v1/tenants/alpha/records"
ARMS = ("deny", "static", "maze")
STRATEGIES = ("follow", "source_aware", "restart")


class StaticDecoy:
    """Benchmark-only cached decoy; no navigation, same initial body byte count.

    Padding controls initial bandwidth, not semantic equivalence or compute cost.
    Uses the same validation and admission implementation as the maze.
    """
    def __init__(self, template):
        data = decode(template.body)
        data["links"] = []
        data["padding"] = ""
        data["padding"] = "x" * (len(template.body) - len(response(200, data).body))
        self.result = response(200, data)
        self.bucket = Bucket()

    def __call__(self, request):
        failure = validate(request)
        if failure:
            return failure
        return self.result if self.bucket.take() else error(429, "decoy_budget_exhausted")


def trial(arm, strategy, seed, budget=25):
    rng = random.Random(seed)
    credentials = {"alpha": "a" * 40, "beta": "b" * 40}
    backend = Protected(Policy(credentials), Ed25519PrivateKey.generate())
    world_seed = hashlib.sha256(str(seed).encode()).digest()
    decoy = Decoy(world_seed, clock=lambda: 1800000000)
    if arm == "static":
        decoy = StaticDecoy(decoy(Request("GET", TARGET)))
    gateway = Gateway(Policy(credentials), backend, decoy,
                      "deny" if arm == "deny" else "maze")
    # Freeze refill time to prevent host scheduling changing admission outcomes.
    for bucket in (gateway.probes, decoy.bucket):
        bucket.clock = lambda: 0
        bucket.updated = 0
    path, trace, stop = TARGET, [], "budget"
    started, cpu = time.perf_counter_ns(), time.process_time_ns()
    for index in range(budget):
        result = gateway(Request("GET", path))
        links = decode(result.body).get("links", [])
        trace.append({"step": index, "route": "continuation" if path.startswith("/maze/") else "entry",
                      "status": result.status, "bytes": len(result.body)})
        if strategy == "restart":
            path = TARGET
            continue
        if strategy == "source_aware" and links:
            stop = "recognized_maze"
            break
        if not links:
            stop = "no_links"
            break
        path = rng.choice(links)
    elapsed, cpu_used = time.perf_counter_ns() - started, time.process_time_ns() - cpu
    return {"arm": arm, "strategy": strategy, "seed": seed, "budget": budget,
            "requests": len(trace), "response_bytes": sum(t["bytes"] for t in trace),
            "continuation_requests": sum(t["route"] == "continuation" for t in trace),
            "protected_operations": backend.operations, "stop": stop,
            "elapsed_ns": elapsed, "cpu_ns": cpu_used, "trace": trace}


def experiment(trials=30, seed=0, budget=25):
    if trials < 1 or not 1 <= budget <= 50:
        raise ValueError("positive trials and budget in 1..50 required")
    rng, runs = random.Random(seed), []
    for block in range(trials):
        for strategy in STRATEGIES:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                runs.append(trial(arm, strategy, seed + block, budget))
    summary = []
    for strategy in STRATEGIES:
        for arm in ARMS:
            subset = [r for r in runs if r["strategy"] == strategy and r["arm"] == arm]
            summary.append({"strategy": strategy, "arm": arm, "n": len(subset),
                            **{f"mean_{metric}": statistics.mean(r[metric] for r in subset)
                               for metric in ("requests", "response_bytes", "cpu_ns")},
                            "protected_operations": sum(r["protected_operations"] for r in subset)})
    return {"schema_version": 1, "scope": "scripted harness pilot; no AI efficacy or throughput claims",
            "config": {"trials": trials, "seed": seed, "budget": budget},
            "summary": summary, "runs": runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget", type=int, default=25)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = experiment(args.trials, args.seed, args.budget)
    result["provenance"] = provenance()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse accidental replacement of an existing experimental artifact.
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
