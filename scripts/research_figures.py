"""Regenerate descriptive research figures from raw measured artifacts."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

POLICIES = ('breadth_first', 'progress_guard', 'branch_quota', 'disclosed_routes')
LABELS = ('Breadth first', 'Schema progress guard', 'Branch quota', 'Disclosed route filter')
ARMS = ('deny', 'static', 'maze')


def generate(adaptive_path, load_path, output, matched_path=None):
    adaptive_path, load_path, output = Path(adaptive_path), Path(load_path), Path(output)
    adaptive, load = json.loads(adaptive_path.read_text()), json.loads(load_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'savefig.facecolor': 'white'})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), layout='constrained')
    image = None
    for axis, visibility in zip(axes, ('clear', 'opaque')):
        rows = {(s['policy'], s['arm']): s for s in adaptive['summary']
                if s['depth'] == 4 and s['budget'] == 40 and s['visibility'] == visibility}
        values = np.array([[rows[policy, arm]['success_rate'] for arm in ARMS] for policy in POLICIES])
        image = axis.imshow(values, vmin=0, vmax=1, cmap='Blues', aspect='auto')
        axis.set_xticks(range(3), ('Deny', 'Static', 'Maze'))
        axis.set_yticks(range(4), LABELS)
        axis.set_title('Visible route families' if visibility == 'clear' else 'Opaque route aliases')
        for y, policy in enumerate(POLICIES):
            for x, arm in enumerate(ARMS):
                entry = rows[policy, arm]
                completed = round(entry['success_rate'] * entry['n'])
                axis.text(x, y, f'{completed}/{entry["n"]}', ha='center', va='center',
                          color='white' if values[y, x] > .65 else '#172737')
    fig.colorbar(image, ax=axes, label='Synthetic task completion fraction', shrink=.8)
    fig.suptitle('Scripted controls: progress-based adaptation defeats this maze\nDepth 4 · fetch budget 40 · no LLM efficacy inference', fontsize=12)
    for suffix in ('png', 'svg'):
        fig.savefig(output / f'adaptive-completion.{suffix}', dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    blocks = sorted({r['block'] for r in load['runs']})
    runs = {(r['block'], r['mode']): r for r in load['runs']}
    for block in blocks:
        latencies = [runs[block, mode]['legitimate']['http_latency_ms']['p95'] for mode in ('deny', 'maze')]
        axes[0].plot([0, 1], latencies, marker='o', linewidth=1.6, label=f'Block {block}')
    axes[0].set_xticks([0, 1], ['Deny', 'Maze'])
    axes[0].set_ylabel('Legitimate completed-response p95 (ms)')
    axes[0].set_title('Paired deployments; inspect errors and drops too')
    axes[0].legend(frameon=False)
    positions = np.arange(len(blocks) * 2)
    bottoms = np.zeros(len(positions))
    for role, color in (('gateway', '#305f88'), ('decoy', '#d08738'), ('protected', '#73a09a')):
        values = []
        for block in blocks:
            for mode in ('deny', 'maze'):
                resources = runs[block, mode]['server_resources'][role]
                values.append(np.nan if resources is None else resources['cpu_seconds'])
        axes[1].bar(positions, values, bottom=bottoms, color=color, label=role)
        bottoms += np.nan_to_num(values)
    axes[1].set_xticks(positions, [f'{mode[0].upper()}{block}' for block in blocks for mode in ('deny', 'maze')])
    axes[1].set_ylabel('Server user + system CPU (s)')
    axes[1].set_title('D = deny, M = maze; per-role /proc deltas')
    axes[1].legend(frameon=False)
    fig.suptitle('Short shared-host HTTP pilot · not an availability or economic bound', fontsize=12)
    for suffix in ('png', 'svg'):
        fig.savefig(output / f'load-pilot.{suffix}', dpi=180)
    plt.close(fig)
    matched = None
    if matched_path is not None:
        matched_path = Path(matched_path)
        matched = json.loads(matched_path.read_text())
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
        presentations = ('original', 'matched_schema', 'matched_schema_and_degree')
        labels = ('Original', 'Matched schema', 'Schema + degree')
        for axis, budget in zip(axes, (40, 64)):
            rows = {(r['presentation'], r['policy']): r for r in matched['summary']
                    if r['arm'] == 'maze' and r['budget'] == budget and r['visibility'] == 'opaque'}
            for offset, policy, label, color in ((-.18, 'breadth_first', 'Breadth first', '#93b8ce'),
                                                  (.18, 'progress_guard', 'Progress guard', '#305f88')):
                values = [rows[presentation, policy]['success_rate'] for presentation in presentations]
                bars = axis.bar(np.arange(3) + offset, values, width=.34, label=label, color=color)
                for bar, presentation, value in zip(bars, presentations, values):
                    n = rows[presentation, policy]['n']
                    axis.text(bar.get_x() + bar.get_width() / 2, value + .025,
                              f'{round(value * n)}/{n}', ha='center', fontsize=8)
            axis.set_xticks(np.arange(3), labels, rotation=12)
            axis.set_ylim(0, 1.2)
            axis.set_yticks([0, .5, 1])
            axis.set_ylabel('Synthetic task completion fraction')
            axis.set_title(f'Fetch budget {budget}')
            axis.legend(frameon=False, loc='upper left', fontsize=8)
        fig.suptitle('Post-result scripted ablation: schema, topology and budget interact\nOpaque paths · depth 4 · no LLM efficacy inference', fontsize=12)
        for suffix in ('png', 'svg'):
            fig.savefig(output / f'matched-control.{suffix}', dpi=180)
        plt.close(fig)
    inputs = {}
    datasets = [(adaptive_path, adaptive), (load_path, load)]
    if matched is not None:
        datasets.append((matched_path, matched))
    for path, artifact in datasets:
        inputs[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'config': artifact['config'], 'provenance': artifact['provenance']}
    (output / 'data-manifest.json').write_text(json.dumps({
        'scope': 'descriptive figures from scripted controls and short HTTP measurement; no LLM efficacy inference',
        'inputs': inputs,
        'outputs': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*'))
                    if p.suffix in ('.png', '.svg')},
    }, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adaptive', type=Path, required=True)
    parser.add_argument('--load', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('paper/figures'))
    parser.add_argument('--matched', type=Path)
    args = parser.parse_args()
    generate(args.adaptive, args.load, args.output, args.matched)
