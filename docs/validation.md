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
