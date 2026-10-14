import importlib.util
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[3]
source=ROOT/'projects/Amlogic-ce/packages/s905x2-board/sources/s905x2_updates.py'
spec=importlib.util.spec_from_file_location('media_updates',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def feed(edition):
    version='22.0-Piers_devel_20261015000000'
    name='CoreELEC-Amlogic-no.aarch64-'+version+('-MEDIA' if edition=='media' else '')+'-S905X2-U212-2G-RTL8822CS.tar'
    return {'schema':1,'edition':edition,'board_id':module.BOARD_ID,'architecture':module.ARCHITECTURE,
        'version':version,'build_id':'a'*40,'artifact':{'name':name,'url':module.RELEASE_BASE+'media-test/'+name,'size':100,'sha256':'b'*64}}


class ChannelTests(unittest.TestCase):
    def test_media_accepts_only_media_feed(self):
        with patch.object(module,'EDITION','media'):
            self.assertEqual(module.validate_feed(feed('media'))['edition'],'media')
            with self.assertRaises(ValueError):module.validate_feed(feed('base'))
    def test_base_accepts_only_base_and_legacy_base(self):
        with patch.object(module,'EDITION','base'):
            self.assertEqual(module.validate_feed(feed('base'))['edition'],'base')
            old=feed('base');old.pop('edition');module.validate_feed(old)
            with self.assertRaises(ValueError):module.validate_feed(feed('media'))


if __name__=='__main__':unittest.main()
