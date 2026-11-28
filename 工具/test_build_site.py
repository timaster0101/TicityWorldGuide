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

PAGES = ("index.html", "locations.html", "map.html", "atlas.html")


def read(name):
    with io.open(ROOT / "网站" / name, encoding="utf-8") as fp:
        return fp.read()


class PagesExist(unittest.TestCase):
    def test_all_pages_on_disk(self):
        for name in PAGES:
            self.assertTrue((ROOT / "网站" / name).is_file(), name)

    def test_stylesheets_linked(self):
        for name in PAGES:
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
        cls.map = read("map.html")

    def test_every_location_is_listed_once(self):
        for item in self.site.items:
            hits = self.loc.count('data-search="%s ' % item["id"].lower())
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
        for name in ("index.html", "atlas.html"):
            for url in re.findall(r'<img[^>]+src="([^"]+)"', read(name)):
                self.assertTrue(url.startswith(base), "%s 里出现非图床地址：%s" % (name, url[:80]))
                self.assertNotIn(" ", url, "%s 里的地址含空格" % name)

    def test_no_placeholder_or_none_leaked(self):
        for name in PAGES:
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

    def test_version_tag_matches_the_generator(self):
        for name in PAGES:
            self.assertIn(B.SITE_VERSION, read(name), name)


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

    def test_volume_of_points_at_a_real_volume(self):
        site = B.Site()
        for item in site.items:
            vol = site.volume_of(item["id"])
            self.assertTrue(vol, item["id"])
            self.assertTrue((ROOT / vol).is_file(), vol)


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

    def test_tiles_have_anchor_ids_for_deep_links(self):
        ids = re.findall(r'class="tile" id="t-([SDRFL]\d{2,3})"', self.atlas)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(self.tiles))

    def test_old_anchor_tiles_are_gone(self):
        self.assertNotIn('<a class="tile"', self.atlas)

    def test_lightbox_markup_is_present(self):
        self.assertIn('id="lb"', self.atlas)
        open_tag = re.search(r'<div class="lb"[^>]*>', self.atlas).group(0)
        self.assertIn("hidden", open_tag, open_tag)
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


class ShareableAndAccessible(unittest.TestCase):
    """分享卡片、图标、无障碍：每页都要能发出去像张卡，弹层要能读屏。"""

    @classmethod
    def setUpClass(cls):
        cls.site = B.Site()
        cls.atlas = read("atlas.html")

    def test_every_page_has_social_and_icon_meta(self):
        for name in PAGES:
            text = read(name)
            self.assertIn('rel="icon" href="data:image/svg+xml,', text, name)
            self.assertIn('<meta name="theme-color" content="#25292d" />', text, name)
            for prop in ("og:type", "og:title", "og:description", "og:image", "og:locale"):
                self.assertIn('property="%s"' % prop, text, name)
            self.assertIn('name="twitter:card"', text, name)
            self.assertIn('name="twitter:image"', text, name)

    def test_og_image_is_absolute_bucket_url(self):
        base = self.site.oss["base_url"]
        for name in PAGES:
            m = re.search(r'property="og:image" content="([^"]+)"', read(name))
            self.assertIsNotNone(m, name)
            self.assertTrue(m.group(1).startswith(base), m.group(1)[:80])

    def test_lightbox_is_a_labelled_modal(self):
        start = self.atlas.split('id="lb"')[0][-120:] + self.atlas.split('id="lb"')[1][:200]
        self.assertIn('role="dialog"', start)
        self.assertIn('aria-modal="true"', start)
        self.assertIn('aria-label=', start)

    def test_script_traps_focus_and_hides_background(self):
        with io.open(ROOT / "网站" / "lightbox.js", encoding="utf-8") as fp:
            js = fp.read()
        for token in ("'Tab'", "focusables", "aria-hidden"):
            self.assertIn(token, js, token)

    def test_stylesheet_honours_reduced_motion(self):
        with io.open(ROOT / "网站" / "site.css", encoding="utf-8") as fp:
            css = fp.read()
        self.assertIn("prefers-reduced-motion", css)


class VersionsAndSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = B.Site()
        cls.atlas = read("atlas.html")
        cls.loc = read("locations.html")

    def test_multi_cell_places_expose_versions(self):
        base = self.site.oss["base_url"]
        tags = re.findall(r'<button type="button" class="tile"[^>]*data-versions="([^"]+)"', self.atlas)
        self.assertTrue(tags, "至少要有条目带历代版本")
        for raw in tags:
            urls = raw.split("|")
            self.assertGreater(len(urls), 1)
            for u in urls:
                self.assertTrue(u.startswith(base), u[:80])

    def test_version_list_matches_the_manifest_cells(self):
        site = self.site
        multi = [it for it in site.items if len(site.versions_of(it["id"])) > 1]
        self.assertTrue(multi)
        for it in multi[:40]:
            joined = "|".join(site.versions_of(it["id"]))
            self.assertIn('data-versions="%s"' % joined, self.atlas, it["id"])

    def test_locations_page_has_a_search_box(self):
        self.assertIn('id="q"', self.loc)
        self.assertIn('type="search"', self.loc)
        self.assertIn('id="count"', self.loc)
        self.assertIn("data-search=", self.loc)

    def test_filter_script_filters_by_text_too(self):
        js = B.FILTER_JS
        for token in ("data-search", "toLowerCase", "'input'", "count"):
            self.assertIn(token, js, token)

    def test_row_links_jump_to_atlas_and_volume(self):
        site = self.site
        for item in site.items[:30]:
            self.assertIn('href="atlas.html#t-%s"' % item["id"], self.loc, item["id"])
            vol = site.volume_of(item["id"])
            self.assertIn('href="%s%s"' % (B.REPO_BLOB, vol), self.loc, item["id"])
            self.assertIn('id="t-%s"' % item["id"], self.atlas, item["id"])


class MapPage(unittest.TestCase):
    def test_map_page_embeds_the_three_svgs(self):
        text = read("map.html")
        for name, _title, _note in B.MAPS:
            self.assertTrue((ROOT / name).is_file(), name)
            self.assertIn('src="地图/%s"' % name, text, name)
            copy = ROOT / "网站" / "地图" / name
            self.assertTrue(copy.is_file(), copy)
            self.assertEqual(copy.stat().st_size, (ROOT / name).stat().st_size, name)

    def test_nav_and_footer_link_the_map(self):
        for name in PAGES:
            text = read(name)
            self.assertIn('<a href="map.html"', text, name)


if __name__ == "__main__":
    unittest.main()
