# Matched-presentation follow-up: frozen development configuration v1

Status: a **post-result development follow-up**, not a preregistration. The
original adaptive study showed a two-page schema fingerprint removed maze
engagement. This follow-up asks whether that finding survives removal of the
very cue the progress guard uses. This file's design section was written before
collecting this follow-up's outcomes. That ordering is not independent registration.

## Fixed design before collection

- World seeds: 60000–60029, distinct from prior development/evaluation ranges.
- Genuine catalog depth: four; fetch budgets: 40 and 64.
- Treatments: deny, static inventory and maze.
- Scripts: breadth-first, progress guard, branch quota and disclosed routes,
  reused unchanged from `benchmarks.adaptive.CatalogPolicy`.
- Route visibility: clear and opaque per-world aliases.
- Presentations: original, matched schema, matched schema and exposed degree.
- Thirty matched world seeds per cell; randomized arm order within each
  world/script/budget/visibility/presentation block; one terminal submission.
- Total: 3 presentations × 2 budgets × 2 visibility conditions × 4 scripts ×
  3 arms × 30 seeds = 4,320 complete runs. These are not 4,320 independent worlds.

The original presentation passes through the existing observation payload.
For successful responses, matched schema presents exactly `links` and `record`,
using `record: null` on pages without a target candidate. Synthetic inventory
`id` and `description` are removed; the genuine target record is preserved
exactly. The second matched condition also exposes at most two children per
successful observation. Genuine catalog branching is already at most two, so
its task graph/content/opportunity remain identical in every presentation.

Errors/status codes are preserved. The wrapper changes tool observations in
process; it is not an HTTP feature, deployed gateway treatment, bandwidth
optimization or compute-cost measurement. The underlying server still builds
its original payload. Original response-body bytes and serialized observation
bytes are recorded separately. The latter serialize path/status/payload/remaining;
they are not HTTP wire bytes or model tokenizer counts.

The tool allowlist contains only links actually exposed after presentation;
a truncated third child cannot be fetched merely because the underlying world
emitted it. Reverse mappings and the completion oracle stay with the runner;
policies receive only observations. One candidate submission terminates a run.

## Analysis specified before collection

Report every condition and all scripts, including low completion in denial.
Compare maze-minus-deny and maze-minus-static completion differences within each
presentation/budget/visibility/script using paired seed-level percentile bootstrap
95% intervals (2,000 resamples). These are descriptive conditional intervals,
without multiplicity adjustment; no inferential robustness claim follows from
many correlated cells. Do not pool requests or route variants as independent
samples. Identical seed-level differences yield degenerate bootstrap intervals.

The expected diagnostic is whether the progress guard's advantage over naive
traversal changes when `record`-field absence is removed. Either direction is
reportable. Disclosed clear routes retain the direct path cue; opaque routes
remove that cue. Matching degree does not match leaf-vs-interior semantics,
objective realism, generation cost, state allocation, or broad task families.
None of these runs tests LLM efficacy or real attacker progress.


## Observed outcomes of this frozen follow-up

A local run completed all 4,320 configurations with zero protected operations.
The table reports completed tasks out of 30 matched seeds in the maze arm under
opaque routes; denial/static completion is 30/30 for these two scripts in every
presentation/budget cell.

| Presentation | Breadth-first, budget 40 | Progress guard, budget 40 | Breadth-first, budget 64 | Progress guard, budget 64 |
| --- | ---: | ---: | ---: | ---: |
| Original | 0/30 | 30/30 | 8/30 | 30/30 |
| Matched schema | 0/30 | 2/30 | 8/30 | 30/30 |
| Matched schema and degree | 8/30 | 9/30 | 30/30 | 30/30 |

The cheap two-fetch progress-guard escape disappears under schema matching.
However, its completion advantage does **not** disappear at the larger budget.
The matched-schema guard consumes twenty successful decoy responses followed by
two 410 session-exhaustion errors, then prunes that root branch. Those errors
lack a `record` field, so the unchanged rule gains a late observable stopping cue.
Its mean maze-candidate requests rise from 2 to 22, and mean total fetches from
26.77 to 46.77 at budget 64. This is a consequence of bounded-session exhaustion,
not evidence that the guard learned a new semantic model of the task.

At budget 40, matched-schema progress-guard completion drops from 30/30 to 2/30;
its maze-minus-denial difference is -0.933 with a descriptive paired-bootstrap
interval [-1.000, -0.833]. Matching exposed degree then raises naive maze
completion to 8/30 at budget 40 and 30/30 at budget 64. Thus branching degree and
observation cues materially change the same deterministic scripts' outcomes.

Clear disclosed-route filtering completes 30/30 in all presentations/budgets
without entering the decoy. Under opaque routes it behaves exactly as
breadth-first, as specified. The branch-quota control remains limited by its
choice to allocate at most half the budget to a genuine branch; report the full
artifact rather than selecting its maze failures as evidence of efficacy.

The proper interpretation is sensitivity to schema, observable exhaustion and
branching under a fixed caller budget. Neither the original 30/30 escape nor its
40-fetch matched failure is an AI-agent result. No follow-up policy was tuned to
these outcomes, and all three presentations, both budgets and both visibility
conditions remain in the artifact.
