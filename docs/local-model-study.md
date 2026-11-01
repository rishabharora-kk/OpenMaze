# Optional local-model infrastructure smoke

Status: optional adapter and small-model plumbing/capability check. This is not a
representative adaptive-attacker study or evidence that OpenMaze protects systems.
Default CI uses fake-completion tests and never downloads weights or calls an API.

## Boundary and protocol

`benchmarks.local_model` runs an offline llama.cpp server bound only to loopback.
The policy receives a fixed task prompt and serialized observations from
`adaptive.ObservationTool`; it never receives the world object, seed or oracle
answer. The runner bootstraps the same entry page in all arms. Subsequent fetch,
submit or finish actions come from model JSON. Only previously exposed paths can
be fetched, fetches are bounded, and the first submission terminates the run.
One submission is allowed after the final fetch. Unexposed paths, invalid actions,
incorrect submissions, abandonments and infrastructure errors remain failures.

Observations are compacted to links, record and error fields: random inventory
IDs/descriptions are excluded. The model also receives visited and currently
unvisited exposed paths. This transformation and constrained JSON output assist
the small models and must not be confused with an unrestricted agent interface.
Opaque route aliases remove the straightforward route-prefix clue. They do not
hide all response-shape clues or make the synthetic world realistic.

Each inference request contains only its current run's observations and a fixed
system prompt; no previous run's conversation is carried forward. Prompt caching
is disabled in the request. The same local server process is reused across arms
for loading efficiency. Temperature is zero; seeds, arm order, token cap, runtime
version/binary hash and model revision/weight hash are recorded. CPU inference
latency includes HTTP, prompt processing and generation; it is not defender cost.
Server timing fields are retained when supplied by llama.cpp.

The output artifact retains complete **synthetic** model messages, completions,
actions and token counts, plus route-class traces and source provenance. These
inputs contain no credentials or protected records. Do not repurpose that trace
policy for real/private endpoints without a separate data-retention design.
The source code records the full prompt and per-tool JSON schema.

## Pinned models/runtime

| Model | Revision | Format/bytes |
| --- | --- | --- |
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) | `9217f5db79a29953eb74d5343926648285ec7e67` | Q4_K_M / 491400032 |
| [SmolLM2-360M-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct-GGUF) | `593b5a2e04c8f3e4ee880263f93e0bd2901ad47f` | Q8_0 / 386404992 |

The upstream Hugging Face metadata reports Apache-2.0 for both pinned repositories.
The models differ in size and quantization; their comparison cannot isolate model
family. Both are tiny capacity baselines, not substitutes for capable agent models.
The file names and SHA256 values are pinned in `MODELS`. Model licenses/cards are
provided by the linked upstream repositories; this repository does not redistribute
weights.

