"""Archive round-trip and refusal checks use synthetic bytes only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('release_archive_blob', Path(__file__).parents[1] / 'scripts' / 'release_archive_blob.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchiveBlobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = bytes(range(256)) * 200
        self.source = self.root / 'synthetic.bin'
        self.source.write_bytes(self.payload)
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.folder = self.root / 'assets'
        self.manifest = self.folder / f'blob-{self.sha}.json'

    def make(self):
        return MODULE.pack(self.source, self.folder, self.sha, part_bytes=127)

    def test_split_roundtrip_exact_bytes_and_source_untouched(self):
        metadata = self.make()
        self.assertGreater(len(metadata['parts']), 1)
        output = self.root / 'restored.bin'
        result = MODULE.restore(self.manifest, self.folder, output)
        self.assertEqual(result['status'], 'VERIFIED_RESTORED')
        self.assertEqual(output.read_bytes(), self.payload)
        self.assertEqual(self.source.read_bytes(), self.payload)

    def test_corrupt_part_refused_without_output(self):
        metadata = self.make()
        (self.folder / metadata['parts'][0]['name']).write_bytes(b'corrupt')
        output = self.root / 'restored.bin'
        with self.assertRaises(ValueError):
            MODULE.restore(self.manifest, self.folder, output)
        self.assertFalse(output.exists())

    def test_part_traversal_and_reordering_refused(self):
        metadata = self.make()
        metadata['parts'][0]['name'] = '../synthetic.bin'
        self.manifest.write_text(json.dumps(metadata), encoding='utf-8')
        with self.assertRaises(ValueError):
            MODULE.restore(self.manifest, self.folder, self.root / 'restored.bin')

    def test_existing_output_preserved(self):
        self.make()
        output = self.root / 'restored.bin'
        output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            MODULE.restore(self.manifest, self.folder, output)
        self.assertEqual(output.read_bytes(), b'keep')

    def test_wrong_source_sha_never_publishes_manifest(self):
        with self.assertRaises(ValueError):
            MODULE.pack(self.source, self.folder, '0' * 64)
        self.assertFalse((self.folder / ('blob-' + '0' * 64 + '.json')).exists())

    def test_wrong_expanded_size_refused(self):
        metadata = self.make()
        metadata['raw_bytes'] = 1
        self.manifest.write_text(json.dumps(metadata), encoding='utf-8')
        output = self.root / 'restored.bin'
        with self.assertRaises(ValueError):
            MODULE.restore(self.manifest, self.folder, output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
