"""Source identity for research artifacts, including dirty working trees."""
import hashlib
import platform
import subprocess
from pathlib import Path


def provenance():
    root = Path(__file__).resolve().parents[1]
    return {
        'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
        'python': platform.python_version(),
        'platform': platform.platform(),
        'source_sha256': {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ('openmaze', 'benchmarks')
            for path in sorted((root / folder).glob('*.py'))
        },
    }
