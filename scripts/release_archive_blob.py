"""Pack one reviewed file into bounded Release assets; restore with full SHA checks.

This tool does not upload, delete originals, scan directories, or infer privacy.
Use only files explicitly cleared by the archive content review.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

BLOCK = 8 * 1024 * 1024


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(BLOCK), b''):
            digest.update(block)
    return digest.hexdigest()


class SplitWriter:
    def __init__(self, folder, prefix, limit):
        self.folder, self.prefix, self.limit = Path(folder), prefix, limit
        self.parts, self.stream = [], None
        self.total = 0
        self.digest = hashlib.sha256()

    def _close_part(self):
        if self.stream:
            self.stream.close()
            self.parts.append({'name': self.name, 'bytes': self.size,
                               'sha256': self.part_digest.hexdigest()})
            self.stream = None

    def write(self, data):
        length = len(data)
        while data:
            if self.stream is None:
                self.name = f'{self.prefix}.gz.part-{len(self.parts) + 1:03d}'
                self.stream = (self.folder / self.name).open('xb')
                self.size, self.part_digest = 0, hashlib.sha256()
            chunk, data = data[:self.limit - self.size], data[self.limit - self.size:]
            self.stream.write(chunk)
            self.part_digest.update(chunk)
            self.digest.update(chunk)
            self.size += len(chunk)
            self.total += len(chunk)
            if self.size == self.limit:
                self._close_part()
        return length

    def flush(self):
        if self.stream:
            self.stream.flush()


def pack(source, folder, expected_sha256, part_bytes=1536 * 1024 * 1024):
    source, folder = Path(source), Path(folder)
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('an explicitly reviewed SHA256 is required')
    if part_bytes <= 0 or part_bytes >= 2 * 1024 ** 3:
        raise ValueError('part size must be positive and below 2 GiB')
    before = source.stat()
    folder.mkdir(parents=True, exist_ok=True)
    writer = SplitWriter(folder, 'blob-' + expected_sha256, part_bytes)
    raw_digest = hashlib.sha256()
    try:
        with source.open('rb') as original, gzip.GzipFile(filename='', fileobj=writer,
                                                         mode='wb', compresslevel=1, mtime=0) as encoded:
            for block in iter(lambda: original.read(BLOCK), b''):
                raw_digest.update(block)
                encoded.write(block)
    finally:
        writer._close_part()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('source changed during packing; no manifest published')
    if raw_digest.hexdigest() != expected_sha256:
        raise ValueError('source SHA mismatch; no manifest published')
    manifest = {'schema': 1, 'codec': 'gzip', 'original_name': source.name,
                'raw_bytes': before.st_size, 'raw_sha256': expected_sha256,
                'compressed_bytes': writer.total, 'compressed_sha256': writer.digest.hexdigest(),
                'parts': writer.parts}
    target = folder / ('blob-' + expected_sha256 + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return manifest


def restore(manifest_path, asset_folder, output):
    manifest_path, asset_folder, output = Path(manifest_path), Path(asset_folder), Path(output)
    manifest = json.loads(manifest_path.read_text('utf-8'))
    if manifest.get('schema') != 1 or manifest.get('codec') != 'gzip' or not manifest.get('parts'):
        raise ValueError('unsupported or empty manifest')
    raw_sha = manifest['raw_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', raw_sha) or not isinstance(manifest['raw_bytes'], int) or manifest['raw_bytes'] < 0:
        raise ValueError('invalid original metadata')
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-restore-', dir=output.parent) as temporary:
        encoded = Path(temporary) / 'payload.gz'
        decoded = Path(temporary) / 'payload.raw'
        combined, compressed_size = hashlib.sha256(), 0
        with encoded.open('xb') as destination:
            for index, part in enumerate(manifest['parts'], 1):
                expected_name = f'blob-{raw_sha}.gz.part-{index:03d}'
                if part['name'] != expected_name:
                    raise ValueError('invalid part name or ordering')
                item = asset_folder / expected_name
                if item.is_symlink() or not item.is_file():
                    raise ValueError('missing or linked part')
                part_hash, part_size = hashlib.sha256(), 0
                with item.open('rb') as source:
                    for block in iter(lambda: source.read(BLOCK), b''):
                        part_hash.update(block)
                        combined.update(block)
                        part_size += len(block)
                        destination.write(block)
                if part_size != part['bytes'] or part_hash.hexdigest() != part['sha256']:
                    raise ValueError('part SHA/size mismatch')
                compressed_size += part_size
        if combined.hexdigest() != manifest['compressed_sha256'] or compressed_size != manifest['compressed_bytes']:
            raise ValueError('combined SHA/size mismatch')
        digest, size = hashlib.sha256(), 0
        with gzip.open(encoded, 'rb') as source, decoded.open('xb') as destination:
            for block in iter(lambda: source.read(BLOCK), b''):
                size += len(block)
                if size > manifest['raw_bytes']:
                    raise ValueError('expanded size exceeds manifest')
                digest.update(block)
                destination.write(block)
        if size != manifest['raw_bytes'] or digest.hexdigest() != raw_sha:
            raise ValueError('original SHA/size mismatch')
        # Atomic no-overwrite publication, including another process creating output.
        os.link(decoded, output)
    return {'status': 'VERIFIED_RESTORED', 'bytes': size, 'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('pack')
    create.add_argument('--source', required=True)
    create.add_argument('--folder', required=True)
    create.add_argument('--expected-sha256', required=True)
    recover = sub.add_parser('restore')
    recover.add_argument('--manifest', required=True)
    recover.add_argument('--assets', required=True)
    recover.add_argument('--output', required=True)
    args = parser.parse_args()
    value = pack(args.source, args.folder, args.expected_sha256) if args.command == 'pack' else restore(args.manifest, args.assets, args.output)
    print(json.dumps(value, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
