# -*- coding: utf-8 -*-
"""网站生成器的闸门：页面必须由 数据/ 现算得出，且不许出现断链、占位符或计数不符。"""

from __future__ import annotations

import io
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "工具"))

import build_site as B  # noqa: E402


def read(name):
    with io.open(ROOT / "网站" / name, encoding="utf-8") as fp:
        return fp.read()


class PagesExist(unittest.TestCase):
    def test_three_pages_on_disk(self):
        for name in ("index.html", "locations.html", "atlas.html"):
            self.assertTrue((ROOT / "网站" / name).is_file(), name)

    def test_stylesheets_linked(self):
        for name in ("index.html", "locations.html", "atlas.html"):
            text = read(name)
            self.assertIn('href="tokens.css"', text)
            self.assertIn('href="site.css"', text)

    def test_check_mode_is_clean(self):
        self.assertEqual(B.main(["--check"]), 0, "盘上页面与现渲染不一致，跑 工具/build_site.py")


class DataIsRendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = B.Site()
        cls.loc = read("locations.html")
        cls.atlas = read("atlas.html")
        cls.index = read("index.html")

    def test_every_location_is_listed_once(self):
        for item in self.site.items:
            hits = self.loc.count(">%s</td>" % item["id"])
            self.assertEqual(hits, 1, "%s 在索引表里出现 %d 次" % (item["id"], hits))

    def test_type_counts_match_the_manifest(self):
        for t, n in self.site.type_counts.items():
            self.assertIn(">%s %d</button>" % (t, n), self.loc, t)

    def test_atlas_covers_every_place_with_an_image(self):
        for item in self.site.items:
            url = self.site.url_of(item["id"])
            if not url:
                self.fail("%s 没有在册图直链" % item["id"])
            self.assertIn(url, self.atlas, item["id"])

    def test_images_point_at_the_public_bucket(self):
        base = self.site.oss["base_url"]
        self.assertTrue(base.startswith("https://"), base)
        for name, text in (("index.html", self.index), ("atlas.html", self.atlas)):
            for url in re.findall(r'<img[^>]+src="([^"]+)"', text):
                self.assertTrue(url.startswith(base), "%s 里出现非图床地址：%s" % (name, url[:80]))
                self.assertNotIn(" ", url, "%s 里的地址含空格" % name)

    def test_no_placeholder_or_none_leaked(self):
        for name in ("index.html", "locations.html", "atlas.html"):
            text = read(name)
            self.assertNotIn(">None<", text, name)
            self.assertNotIn("{", text.split("<script>")[0], name)


class CopyMatchesTheCanon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = B.Site()
        cls.index = read("index.html")

    def test_key_numbers_come_from_the_data(self):
        index = self.index
        self.assertIn("{:,}".format(len(self.site.items)), index)
        self.assertIn("{:,}".format(self.site.img_total), index)
        self.assertIn("{:,}".format(len(self.site.rulings)), index)
        self.assertIn("{:,}".format(int(self.site.registry["region_area_km2"])), index)

    def test_ring_counts_come_from_the_manifest(self):
        for ring, n in self.site.ring_counts.items():
            self.assertIn("%d 处" % n, self.index, ring)

    def test_version_tag_matches_the_repo(self):
        self.assertIn("v1.0.6", self.index)


class GeneratorIsDataDriven(unittest.TestCase):
    def test_index_rerenders_from_data(self):
        site = B.Site()
        first = site.index()
        self.assertEqual(first, B.Site().index(), "同样数据两次渲染必须逐字相同")

    def test_url_of_returns_first_registered_cell(self):
        site = B.Site()
        for item in site.items[:20]:
            urls = item.get("image_url") or []
            self.assertEqual(site.url_of(item["id"]), urls[0] if urls else None)


class AtlasLightbox(unittest.TestCase):
    """图集要能点开放大、左右翻页：缩略图是按钮，带原图地址，页尾挂灯箱与脚本。"""

    @classmethod
    def setUpClass(cls):
        cls.site = B.Site()
        cls.atlas = read("atlas.html")
        cls.index = read("index.html")
        cls.tiles = re.findall(r'<button type="button" class="tile"[^>]*>', cls.atlas)

    def test_every_place_has_a_tile_button(self):
        with_url = [it for it in self.site.items if self.site.url_of(it["id"])]
        self.assertEqual(len(self.tiles), len(with_url))

    def test_tiles_carry_full_url_and_id(self):
        base = self.site.oss["base_url"]
        for tag in self.tiles:
            full = re.search(r'data-full="([^"]+)"', tag)
            self.assertIsNotNone(full, tag)
            self.assertTrue(full.group(1).startswith(base), full.group(1)[:80])
            self.assertRegex(tag, r'data-id="[SDRFL]\d{2,3}"')
            self.assertRegex(tag, r'data-cap="[^"]+"')

    def test_old_anchor_tiles_are_gone(self):
        self.assertNotIn('<a class="tile"', self.atlas)

    def test_lightbox_markup_is_present(self):
        self.assertIn('id="lb"', self.atlas)
        self.assertIn('hidden', self.atlas.split('id="lb"')[1][:40])
        for act in ("prev", "next", "close"):
            self.assertIn('data-lb="%s"' % act, self.atlas)

    def test_lightbox_script_is_wired_and_exists(self):
        self.assertIn('<script src="lightbox.js" defer></script>', self.atlas)
        self.assertTrue((ROOT / "网站" / "lightbox.js").is_file())
        self.assertNotIn("lightbox.js", self.index, "只有图集页需要灯箱")

    def test_lightbox_script_has_navigation_and_zoom(self):
        with io.open(ROOT / "网站" / "lightbox.js", encoding="utf-8") as fp:
            js = fp.read()
        for token in ("ArrowLeft", "ArrowRight", "Escape", "wheel", "touchstart", "dblclick"):
            self.assertIn(token, js, token)
        self.assertIn("data-full", js)


if __name__ == "__main__":
    unittest.main()
