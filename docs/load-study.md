# Local HTTP defender-cost pilot

`benchmarks.load` measures legitimate-client behavior under a finite offered load
against real local HTTP services. It complements the scripted task-opportunity
experiment; it does not measure agent efficacy or a production availability SLO.

```bash
python -m benchmarks.load --repetitions 3 --duration 5 \
  --legitimate-rate 10 --probe-rate 50 --workers 16 \
  --output artifacts/load-pilot.json
```

Each independent repetition creates fresh private state and three subprocesses:
gateway (loopback HTTP), protected service and decoy (filesystem Unix sockets).
It warms up a signed legitimate request, then measures a fixed offered schedule.
Denial and maze arms run in randomized order within repetition blocks. The
`seed` affects arm ordering, not traffic generation or cryptographic state.
Keys, credentials and continuation tokens are never retained in the artifact.

## Offered work and accounting

Legitimate requests are authorized alpha reads. Every one creates and consumes
a fresh nonce and verifies the pinned Ed25519 response envelope and returned
tenant. The gateway's existing authorization/admission implementation is used.

Probe traffic is a fixed cycle of eight uncredentialed entry requests, one invalid
credential request and one cross-tenant request carrying a valid alpha credential.
The last two require 401 and 403 respectively; unexpected status is reported
separately. This is an **entry-session-churn** workload, not maze navigation.
It tests the cost of repeatedly creating fresh sessions, so a per-session response
bound must not be presented as a bound on total attacker work.

Requests are scheduled at fixed offsets, rather than waiting for earlier responses.
A client pool has at most the configured number of pending requests. When the pool
is full, an offered request is recorded as `client_capacity_drop`, not silently
queued or omitted. Record counts distinguish offered, attempted, completed HTTP
responses, timeouts, client drops and other failures. All response statuses count
as completed HTTP exchanges; only verified legitimate responses count as successful
legitimate service. Legitimate error fraction includes every offered legitimate
request, including client drops. Low-rate/short runs may contain an incomplete
probe cycle, so inspect the actual per-kind counts.

## Measurements

Per-request records contain route class, status, outcome, response-body bytes,
HTTP latency and total processing time, plus scheduling lag. No raw target,
credential, nonce, signed payload or key is retained. `response_body_bytes`
counts fully read response bodies and excludes partial failed reads, HTTP headers,
TCP framing, retransmission and request bytes; it is not network bandwidth. There is one HTTP connection per request and no TLS.

HTTP latency starts before creating the connection and ends after reading its
body. It excludes subsequent signature verification; `total_ms` includes it.
The p50/p95/p99 summaries use nearest-rank quantiles across **all completed
legitimate HTTP responses**, including error responses. They exclude timeouts
and client drops, whose counts/error contribution must always accompany latency.
Fast failures cannot establish improved availability. Do not merge latency
samples across deployment repetitions and treat each request as independent.

On Linux, `/proc` is sampled for each known server subprocess: user+system CPU,
RSS, and thread count. CPU is the per-role delta across the measured window;
Linux clock-tick granularity can yield zero for short/light trials. Report CPU
seconds rather than treating sampled Python-process CPU as container or host CPU.
`server_resource_endpoints.before/after` preserve each role's underlying snapshot
so independent checks can recompute the CPU delta. Recompute maxima over those
two snapshots plus all non-null `resource_samples[].roles[role]` values.
RSS/thread maxima are **sampled maxima**, not exact peak memory/thread values.
Sampling is opportunistic at offered events, at most about 10 Hz, plus window
endpoints. On unsupported/restricted `/proc`, role resources are `null`; missing
measurement must not become zero. Client scheduling, JSON parsing, signature
verification and sampling execute in a separate process and are excluded from
server CPU deltas, but contend on the same host. Per-role reads and endpoints are
sequential, not atomic; their intervals differ by sampling overhead.

