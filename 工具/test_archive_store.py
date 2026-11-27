# -*- coding: utf-8 -*-
"""`工具/archive_store.py` 的判据：仓内优先、只在真仓库根才回落归档根、找不到就说找不到。

夹具全部在仓库外临时目录（`tempfile.mkdtemp`），跑完删净；每个用例都断言「正例为真」再断言
「违例为假」，避免把恒真的解析器当成已验收（本仓库对判据的一贯要求）。
"""
import os
import shutil
import tempfile
import unittest

import archive_store as A


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='archive_store_test_')
        self.repo = os.path.join(self.tmp, 'repo')
        self.arch = os.path.join(self.tmp, 'arch')
        os.makedirs(self.repo)
        os.makedirs(self.arch)
        self._old_root = A.ROOT
        self._old_env = os.environ.get(A.ENV)
        A.ROOT = self.repo
        os.environ[A.ENV] = self.arch

    def tearDown(self):
        A.ROOT = self._old_root
        if self._old_env is None:
            os.environ.pop(A.ENV, None)
        else:
            os.environ[A.ENV] = self._old_env
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertFalse(os.path.exists(self.tmp), '临时夹具必须删净')

    def put(self, root, rel, data=b'x'):
        p = os.path.join(root, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as fp:
            fp.write(data)
        return p


class RepoFirst(Base):
    def test_repo_copy_wins_when_both_exist(self):
        self.put(self.repo, 'vibe_images/a.png', b'repo')
        self.put(self.arch, 'vibe_images/a.png', b'arch')
        p = A.resolve('vibe_images/a.png')
        self.assertEqual(os.path.realpath(p), os.path.realpath(os.path.join(self.repo, 'vibe_images', 'a.png')))
        self.assertEqual(A.where('vibe_images/a.png'), 'repo')

    def test_archive_copy_is_found_when_repo_lacks_it(self):
        self.put(self.arch, 'backup/数据/视觉控制资产/卡牌/c.png')
        self.assertTrue(A.exists('backup/数据/视觉控制资产/卡牌/c.png'))
        self.assertEqual(A.where('backup/数据/视觉控制资产/卡牌/c.png'), 'archive')

    def test_missing_returns_repo_path_and_says_missing(self):
        p = A.resolve('vibe_images/nope.png')
        self.assertEqual(os.path.realpath(p), os.path.realpath(os.path.join(self.repo, 'vibe_images', 'nope.png')))
        self.assertFalse(A.exists('vibe_images/nope.png'))
        self.assertEqual(A.where('vibe_images/nope.png'), 'missing')

    def test_backslash_paths_are_normalised(self):
        self.put(self.arch, 'vibe_images/b.png')
        self.assertTrue(A.exists(r'vibe_images\b.png'))


class Directories(Base):
    """`resolve_dir()`：整棵树外置后，目录也要能解析到归档根（`resolve()` 只认文件，会漏）。"""

    def test_archive_directory_is_resolved(self):
        os.makedirs(os.path.join(self.arch, 'backup', '数据', '图集', '四向', 'S02'))
        got = A.resolve_dir('backup/数据/图集')
        self.assertEqual(os.path.realpath(got), os.path.realpath(
            os.path.join(self.arch, 'backup', '数据', '图集')))
        self.assertTrue(A.exists_dir('backup/数据/图集'))

    def test_directory_falls_back_to_repo_path_when_absent_everywhere(self):
        got = A.resolve_dir('backup/数据/图集')
        self.assertEqual(os.path.realpath(got), os.path.realpath(
            os.path.join(self.repo, 'backup', '数据', '图集')))
        self.assertFalse(A.exists_dir('backup/数据/图集'))

    def test_directory_negative_fixture_root_never_borrows_archive(self):
        """违例负测：临时 root 下不许回落到真实归档根，否则夹具里的空目录会被补成「存在」。"""
        os.makedirs(os.path.join(self.arch, 'backup', '数据', '图集'))
        elsewhere = os.path.join(self.tmp, 'elsewhere')
        os.makedirs(elsewhere)
        self.assertTrue(A.exists_dir('backup/数据/图集'), '基线：真仓库根下必须找得到')
        self.assertFalse(A.exists_dir('backup/数据/图集', root=elsewhere))


class NoFallbackOutsideRepo(Base):
    def test_fixture_root_never_borrows_the_real_archive(self):
        """违例负测：闸门负测把 root 指到临时目录，夹具里故意缺的件不许被归档件补上。"""
        self.put(self.arch, 'backup/数据/视觉控制资产/卡牌/c.png')
        elsewhere = os.path.join(self.tmp, 'elsewhere')
        os.makedirs(elsewhere)
        self.assertTrue(A.exists('backup/数据/视觉控制资产/卡牌/c.png'), '基线：真仓库根下必须能找到')
        self.assertFalse(A.exists('backup/数据/视觉控制资产/卡牌/c.png', root=elsewhere),
                         '非仓库根时必须判缺件，否则负测会被归档件静默补绿')
        self.assertEqual(len(A.candidates('vibe_images/x.png', root=elsewhere)), 1)


class Prefixes(Base):
    def test_externalised_prefixes(self):
        for rel in ('vibe_images/a.png', 'backup/数据/图集/四向/S02/x.jpg',
                    'backup/vibe_images/y.png', 'backup/同级vibe_images/z.png'):
            self.assertTrue(A.is_externalised(rel), rel)
        for rel in ('backup/归档明细_早于定档_20261106.json', 'backup/归档说明.md',
                    '数据/图集/D01/a.png', 'vibe_images_old/a.png'):
            self.assertFalse(A.is_externalised(rel), rel)


class Describe(Base):
    def test_describe_counts_both_sides(self):
        self.put(self.repo, 'vibe_images/a.png')
        self.put(self.arch, 'vibe_images/b.png')
        self.put(self.arch, 'vibe_images/c.png')
        self.put(self.arch, 'backup/数据/图集/四向/S02/d.jpg')
        d = A.describe()
        self.assertEqual(d['归档根'], self.arch)
        self.assertTrue(d['归档根存在'])
        self.assertEqual(d['外置树']['vibe_images']['仓内件数'], 1)
        self.assertEqual(d['外置树']['vibe_images']['归档件数'], 2)
        self.assertEqual(d['外置树']['backup/数据']['归档件数'], 1)

    def test_describe_is_not_lazy_when_archive_absent(self):
        os.environ[A.ENV] = os.path.join(self.tmp, 'not_there')
        d = A.describe()
        self.assertFalse(d['归档根存在'])
        self.assertEqual(d['外置树']['vibe_images']['归档件数'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
