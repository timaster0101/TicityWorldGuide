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

    def test_archive_gallery_goes_under_archive_prefix(self):
        """外置的 `backup/数据/图集/`（四向基准照）单独进 archive/gallery/，不与在册图混。"""
        self.assertEqual(G.remote_key("backup/数据/图集/四向/L001/x-r01.jpg"),
                         "taihucheng/archive/gallery/四向/L001/x-r01.jpg")

    def test_other_archive_trees_keep_their_relative_path(self):
        """`backup/vibe_images/` 这类只在被引用时上传，key 保留原相对路径便于回溯。"""
        self.assertEqual(G.remote_key("backup/vibe_images/S02-B3.png"),
                         "taihucheng/archive/backup/vibe_images/S02-B3.png")
        self.assertEqual(G.remote_key("vibe_images/x.png"),
                         "taihucheng/archive/vibe_images/x.png")

    def test_process_trees_are_enumerated(self):
        """三棵过程图（`vibe_images` 各棵）也要进计划：用户问「图片都传了么」，答案是全传。"""
        self.assertEqual(G.PROCESS_TREES,
                         ("backup/vibe_images", "backup/同级vibe_images", "vibe_images"))
        for rel in G.PROCESS_TREES:
            self.assertIn(rel, " ".join(G.PROCESS_TREES))
        # key 一律落在 archive/ 下，与在册图（gallery/）分开
        self.assertTrue(G.remote_key("vibe_images/a.png").startswith("taihucheng/archive/"))

    def test_runtime_assets_go_under_runtime_prefix(self):
        """`数据/运行时资产/`（卡面专用图、印章）既不属图集也不属母图池，单独进 runtime/。

        2026-11-28 全仓扫图时这 6 件没进计划、没上云——判据就是「key 必须落在 runtime/ 且进计划」。
        """
        self.assertEqual(G.RUNTIME_REL, "数据/运行时资产")
        self.assertEqual(G.remote_key("数据/运行时资产/印章-已获得-酒红.png"),
                         "taihucheng/runtime/印章-已获得-酒红.png")
        self.assertEqual(G.remote_key("数据/运行时资产/卡面专用图/L003.png"),
                         "taihucheng/runtime/卡面专用图/L003.png")
        self.assertTrue(G.remote_key("数据/运行时资产/x.png").startswith(G.PREFIX))


