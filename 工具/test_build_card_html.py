#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_card_html.py 正负测。夹具走 tempfile 并 monkeypatch OUT_DIR，不往被守护仓库写一个字节。"""
import json
import os
import re
import tempfile
import unittest

import build_card_html as B
import card_geometry as G


def load_manifest():
    with open(B.MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


class BuildCardHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig_out = B.OUT_DIR
        B.OUT_DIR = self.tmp.name
        self.addCleanup(setattr, B, "OUT_DIR", self._orig_out)

    def _run(self):
        rc = B.main([])
        self.assertEqual(rc, 0)
        return self.tmp.name

    def test_emits_all_expected_files(self):
        out = self._run()
        for f in ("card.css", "template.html", "cards.json", "index.html"):
            self.assertTrue(os.path.exists(os.path.join(out, f)), f + " 缺失")
        self.assertEqual(len(os.listdir(os.path.join(out, "cards"))), 124)

    def test_records_match_manifest_counts(self):
        self._run()
        recs = json.load(open(os.path.join(self.tmp.name, "cards.json"), encoding="utf-8"))
        man = load_manifest()["cards"]
        self.assertEqual(len(recs), len(man))
        self.assertEqual(sum(1 for r in recs if r["status"] == "OK"),
                         sum(1 for c in man if c["status"] == "OK"))

    def test_ok_cards_have_main_image_others_placeholder(self):
        man = load_manifest()["cards"]
        # 按 idx 取，不按 code：34 张待投卡的 code 是空串，补投转 OK 后它们在 code 字典里会互相顶掉
        by_idx = {c["idx"]: c for c in man}
        self._run()
        recs = json.load(open(os.path.join(self.tmp.name, "cards.json"), encoding="utf-8"))
        for r in recs:
            if r["status"] == "OK":
                self.assertTrue(r["main_image"], "idx%s OK 应有主图" % r["idx"])
                self.assertFalse(os.path.isabs(r["main_image"]), "主图须是相对路径")
                self.assertFalse(re.match(r"^[A-Za-z]:", r["main_image"]), "主图不得带盘符")
                self.assertTrue(r["main_image"].replace("\\", "/").endswith(
                    os.path.basename(by_idx[r["idx"]]["source"])),
                    "主图应指向该卡 manifest.source 的 basename：" + r["main_image"])
            else:
                self.assertIsNone(r["main_image"], "idx%s 非 OK 不该有主图" % r["idx"])

    def test_template_faces_are_not_counted_as_pending_scene(self):
        """用户 2026-11-08 拍板档 A：模板背面 5／模板正面 5 走程序模板面、不投实景，
        所以 cards.json 要把这十张标成 template_face，且「实景待投」只数其余无主图的卡。"""
        man = load_manifest()["cards"]
        faces = [c["card_type"] for c in man if c["card_type"] in B.TEMPLATE_FACES]
        self.assertEqual(faces.count("模板背面"), 5)
        self.assertEqual(faces.count("模板正面"), 5)
        self._run()
        recs = json.load(open(os.path.join(self.tmp.name, "cards.json"), encoding="utf-8"))
        flagged = [r for r in recs if r["template_face"]]
        self.assertEqual(len(flagged), 10)
        self.assertTrue(all(r["main_image"] is None for r in flagged), "模板面不该有主图")
        pending = sum(1 for r in recs if not r["main_image"] and not r["template_face"])
        self.assertEqual(pending, sum(1 for c in man if c["status"] in ("MISSING", "OVERFLOW")) - 5)
        html = open(os.path.join(self.tmp.name, "index.html"), encoding="utf-8").read()
        self.assertIn("模板正面", html)
        self.assertEqual(html.count('<div class="placeholder">实景待投</div>'), pending * 2,
                         "index.html 每张卡有/无文案两个变体，故待投占位窗应为 2×")

    def test_index_legend_counts_follow_records_not_hardcoded(self):
        """图例里的三个数必须随记录走：造 1 有图／1 模板面／1 待投的假记录，字面量 80/10/34 一律不许出现。
        此前这三个数是手抄在模板里的，补投转 OK 后会静默挂着旧读数骗人。"""
        base = {"idx": 1, "card_type": "景群地标卡", "template": "landmark", "title": "T",
                "subtitle": "S", "bottom": "B", "seal": "s.png", "file": "x-1.png", "code": "L001"}
        with_img = dict(base, status="OK", main_image="m.png", template_face=False)
        face = dict(base, idx=2, code="T01", status="BACK", main_image=None, template_face=True,
                    card_type="模板正面")
        pending = dict(base, idx=3, code="", status="MISSING", main_image=None, template_face=False,
                       file="idx007-T1轻量-城市主题壁纸包.png", card_type="兑换卡")
        html = B.render_index([with_img, face, pending])
        self.assertIn("现 1 张", html)
        self.assertIn("共 1 张走程序模板面", html)
        self.assertIn("其余 1 张 MISSING", html)
        for stale in ("现 80 张", "共 10 张走程序模板面", "其余 34 张 MISSING"):
            self.assertNotIn(stale, html)
        self.assertEqual(html.count('class="card'), 6, "三张卡 × 有/无文案两个变体")

    def test_district_title_splits_into_gold_and_bright(self):
        rec = {"template": "district", "title": "城市片区·北湖政务片区"}
        lines = B.title_lines(rec)
        self.assertEqual([cls for _, cls in lines], ["gold", "bright"])
        self.assertEqual(lines[0][0], "城市片区·")

    def test_landmark_title_single_bright_line(self):
        rec = {"template": "landmark", "title": "东湖金融线·东岸企业会客厅"}
        lines = B.title_lines(rec)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0][1], "bright")

    def test_index_has_two_variants_per_card(self):
        out = self._run()
        html = open(os.path.join(out, "index.html"), encoding="utf-8").read()
        self.assertEqual(html.count('class="card'), 248)
        self.assertIn("cards.json", html)

    def test_bottom_text_only_in_with_text_variant(self):
        rec = {"template": "landmark", "title": "T", "subtitle": "S",
               "bottom": "底部文案", "main_image": "x.png", "seal": "s.png", "status": "OK"}
        self.assertIn("底部文案", B.render_card_html(rec, "有文案"))
        self.assertNotIn("底部文案", B.render_card_html(rec, "无文案"))

    def test_escapes_html_in_text(self):
        rec = {"template": "info", "title": "<script>x</script>", "subtitle": "",
               "bottom": "", "main_image": "x.png", "seal": "s.png", "status": "OK"}
        out = B.render_card_html(rec, "有文案")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_missing_card_renders_placeholder_not_broken_image(self):
        rec = {"template": "info", "card_type": "兑换卡", "title": "T1轻量", "subtitle": "兑换卡",
               "bottom": "", "main_image": None, "seal": "s.png", "status": "MISSING"}
        out = B.render_card_html(rec, "有文案")
        self.assertIn('class="placeholder"', out)
        self.assertIn("实景待投", out)
        self.assertNotIn('<img class="bg"', out)

    def test_template_face_card_is_labeled_as_template_not_pending(self):
        """档 A 拍板的负向侧：模板正面不许再显示「实景待投」，否则它会永远挂在待投队列里。"""
        rec = {"template": "info", "card_type": "模板正面", "title": "兑换",
               "subtitle": "积攒卡牌积分兑换现实权益", "bottom": "",
               "main_image": None, "seal": "s.png", "status": "MISSING"}
        out = B.render_card_html(rec, "有文案")
        self.assertIn("模板正面", out)
        self.assertNotIn("实景待投", out)

    def test_single_card_document_rebases_image_srcs_one_level_deeper(self):
        """cards/*.html 比 index.html 深一层目录，主图与印章 src 必须多补一个 ../，
        否则单卡文件里的两张图全断链（渲染器正式化后第一次实读发现的实际缺陷）。"""
        rec = {"template": "landmark", "card_type": "景群地标卡", "title": "T", "subtitle": "",
               "bottom": "", "main_image": "../视觉控制资产/卡牌/主图3x4/L009.png",
               "seal": "../运行时资产/印章-已获得-酒红.png", "status": "OK"}
        index_html = B.render_card_html(rec, "有文案")
        single_html = B.render_card_html(rec, "有文案", "../")
        self.assertIn('src="../视觉控制资产/卡牌/主图3x4/L009.png"', index_html)
        self.assertIn('src="../运行时资产/印章-已获得-酒红.png"', index_html)
        self.assertIn('src="../../视觉控制资产/卡牌/主图3x4/L009.png"', single_html)
        self.assertIn('src="../../运行时资产/印章-已获得-酒红.png"', single_html)
        self.assertNotIn('src="../视觉控制资产', single_html)
        self.assertNotIn('src="../运行时资产', single_html)

    def test_panel_does_not_blur_over_the_aigc_badge(self):
        """浮层不许对主图做 backdrop-filter：平台强制的「AI生成」角标就落在台标带里
        （114 张全量实测上沿最靠内 1024−52.6＝971.4 px，浮层上沿 973.5 px），6px 模糊把它糊成三团亮斑
        ＝遮盖 AIGC 标识，属合规红线。同一条也钉住浮层仍是用户点单的「暗黑色 70% 透明」——
        改成不透明同样是遮盖，所以底色字面量与变量引用一起验。"""
        out = self._run()
        for f in ("card.css", "index.html", "template.html"):
            with open(os.path.join(out, f), encoding="utf-8") as fh:
                text = fh.read()
            self.assertNotIn("backdrop-filter", text, f + " 不许给浮层加背景模糊")
        files = os.listdir(os.path.join(out, "cards"))
        self.assertEqual(len(files), 124)
        for f in files:
            with open(os.path.join(out, "cards", f), encoding="utf-8") as fh:
                self.assertNotIn("backdrop-filter", fh.read(), f + " 不许内联背景模糊")
        with open(os.path.join(out, "card.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertEqual(B.PANEL_BG, "rgba(0,0,0,.3)", "浮层底色档位属用户点单，改它要走裁定")
        self.assertIn("--panel-bg:" + B.PANEL_BG, css)

    def test_seal_css_percentages_are_derived_not_recopied(self):
        """渲染器不许再抄一份印章落点数字：CSS 里的百分字面量必须由 card_geometry.SEAL_LANDING_B 换算而来。
        改了常数没改 CSS（或反之）都会在这里判红。"""
        l = G.SEAL_LANDING_B
        for key, prop in (("size_r", "width"), ("right_r", "right"), ("bottom_r", "bottom")):
            want = "%s:%s%%" % (prop, B.pct(l[key]))
            self.assertIn(want, B.CSS, "CSS 的 %s 没跟随常数 %s=%s" % (prop, key, l[key]))
        self.assertEqual([B.pct(l[k]) for k in ("size_r", "right_r", "bottom_r")], ["27.6", "4", "19"])

    def test_seal_landing_clears_badge_band_at_measured_box(self):
        """落点换算须对平 2026-11-08 Chrome 实测包围盒（实测 (525,618)-(737,829)，换算 y0=617.47 取整差 1 px），
        且可见章面下沿让开右下台标带（44 px）。"""
        self.assertEqual(G.seal_box_canvas(), (525, 617, 737, 829))
        vis = G.seal_visible_box_canvas()
        self.assertEqual(vis, (537, 627, 726, 816))
        self.assertLessEqual(vis[3], G.CANVAS[1] - G.SEAL_BADGE_BAND)
        # 反证：下内缩归零时章面必然压进台标带，证明这条判据不是恒真
        tight = G.seal_visible_box_canvas({"size_r": 0.276, "right_r": 0.04, "bottom_r": 0.0})
        self.assertGreater(tight[3], G.CANVAS[1] - G.SEAL_BADGE_BAND)

    def test_seal_diameter_is_the_ruling_backed_212px(self):
        """章径档位是 2026-11-08 用户「都做」拍板的 212 px（烤图时代裁定「章径＝本体宽 1/3」的视觉尺寸），
        不是路线 B 转档时顺手抄的 184.3；改这一档须走裁定，不许在这里悄悄换个 size_r。"""
        self.assertEqual(round(G.CANVAS[0] * G.SEAL_LANDING_B["size_r"]), 212)
        x0, y0, x1, y1 = G.seal_box_canvas()
        self.assertEqual((x1 - x0, y1 - y0), (212, 212))

    def test_badge_band_is_the_minimal_cover_of_the_full_bleed_measurement(self):
        """SEAL_BADGE_BAND 不许与 `数据/台标带实测.json` 脱钩：它必须盖住满幅实测的台标上沿，
        且取最小覆盖整数。两头各有一条判据——调小判「章面压进台标带」，调大判「白丢净空」，
        重测后台标更靠内也在这里当场翻红，不用人记着去抬常数。"""
        with open(os.path.join(B.ROOT, "数据", "台标带实测.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        dist = [r["dist_above_photo_bottom"] for r in m["rows"] if r.get("detected")]
        self.assertEqual(len(m["rows"]), m["检出"] + m["未检出"], "实测件统计面与明细不平")
        self.assertGreaterEqual(G.SEAL_BADGE_BAND, max(dist), "台标带低于实测最靠内的台标上沿：章面会压台标")
        self.assertLess(G.SEAL_BADGE_BAND - 1, max(dist), "台标带不是最小覆盖值：白丢了印章净空")


if __name__ == "__main__":
    unittest.main()
