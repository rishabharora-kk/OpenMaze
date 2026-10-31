# OpenMaze development paper and measured artifact

`main.md` is the manuscript source; `references.bib` contains inspected primary
sources. This is a research development draft, not a submitted or accepted paper.

Build the portable PDF and standalone HTML:

```bash
python -m pip install -e . -r requirements-paper.txt
python -m scripts.build_paper
```

Outputs are `artifacts/paper/openmaze-draft.pdf`, `openmaze-draft.html` and
`paper-manifest.json`. CI builds and retains the same draft. A version-tag
workflow includes those checked files in a draft GitHub Release.

`figures/` contains descriptive plots and a data/source hash manifest. Full raw
measured data are collected into compressed JSON under `data/`; their index
identifies source snapshots, raw/gzip hashes and scope. No real credentials,
keys or model weights are included. Local-model traces contain synthetic task
observations, outputs and actions; failed development protocols remain labeled.
A source hash is an identity check, not proof of experimental validity.

For archival runs collected from a clean committed snapshot, preserve the commit
before changing figures/tables. Decompress and independently validate the raw
JSON before regenerating figures; do not substitute a fresh run's latency values
into a historical manuscript without updating its table and provenance.

```bash
python -m scripts.check_extended_artifacts artifacts/adaptive.json artifacts/matched.json artifacts/load.json
python -m scripts.research_figures --adaptive artifacts/adaptive.json --matched artifacts/matched.json --load artifacts/load.json
python -m scripts.build_paper
```

The full scripted conditions reuse world seeds across arms/policies/conditions;
10,800 runs are not 10,800 independent worlds or intelligent agents. The small
HTTP pilot is not an SLO. Tiny-model capability failures identify no maze effect.
There is no automatic paper submission or public deployment. A stronger paper
still needs realistic task-family validation, capable pinned agents, a frozen
analysis and sustained deployment-cost measurements.