class Backfill(unittest.TestCase):
    """URL 回写：开图清单的 image_url 与 image_file 逐格对齐、图集清单逐件有 url、缺链必须报出来。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oss_backfill_")
        self._old = (G.ROOT, G.MANIFEST, G.LINKS, G.PROMPTS, G.META_DIR, G.LINKS_MD)
        G.ROOT = self.tmp
        G.MANIFEST = os.path.join(self.tmp, "gal.json")
        G.LINKS = os.path.join(self.tmp, "links.json")
        G.PROMPTS = os.path.join(self.tmp, "prompts.json")
        G.LINKS_MD = os.path.join(self.tmp, "links.md")
        G.META_DIR = os.path.join(self.tmp, "视觉控制资产")
        self.img1 = os.path.join(self.tmp, "数据", "图集", "D01", "a.png")
        self.img2 = os.path.join(self.tmp, "数据", "图集", "D01", "b.png")
        os.makedirs(os.path.dirname(self.img1))
        for p in (self.img1, self.img2):
            with open(p, "wb") as fp:
                fp.write(b"x" * 16)
        self._dump(G.MANIFEST, {"逐件": [
            {"路径": "数据/图集/D01/a.png", "字节": 16, "sha256": "0" * 64},
            {"路径": "数据/图集/D01/b.png", "字节": 16, "sha256": "1" * 64}]})
        self._dump(G.PROMPTS, {"items": [
            {"id": "D01", "name": "北湖政务片区", "type": "城市片区",
             "image_file": ["数据/图集/D01/a.png", "数据/图集/D01/b.png"]}]})

    def tearDown(self):
        (G.ROOT, G.MANIFEST, G.LINKS, G.PROMPTS, G.META_DIR, G.LINKS_MD) = self._old

    @staticmethod
    def _dump(path, doc):
        with io.open(path, "w", encoding="utf-8") as fp:
            json.dump(doc, fp, ensure_ascii=False)

    def _load(self, path):
        with io.open(path, encoding="utf-8") as fp:
            return json.load(fp)

    def test_urls_are_written_aligned_with_image_file(self):
        missing = G.backfill(G.plan())
        self.assertEqual(missing, [])
        item = self._load(G.PROMPTS)["items"][0]
        self.assertEqual(len(item["image_url"]), len(item["image_file"]))
        for url in item["image_url"]:
            self.assertTrue(url.startswith("https://timaster."), url)
        rows = self._load(G.MANIFEST)["逐件"]
        self.assertTrue(all(r["url"].startswith("https://timaster.") for r in rows))

    def test_cell_without_link_is_reported_not_silently_blank(self):
        self._dump(G.PROMPTS, {"items": [
            {"id": "D01", "name": "n", "type": "城市片区",
             "image_file": ["数据/图集/D01/a.png", "数据/图集/D01/未上传.png"]}]})
        missing = G.backfill(G.plan())
        self.assertEqual([m[1] for m in missing], ["数据/图集/D01/未上传.png"])
        item = self._load(G.PROMPTS)["items"][0]
        self.assertEqual(item["image_url"][0][:9], "https://t")
        self.assertIsNone(item["image_url"][1])

    def test_backfill_is_idempotent(self):
        G.backfill(G.plan())
        first = self._load(G.PROMPTS)
        G.backfill(G.plan())
        self.assertEqual(self._load(G.PROMPTS), first)


class RealBackfillFace(unittest.TestCase):
    """仓内两份真账本：每一格都要有链，长度与 image_file 对齐。"""

    def test_every_cell_has_a_url(self):
        with io.open(G.PROMPTS, encoding="utf-8") as fp:
            items = json.load(fp)["items"]
        bad = []
        for item in items:
            files = item.get("image_file") or []
            urls = item.get("image_url")
            if not isinstance(urls, list) or len(urls) != len(files):
                bad.append((item["id"], "长度不符"))
                continue
            if any(u is None for u in urls):
                bad.append((item["id"], "有空格无链"))
        self.assertEqual(bad, [], "这些条目的 image_url 不达标：%s" % bad[:5])

    def test_gallery_rows_carry_url(self):
        with io.open(G.MANIFEST, encoding="utf-8") as fp:
            rows = json.load(fp)["逐件"]
        bad = [r["路径"] for r in rows if not str(r.get("url") or "").startswith("https://")]
        self.assertEqual(bad, [], "这些件缺 url：%s" % bad[:5])


class LinksDoc(unittest.TestCase):
    def _manifest(self, tmp, rows):
        man = {"逐件": rows}
        p = os.path.join(tmp, "man.json")
        with io.open(p, "w", encoding="utf-8") as fp:
            json.dump(man, fp, ensure_ascii=False)
        return p

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oss_links_")
        self._old = (G.MANIFEST, G.LINKS, G.META_DIR, G.ROOT, G.LINKS_MD)
        G.ROOT = self.tmp
        G.MANIFEST = os.path.join(self.tmp, "man.json")
        G.LINKS = os.path.join(self.tmp, "links.json")
        G.LINKS_MD = os.path.join(self.tmp, "links.md")
        G.META_DIR = os.path.join(self.tmp, "视觉控制资产")
        os.makedirs(os.path.join(self.tmp, "数据", "图集", "D01"))
        self.img = os.path.join(self.tmp, "数据", "图集", "D01", "a.png")
        with open(self.img, "wb") as fp:
            fp.write(b"x" * 32)
        self._manifest(self.tmp, [{"路径": "数据/图集/D01/a.png", "字节": 32, "sha256": "0" * 64}])

    def tearDown(self):
        G.MANIFEST, G.LINKS, G.META_DIR, G.ROOT, G.LINKS_MD = self._old

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


class LinksMdCoversEverything(unittest.TestCase):
    """`数据/图集直链.md` 是人读入口：项目里 2,614 件图必须件件有点得开的链接。

    旧版只按 312 个地点列在册图，母图池／历史归档／过程图／运行资产全都不在里面——
    用户要的是「人读版也能看到全部图片」，这条闸门判的就是「逐件的 url 都在 md 里出现」。
    """

    def setUp(self):
        with io.open(G.LINKS, encoding="utf-8") as fp:
            self.doc = json.load(fp)
        with io.open(G.LINKS_MD, encoding="utf-8") as fp:
            self.md = fp.read()

    def test_every_image_url_appears_in_the_markdown(self):
        miss = [rel for rel, v in self.doc["逐件"].items() if v["url"] not in self.md]
        self.assertEqual(miss, [], "直链表漏了 %d 件，例：%s" % (len(miss), miss[:3]))

    def test_other_images_section_is_present(self):
        self.assertIn("## 二、在册图之外的图", self.md)
        for title in ("母图池", "历史归档·图集", "过程图", "运行资产"):
            self.assertIn(title, self.md)

    def test_process_images_are_labelled_not_deliverable(self):
        """过程图是生成过程产物，md 里必须写明「不代表可对外引用的成品」。"""
        self.assertIn("不代表可对外引用的成品", self.md)


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
