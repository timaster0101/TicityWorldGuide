# -*- coding: utf-8 -*-
"""`工具/oss_gallery.py` 的判据测试：key 映射、URL 拼接、对照表与清单一致、缺件/前缀错必须判红。

不打真实网络：所有用例都走纯函数面（remote_key／url_of／write_links 用临时目录里的假清单）。
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oss_gallery as G  # noqa: E402


class KeyMapping(unittest.TestCase):
    def test_gallery_goes_under_gallery_prefix(self):
        self.assertEqual(G.remote_key("数据/图集/D01/a.png"), "taihucheng/gallery/D01/a.png")

    def test_mothers_go_under_mothers_prefix(self):
        self.assertEqual(G.remote_key("数据/视觉控制资产/E1定档/x.png"),
                         "taihucheng/mothers/E1定档/x.png")

    def test_backslash_is_normalised(self):
        self.assertEqual(G.remote_key("数据\\图集\\D01\\a.png"), "taihucheng/gallery/D01/a.png")

    def test_every_key_stays_inside_the_policy_prefix(self):
        for rel in ("数据/图集/D01/a.png", "数据/视觉控制资产/x/y.png", "分卷/原稿/01.md"):
            key = G.remote_key(rel)
            self.assertTrue(key.startswith("taihucheng/"), key)
            self.assertNotIn("//", key)

    def test_url_has_no_double_slash(self):
        url = G.url_of(G.remote_key("数据/图集/D01/a.png"))
        self.assertTrue(url.startswith("https://timaster.oss-cn-shenzhen.aliyuncs.com/taihucheng/"))
        self.assertNotIn("//taihucheng", url)


class LinksDoc(unittest.TestCase):
    def _manifest(self, tmp, rows):
        man = {"逐件": rows}
        p = os.path.join(tmp, "man.json")
        with io.open(p, "w", encoding="utf-8") as fp:
            json.dump(man, fp, ensure_ascii=False)
        return p

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oss_links_")
        self._old = (G.MANIFEST, G.LINKS, G.META_DIR, G.ROOT)
        G.ROOT = self.tmp
        G.MANIFEST = os.path.join(self.tmp, "man.json")
        G.LINKS = os.path.join(self.tmp, "links.json")
        G.META_DIR = os.path.join(self.tmp, "视觉控制资产")
        os.makedirs(os.path.join(self.tmp, "数据", "图集", "D01"))
        self.img = os.path.join(self.tmp, "数据", "图集", "D01", "a.png")
        with open(self.img, "wb") as fp:
            fp.write(b"x" * 32)
        self._manifest(self.tmp, [{"路径": "数据/图集/D01/a.png", "字节": 32, "sha256": "0" * 64}])

    def tearDown(self):
        G.MANIFEST, G.LINKS, G.META_DIR, G.ROOT = self._old

    def test_links_cover_every_manifest_file(self):
        items = G.plan()
        G.write_links(items)
        with io.open(G.LINKS, encoding="utf-8") as fp:
            doc = json.load(fp)
        self.assertEqual(doc["统计"]["件数"], 1)
        self.assertIn("数据/图集/D01/a.png", doc["逐件"])
        self.assertIn("D01", doc["按地点"])
        self.assertEqual(doc["按地点"]["D01"][0]["文件"], "a.png")

    def test_missing_local_file_is_not_planned(self):
        os.unlink(self.img)
        self.assertEqual(G.plan(), [])

    def test_links_prefix_matches_policy(self):
        G.write_links(G.plan())
        with io.open(G.LINKS, encoding="utf-8") as fp:
            doc = json.load(fp)
        for rec in doc["逐件"].values():
            self.assertTrue(rec["key"].startswith("taihucheng/"))
            self.assertIn("/taihucheng/", rec["url"])


class RealLinksFace(unittest.TestCase):
    """仓内两份真文件的一致性：清单里有几件，对照表里就得有几条直链。"""

    def test_every_manifest_file_has_a_link(self):
        if not os.path.exists(G.LINKS):
            self.skipTest("数据/图集OSS.json 尚未生成")
        with io.open(G.MANIFEST, encoding="utf-8") as fp:
            man = json.load(fp)
        with io.open(G.LINKS, encoding="utf-8") as fp:
            doc = json.load(fp)
        missing = [r["路径"] for r in man["逐件"]
                   if r["路径"].replace("\\", "/") not in doc["逐件"]]
        self.assertEqual(missing, [], "这些图没有直链：%s" % missing[:5])

    def test_link_prefix_and_bucket(self):
        if not os.path.exists(G.LINKS):
            self.skipTest("数据/图集OSS.json 尚未生成")
        with io.open(G.LINKS, encoding="utf-8") as fp:
            doc = json.load(fp)
        self.assertEqual(doc["bucket"], G.BUCKET)
        for rec in doc["逐件"].values():
            self.assertTrue(rec["key"].startswith(G.PREFIX))
            self.assertTrue(rec["url"].startswith(G.BASE.rstrip("/")))




if __name__ == "__main__":
    unittest.main()
