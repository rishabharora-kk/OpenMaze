# CI and release delivery

Every branch push and pull request runs `.github/workflows/tests.yml`:

| Job | Gate |
| --- | --- |
| Security and protocol | Full unit/process suite on Python 3.11, 3.12 and 3.13 |
| Research artifact checks | Two 270-run scripted experiments; paired blocks, budgets, bytes, oracle control and zero protected operations |
| Build and install distribution | Wheel/sdist build, metadata validation, clean-venv wheel installation outside checkout |
| Container boundaries and lifecycle | Build; deny/maze Compose runs; verified client; tenant rejection; effective quotas/mounts/network; decoy egress; upstream failure; socket cleanup |

Research traces and the Python package inventory are retained as Actions artifacts
for 30 days. Distribution artifacts include SHA256SUMS. CI checks bookkeeping and
controls rather than requiring a maze effect: a future negative research result
must not be treated as a software regression. Scripted controls are not model
trials. Keep permanent publication artifacts in a versioned archive with a DOI;
Actions retention is not archival storage.

Actions use full commit pins; Dependabot proposes weekly action and Python
dependency updates. Jobs have read-only repository permission and timeouts.
Only the final release job requests contents write permission. Pull-request jobs
do not receive provider secrets and do not call paid models.

## Delivery

Pushing a `v*` tag runs the complete CI workflow again at that tag. After all jobs
pass, the delivery job requires the tag to equal `v` plus `project.version`,
downloads the already-tested distributions, checks their hashes, and creates a
**draft GitHub Release** containing distributions and research JSON artifacts.
It does not rebuild those assets or deploy a public service. A mismatched tag or
existing release causes failure. On partial release-upload failure, inspect the
draft and its assets before retrying; the workflow does not overwrite releases.

For a release, update the package version, merge reviewed changes, create and
push a matching version tag, inspect the resulting draft and publish it when
ready. No tag or release was created as part of introducing this workflow.
No PyPI, cloud hosting or registry credential is required for this delivery path.

Configure branch rules to require these checks before merging if that policy is
wanted; adding a workflow file does not itself enforce branch protection.

## Local reproduction

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m benchmarks.pilot --output artifacts/pilot.json
python -m benchmarks.objective --output artifacts/objective.json
python scripts/check_artifacts.py artifacts/pilot.json artifacts/objective.json
python -m pip install build==1.6.1 twine==7.0.0
python -m build
python -m twine check dist/*
docker build -t openmaze:ci .
python scripts/container_checks.py --image openmaze:ci
```

Use new output paths for subsequent experiments. Container checks create fresh
state in a temporary project directory and remove their stack/state afterward.
They require a local Docker daemon with bind-mount access to that directory and
a non-root user. Never point the checks at existing state or a remote daemon.
Ports are selected dynamically. The Compose demo port can be selected with
`OPENMAZE_PORT`; `OPENMAZE_IMAGE` selects the image.

In a managed environment with a TLS inspection proxy, keep inherited proxy
settings and build with the public CA bundle as a BuildKit secret:

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t openmaze:ci .
```

The optional CA is mounted only for the dependency installation step. It is not
copied into the image. Application code is made readable for the non-root runtime;
state credentials retain owner-only permissions. The Python base image is pinned
by digest; review and refresh it deliberately along with dependency updates.

References: [reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
and [draft release CLI](https://cli.github.com/manual/gh_release_create).
