import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from benchmarks.provenance import provenance


class ProvenanceTests(unittest.TestCase):
    def source_tree(self, root):
        (root / 'benchmarks').mkdir()
        (root / 'benchmarks' / 'example.py').write_text('value = 1\n')
        return root / 'benchmarks' / 'example.py'

    def test_archive_has_hashes_without_inventing_git_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source_tree(root)
            info = provenance(root)
            self.assertEqual('source_archive', info['source_kind'])
            self.assertIsNone(info['commit'])
            self.assertIsNone(info['dirty'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), info['source_sha256']['benchmarks/example.py'])

    def test_git_identity_and_dirty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.source_tree(root)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            subprocess.run(['git', '-c', 'user.name=OpenMaze fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], cwd=root, check=True)
            clean = provenance(root)
            self.assertEqual('git_checkout', clean['source_kind'])
            self.assertRegex(clean['commit'], '^[0-9a-f]{40}$')
            self.assertFalse(clean['dirty'])
            source.write_text('value = 2\n')
            self.assertTrue(provenance(root)['dirty'])
            archive = root / 'extracted'
            archive.mkdir()
            self.source_tree(archive)
            self.assertEqual('source_archive', provenance(archive)['source_kind'])

    def test_git_executable_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source_tree(root)
            with patch('benchmarks.provenance.subprocess.check_output', side_effect=FileNotFoundError):
                info = provenance(root)
            self.assertEqual('source_archive', info['source_kind'])
            self.assertIsNone(info['commit'])
            self.assertTrue(info['source_sha256'])