`measurement_metadata` records CPU model, architecture/kernel, OS CPU count,
client CPU affinity count, clock-tick frequency, HTTP timeout/quantile method,
and visible cgroup quota/memory-limit files. These are non-secret observations of
this execution context, not a complete ancestor-cgroup or host-resource inventory.
Missing metadata stays `null`; never silently substitute unlimited resources.

The nominal interval is allowed to finish, then all already-attempted requests
drain. `elapsed_with_drain_seconds` records actual duration including drain;
requests have two-second HTTP timeouts. Resource deltas cover that same window,
not startup/warmup or shutdown. Fixed maxima bound duration, rates, request count,
client workers and repetition count. Arbitrary external destinations are unsupported.

## Interpretation and next study

The short default pilot is a reproducibility/measurement check. It lacks
sustained-load levels, dedicated hosts, TLS/front-proxy costs, container resource
limits, model activity, held-out scenarios and independently powered sample size.
Fresh processes on a shared host are separate experimental repetitions, but host
load/thermal/cache effects can still correlate them. Repeat on isolated hosts,
record kernel/CPU/container configuration, and freeze offered rates/durations,
meaningful error/latency effects, rejection handling and analysis before collecting
held-out deployment results. Compute paired differences at the deployment-block
level, with uncertainty that respects host/repetition structure.

A useful next design crosses deny/maze with legitimate-only, mixed entry churn,
maze navigation and saturation conditions at multiple offered rates. Keep total
offered traffic matched within comparisons. Analyze valid-client latency/error
jointly with CPU, sampled RSS, accepted probe/session work and response bytes.
These costs belong alongside adaptive-agent objective results in the paper;
more decoy requests alone are not evidence of beneficial defense.


## Recorded development run

The initial `artifacts/load-pilot.json` contains three paired five-second blocks
at 10 legitimate requests/s plus 50 probe requests/s (16 client workers). Across
six fresh deployments all 1,800 offered requests completed HTTP exchanges, all
300 legitimate responses verified, and all 300 invalid/cross-tenant probes
received their expected 401/403 statuses. No client capacity drops occurred.

| Block | Deny legitimate p95 (ms) | Maze legitimate p95 (ms) | Deny gateway CPU (s) | Maze gateway CPU (s) | Maze decoy CPU (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 2.662 | 2.104 | 0.10 | 0.14 | 0.04 |
| 1 | 1.872 | 2.112 | 0.10 | 0.13 | 0.04 |
| 2 | 1.908 | 2.158 | 0.10 | 0.13 | 0.05 |

This shared-runner, low-rate result checks that server work and legitimate-service
outcomes are measurable. Three short repetitions do not establish equivalence,
a useful latency bound, a production availability target or a universal CPU cost.
The decoy's additional measured work must be paired with independently measured
agent/task benefit before claiming favorable defender economics. Per-role RSS and
other request-level metrics are retained in the raw local artifact.


## Bounded follow-up recipe

After freezing the analysis plan, collect a small offered-rate sweep sequentially
on an otherwise idle runner; do not overlap model compilation/inference or other
load experiments. This development recipe offers 10 legitimate requests/s and
0, 50, 200 or 800 probes/s for 10 seconds, with five paired deployments per rate
and a 16-request client cap. Every individual deployment stays below the harness's
10,000-offered-request and 60-second limits. The highest rate may produce explicit
client drops and admission rejections; report them rather than interpreting only
completed-request latency. Existing global admission limits can reduce actual
decoy work well below offered traffic.

```bash
for rate in 0 50 200 800; do
  python -m benchmarks.load --repetitions 5 --duration 10 --seed 2026 \
    --legitimate-rate 10 --probe-rate "$rate" --workers 16 \
    --output "artifacts/load-rate-${rate}.json"
done
```

Use fresh output paths on reruns. Do not select only favorable rates or infer a
universal saturation threshold from this host. Treat the sweep as development
unless its rates, exclusions and analysis were frozen before collecting it.
