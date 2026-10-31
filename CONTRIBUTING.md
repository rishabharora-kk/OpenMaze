# Contributing

Use Python 3.11+ and install with `python -m pip install -e .`. Run
`python -m unittest discover -s tests -v` and `python -m benchmarks.scripted`.
Use synthetic fixtures only. Never commit `.openmaze/`, credentials, private keys,
real service data or logs from other systems.

Open a focused PR explaining the boundary or experiment changed, validation,
and remaining limitations. Changes to policy, parsing, signatures, isolation or
execution behavior require regression tests and should receive two independent
maintainer reviews before merge. Other changes need one review. Do not merge
unreviewed AI-generated security changes.

No arbitrary code execution, reverse shells, attacker-infrastructure access,
external callbacks, public-target testing or live paid-model calls in CI. Propose
larger experiment scope first. Cite original sources for effectiveness claims;
publish negative results. Read SECURITY.md for private disclosures.

Contributions are licensed under Apache-2.0. Preserve third-party notices and
do not import research datasets without verifying their reuse permissions.
