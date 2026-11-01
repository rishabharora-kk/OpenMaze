# Bounded HTTP load sweep: prospective collection plan

Status: fixed local collection plan written before this sweep. This is not an
externally registered protocol, a power calculation, a production SLO, or an
agent-efficacy experiment. The earlier five-second pilot informed instrumentation.

## Fixed design

- Existing three-process loopback-HTTP / Unix-upstream deployment and entry-churn
  workload from benchmarks.load; each run gets fresh private state/processes.
- Arms: deny and maze; legitimate rate10/s; probe rates0,50,200,800/s.
- Five paired repetition blocks per rate, ten seconds per deployment,32bounded
  client workers, two-second request timeout. At most8,100offered requests/trial.
- Randomize the four rate-group execution order using seed20261101. Within each
  group use the same fixed seed20261101 for the existing randomized arm order.
- Run groups sequentially on the same two-CPU-quota,8GiB runner. No model
  inference, tests, figure builds or other deliberate CPU-heavy work during
  collection. Normal host background contention remains a confound.
- Source must be committed and clean before collection. Preserve per-file
  provenance, full request outcomes, /proc endpoint/samples and hardware/quota
  metadata; record UTC start/end times and actual group order in a sweep manifest.

## Outcomes and analysis fixed before collection

Report per-deployment offered/attempted/completed counts, scheduling lag,
client-capacity drops, verified legitimate fraction and transport/status failures.
Report p50/p95/p99 for all completed legitimate HTTP responses, paired with the
error/drop population. Fast error responses cannot count as improved service.
Also report per-role CPU deltas and sampled RSS/thread maxima, accepted versus
rejected uncredentialed entry work and response-body bytes.

Pair maze-minus-deny differences within repetition block for each rate. Report
all five differences and descriptive means/medians. Do not pool requests or rate
groups as independent repetitions, discard inconvenient runs, report significance
from five blocks, or infer a universal availability bound. Rate group order is
randomized once, not independently across hosts; one shared machine does not
establish external validity or powered equivalence.

No improvement in maze engagement/task outcomes is measured here, so extra maze
CPU/bytes cannot be described as a favorable defense tradeoff by itself. Admission
429 and client drops are legitimate measurements, not reasons to recollect until
numbers look better. Preserve negative results and unsupported /proc values.

## Stopping and validation

Maximum four groups/five pairs per group; no expansion after inspecting results.
Cap total run wall time at20minutes. Stop and preserve evidence on infrastructure
failure, signature verification failure, or unexpected invalid/cross-tenant
acceptance; diagnose rather than silently rerunning. Expected saturation/errors
are reported, not hidden. Independently validate all run accounting and resource
endpoints before analyzing. No public targets, external API, paid model or public
deployment is involved.


## Collection interruption

Collection was attempted on 1 November 2026 at 02:33 UTC, after a usage-limit
interruption delayed the overnight sprint. The execution transport disconnected
during the first rate group. No completed sweep artifact was recovered or
validated. There are no sweep outcomes to report. If partial files become
available, retain and label them; do not combine incomplete groups into a claimed
completed study. A future collection must explicitly identify itself as a rerun.
