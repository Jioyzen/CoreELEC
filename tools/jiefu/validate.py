#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Validate the board contract in compiled DTBs and extracted SYSTEM images."""
import hashlib
import json
import pathlib
import subprocess

BOARD_ID = 'g12a_s905x2_u212_2g_jeff2021'
OEM_ID = 'g12a_s905x2_u212_2g_rtl8822cs'
FIRMWARE_SHA256 = '42db5218c54b0638e1bafdbc7d0986172288e55a9e1c879080d41206bb87dfa2'
BOOT_DEFAULTS = {
    'consoleopt': ('console=tty0 console=ttyS0,115200n8 no_console_suspend loglevel=0 '
                   'systemd.show_status=false vt.global_cursor_default=0 fbcon=nodefer'),
    'cec_func_config': '0',
    'vout': '1080p60hz',
    'kernel_hdmimode': '1080p60hz',
    'coreelec': 'quiet setfbres=1080',
}


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fdt(dtb, node, prop, kind='s'):
    return subprocess.check_output(
        ['fdtget', '-t', kind, str(dtb), node, prop], text=True).strip()


def validate_dtb(dtb):
    assert fdt(dtb, '/', 'coreelec-dt-id') == BOARD_ID
    assert fdt(dtb, '/', 'amlogic-dt-id') == OEM_ID
    assert fdt(dtb, '/reserved-memory/ramoops@0x07400000', 'reg', 'x') == '0 9400000 0 100000'
    assert fdt(dtb, '/reserved-memory/linux,meson-fb', 'reg', 'x') == '0 7f800000 0 800000'
    assert fdt(dtb, '/vpu', 'clk_level', 'u') == '8'
    assert fdt(dtb, '/aocec', 'status') == 'disabled'
    assert fdt(dtb, '/dwc2_a@ff400000', 'status') == 'disabled'
    assert fdt(dtb, '/dwc3@ff500000', 'status') == 'okay'
    assert fdt(dtb, '/sd2@ffe05000', 'max-frequency-sdio', 'u') == '167000000'
    assert fdt(dtb, '/vout_mux', 'status') == 'okay'
    assert fdt(dtb, '/vout_mux', 'compatible') == 'amlogic, vout_mux'
    clocks = fdt(dtb, '/ethernet@ff3f0000', 'clocks', 'x').split()
    assert len(clocks) == 6 and clocks[0] == clocks[2] == clocks[4]
    assert clocks[1::2] == ['26', '2', 'b1'], 'Ethernet gate must be CLKID_ETH'


def validate_boot_config(path):
    values = {}
    for line in pathlib.Path(path).read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key] = value.strip("'\"")
    for key, value in BOOT_DEFAULTS.items():
        assert values.get(key) == value, 'Wrong boot default: ' + key


def validate_system(system):
    system = pathlib.Path(system)
    manifest = json.loads((system / 'usr/share/jiefu/manifest.json').read_text())
    assert manifest['dt_id'] == BOARD_ID and manifest['dolby_vision'] is False
    assert json.loads((system / 'usr/share/s905x2/manifest.json').read_text()) == manifest
    assert not list(system.rglob('dovi.ko*')), 'DV module must not be packaged'
    assert not (system / 'usr/lib/coreelec/dovi-loader').exists(), 'DV fallback loader present'
    service = (system / 'usr/lib/systemd/system/opentee_linuxdriver.service').read_text()
    assert 'dovi-loader' not in service
    assert 'ExecStart=/usr/lib/coreelec/tee-loader start' in service
    assert 'ExecStop=/usr/lib/coreelec/tee-loader stop' in service
    assert (system / 'usr/lib/coreelec/tee-loader').is_file()
    assert len(list(system.rglob('88x2cs.ko'))) == 1
    firmware = list(system.glob('usr/lib/kernel-overlays/*/lib/firmware/rtlbt/rtl8822cs_fw'))
    assert len(firmware) == 1 and sha256(firmware[0]) == FIRMWARE_SHA256
    rules = system / 'usr/lib/udev/rules.d'
    nfs = (rules / '60-nfs.rules').read_text()
    assert '--pattern' not in nfs and nfs.count('systemd-sysctl --prefix=') == 5
    readahead = (rules / '99-nfs.rules').read_text()
    assert 'TEST="/usr/lib/nfsrahead"' in readahead
    assert 'PROGRAM="/usr/lib/nfsrahead %k"' in readahead
    boot = system / 'usr/share/bootloader'
    validate_boot_config(boot / 'config.ini')
    validate_dtb(boot / 'device_trees' / (BOARD_ID + '.dtb'))
    assert BOARD_ID in (boot / 'update.sh').read_text()
    assert BOARD_ID in (boot / 'canupdate.sh').read_text()
    updater = system / 'usr/share/kodi/addons/service.coreelec.settings/resources/lib/s905x2_updates.pyc'
    assert b'jiefu-channel/update.json' in updater.read_bytes()
    assert b'media-channel/update.json' not in updater.read_bytes()
    profile = json.loads((system / 'usr/share/jioyzen-media/profile.json').read_text())
    assert profile['board_id'] == BOARD_ID
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--dtb', type=pathlib.Path)
    selection.add_argument('--system', type=pathlib.Path)
    args = parser.parse_args()
    if args.dtb:
        validate_dtb(args.dtb)
    else:
        validate_system(args.system)
    print('Jiefu board validation passed')
