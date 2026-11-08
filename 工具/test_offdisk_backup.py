#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""异盘副本三条判据的自证：整件对拍不是走过场、同盘目标一律拒、zip 重建后一致性旗标必须翻假。

夹具全在系统临时目录，不碰仓库、也不碰真还原点目录；目标盘符判据用真实盘符比较，
所以「同盘拒绝」这条在本机一定能跑（临时目录与仓库同在 C:）。
"""
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile

import backup_card_main_images as B


def make_zip(path, members):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, payload in members:
            z.writestr(name, payload)


class OffdiskCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp_root = tempfile.gettempdir()
        self.before = {p for p in os.listdir(self.temp_root) if p.startswith('taihoo_offdisk_')}
        self.tmp = tempfile.mkdtemp(prefix='taihoo_offdisk_', dir=self.temp_root)
        self.src_zip = os.path.join(self.tmp, '主图3x4.zip')
        self.ledger = os.path.join(self.tmp, '卡面主图备份台账.json')
        make_zip(self.src_zip, [('A01.png', b'x' * 4096), ('A02.png', b'y' * 2048)])
        with io.open(self.ledger, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps({'归档sha256_12': B.sha12(self.src_zip)[0]}, ensure_ascii=False))
        self._paths = (B.ZIP_PATH, B.LEDGER)
        B.ZIP_PATH, B.LEDGER = self.src_zip, self.ledger
        self.dest = os.path.join(self.tmp, 'offdisk')

    def tearDown(self):
        B.ZIP_PATH, B.LEDGER = self._paths
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertFalse(os.path.exists(self.tmp), '夹具目录没删掉：%s' % self.tmp)
        leaked = sorted({p for p in os.listdir(self.temp_root)
                         if p.startswith('taihoo_offdisk_')} - self.before)
        self.assertEqual(leaked, [], '夹具泄漏到系统临时目录：%s' % leaked)

    def test_copy_verified_writes_a_byte_equal_file_and_no_part(self):
        dst = os.path.join(self.dest, os.path.basename(self.src_zip))
        sha, size = B.copy_verified(self.src_zip, dst)
        self.assertEqual(sha, B.sha256_full(self.src_zip), '副本摘要与源不符')
        self.assertEqual(size, os.path.getsize(self.src_zip))
        self.assertFalse(os.path.exists(dst + '.part'), '.part 没被 os.replace 收掉')

    def test_a_truncated_offdisk_copy_is_red(self):
        """违例负测：副本被截断（整件 sha 不符）与副本 zip 打不开（半件写盘）两种形态都必须判红，
        否则「逐字节对拍」只是把文件拷了一遍再夸自己一遍。"""
        dst = os.path.join(self.dest, os.path.basename(self.src_zip))
        B.copy_verified(self.src_zip, dst)
        with io.open(dst, 'r+b') as f:
            f.truncate(os.path.getsize(dst) // 2)
        ok, rows, zinfo = B.offdisk_state(self.dest, only_zip=True)
        self.assertFalse(ok, '截断后的副本仍被判为一致，整件 sha256 对拍是走过场')
        self.assertFalse(rows[0]['整件sha256与源相同'])
        os.remove(dst)
        with io.open(dst, 'wb') as f:
            f.write(b'not a zip at all')
        ok, rows, zinfo = B.offdisk_state(self.dest, only_zip=True)
        self.assertFalse(ok, '打不开的副本 zip 仍被判绿')
        self.assertFalse(zinfo['副本zip可打开'], '坏 zip 应显式记「不可打开」而不是抛异常')

    def test_same_drive_destination_is_refused(self):
        """目标盘与仓库同盘时不写任何东西——异盘副本的意义就是换一块物理盘。"""
        argv = B.sys.argv
        B.sys.argv = ['backup_card_main_images.py', '--offdisk', self.dest]
        try:
            self.assertEqual(B.main(), 1, '同盘目标没被拒')
        finally:
            B.sys.argv = argv
        self.assertFalse(os.path.exists(self.dest), '被拒的调用仍然建了目标目录')

    def test_carry_offdisk_block_flips_when_the_zip_is_rebuilt(self):
        """zip 重建后，异盘段的一致性旗标必须由 true 翻成 false：只看「段还在不在」是抓不到
        「副本没跟着重建」这类断链的。"""
        prev = {'zip_sha256_12': B.sha12(self.src_zip)[0], '与当前还原点一致': True}
        same = B.carry_offdisk_block(dict(prev), B.sha12(self.src_zip)[0])
        self.assertTrue(same['与当前还原点一致'])
        make_zip(self.src_zip, [('A01.png', b'x' * 4096), ('A02.png', b'z' * 2048)])
        moved = B.carry_offdisk_block(dict(prev), B.sha12(self.src_zip)[0])
        self.assertFalse(moved['与当前还原点一致'], 'zip 已变，异盘副本旗标仍留 true')
        self.assertIsNone(B.carry_offdisk_block(None, 'whatever'), '没有历史段时不该凭空造一段')


if __name__ == '__main__':
    unittest.main()
