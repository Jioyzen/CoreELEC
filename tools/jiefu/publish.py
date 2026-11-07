#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Publish the verified Jiefu media image as an isolated prerelease."""
import argparse
import importlib.util
import json
import pathlib
import re
import subprocess

from validate import BOARD_ID, sha256

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPOSITORY = 'Jioyzen/CoreELEC'


def verify(output, expected_commit):
    output = pathlib.Path(output)
    sums = {}
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if (not re.fullmatch('[0-9a-f]{64}', digest) or name in sums or
                pathlib.Path(name).name != name):
            raise ValueError('Invalid checksum manifest')
        sums[name] = digest
    if set(sums) != {p.name for p in output.iterdir() if p.name != 'SHA256SUMS'}:
        raise ValueError('Missing or untracked release asset')
    for name, digest in sums.items():
        path = output / name
        if not path.is_file() or path.is_symlink() or sha256(path) != digest:
            raise ValueError('Release checksum mismatch: ' + name)

    manifest = json.loads((output / 'build-manifest.json').read_text())
    feed = json.loads((output / 'update.json').read_text())
    tag = manifest['release_tag']
    if (manifest['dt_id'] != BOARD_ID or manifest['edition'] != 'jiefu-media' or
            manifest['dolby_vision'] is not False or
            manifest['source_commit'] != expected_commit or
            not re.fullmatch('[0-9a-f]{40}', expected_commit) or
            not re.fullmatch('jiefu-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}', tag)):
        raise ValueError('Wrong Jiefu release identity or source commit')
    if (manifest['image_validation'] != 'passed' or
            manifest['media_offline_validation'] != 'passed'):
        raise ValueError('Compiled image validation missing')
    report = json.loads((output / 'offline-image-validation.json').read_text())
    if report['embedded_installer'] != 'passed' or not report['flash_image_system_matches_update']:
        raise ValueError('Embedded media image validation missing')

    spec = importlib.util.spec_from_file_location('jiefu_release_updates', ROOT /
        'projects/Amlogic-ce/packages/jiefu-board/sources/s905x2_updates.py')
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    updater.validate_feed(feed)
    artifact = feed['artifact']
    package = output / artifact['name']
    expected_url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{package.name}'
    images = list(output.glob('*.img.gz'))
    updates = list(output.glob('*.tar'))
    if (len(images) != 1 or len(updates) != 1 or updates[0] != package or
            images[0].name != package.name.removesuffix('.tar') + '.img.gz' or
            feed['build_id'] != expected_commit or feed['version'] != manifest['version'] or
            artifact['url'] != expected_url or artifact['sha256'] != sha256(package) or
            artifact['size'] != package.stat().st_size):
        raise ValueError('Feed does not match the validated artifacts')
    return manifest


def publish(output, expected_commit):
    output = pathlib.Path(output)
    manifest = verify(output, expected_commit)
    tag = manifest['release_tag']
    # Keep uploads private until all assets have reached GitHub successfully.
    subprocess.run(['gh', 'release', 'create', tag, '--repo', REPOSITORY,
                    '--target', expected_commit, '--draft', '--prerelease', '--latest=false',
                    '--title', 'CoreELEC 22 NO · Jiefu 媒体完整版 · ' +
                    manifest['version'].rsplit('_', 1)[-1][:8],
                    '--notes-file', str(output / 'RELEASE-NOTES.md'),
                    *map(str, sorted(output.iterdir()))], check=True)
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', REPOSITORY,
                    '--draft=false', '--prerelease', '--latest=false'], check=True)
    url = f'https://github.com/{REPOSITORY}/releases/tag/{tag}'
    print(url)
    return url


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    args = parser.parse_args()
    publish(args.output, args.expected_commit)
