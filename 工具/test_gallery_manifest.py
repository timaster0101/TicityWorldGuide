# -*- coding: utf-8 -*-
"""图集清单（`数据/图集清单.json`）的闸门：仓内唯一能核对「不入仓的 1.9GB 图集」的那份证据。

三条硬约束：
① 盘面与清单逐件对得上（路径／字节／sha256）——图集增删后不重跑生成器，这里当场判红；
② 清单要覆盖 开图清单 里所有挂在 `数据/图集/` 下的在册格——否则「可核对」只覆盖了一部分；
③ 图集本体确实在 `.gitignore` 里——清单的意义正在于「大档不入仓、引用与摘要入仓」，
   哪天有人把这条删了，仓库体积会一次性涨 1.9GB，这条断言就是那道闸。
另配一类负测：清单核对器本身必须能判出「删了／改了／多了一枚」，不许永远返回空问题表。
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import build_gallery_manifest as bgm


class RealGalleryFace(unittest.TestCase):
    def test_a_manifest_matches_the_gallery_on_disk(self):
        problems, rec = bgm.verify(ROOT)
        self.assertEqual(problems, [], '图集与清单不一致（前三条：%s）＝增删后没重跑 build_gallery_manifest.py'
                         % problems[:3])
        self.assertEqual(rec['统计']['件数'], len(rec['逐件']))
        self.assertEqual(rec['统计']['合计字节'], sum(r['字节'] for r in rec['逐件']))
        self.assertGreater(rec['统计']['件数'], 0)

    def test_b_every_registered_cell_is_covered(self):
        with io.open(os.path.join(ROOT, '数据', '图集清单.json'), encoding='utf-8') as fp:
            listed = {r['路径'] for r in json.loads(fp.read())['逐件']}
        with io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8') as fp:
            items = json.loads(fp.read())['items']
        cells = set()
        for it in items:
            files = it.get('image_file') or []
            if isinstance(files, str):
                files = [files]
            for f in files:
                if f.startswith('数据/图集/'):
                    cells.add(f)
        missing = sorted(cells - listed)
        self.assertEqual(missing, [], '在册格不在图集清单里（前三条：%s）' % missing[:3])
        self.assertGreater(len(cells), 0)

    def test_c_gallery_binaries_are_gitignored(self):
        with io.open(os.path.join(ROOT, '.gitignore'), encoding='utf-8') as fp:
            lines = [ln.strip() for ln in fp.read().splitlines()]
        self.assertIn('数据/图集/', lines,
                      '图集目录不再被忽略：1.9GB 大档会一次性进 git，清单这层冗余也就失去意义')


class VerifierSeesTrouble(unittest.TestCase):
    """负测：三类不一致各造一次，核对器必须报出来。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        os.makedirs(os.path.join(self.root, '数据', '图集', 'X01'))
        self.p = os.path.join(self.root, '数据', '图集', 'X01', 'x.png')
        with io.open(self.p, 'wb') as fp:
            fp.write(b'\x89PNG\r\n\x1a\nAAA')
        with io.open(os.path.join(self.root, '数据', '开图清单.json'), 'w', encoding='utf-8') as fp:
            fp.write(json.dumps({'items': []}))
        rows, stat = bgm.collect(self.root)
        rec = {'统计': stat, '逐件': rows}
        with io.open(os.path.join(self.root, '数据', '图集清单.json'), 'w', encoding='utf-8') as fp:
            fp.write(json.dumps(rec, ensure_ascii=False))

    def kinds(self):
        problems, _rec = bgm.verify(self.root)
        return [p['类型'] for p in problems]

    def test_d_clean_fixture_has_no_problems(self):
        self.assertEqual(self.kinds(), [])

    def test_e_modified_file_is_reported(self):
        with io.open(self.p, 'wb') as fp:
            fp.write(b'\x89PNG\r\n\x1a\nBBB')
        self.assertIn('摘要不符', self.kinds())

    def test_f_deleted_file_is_reported(self):
        os.remove(self.p)
        self.assertIn('清单有、盘上没有', self.kinds())

    def test_g_extra_file_is_reported(self):
        with io.open(os.path.join(self.root, '数据', '图集', 'X01', 'extra.png'), 'wb') as fp:
            fp.write(b'zz')
        self.assertIn('盘上有、清单没有', self.kinds())


class RebuildKeepsOssUrls(unittest.TestCase):
    """重跑生成器不许抹掉直链：`url` 由 `工具/oss_gallery.py --backfill` 写，不是本生成器的产物。

    首版没带这个字段，重写清单会静默清空 808 条 url，随后 `test_oss_gallery` 判红——
    这是「生成器只重算自己负责的字段」的口径，不是把 url 变成生成器的活。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='bgm_url_')
        os.makedirs(os.path.join(self.tmp, '数据', '图集', 'X01'))
        self.p = os.path.join(self.tmp, '数据', '图集', 'X01', 'a.png')
        with io.open(self.p, 'wb') as fp:
            fp.write(b'abc')
        self._old_out = bgm.OUT
        self._old_root = bgm.ROOT
        bgm.ROOT = self.tmp
        bgm.OUT = os.path.join(self.tmp, '清单.json')
        with io.open(os.path.join(self.tmp, '数据', '开图清单.json'), 'w', encoding='utf-8') as fp:
            fp.write('{"items": []}')

    def tearDown(self):
        bgm.OUT = self._old_out
        bgm.ROOT = self._old_root

    def _write_manifest(self, url=None):
        rows = [{'路径': '数据/图集/X01/a.png', '字节': 3,
                 'sha256': hashlib.sha256(b'abc').hexdigest()}]
        if url:
            rows[0]['url'] = url
        with io.open(bgm.OUT, 'w', encoding='utf-8') as fp:
            json.dump({'统计': {}, '逐件': rows}, fp, ensure_ascii=False)

    def test_existing_url_survives_rebuild(self):
        url = 'https://timaster.oss-cn-shenzhen.aliyuncs.com/taihucheng/gallery/X01/a.png'
        self._write_manifest(url)
        argv_backup = sys.argv
        sys.argv = ['build_gallery_manifest.py']
        try:
            with io.open(os.devnull, 'w') as null:
                old = sys.stdout
                sys.stdout = null
                try:
                    bgm.main(['x'])
                finally:
                    sys.stdout = old
        finally:
            sys.argv = argv_backup
        with io.open(bgm.OUT, encoding='utf-8') as fp:
            rows = json.loads(fp.read())['逐件']
        self.assertEqual([r.get('url') for r in rows], [url])

    def test_manifest_without_url_stays_without_url(self):
        self._write_manifest(None)
        with io.open(os.devnull, 'w') as null:
            old = sys.stdout
            sys.stdout = null
            try:
                bgm.main(['x'])
            finally:
                sys.stdout = old
        with io.open(bgm.OUT, encoding='utf-8') as fp:
            rows = json.loads(fp.read())['逐件']
        self.assertNotIn('url', rows[0])


if __name__ == '__main__':
    unittest.main()
