# Adaptive scripted controls: development protocol v1

This experiment tests the **fragility of a synthetic diversion result**, not
whether an LLM or malicious agent is captured. No model inference or external API
calls occur. It extends the catalog opportunity in `benchmarks.objective` with
an observation/action boundary and elementary response-driven scripts.

## Run and artifact

```bash
python -m unittest discover -s tests -p test_adaptive.py -v
python -m benchmarks.adaptive --trials 30 --split evaluation --output artifacts/adaptive.json
```

Output creation refuses replacement. The artifact includes source hashes, commit
and dirty status, runtime, the protocol source hash, all run counters/traces,
conditional summaries and paired world-seed bootstrap contrasts. Raw record
values, credentials and maze continuation tokens are absent from traces. The
recorded response byte count is the original synthetic server-body size, not the
length of the opaque remapped tool observation or a network throughput metric.

`development` uses seeds 20000 onward; `evaluation` uses seeds 50000 onward.
At most 1000 trials are allowed, so the ranges do not overlap. These labels provide
an explicit seed split, not a preregistration or a claim that later researchers
have not viewed the results. Policies and parameter choices are visible in code.
The evaluation worlds vary target location and initial root order within the
same generator family; they do not establish generalization to new tasks.

## Observation and action separation

A policy receives only `Observation(path, status, payload, remaining)` and emits
one of:

```json
{"tool":"fetch","argument":"/previously-observed/path"}
{"tool":"submit","argument":{"item":"requested-inventory-item","value":"candidate"}}
{"tool":"finish"}
```

`ObservationTool` is retained by the runner. Its allowlist accepts only the entry
route and paths observed in links. It enforces the fetch budget and holds the
world/oracle, which are not passed to `CatalogPolicy`. The task item name is public.
A single candidate submission ends the run; failed guesses cannot obtain a free
oracle-query loop. A candidate found on the final permitted fetch may still be
submitted. Fetches and submissions have separate recorded counts.

This is interface separation in one Python process, **not a security sandbox**.
An actual model adapter should receive serialized observations/tool descriptions,
never the Python `ObservationTool`/`TaskWorld` object or seed. Policies see fetched
candidate values, as they must to submit an answer, but not the hidden expected
answer or oracle feedback before their terminal submission.

## Factorial conditions and fixed scripts

The default design crosses catalog depths 3, 4 and 5 with fetch budgets 24, 40
and 64. Each of nine depth/budget conditions runs under clear and opaque paths,
four scripts, three treatment arms and 30 matched world seeds: **6,480 complete
runs**, not 6,480 independent worlds. World seeds are reused across conditions.
Arm execution order is randomized within world/script/condition blocks.

Opaque task aliases are HMACs under a per-world derived key. They differ between
world seeds and match exactly across arms, independent of traversal order. The
runner maintains reverse mappings; policies never receive the key. Opaque paths
remove the literal `/study/` and `/maze/` prefix signal, while preserving payload
schema, link count and other observational clues. This is an ablation of a clue,
not a mechanism claimed to conceal paths against knowledgeable adversaries.

- **Breadth-first:** explore observed links, with a visited set.
- **Progress guard:** the same traversal, but stop an entry-root branch after two
  fetched pages lack a `record` field. The catalog supplies `record: null` on
  non-target pages; the current maze supplies no `record` field. This is a
  deliberately cheap schema fingerprint and depends on that synthetic mismatch.
- **Branch quota:** cap each entry-root branch at half the request budget. This
  bounds attention to a large branch but can prematurely abandon genuine work.
- **Disclosed routes:** skip non-`/study/` routes when clear prefixes are exposed.
  Under opaque paths it falls back to breadth-first. Source knowledge does not
  reveal the private runtime reverse mapping; schema clues remain observable.

The maze itself retains its existing three children per page and 20-response
session cap. This design changes catalog depth and global fetch budget; it does
not vary maze branching or test consistency against inconsistent decoys. Those
are separate, still-needed ablations.

## Observed development results

A local 30-seed evaluation-split run of this protocol completed all 6,480 runs
with zero protected operations. For depth four and 40 fetches:

| Script | Visibility | Deny completion | Static completion | Maze completion | Mean maze-candidate fetches in maze arm |
| --- | --- | ---: | ---: | ---: | ---: |
| Breadth-first | clear or opaque | 30/30 | 30/30 | 0/30 | 28.53 |
| Progress guard | clear or opaque | 30/30 | 30/30 | 30/30 | 2.00 |
| Branch quota | clear or opaque | 10/30 | 10/30 | 6/30 | 20.00 |
| Disclosed routes | clear | 30/30 | 30/30 | 30/30 | 0.00 |
| Disclosed routes | opaque | 30/30 | 30/30 | 0/30 | 28.53 |

The progress guard's mean requests were 27.17 in maze versus 26.17 in denial:
only one extra fetch on average. Hiding path prefixes did not change this result,
because the schema fingerprint remained visible. A simple budget allocation rule
hurt genuine task completion in every arm; its low maze completion rate cannot
be interpreted without that weak denial baseline.

The effect is also budget-dependent. At depth three, breadth-first maze
completion rose from 6/30 with 24 fetches to 13/30 with 40 and 30/30 with 64.
At depth five and 64 fetches, progress guard completed 29/30 in both maze and
denial, whereas breadth-first completed 0/30 in maze and 29/30 in denial.

These statements describe this fixed graph/schema experiment. The response
schema is unusually easy to distinguish, the objective has a narrow form, the
scripts are deterministic, and the world family is small. It would be misleading
to turn the naive script's 0/30 result into an AI-agent defense success rate.
The defensible finding is that **one apparent diversion result disappears under
an elementary observable-schema adaptation**, even after route-prefix masking.

## Analysis limits

For each script/depth/budget/visibility condition, the artifact reports paired
maze-minus-control completion differences and percentile-bootstrap 95% intervals
with 2000 resamples over the 30 matched seeds. These are descriptive conditional
intervals, with no multiplicity adjustment. Identical binary differences produce
degenerate intervals; they do not establish an exact population effect. Do not
pool fetches, scripts or visibility variants as independent samples. This design
has no model stochasticity, hosted-model cost or deployed-server latency data.

Further work needs richer response-matched decoys, varying world/task families,
maze branching/consistency ablations, independently reviewed task validity,
source-informed model policies, and separate server-resource/load measurements.
A model adapter can reuse the tool interface, but a tiny local-model smoke run
would establish integration only, not general efficacy or a model-family study.
