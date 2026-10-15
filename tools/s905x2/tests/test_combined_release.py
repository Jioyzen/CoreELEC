import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'combine_release.py'
spec = importlib.util.spec_from_file_location('combined_release', SOURCE)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class CombinedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = self.fixture('base')
        self.media = self.fixture('media')
        self.output = self.root / 'release'

    def fixture(self, edition):
        folder = self.root / edition
        folder.mkdir()
        version = '22.0-Piers_devel_2026101516000' + ('1' if edition == 'base' else '2')
        revision = ('a' if edition == 'base' else 'b') * 40
        stem = 'CoreELEC-Amlogic-no.aarch64-' + version + ('-MEDIA' if edition == 'media' else '') + '-S905X2-U212-2G-RTL8822CS'
        artifacts = {}
        for suffix in ('.img.gz', '.tar'):
            path = folder / (stem + suffix)
            path.write_bytes((edition + suffix).encode())
            artifacts[path.name] = release.digest(path)
        package = folder / (stem + '.tar')
        manifest = dict(source_commit=revision, version=version, release_tag='20261015-0800-s905x2-'+revision[:8],
                        dt_id='g12a_s905x2_u212_2g_rtl8822cs', artifacts=artifacts,
                        linux_commit='c'*40, common_drivers_commit='d'*40,
                        media_modules_commit='e'*40, kodi_commit='f'*40)
        feed = dict(schema=1, version=version, build_id=revision,
                    board_id=manifest['dt_id'], architecture='Amlogic-no.aarch64',
                    artifact=dict(name=package.name, size=package.stat().st_size,
                                  sha256=release.digest(package), url=release.DOWNLOAD+'old/'+package.name))
        validation = dict(flash_image_system_matches_update=True)
        if edition == 'media':
            manifest.update(edition='media', profile={'profile_id': 'profile-test'})
            feed.update(edition='media')
            validation.update(embedded_installer='passed', wifi_wizard='embedded and enabled',
                              wifi_first_start_only=True, profile_id='profile-test')
            release.write_json(folder/'offline-validation.json', {'offline':'passed'})
        else:
            validation.update(edition='base', media_payload_absent=True)
        release.write_json(folder/'offline-image-validation.json', validation)
        release.write_json(folder/'build-manifest.json', manifest)
        release.write_json(folder/'update.json', feed)
        return folder

    def combine(self):
        return release.combine(self.base, self.media, self.output)

    def test_both_editions_and_distinct_feeds_share_one_immutable_release(self):
        manifest = self.combine()
        self.assertEqual(len(list(self.output.glob('*.img.gz'))), 2)
        self.assertEqual(len(list(self.output.glob('*.tar'))), 2)
        self.assertEqual(set(manifest['editions']), {'base','media'})
        for edition, name in [('base','update.json'), ('media','media-update.json')]:
            feed = release.read_json(self.output/name)
            self.assertEqual(feed['edition'], edition)
            self.assertEqual(feed['artifact']['url'], release.DOWNLOAD+manifest['release_tag']+'/'+feed['artifact']['name'])
        self.assertEqual(release.verify(self.output), manifest)

    def test_source_corruption_prevents_assembly(self):
        next(self.media.glob('*.tar')).write_bytes(b'corrupt')
        with self.assertRaises(ValueError): self.combine()
        self.assertFalse(self.output.exists())

    def test_source_edition_swap_is_rejected(self):
        with self.assertRaises(ValueError): release.combine(self.media, self.base, self.output)

    def test_core_version_mismatch_prevents_combined_release(self):
        data = release.read_json(self.media/'build-manifest.json')
        data['linux_commit']='0'*40
        release.write_json(self.media/'build-manifest.json', data)
        with self.assertRaisesRegex(ValueError, 'Core source mismatch'): self.combine()

    def test_unverified_first_start_policy_cannot_publish(self):
        data = release.read_json(self.media/'offline-image-validation.json')
        data.pop('wifi_first_start_only')
        release.write_json(self.media/'offline-image-validation.json', data)
        with self.assertRaises(ValueError): self.combine()

    def test_unverified_base_isolation_cannot_publish(self):
        release.write_json(self.base/'offline-image-validation.json', {'flash_image_system_matches_update': True})
        with self.assertRaises(ValueError): self.combine()

    def test_stale_output_and_extra_assets_are_rejected(self):
        self.combine()
        with self.assertRaises(ValueError): self.combine()
        (self.output/'unexpected.json').write_text('{}')
        with self.assertRaises(ValueError): release.verify(self.output)

    def test_feed_tampering_is_detected_before_upload(self):
        self.combine()
        (self.output/'media-update.json').write_text('{}')
        with patch.object(release.subprocess, 'run') as run:
            with self.assertRaises(ValueError): release.publish(self.output)
            run.assert_not_called()

    def uploaded(self):
        return [{'name': p.name, 'state':'uploaded', 'size': p.stat().st_size,
                 'digest':'sha256:'+release.digest(p)} for p in self.output.iterdir()]

    def test_bad_github_upload_stays_draft_and_does_not_advance_any_feed(self):
        self.combine()
        assets = self.uploaded()
        assets[0]['digest']='sha256:'+'0'*64
        with patch.object(release.subprocess, 'run') as run, \
             patch.object(release.subprocess, 'check_output', return_value=json.dumps({'assets':assets})):
            with self.assertRaises(ValueError): release.publish(self.output)
            self.assertEqual(run.call_count, 1)
            self.assertIn('--draft', run.call_args.args[0])

    def test_success_publishes_then_advances_media_feed_using_legacy_filename(self):
        manifest = self.combine()
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1:3] == ['release','upload']:
                path = Path(command[4])
                self.assertEqual(path.name, 'update.json')
                feed=release.read_json(path)
                self.assertEqual(feed['edition'], 'media')
                self.assertIn('/'+manifest['release_tag']+'/',feed['artifact']['url'])
        with patch.object(release.subprocess, 'run', side_effect=run), \
             patch.object(release.subprocess, 'check_output', return_value=json.dumps({'assets':self.uploaded()})):
            release.publish(self.output)
        self.assertEqual([c[2] for c in calls], ['create','edit','upload'])
        self.assertIn('--latest', calls[1])


if __name__=='__main__': unittest.main()
