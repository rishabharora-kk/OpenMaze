# Evaluation protocol

Keep enforcement tests independent from deception experiments. A crawler following
links is not evidence that a malicious agent was contained or diverted from a real
objective. A remote agent can stop, restart or parallelize.

## Implemented checks

`python -m unittest discover -s tests -v` runs unit, transport and process checks.
`python -m benchmarks.scripted` compares deny-only and bounded-maze behavior for a
fixed scripted crawler in process. Its request counts, wall time and protected
operation counts characterize the harness only. No API credits or external targets
are used. It is deliberately not a performance/SLO or AI-robustness claim.

## Next controlled experiment

Arms: A deny-only, B static decoy (not yet implemented), C consistent bounded maze.
Keep protected data, policy, target objectives and agent budget identical. Evaluate
receipt behavior separately. Include informed and uninformed agents, short-timeout
callers, parallel workers, new sessions and valid limited credentials.

Record model/version, prompt, tools, harness commit, random seed, run budget,
request trace, token use, latency, objective success, telemetry utility and defender
CPU/memory/bytes. Record abandonments and timeouts distinctly. A model naming a
trap is not the same as avoiding it; entering a trap is not the same as missing a
real vulnerability.

Use randomized arm order and held-out worlds. Start with 30 independent trials
per scenario/arm, then use a power analysis for a prespecified meaningful effect.
Requests within one run are not independent trials. Report confidence intervals
and negative results. Source-aware agents must be included, since this is open source.

Release blockers: any unauthorized protected operation, cross-tenant result,
accepted modified/replayed receipt, unbounded resource growth, or verified decoy
access to real secrets/backend. Future targets (unmeasured): under sustained
decoy load, legitimate error increase below 0.1 percentage point and p95 latency
increase below 10% relative to the same deny-only deployment.

Proceed beyond the lab only if the maze improves detection decisions or reduces
attacker objective progress at acceptable defender cost. Remove it if it merely
creates more activity. No AI-agent efficacy measurement has been performed.
