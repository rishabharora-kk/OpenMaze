"""Source identity for Git checkouts and extracted source archives."""
import hashlib
import platform
import subprocess
from pathlib import Path


def provenance(root=None):
    root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    commit, dirty, source_kind = None, None, 'source_archive'
    try:
        top = subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'], cwd=root, text=True,
            stderr=subprocess.DEVNULL).strip()
        # An archive extracted inside another checkout must not inherit its identity.
        if Path(top).resolve() == root:
            commit = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=root, text=True,
                stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(
                ['git', 'status', '--porcelain'], cwd=root, stderr=subprocess.DEVNULL))
            source_kind = 'git_checkout'
    except (OSError, subprocess.CalledProcessError):
        pass
    return {
        'source_kind': source_kind, 'commit': commit, 'dirty': dirty,
        'python': platform.python_version(), 'platform': platform.platform(),
        'source_sha256': {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ('openmaze', 'benchmarks')
            for path in sorted((root / folder).rglob('*.py'))
        },
    }
