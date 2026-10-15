"""Execute the real workflow sync shell against private local Git repositories."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[3]


class WorkflowSyncTests(unittest.TestCase):
    def git(self, directory, *args, check=True):
        return subprocess.run(['git', '-C', str(directory), *args], text=True,
                              capture_output=True, check=check)

    def fixture(self, root, conflict):
        seed = root/'seed'
        seed.mkdir()
        self.git(seed, 'init', '-q')
        self.git(seed, 'config', 'user.name', 'Sync test')
        self.git(seed, 'config', 'user.email', 'test@example.invalid')
        (seed/'shared.txt').write_text('original\n')
        tools = seed/'tools/s905x2'
        tools.mkdir(parents=True)
        (tools/'test.sh').write_text('#!/bin/sh\nexit 0\n')
        (tools/'test.sh').chmod(0o755)
        (tools/'combine_release.py').write_text('# fixture\n')
        (seed/'tools/media/tests').mkdir(parents=True)
        (seed/'tools/media/tests/test_smoke.py').write_text(
            'import unittest\nclass Smoke(unittest.TestCase):\n    def test_fixture(self):\n        self.assertTrue(True)\n')
        self.git(seed, 'add', '.')
        self.git(seed, 'commit', '-qm', 'initial')
        self.git(seed, 'branch', '-M', 's905x2-no-fixes')
        initial = self.git(seed, 'rev-parse', 'HEAD').stdout.strip()
        self.git(root, 'clone', '-q', '--bare', str(seed), str(root/'upstream.git'))
        self.git(seed, 'switch', '-qc', 's905x2-media-edition')
        (seed/'media.txt').write_text('media only\n')
        if conflict == 'media':
            (seed/'shared.txt').write_text('media conflicting change\n')
        self.git(seed, 'add', '.')
        self.git(seed, 'commit', '-qm', 'media additions')
        self.git(seed, 'switch', '-q', 's905x2-no-fixes')
        if conflict == 'base':
            (seed/'shared.txt').write_text('base conflicting change\n')
            self.git(seed, 'add', '.')
            self.git(seed, 'commit', '-qm', 'base conflicting change')
        self.git(root, 'clone', '-q', '--bare', str(seed), str(root/'origin.git'))
        # Populate an independent upstream commit, never the actual GitHub repo.
        self.git(seed, 'switch', '-q', '--detach', initial)
        (seed/'shared.txt').write_text('official upstream change\n')
        self.git(seed, 'add', '.')
        self.git(seed, 'commit', '-qm', 'official update')
        upstream = self.git(seed, 'rev-parse', 'HEAD').stdout.strip()
        self.git(seed, 'push', '-q', str(root/'upstream.git'), 'HEAD:refs/heads/coreelec-22')
        self.git(root, 'clone', '-q', '--branch', 's905x2-no-fixes', str(root/'origin.git'), str(root/'checkout'))
        return upstream

    def exercise(self, conflict=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            upstream = self.fixture(root, conflict)
            remote = root/'origin.git'
            branches = ('s905x2-no-fixes', 's905x2-media-edition')
            before = {b:self.git(remote,'rev-parse',b).stdout.strip() for b in branches}
            yaml = (ROOT/'.github/workflows/s905x2-weekly.yml').read_text()
            block = yaml.split("          git config user.name 'S905X2 build bot'",1)[1]
            block = block.split('      - uses: actions/checkout@v4',1)[0]
            script = "git config user.name 'S905X2 build bot'\n"+textwrap.dedent(block)
            script = 'set -euo pipefail\n'+script
            script = script.replace('https://github.com/CoreELEC/CoreELEC.git',shlex.quote(str(root/'upstream.git')))
            script = script.replace('${{ github.event_name }}','workflow_dispatch')
            runner = root/'runner'
            runner.mkdir()
            env = dict(os.environ, SYNC_UPSTREAM='true',RUNNER_TEMP=str(runner),GITHUB_OUTPUT=str(root/'output'))
            result = subprocess.run(['bash','-c',script],cwd=root/'checkout',env=env,text=True,capture_output=True)
            after = {b:self.git(remote,'rev-parse',b).stdout.strip() for b in branches}
            if conflict:
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(after,before,'A conflicting merge changed a remote branch')
                self.assertIn('both remote branches and published images are unchanged',result.stdout)
                self.assertNotEqual(self.git(root/'checkout','rev-parse','--verify','MERGE_HEAD',check=False).returncode,0)
            else:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                for branch in branches:
                    self.assertNotEqual(after[branch],before[branch])
                    self.git(root/'checkout','merge-base','--is-ancestor',upstream,after[branch])
                outputs = (root/'output').read_text()
                self.assertIn('base_sha='+after[branches[0]],outputs)
                self.assertIn('media_sha='+after[branches[1]],outputs)

    def test_success_synchronizes_both_branches(self):
        self.exercise()

    def test_base_conflict_stops_without_changing_either_remote_branch(self):
        self.exercise('base')

    def test_media_conflict_also_preserves_remote_base(self):
        self.exercise('media')


if __name__=='__main__':unittest.main()
