# Study protocol v0: task diversion under bounded API deception

Status: development protocol, not a preregistration. The scripted outcomes below
were observed while developing the harness. Future model/held-out studies must
freeze a new protocol version and analysis plan before collecting those results.

## Research question and candidate contribution

Does consistent navigable API deception reduce an adaptive caller's progress on
an otherwise reachable objective, relative to denial and static inventory, at an
acceptable resource cost to the defender?

Candidate paper angle: **the boundary of useful API deception under source
knowledge and bounded defender resources**. Source-aware failure is a result to
explain and measure, not a case to omit. This is a measurement/experimental-design
contribution if supported by adaptive-agent evidence; the maze mechanism alone
is not an established novelty contribution.

## Current construct check

`python -m benchmarks.objective --trials 30 --seed 10000 --output artifacts/objective.json`

Each world has a public binary catalog of depth four, a designated inventory
record at one leaf, and a separate decoy candidate. The objective is to retrieve
the designated record. An oracle checks the exact item/value, not the response
status or an agent's self-assessment. Catalog content, answer, entry-link order
and task opportunity are identical across treatments for each world seed.

Treatments are deny, static inventory padded to match the maze's initial response
length, and the existing consistent maze. The wrapper only adds public synthetic
catalog routes in process; protected API policy is unchanged. All callers have
40 fetches, including the starting page. Each run starts with fresh services and
frontier. Arm order is randomized within matched world/strategy blocks.

Three scripted strategies check the design:

- Breadth-first traversal with a visited set.
- Random frontier selection with a seeded choice stream.
- A source-aware traversal that excludes the disclosed non-task route family.

The source-aware script is a deliberately privileged oracle-like control, not a
simulation of how a real model will use source. Strategies inspect observations
and cannot succeed merely by returning a fake record. Raw tokens/answers are not
published in traces; route class, bytes, status and oracle outcome are retained.
World seeds are public in the development artifact, so do not reuse them as a
hidden evaluation dataset for source-aware models.

On 30 development worlds, deny/static complete all tasks for all three scripts;
maze completes none for breadth-first/random-frontier and all for source-aware.
These are deliberately simple synthetic constructs, not a security success rate.
The branching maze floods naive frontiers by construction. Navigation prefixes
make filtering trivial with source knowledge. This checks that the harness can
register both diversion and its disappearance; it does not demonstrate that
intelligent attackers will be diverted or that arbitrary objectives are protected.

## Outcomes and statistics

Primary: oracle-verified completion within the fetch budget. Secondary: requests,
decoy-candidate requests, bytes and stop reason. No model tokens or deployment
CPU/memory/latency are measured by this experiment. The original `pilot` command
is a separate engagement/bookkeeping check.

Report maze-minus-control success differences within each strategy and paired
percentile-bootstrap 95% intervals over world seeds, using 2,000 resamples.
These intervals cover variability over this fixed synthetic world generator,
not model stochasticity or real systems. With identical binary effects the
bootstrap interval is degenerate; it is not proof that the population effect is
exactly 0 or -1. No significance test, multiplicity-adjusted inference, or
power claim is made. Never treat requests as independent samples.

Scripts share the same choice seed across arms; different observations can consume
the choice stream differently. Session IDs and signing keys remain random, while
route-class traces and objective outcomes are reproducible. Session clocks and
admission refill are frozen. Setup and timing are not part of this task experiment.

## Freeze before the agent study

1. Define an owned target task representing a realistic API objective and hidden
   oracle. This catalog task measures opportunity cost, not exploit prevention.
2. Add a common agent adapter that exposes only observations/fetch/submit tools,
   never the Python world object or oracle answer. Hold task prompts, tool schema,
   budget, credentials and model settings constant across arms.
3. Pin multiple model families/versions. Cross informed and source-informed
   conditions; include session churn, parallel workers and short-timeout policies.
   Log tool traces, model token/cost data, abandonments and infrastructure errors.
4. Separate development and held-out world families/seeds. Freeze meaningful effect,
   exclusion criteria, stopping rule, paired analysis and sample size based on
   pilot variance before held-out runs. Include model/world clustering in analysis.
5. Add an inconsistent-link/content ablation to distinguish consistency from
   branching. Match initial sizes/content and disclose semantic confounds.
6. Run a separate controlled HTTP load study of legitimate-client latency/errors,
   server CPU/RSS/bytes and session churn. A bound on one session is not a bound
   on total attacker engagement, and container limits are not an availability SLO.
7. If claiming telemetry utility, prespecify an operational decision and blinded
   labels, and compare against denial/static telemetry on held-out runs.

Proceed to a results-bearing manuscript only after the agent and cost studies.
Archive complete configurations, source, analysis and failures; report a negative
finding if source awareness or defender cost removes the benefit.
