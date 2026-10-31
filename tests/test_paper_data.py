import contextlib
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_paper_data import audit


class PaperArchiveTests(unittest.TestCase):
    def fixture(self, directory):
        raw = json.dumps({'runs': [], 'provenance': {}, 'scope': 'model-development fixture'}).encode()
        compressed = gzip.compress(raw, mtime=0)
        name = 'model-development.json.gz'
        (directory / name).write_bytes(compressed)
        index = {'artifacts': [{'file': name, 'gzip_bytes': len(compressed), 'uncompressed_bytes': len(raw),
                               'gzip_sha256': hashlib.sha256(compressed).hexdigest(),
                               'raw_sha256': hashlib.sha256(raw).hexdigest(), 'provenance': {}, 'runs': 0}]}
        path = directory / 'index.json'
        path.write_text(json.dumps(index))
        return path, index

    def test_detects_changed_raw_hash_and_archive_paths(self):
        for mutation in ('raw_sha256', 'file'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                path, index = self.fixture(Path(directory))
                index['artifacts'][0][mutation] = '0' * 64 if mutation == 'raw_sha256' else '../model-development.json.gz'
                path.write_text(json.dumps(index))
                with self.assertRaises(ValueError):
                    audit(path)

    def test_archive_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, audit(path))