Runtime: [llama.cpp b12023](https://github.com/ggml-org/llama.cpp/releases/tag/b12023),
CPU Linux x64 prebuilt archive `llama-b12023-bin-ubuntu-x64.tar.gz`, SHA256
`ae1311cdc0f67bd78e01e7b20bc5ed403814a621c290dd0ee29b8c67c0feece0`.
The executed binary reported build 12023 / commit `f3586e66b`; actual executable
SHA256 and reported version are retained in each artifact. Setup used two CPU
threads with context 4096 and max 192 completion tokens. No paid API was used.

## Reproduce

Use the named upstream release/model revision URLs and verify hashes before
execution. The CLI rejects model files that do not match the pinned size/hash.
Keep binary and model files outside the checkout. Example after downloading:

```bash
python -m unittest discover -s tests -p test_local_model.py -v
python -m benchmarks.local_model \
  --server-bin /tmp/openmaze-model-runtime/llama-b12023/llama-server \
  --model-id qwen2.5-0.5b \
  --model-file /tmp/openmaze-model-runtime/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --trials 2 --output artifacts/local-qwen-evaluation.json
```

For the other model use `--model-id smollm2-360m` and its pinned GGUF file. Existing
output files are never overwritten. Default evaluation seeds start at 90000;
`--split development` uses 70000. Development worlds and tiny evaluation seeds
are disjoint locations/order from one generator, not held-out world families.

## Development failures are retained

Protocol v1 included a literal placeholder submission example. Both models copied
that placeholder and submitted before exploring. Those runs do not show model
incapacity or a defense effect; they expose a prompt defect. Protocol v2 removed
the answer example, but its generic schema permitted cross-tool argument types;
Qwen emitted a finish action with string `"null"` and failed action validation.
The inspected v1/v2 artifacts are development evidence, including those initially
created with an evaluation filename. They must not be presented as held-out results.

Protocol v3 fixes the schema to tool-specific branches: fetch argument string,
finish argument null, submit argument record object. The prompt is unchanged from
v2. It does not force fetches, choose routes, supply an answer or replace model
actions with a script. Final v3 smoke uses fresh seeds starting at 90000. No further
prompt tuning is permitted against those inspected smoke outcomes.

## Interpretation limits

If either model cannot complete the denial/static task or exits before reaching a
treatment-specific response, the experiment has a capability floor and identifies
no deception effect. Report this failure rather than turning equal zeros into
an efficacy claim. With two worlds/model/arm, any completion difference would
remain exploratory and far too small for generalization, significance or power
claims. A proper study still needs capable pinned models, realistic owned tasks,
full-source-informed conditions, held-out world families and a frozen analysis.

Official API reference consulted:
[llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
including schema-constrained responses, loopback host and CPU/token/context options.


## Frozen v3 smoke observations

Two disjoint evaluation world seeds (90000, 90001), three treatments and two model
checkpoints produced 12 runs. Each run had 12 fetches available at catalog depth
two. No run completed the objective; in particular, denial success was 0/2 for
**each** model. This is a capability floor, so treatment effects are unidentified.

| Model | Runs | Outcome | Model calls | Prompt/completion tokens | Summed inference request wall time |
| --- | ---: | --- | ---: | ---: | ---: |
| Qwen2.5-0.5B Q4_K_M | 6 | All abandoned after entry, before treatment exposure | 6 | 1866 / 60 | 9.50 s |
| SmolLM2-360M Q8_0 | 6 | Five invalid actions and one incorrect submission | 36 | 30235 / 1361 | 171.12 s |

The invalid Smol actions attempted to fetch literal relative `path`, rejected by
validation; these were not HTTP timeouts or resource exhaustion. All 42 model
calls reported finish reason `stop`, with no completion truncation. The source
boundary remained intact: zero protected operations across all 12 runs.
Smol made 2–11 fetches per run and sometimes entered the decoy candidate, but
engagement without baseline task capability cannot establish diversion.

Qwen's first server-reported timing was approximately 208 prompt tokens/s and
38.4 generated tokens/s on this runner. Timing includes a small-model CPU setup,
not production throughput or attacker/defender economics. The total times above
exclude model download/load, hashing and setup.

Full artifacts were written locally as
`/tmp/openmaze-qwen-smoke-v3-evaluation.json` and
`/tmp/openmaze-smollm-smoke-v3-evaluation.json` for integration into the research
archive. The preceding v1/v2 development files also remain available; their
misleading early `final`/`evaluation` filenames do not change their development
status. Preserve them as failed protocol development, not selected positive runs.

A later, separately recorded capacity control may use a larger public checkpoint
with the **same frozen v3 prompt/schema** and fresh seeds. It must first show
baseline task competence; if it exits before task progress under denial, stop
rather than spending on additional treatment arms or tuning against outcomes.


## Additional 1.5B capacity control: unarchived development observation

**Evidence status:** the trace below was inspected locally, but it was not copied
into the published data archive before the execution environment disconnected.
It cannot currently be independently audited from the repository and is excluded
from the manuscript's quantitative results. The numbers below are development
notes, not validated archived findings. Recover and verify the original trace or
collect a separately labeled rerun before using it as paper evidence.

After freezing v3, one additional public capacity checkpoint was tested with the
same prompt, tool schema, temperature, 12-fetch budget and depth-two task:
[Qwen2.5-1.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF),
revision `91cad51170dc346986eccefdc2dd33a9da36ead9`, Q4_K_M file
`qwen2.5-1.5b-instruct-q4_k_m.gguf`, 1117320736 bytes, SHA256
`6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`.
The upstream metadata reports Apache-2.0. This is another size of the Qwen family,
not a third independent model family.

A denial-only capability gate preceded any treatment trial, using fresh seed
100000. Qualification required oracle-verified submission. The run exhausted its
budget with 12 fetches and 12 model calls, no submission, and primary success
false. It used 9974 prompt tokens and 376 completion tokens; summed inference
request wall time was 119.05 seconds. All calls reported finish reason `stop`;
there were no HTTP timeouts, malformed actions or completion truncations.

An exploratory trace diagnostic is important: the policy visited nine unique
pages with three repeated fetches, including the actual non-null goal record.
It made 11 task fetches and one denial-candidate fetch, but continued fetching
instead of submitting the observed record. Thus it **did retrieve the target
information**; it failed the prespecified terminal-submission protocol. Do not
claim that this checkpoint was unable to navigate to the goal. Equally, do not
redefine primary completion or the qualification rule after inspecting the trace.

The gate did not qualify, so no static/maze arms, further model selection or prompt
tuning were performed. This single observation supports a diagnostic of agent
protocol adherence, not a model-capability ranking or a deception effect.
Artifact: `/tmp/openmaze-qwen15-capability-v3.json`, containing full synthetic
messages/actions and matching source hashes for archival integration.

The CLI now supports explicit treatment selection for such controls:

```bash
python -m benchmarks.local_model   --server-bin /tmp/openmaze-model-runtime/llama-b12023/llama-server   --model-id qwen2.5-1.5b   --model-file /tmp/openmaze-model-runtime/qwen2.5-1.5b-instruct-q4_k_m.gguf   --trials 1 --arms deny --seed 100000   --output artifacts/local-qwen15-capability.json
```

The selected arms are recorded in configuration. Duplicate arms are rejected,
and unit tests check denial-only selection and fresh observation histories. There
are now seven fake-completion unit tests; these remain independent of weights
and network access.
