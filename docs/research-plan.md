# OpenMaze: research assessment and study specification

## Assessment

The current artifact is a small authorization/deception testbed with explicit
limits, independent backend authorization, negative receipt tests and finite
session/admission budgets. These are useful engineering foundations. They are
not yet an empirical contribution showing defensive benefit.

Working title: **OpenMaze: Evaluating Bounded API Deception Against Adaptive Agents**.
This is a proposed study, not a publication-ready paper or validated novelty claim.

Candidate contribution: a reproducible API-level study of when navigable,
consistent deception improves defender decisions or reduces objective progress,
relative to explicit denial and a static decoy, under explicit resource limits.
The study must remain informative if source-aware agents immediately disengage.

Do not frame the contribution as permanent capture, AI identification, new
cryptography, or the first agent trap. Signed receipts are an orthogonal client
integrity mechanism; evaluate them separately and keep them out of the primary
causal comparison.

## Closest evidence checked

[Cloak, Honey, Trap: Proactive Defenses Against LLM Agents](https://www.usenix.org/conference/usenixsecurity25/presentation/ayzenshteyn),
Ayzenshteyn, Weiss and Mirsky, USENIX Security 2025, pp. 8095–8114,
already studies deception, honey-tokens and loops against LLM penetration-testing
agents. Its official abstract describes six strategies and fifteen techniques,
with evaluation on eleven CTF machines. Those are the authors' reported results,
not independently reproduced here. Only the conference abstract was read for
this assessment; a full-paper and artifact comparison is required before fixing
OpenMaze's novelty claim.

The existing README also identifies Cloudflare AI Labyrinth, Endlessh and
OpenCanary. Compare these by protocol, attacker assumptions, control conditions,
resource accounting and adaptation, rather than presenting a feature checklist
as proof of novelty. The initial literature search is not exhaustive.

## Runnable pilot

From the repository root after installing the package:

```bash
python -m unittest discover -s tests -v
python -m benchmarks.pilot --trials 30 --seed 2026 --output results/pilot.json
```

Output creation is exclusive: use a new filename for each run. The artifact stores
configuration, source hashes, base commit, dirty status, runtime, arm order,
per-run counters and synthetic route-class traces. No credentials or continuation
tokens are stored. There are 30 blocks × 3 scripted strategies × 3 arms = 270 runs.
Each run creates fresh services; arm order is randomized within each block.

The static arm is benchmark-only, served through the same gateway's decoy route.
It caches synthetic inventory, removes navigation and pads the initial body to
the maze's initial byte length. It uses the same validation and admission code.
It does not match maze computation, state allocation, semantics or subsequent
response sizes. It is not yet available through the HTTP/Compose CLI.

The maze uses a frozen synthetic session clock; admission refill is frozen too.
World seeds and link choices are seeded, while session identifiers and signing
keys remain cryptographically random. Counters and route-class traces reproduce;
raw bodies, tokens and timing do not. CPU and elapsed measurements include the
in-process caller and JSON parsing, exclude setup, and measure neither isolated
server cost nor network throughput. Warmup, sustained load and memory are absent.

Pilot observed on this runner:

| Scripted caller | Deny requests | Static requests | Maze requests |
| --- | ---: | ---: | ---: |
| Follow a random returned link until none remain | 1 | 1 | 21 |
| Stop on recognizing navigation from known source | 1 | 1 | 1 |
| Restart at the entry route until budget expires | 25 | 25 | 25 |

All 270 runs recorded zero protected operations. The 21st follower request gets
session exhaustion after 20 successful responses. These observations validate
harness behavior. They do not establish efficacy, independent world diversity,
statistical power, or an availability guarantee. Thirty repetitions of a simple
script do not supply thirty independent observations of intelligent behavior.
No confidence interval over these repetitions should be used as an AI result.

## Task opportunity implemented after this assessment

The new [study protocol](study-protocol.md) and `benchmarks.objective` add an
owned synthetic task with identical genuine opportunities across treatments,
an independent completion oracle, source-aware controls and paired world-level
contrasts. This closes a harness gap; adaptive-agent and resource-cost studies
remain outstanding. [CI and delivery](ci-cd.md) validate and retain both experiments.

## Primary study: specify before model runs

1. **Objective and opportunity.** Build owned synthetic worlds containing a
   reachable, explicitly scoped task with a measurable success oracle, plus decoy
   branches. The existing protected API offers an uncredentialed caller no
   legitimate success opportunity, so equal zero success cannot establish
   diversion. Score actual task completion with a hidden ground-truth oracle,
   never with HTTP 200 or synthetic records alone.
2. **Treatment.** Denial, static inventory and consistent navigable inventory.
   Hold policy, task opportunity, initial observation, agent tools, model settings
   and budgets constant. Match content/size where feasible and disclose residual
   confounds. Add an inconsistent-maze ablation to isolate consistency from links.
3. **Agents.** Include at least multiple independent model families and a pinned
   non-model baseline. Cross source-aware/uninformed instructions, repeated-session
   behavior and parallel callers. Source-aware agents receive the actual source,
   not merely a hint that traps exist. Pin prompts, tool schemas, model IDs,
   sampling settings and run budgets; record refusal and infrastructure failure.
4. **Unit and randomization.** One complete agent/world run is the unit. Use
   matched world/task blocks across arms with fresh agent context. Randomize arm
   order. Separate development and held-out world generators/seeds. Budget and
   select trial counts using variance estimates and a prespecified useful effect;
   30 runs is a pilot starting point, not a power guarantee.
5. **Outcomes.** Prespecify objective success as primary. Report paired differences
   and run-level confidence intervals, accounting for world/model clustering.
   Secondary outcomes: fraction of budget spent on decoys, time to disengagement,
   token/tool cost, and independently labeled useful telemetry. Distinguish budget
   exhaustion, abandonment, timeout, refusal and harness failure. More requests
   alone are not improved defense. Report every arm and negative result.
6. **Defender cost.** In a separate HTTP experiment, measure server CPU, RSS,
   bytes, sessions, worker occupancy and legitimate-client errors/p50/p95/p99
   latency under matched offered load, including entry-session churn. Include
   denial-only load controls and repetitions at the deployment level. Do not
   infer deployed performance from this in-process pilot.
7. **Telemetry value.** Define an actionable decision and blinded labels before
   evaluating utility. Compare a fixed detector with and without maze telemetry
   on held-out runs, reporting precision/recall and false-positive costs. Avoid
   labeling a request malicious merely because it followed a decoy link.

## Implementation order and publication gates

- First: complete a full-paper related-work comparison and freeze the scoped
  question, task oracle, outcomes and analysis plan.
- Next: add task-bearing synthetic worlds, a common agent tool adapter, trace
  replay, and the static treatment over HTTP. Keep provider calls opt-in and
  record their costs; no paid model runs were performed in this pilot.
- Then: implement deployment/load instrumentation and validate effective container
  mounts, networking and resource limits. Passing application tests cannot prove
  a compromised decoy is contained.
- Finally: execute held-out agent trials, publish prompts/configuration/failures,
  generate figures from raw artifacts, and write claims to match the findings.

A workshop/tool paper becomes plausible with a reproducible artifact and useful
initial empirical findings. A stronger systems/security submission needs a
substantive result about adaptive agents or defender economics, convincing
controls and validated deployment boundaries. Venue fit is conditional on those
results, not on code volume or presentation polish.

Suggested paper structure: motivation and hypotheses; threat model; architecture
and boundaries; experiment and analysis design; adaptive-agent results; resource
cost and legitimate-client impact; limitations; related work; artifact appendix.
Do not write a results-bearing abstract until those results exist.
