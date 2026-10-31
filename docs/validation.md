# Implementation validation — 1 November 2026

Environment: Linux, Python 3.12.14, cryptography 50.0.2.

- Editable package build/install succeeded with existing dependencies
  (`pip install --no-build-isolation --no-deps -e .`). A clean dependency download
  was not exercised in this runner.
- `python -m unittest discover -s tests -v`: 30 tests, 29 passed, one explicitly
  skipped because filesystem AF_UNIX sockets are prohibited by the runner.
- A real three-process loopback TCP demo was launched; uncredentialed synthetic
  responses, verified protected responses, cross-tenant denial, example client,
  and process shutdown were exercised.
- `python -m benchmarks.scripted`: denial stopped the scripted crawler at one
  401; the maze returned twenty 200 responses and then one 410. Both arms performed
  zero protected operations for the uncredentialed crawler. This is controlled
  scripted behavior, not evidence of AI engagement or attacker delay.
- Compose YAML parsed and role mount/network declarations were inspected.
- Python compilation and `git diff --check` passed.

Outstanding: Docker image build/runtime, effective container quotas, network
egress checks, Unix-socket lifecycle, independent cryptographic review, multi-model
agent trials, sustained-load measurements, and CI on other Python versions.

No deployment isolation or production availability claim follows from these tests.


## CI/research foundation validation — 1 November 2026

The earlier runner limitations above are historical. On the current Linux runner
(Python 3.12.14, cryptography 50.0.2, Docker 28.4.0, Compose 2.40.3):

- Clean dependency installation and editable package installation succeeded.
- The expanded unit/process suite passed, including filesystem Unix sockets.
- Both scripted research experiments completed 270 runs, with zero unauthorized
  protected operations and artifact accounting/control checks passing.
- actionlint 1.7.7 validated both workflow files locally.
- Wheel and source archive built and passed Twine metadata checks. A wheel was
  installed into a fresh venv and its CLI/help/state setup ran outside the checkout.
- Docker image built with TLS verification and a temporary BuildKit CA mount.
- The disposable Compose check passed in deny and maze modes: signed protected
  response, cross-tenant 403, effective CPU/memory/PID/read-only/capability settings,
  decoy bind-mount allowlist, absent sensitive paths, blocked direct outbound
  IPv4/IPv6 connections, upstream 503 behavior, restart readiness and socket cleanup.
- The first container execution caught unreadable source files copied from this
  runner. The Dockerfile now makes application code readable by the non-root
  runtime, without changing owner-only state permissions.

The test harness waits for protected responses after startup/restart; a listening
gateway or `docker compose start` alone is not protected-service readiness.
This validates graceful stop/start of ready services, not arbitrary interruption
at every startup instruction or forced-kill recovery. The service deliberately
refuses stale Unix sockets rather than silently replacing them.

Outstanding: independent cryptographic review, exhaustive hostile-container
checks, DNS/metadata-specific probes, sustained-load/legitimate-client costs,
real adaptive-agent trials and held-out world generalization. GitHub-hosted CI
and tag-triggered release execution must be distinguished from these local runs.
No version tag, public deployment or published release was created here.
