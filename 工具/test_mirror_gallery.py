# -*- coding: utf-8 -*-
"""mirror_gallery 的闸门：定策口径、拷贝记账、以及「不许把不符当相符」的负测。

夹具一律建在临时目录：plan/run 收的是根目录参数，不碰真实图集；e2e 那条用 monkeypatch 把
模块级 GALLERY／MANIFEST 指到夹具上，跑完即弃。
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mirror_gallery as M


def sha(data):
    return hashlib.sha256(data).hexdigest()


class EntriesFace(unittest.TestCase):
    def test_reads_relative_path_and_sha(self):
        rows = M.entries({'条目': [{'相对路径': 'D01/a.png', 'sha256': 'x' * 64, '字节': 3}]})
        self.assertEqual(rows, [('D01/a.png', 'x' * 64, 3)])

    def test_empty_manifest_gives_empty_face(self):
        self.assertEqual(M.entries({}), [])


class PlanDecides(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mirror_'))
        self.src = self.tmp / 'src'
        self.dst = self.tmp / 'dst'
        self.src.mkdir()
        self.dst.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pair(self, rel, data, also_dst=None):
        p = self.src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        if also_dst is not None:
            q = self.dst / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_bytes(also_dst)
        return (rel, sha(data), len(data))

    def test_same_when_target_matches(self):
        ent = self._pair('D01/a.png', b'alpha', also_dst=b'alpha')
        self.assertEqual(M.plan([ent], self.src, self.dst)[0]['动作'], 'same')

    def test_copy_when_target_missing(self):
        ent = self._pair('D01/a.png', b'alpha')
        self.assertEqual(M.plan([ent], self.src, self.dst)[0]['动作'], 'copy')

    def test_copy_when_target_differs_same_size(self):
        ent = self._pair('D01/a.png', b'alpha', also_dst=b'ALPHA')
        self.assertEqual(M.plan([ent], self.src, self.dst)[0]['动作'], 'copy')

    def test_missing_src_is_reported_not_skipped(self):
        rows = M.plan([('D01/ghost.png', 'f' * 64, 9)], self.src, self.dst)
        self.assertEqual(rows[0]['动作'], 'missing_src')

    def test_same_by_size_but_wrong_sha_is_not_same(self):
        # 目标侧字节数凑巧相等、内容不同 —— 必须定成 copy（按 sha 判，不按大小判）
        ent = self._pair('D01/a.png', b'abcdef', also_dst=b'fedcba')
        self.assertEqual(M.plan([ent], self.src, self.dst)[0]['动作'], 'copy')


class RunCopies(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mirror_'))
        self.src = self.tmp / 'src'
        self.dst = self.tmp / 'dst'
        (self.src / 'D01').mkdir(parents=True)
        (self.src / 'D01' / 'a.png').write_bytes(b'alpha')
        self.rows = [{'相对路径': 'D01/a.png', '动作': 'copy', 'sha256': sha(b'alpha'), '字节': 5}]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_copies_bytes_and_reports(self):
        copied, failed = M.run(self.rows, self.src, self.dst, verify=False)
        self.assertEqual(copied, ['D01/a.png'])
        self.assertEqual(failed, [])
        self.assertEqual((self.dst / 'D01' / 'a.png').read_bytes(), b'alpha')

    def test_verify_mode_writes_nothing(self):
        copied, failed = M.run(self.rows, self.src, self.dst, verify=True)
        self.assertEqual((copied, failed), ([], []))
        self.assertFalse((self.dst / 'D01' / 'a.png').exists())

    def test_second_run_is_idempotent(self):
        M.run(self.rows, self.src, self.dst, verify=False)
        rows = M.plan([('D01/a.png', sha(b'alpha'), 5)], self.src, self.dst)
        self.assertEqual(rows[0]['动作'], 'same')
        copied, _ = M.run(rows, self.src, self.dst, verify=False)
        self.assertEqual(copied, [])


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mirror_e2e_'))
        self.gal = self.tmp / 'gallery'
        (self.gal / 'D01').mkdir(parents=True)
        (self.gal / 'D01' / 'a.png').write_bytes(b'alpha')
        self.man = self.tmp / 'manifest.json'
        self.man.write_text(json.dumps({'条目': [
            {'相对路径': 'D01/a.png', 'sha256': sha(b'alpha'), '字节': 5}]}, ensure_ascii=False),
            encoding='utf-8')
        self.out = self.tmp / 'mirror'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, argv):
        with mock.patch.object(M, 'GALLERY', self.gal), mock.patch.object(M, 'MANIFEST', self.man):
            with mock.patch('sys.argv', ['mirror_gallery.py'] + argv):
                return M.main()

    def test_e2e_copies_and_writes_report(self):
        rc = self._run(['--to', str(self.out)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / 'D01' / 'a.png').exists())
        report = json.loads((self.out / M.REPORT_NAME).read_text(encoding='utf-8'))
        self.assertEqual(report['统计']['本轮新拷或覆盖'], 1)
        self.assertEqual(report['统计']['源缺件'], 0)

    def test_e2e_verify_does_not_write_target(self):
        rc = self._run(['--to', str(self.out), '--verify'])
        self.assertEqual(rc, 0)
        self.assertFalse((self.out / 'D01' / 'a.png').exists())

    def test_e2e_empty_manifest_fails_loud(self):
        self.man.write_text(json.dumps({'条目': []}, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(self._run(['--to', str(self.out)]), 1)


class RealManifest(unittest.TestCase):
    def test_real_manifest_has_sha_for_every_file(self):
        man = M.jload(M.MANIFEST)
        rows = M.entries(man)
        self.assertGreater(len(rows), 600)
        bad = [r for r in rows if not r[0] or not r[1] or len(r[1]) != 64]
        self.assertEqual(bad, [])

    def test_real_gallery_files_all_listed(self):
        rows = M.entries(M.jload(M.MANIFEST))
        on_disk = sum(1 for _ in M.GALLERY.rglob('*.png'))
        self.assertGreaterEqual(on_disk, len(rows))


if __name__ == '__main__':
    unittest.main()
