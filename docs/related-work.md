# Related-work audit: bounded API deception

Audit date: 1 November 2026 (Asia/Calcutta). This is a focused primary-source
review, not an exhaustive literature survey. Numerical results below are reports
by the cited authors; OpenMaze has not reproduced those experiments.

## Novelty assessment

**Agent traps, deception-aware evaluation, verifiable API goals, and attacker /
defender cost comparisons already have substantial prior art.** A claim that
OpenMaze first combines these ideas would be unsupported. The current defensible
position is a small reproducible, deterministic API-deception testbed whose
controls make session bounds, genuine task opportunity, and the difference
between engagement and objective progress explicit. Its research value must
come from a new measurement, replication, or boundary finding; code packaging
and CI alone do not establish a scientific contribution.

| Work and primary source | Evidence inspected | Relevant contribution | Consequence for OpenMaze |
| --- | --- | --- | --- |
| [CHeaT: Cloak, Honey, Trap](https://www.usenix.org/system/files/usenixsecurity25-ayzenshteyn.pdf), USENIX Security 2025 | Full conference PDF retrieved; inspected strategies, §§6.1–6.2, §7, Tables 3–4, ethics and artifacts | Deception and loops against LLM pentesters; CTF controls; defense-aware context, preprocessing, prompting and fine-tuning | Neither trapping nor awareness is new; preserve genuine-task capability controls and false-positive costs |
| [Cloudflare AI Labyrinth](https://blog.cloudflare.com/ai-labyrinth/), 19 March 2025 | Primary announcement article read; published date from page metadata | Pre-generated linked decoy HTML for suspected unauthorized crawlers; caching, sanitization and telemetry integration | Navigable decoy content is established; distinguish JSON API experiments from crawler deployment, and do not infer AI identity from following a link |
| [Honeyval](https://arxiv.org/html/2605.29963v1), arXiv v1, 28 May 2026 | Full HTML retrieved; inspected §§3–5 and §6 limitations | HTTP honeypot evaluation grounded in 16 backend APIs; verifiable exploit goals; agent and honeypot control tasks; rule-based baselines; latency and cost asymmetry | The API-goal/control/cost framework is especially close. OpenMaze must distinguish its deterministic bounded mechanism and measurement target, not claim a first API benchmark |
| [Rouxii](https://arxiv.org/html/2609.26555v1), arXiv v1, 22 September 2026 | Full HTML retrieved; inspected matched-cohort design, §§5–7 and outcome definitions | Matched vanilla versus anti-deception agents; fingerprints, false positives, stalls and post-detection risks | Source knowledge must be a real treatment; trap recognition is distinct from successful avoidance or task completion |
| [LLM-Based Penetration Testing in the Presence of Honeypots](https://arxiv.org/html/2609.08093v1), arXiv v1, 8 September 2026 | Full HTML retrieved; inspected §§3–6, cost accounting and ground-truth outcomes | Honeypot-aware budget allocation over a mixed genuine/honeypot pool; detector-guided entry, post-connect stopping and budget ablations | Budget-aware avoidance and task-bearing mixed targets are also established. Compare completion and wasted budget, not only a detection label |

The 2026 entries are cited as the inspected arXiv preprint versions; this audit
does not establish acceptance at a peer-reviewed venue or reproduce their code.
The PDF/HTML extraction includes duplicated text and math-formatting artifacts.
Claims below rely on identifiable section/table text rather than malformed
inline mathematical rendering.

## CHeaT: what the full paper changes

The earlier OpenMaze assessment read only CHeaT's abstract. The full paper has an
explicit **Adaptive Adversaries** section (§7). Its defense-aware conditions
include paper/payload context, input preprocessing, informed system prompts,
fine-tuning and an ensemble. Table 4 reports both defense success and payload
classification/false-positive measures. The discussion explains that low defense
success can accompany an overly cautious agent that rejects genuine paths.
OpenMaze should therefore avoid claiming that awareness alone exposes a new
unexamined weakness. It should measure task capability alongside avoidance.
[Source: §7.1, Table 4](https://www.usenix.org/system/files/usenixsecurity25-ayzenshteyn.pdf).

The end-to-end experiment in §6.2 uses eleven CTF machines with PentestGPT/GPT-4o,
three runs per machine with and without defense, and staged initial-access /
privilege-escalation objectives. Table 3 shows that some undefended tasks already
fail. This makes a strong opportunity control essential: zero success in a maze
arm is not informative if the same caller could not complete the underlying task.
[Source: §6.2, Table 3](https://www.usenix.org/system/files/usenixsecurity25-ayzenshteyn.pdf).

OpenMaze intentionally excludes attacker-infrastructure counterattacks, arbitrary
execution and LLM-specific identification. It shares the idea of increasing
unproductive interaction but has a much narrower mechanism and threat model.
That is a scope distinction, not evidence of superiority.

## Honeyval: the closest API evaluation framework

Honeyval defines a main agent-versus-honeypot task and two controls: the agent
attempts the real backend, while the honeypot attempts functional backend tests.
Its API specifications and exploit goals ground the interaction in an actual
application model. It compares LLM-backed and rule-based HTTP simulations and
measures interaction length, detection, latency and costs. Its §5.1 describes
independent repetitions and run budgets; §5.2 explicitly discusses cost/context
asymmetry. [Source: §§4–5](https://arxiv.org/html/2605.29963v1).

OpenMaze currently does not match that evaluation breadth. It generates responses
without a defender LLM and concentrates on finite session/admission resources,
application authority separation, and an auditable synthetic catalog oracle.
A plausible follow-up would test whether that low-compute design retains any
objective-diversion benefit under matched source-informed callers, then measure
its legitimate-client opportunity cost. It should be presented as a controlled
baseline / bounded-design study, not a replacement for Honeyval.

## Awareness and budget allocation

Rouxii's central contrast holds models, targets, operators and workflow fixed
while varying counter-deception information in the prompt. Its §5.2 separately
defines raw detection, grounded detection and stalled interactions. Its §7 warns
that external frameworks have different context/workflow budgets and that real
OT false-positive controls are absent. OpenMaze should use within-harness
contrasts and separate timeout, refusal, recognition, abandonment and task success.
[Source: §§5.2 and 7](https://arxiv.org/html/2609.26555v1).

Xie et al. evaluate a two-stage detector-guided policy over genuine and deceptive
hosts. The agent does not receive ground-truth host type. §4.3 counts model calls
used for tool selection and observation processing in the LLM budget, while
excluding the deterministic tools' runtime. §5.1 distinguishes genuine
confirmation, false rejection, false entry, delayed abandonment and unresolved
hosts. These definitions illustrate why a hidden task oracle and a complete
budget ledger matter. [Source: §§4.3 and 5.1](https://arxiv.org/html/2609.08093v1).

## Minimum credible submission bar

An artifact/demo or workshop submission could center on a transparent bounded
implementation and a reproducible negative/replication result, provided it:

1. States the narrow contribution against the papers above.
2. Uses genuine task opportunity and source-informed controls with realistic
   observations, not a policy that is handed oracle labels or a trivial route rule.
3. Separates development from held-out worlds/configurations and accounts for
   repeated runs at the independent world/model level.
4. Reports defender CPU/RSS/bytes and legitimate-client latency/errors under
   matched offered load, rather than calling extra requests a defensive win.
5. Includes failures, shutdown/restart behavior, finite resource bounds and
   permanent raw-artifact/configuration availability.

A strong security/systems paper additionally needs a substantive finding beyond
these engineering checks, meaningful adaptive-agent evidence, broader task
validity, and validated deployment boundaries. A morning deadline cannot turn
scripted traversal into evidence of autonomous-agent effectiveness.


## Current result and appropriately narrow framing

The extended OpenMaze factorial contains 6,480 scripted runs across thirty reused
world seeds, depth/budget conditions, path visibility, policies and treatments.
At depth four and forty fetches, breadth-first maze completion is 0/30, whereas a
progress guard completes 30/30 after two decoy fetches under both clear and opaque
paths. The guard detects the synthetic response-schema mismatch, not a hidden
oracle label. Prefix masking alone therefore does not repair the effect. A
branch quota also reduces genuine completion in denial/static controls.

This is a reproducible **negative control for this mechanism and world family**.
It is not a first observation that awareness defeats deception, nor an empirical
claim about LLMs. Its workshop/replication value depends on transparent source,
raw traces and limits, useful integration with the real HTTP cost instrumentation,
and an honest comparison to the stronger adaptive-agent studies above.


A separate 4,320-run post-result follow-up holds the policies fixed and removes
the successful-response schema clue. In the opaque depth-four slice, progress-
guard maze completion falls from 30/30 to 2/30 at forty fetches (9/30 when exposed
degree is also limited to two). At sixty-four fetches all guard presentations
complete 30/30, but schema-only matching raises mean decoy fetches from two to
twenty-two: twenty successful responses followed by two exhaustion errors expose
a later pruning cue. This narrows the finding further: the cheap escape is
fingerprint-specific, and bounds, topology and caller budget jointly affect
when avoidance becomes possible. It is not evidence that schema matching
establishes general deception resilience.
