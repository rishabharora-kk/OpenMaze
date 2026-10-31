# Roadmap and starter issues

- [x] Local three-service prototype; default denial; explicit per-tenant policy.
- [x] Independent backend authorization and signed-response client.
- [x] Consistent bounded decoy and negative security tests.
- [x] Scripted deny/maze comparison and CI definition.
- [x] Validate Docker build, effective runtime settings and basic decoy mount/egress boundaries.
- [x] Run Unix-socket lifecycle and reachability checks on a Docker-capable Linux runner.
- [ ] Replace experimental envelope with a reviewed RFC 9421 profile/library.
- [x] Benchmark-only static decoy, scripted source-aware controls, paired trials and task oracle.
- [x] CI package/container/research gates and tag-driven draft release workflow.
- [x] Observation-only adaptive controls and opt-in pinned local-model smoke adapter.
- [x] Response-matched schema/degree follow-up and independent aggregate validation.
- [x] HTTP legitimate-client/per-role resource instrumentation and paper/PDF CI.
- [ ] Expose static baseline over HTTP and evaluate capable agents on realistic held-out task families.
- [ ] Measure sustained-load behavior and legitimate-client impact.
- [ ] Independent security review before any external deployment.

Suggested first contributions:

1. Container boundary tests: demonstrate decoy cannot access credentials, signing
   key, protected socket, external network or Docker daemon.
2. Parser tests: differential HTTP framing cases against a mature front proxy;
   preserve the prototype's exact-target policy and body rejection.
3. Receipt vectors: independently generated positive/negative fixtures and
   tests for clock skew, unknown keys and restart behavior.
4. Static baseline: same response sizes, synthetic content and global admission;
   isolate the effect of navigable links.
5. Agent evaluation: owned local target only; pin model/harness/prompt; include
   parallel and deception-aware agents; publish failures and cost accounting.
6. Availability: compare deny and maze under rotating-session saturation; track
   memory, threads, logs and valid-request latency without claiming universal DoS safety.

Each security contribution needs a reproducible failing case, explicit invariant,
regression test and documented limits. These are proposed issues, not automatically
created GitHub issues. No production readiness date is promised.
