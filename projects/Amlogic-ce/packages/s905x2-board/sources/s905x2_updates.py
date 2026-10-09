# SPDX-License-Identifier: GPL-2.0-or-later
"""Dedicated S905X2 release feed; used by the existing CoreELEC updater."""
import datetime
import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request

FEED_URL = 'https://github.com/Jioyzen/CoreELEC/releases/latest/download/update.json'
RELEASE_BASE = 'https://github.com/Jioyzen/CoreELEC/releases/download/'
BOARD_ID = 'g12a_s905x2_u212_2g_rtl8822cs'
ARCHITECTURE = 'Amlogic-no.aarch64'
CHANNEL = 'S905X2-22'
MARKER = '/usr/share/s905x2/manifest.json'


def validate_feed(data, architecture=ARCHITECTURE):
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    if (data['schema'] != 1 or data['board_id'] != BOARD_ID or
            data['architecture'] != architecture or architecture != ARCHITECTURE):
        raise ValueError('Incompatible S905X2 update feed')
    if not re.fullmatch(r'22\.0-Piers_(?:devel|nightly)_\d{14}', data['version']):
        raise ValueError('Invalid CoreELEC 22 build version')
    if not re.fullmatch(r'[0-9a-f]{40}', data['build_id']):
        raise ValueError('Invalid source commit')
    artifact = data['artifact']
    name = artifact['name']
    expected = ('CoreELEC-' + ARCHITECTURE + '-' + data['version'] +
                '-S905X2-U212-2G-RTL8822CS.tar')
    if name != expected:
        raise ValueError('Unexpected upgrade package name')
    url = artifact['url']
    parts = urllib.parse.urlsplit(url)
    prefix = '/Jioyzen/CoreELEC/releases/download/'
    if (parts.scheme != 'https' or parts.netloc != 'github.com' or
            parts.query or parts.fragment or not parts.path.startswith(prefix)):
        raise ValueError('Unexpected upgrade download location')
    suffix = parts.path[len(prefix):].split('/')
    if len(suffix) != 2 or not re.fullmatch(r'[A-Za-z0-9._-]+', suffix[0]) or suffix[1] != name:
        raise ValueError('Invalid release path')
    if not re.fullmatch(r'[0-9a-f]{64}', artifact['sha256']):
        raise ValueError('Invalid upgrade SHA256')
    if type(artifact['size']) is not int or not 0 < artifact['size'] < 2 * 1024**3:
        raise ValueError('Invalid upgrade size')
    return data


def fetch_feed(architecture=ARCHITECTURE):
    request = urllib.request.Request(FEED_URL, headers={'User-Agent': 'CoreELEC-S905X2-Updater'})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError('Update feed too large')
    return validate_feed(payload, architecture)


def read_os_release(path='/etc/os-release'):
    result = {}
    for line in pathlib.Path(path).read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            result[key] = value.strip('"')
    return result


def build_time(version):
    match = re.search(r'_(\d{14}|\d{8})$', version)
    if not match:
        raise ValueError('Unknown local build version')
    value = match[1]
    return datetime.datetime.strptime(value, '%Y%m%d%H%M%S' if len(value) == 14 else '%Y%m%d')


def is_newer(feed, local):
    if feed['build_id'] == local.get('BUILD_ID') or feed['version'] == local['VERSION']:
        return False
    return build_time(feed['version']) > build_time(local['VERSION'])


def automatic_response(feed, local):
    data = {}
    if is_newer(feed, local):
        parts = urllib.parse.urlsplit(feed['artifact']['url'])
        folder, name = parts.path.lstrip('/').rsplit('/', 1)
        data = {'host': parts.netloc, 'folder': folder, 'update': name}
    return json.dumps({'data': data})


def manual_response(feed):
    url = feed['artifact']['url']
    base, name = url.rsplit('/', 1)
    return {CHANNEL: {
        'url': base + '/',
        'prettyname_regex': r'CoreELEC-Amlogic-no\.aarch64-(.*)-S905X2-U212-2G-RTL8822CS\.tar',
        'project': {ARCHITECTURE: {'releases': {'1': {'file': {'name': name}}}}},
    }}


def verify_download(path, feed, url):
    if url != feed['artifact']['url']:
        raise ValueError('Download does not match selected update')
    artifact = feed['artifact']
    path = pathlib.Path(path)
    if path.stat().st_size != artifact['size']:
        raise ValueError('Incomplete upgrade download')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != artifact['sha256']:
        raise ValueError('Upgrade SHA256 mismatch')
