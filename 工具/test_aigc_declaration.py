# -*- coding: utf-8 -*-
"""图集 AI 声明件的闸门：逐件对拍 + 违例负测。

守的是什么：图集里每一枚图片都能在这份声明里找到一行、且那行的 sha256 与盘面一致；
少了这一行（或行是旧的），「这张图是 AI 生成的」就没有载体了——因为图片本身从 R10 起
不再含水印与元数据。
"""
import io
import json
import os
import shutil
import tempfile
import unittest

import build_aigc_declaration as B


def _mkroot(tmp, files, items):
    root = os.path.join(tmp, 'repo')
    os.makedirs(os.path.join(root, '数据', '图集'), exist_ok=True)
    for rel, data in files.items():
        p = os.path.join(root, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, 'wb') as fp:
            fp.write(data)
    with io.open(os.path.join(root, '数据', '开图清单.json'), 'w', encoding='utf-8') as fp:
        json.dump({'items': items}, fp, ensure_ascii=False)
    return root


def _item(eid='D01', name='北湖政务片区'):
    return {'id': eid, 'name': name, 'type': '城市片区', 'prompt_sha256': 'a' * 64}


class RealGalleryIsDeclared(unittest.TestCase):
    def test_every_gallery_file_has_a_row(self):
        rec, problems = B.build()
        self.assertEqual(problems, [])
        self.assertEqual(len(rec['逐件']), rec['统计']['件数'])
        self.assertGreater(rec['统计']['件数'], 600)

    def test_written_declaration_matches_disk(self):
        self.assertEqual(B.main(['b', '--check']), 0)


class ViolationsMustRed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='aigc_dec_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_id_not_in_prompt_list(self):
        root = _mkroot(self.tmp, {'数据/图集/D99/x_1795000000000_abcdef12.png': b'x'}, [_item()])
        _rec, problems = B.build(root)
        self.assertTrue(problems)
        self.assertEqual(problems[0]['类型'], '图集里有、开图清单里没有这个ID')

    def test_file_not_under_id_dir(self):
        root = _mkroot(self.tmp, {'数据/图集/loose.png': b'x'}, [_item()])
        _rec, problems = B.build(root)
        self.assertTrue(problems)
        self.assertEqual(problems[0]['类型'], '路径不在 <ID> 目录里')

    def test_stale_row_reds_check(self):
        root = _mkroot(self.tmp, {'数据/图集/D01/x_1795000000000_abcdef12.png': b'x'}, [_item()])
        rec, problems = B.build(root)
        self.assertEqual(problems, [])
        rec['逐件'][0]['sha256'] = '0' * 64
        path = os.path.join(root, '数据', '图集AIGC声明.json')
        with io.open(path, 'w', encoding='utf-8') as fp:
            json.dump(rec, fp, ensure_ascii=False)
        old = B.ROOT
        try:
            B.ROOT = root
            self.assertEqual(B.main(['b', '--check']), 1)
        finally:
            B.ROOT = old

    def test_channel_unknown_falls_back_to_history(self):
        root = _mkroot(self.tmp, {'数据/图集/D01/x_1795000000000_abcdef12.png': b'x'}, [_item()])
        rec, problems = B.build(root)
        self.assertEqual(problems, [])
        self.assertEqual(rec['逐件'][0]['来源通道'], 'ImageGen（会话内置，历史轮）')
        self.assertEqual(rec['统计']['方舟轮件数'], 0)


if __name__ == '__main__':
    unittest.main()
