#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Publish a validated K-box media release without requiring a base image."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess

REPOSITORY = 'Jioyzen/CoreELEC'


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def verify(output):
    output = pathlib.Path(output)
    sums = {}
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        sha, name = line.split('  ', 1)
        if not re.fullmatch('[0-9a-f]{64}', sha) or pathlib.Path(name).name != name or name in sums:
            raise ValueError('Invalid checksum manifest')
        sums[name] = sha
    if set(sums) != {p.name for p in output.iterdir() if p.name != 'SHA256SUMS'}:
        raise ValueError('Missing or untracked release asset')
    for name, sha in sums.items():
        path = output / name
        if not path.is_file() or path.is_symlink() or digest(path) != sha:
            raise ValueError('Release checksum mismatch: ' + name)
    manifest = json.loads((output / 'build-manifest.json').read_text())
    feed = json.loads((output / 'update.json').read_text())
    tag = manifest['release_tag']
    if (manifest['edition'] != 'media' or feed['edition'] != 'media' or
            feed['board_id'] != 'g12a_s905x2_u212_2g_rtl8822cs' or
            feed['architecture'] != 'Amlogic-no.aarch64' or
            not re.fullmatch('media-[A-Za-z0-9._-]+', tag)):
        raise ValueError('Wrong media release identity')
    artifact = feed['artifact']
    if pathlib.Path(artifact['name']).name != artifact['name']:
        raise ValueError('Invalid artifact name')
    package = output / artifact['name']
    expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{package.name}'
    if (artifact['url'] != expected or artifact['sha256'] != digest(package) or
            artifact['size'] != package.stat().st_size or
            manifest['source_commit'] != feed['build_id']):
        raise ValueError('Feed does not match release')
    report = json.loads((output / 'offline-image-validation.json').read_text())
    if report['embedded_installer'] != 'passed':
        raise ValueError('Image offline validation missing')
    return manifest


def publish(output):
    output = pathlib.Path(output)
    manifest = verify(output)
    tag = manifest['release_tag']
    subprocess.run(['gh', 'release', 'create', tag, '--repo', REPOSITORY,
                    '--target', manifest['source_commit'], '--latest',
                    '--title', 'CoreELEC 22 S905X2-K Media ' + manifest['version'],
                    '--notes-file', str(output / 'RELEASE-NOTES.md'),
                    *map(str, sorted(output.iterdir()))], check=True)
    # The existing media client keeps its channel URL. The ordinary feed is frozen.
    subprocess.run(['gh', 'release', 'upload', 'media-channel', '--repo', REPOSITORY,
                    '--clobber', str(output / 'update.json')], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    publish(args.output)
