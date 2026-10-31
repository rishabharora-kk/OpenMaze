"""Verify compressed archival bytes and independently check supported statistics."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

from scripts.check_artifacts import finite_values, unique_pairs, validate as validate_initial
from scripts.check_extended_artifacts import validate as validate_extended

MAX_RAW_BYTES = 64 * 1024 * 1024


def audit(index_path):
    index_path = Path(index_path)
    index = json.loads(index_path.read_text(), object_pairs_hook=unique_pairs)
    names = set()
    for entry in index['artifacts']:
        name = entry['file']
        if Path(name).name != name or not name.endswith('.json.gz') or name in names:
            raise ValueError('invalid or duplicate archive filename')
        names.add(name)
        compressed = (index_path.parent / name).read_bytes()
        if len(compressed) != entry['gzip_bytes'] or hashlib.sha256(compressed).hexdigest() != entry['gzip_sha256']:
            raise ValueError('compressed artifact identity mismatch')
        if not 0 <= entry['uncompressed_bytes'] <= MAX_RAW_BYTES:
            raise ValueError('archived data exceeds bound')
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            raw = source.read(MAX_RAW_BYTES + 1)
        if len(raw) != entry['uncompressed_bytes'] or hashlib.sha256(raw).hexdigest() != entry['raw_sha256']:
            raise ValueError('raw artifact identity mismatch')
        artifact = json.loads(raw, object_pairs_hook=unique_pairs)
        finite_values(artifact)
        if artifact.get('provenance', {}) != entry['provenance'] or len(artifact.get('runs', [])) != entry['runs']:
            raise ValueError('archived identity/count differs from index')
        if name in {'adaptive.json.gz', 'matched.json.gz', 'load.json.gz'}:
            kind, count = validate_extended(artifact)
            print(f'{name}: {count} {kind} runs; byte identity and recorded statistics checked')
        elif name in {'pilot.json.gz', 'objective.json.gz'}:
            count = validate_initial(artifact)
            print(f'{name}: {count} runs; byte identity and recorded statistics checked')
        else:
            print(f'{name}: model-development/smoke trace integrity checked; no efficacy inference')
    return len(names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=Path('paper/data/index.json'))
    audit(parser.parse_args().index)
