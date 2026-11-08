# -*- coding: utf-8 -*-
"""卡面资产闸门（工具/verify_card_faces.py）的正负测。

夹具一律建在 tempfile 目录里，只从仓库**读**真图当原料，不往被守护目录写任何东西。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(HERE, "verify_card_faces.py")
sys.path.insert(0, HERE)
CARDS = os.path.join(ROOT, "数据", "视觉控制资产", "卡牌", "768x1024")
DRAFT = os.path.join(ROOT, "数据", "卡面文案底稿.json")

# 一张有实景的、一张占位的、一张背面：三条支路各覆盖一次
SAMPLES = ["东湖金融线-L009-东岸企业会客厅-实际卡",
           "职业卡-三电系统实训-A14-实际卡",
           "兑换卡-背面-v01-CG写实"]


def run(root):
    p = subprocess.run([sys.executable, "-X", "utf8", GATE, "--root", root],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def build_fixture(tmp):
    """把三条样本连同底稿/manifest 的最小子集搬进 tmp，返回一个必须判绿的干净夹具。"""
    with open(DRAFT, encoding="utf-8") as fh:
        draft = json.load(fh)
    with open(os.path.join(CARDS, "manifest.json"), encoding="utf-8") as fh:
        man = json.load(fh)
    keep = set(SAMPLES)
    draft["items"] = [it for it in draft["items"] if os.path.splitext(it["file"])[0] in keep]
    man["cards"] = [c for c in man["cards"] if os.path.splitext(c["file"])[0] in keep]

    cards_dir = os.path.join(tmp, "数据", "视觉控制资产", "卡牌", "768x1024")
    for v in man["variants"]:
        os.makedirs(os.path.join(cards_dir, v))
        for stem in SAMPLES:
            shutil.copyfile(os.path.join(CARDS, v, stem + ".png"),
                            os.path.join(cards_dir, v, stem + ".png"))
    with open(os.path.join(cards_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False)
    os.makedirs(os.path.join(tmp, "数据"), exist_ok=True)
    with open(os.path.join(tmp, "数据", "卡面文案底稿.json"), "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False)
    return cards_dir, man


class CardFacesGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cards, self.man = build_fixture(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _manifest(self, mutate):
        with open(os.path.join(self.cards, "manifest.json"), encoding="utf-8") as fh:
            man = json.load(fh)
        mutate(man)
        with open(os.path.join(self.cards, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(man, fh, ensure_ascii=False)

    def test_干净夹具必须判绿(self):
        code, out = run(self.root)
        self.assertEqual(code, 0, out)

    def test_真仓必须判绿(self):
        code, out = run(ROOT)
        self.assertEqual(code, 0, out)

    def test_缺一张无文案必须判红(self):
        os.remove(os.path.join(self.cards, "无文案", SAMPLES[0] + ".png"))
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("与底稿不同名", out)

    def test_尺寸不是768x1024必须判红(self):
        p = os.path.join(self.cards, "有文案", SAMPLES[0] + ".png")
        Image.open(p).resize((768, 1023)).save(p)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("尺寸", out)

    def test_副标题留档号必须判红(self):
        def mutate(man):
            man["cards"][0]["subtitle"] = "景群套系·L009"
        self._manifest(mutate)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("仍含档号", out)

    def test_占位窗与状态不符必须判红(self):
        def mutate(man):
            for c in man["cards"]:
                if c["file"].startswith("东湖金融线-L009"):
                    c["status"] = "MISSING"
        self._manifest(mutate)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("占位窗判据与状态不符", out)

    def test_源放不下必须判红(self):
        def mutate(man):
            man["cards"].append({"file": "古城记忆线-L022-白石钟楼-实际卡.png",
                                 "template": "landmark", "status": "OVERFLOW",
                                 "subtitle": "景群套系", "bottom": ""})
        self._manifest(mutate)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("放不下窗幅", out)

    def test_无文案版底部叠字必须判红(self):
        p = os.path.join(self.cards, "无文案", SAMPLES[0] + ".png")
        from verify_card_faces import body_rect, BOTTOM_BAND
        with Image.open(p) as im:
            im = im.convert("RGB")
            bx, by, bw, bh = body_rect(*im.size)
            top = by + round(bh * BOTTOM_BAND[0])
            for px in range(bx + bw // 8, bx + bw - bw // 8):
                im.putpixel((px, top + 5), (30, 26, 22))
            im.save(p)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("无文案版底部文字带仍有墨", out)

    def test_有文案版底部丢字必须判红(self):
        p = os.path.join(self.cards, "有文案", SAMPLES[0] + ".png")
        plain = os.path.join(self.cards, "无文案", SAMPLES[0] + ".png")
        shutil.copyfile(plain, p)
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("有文案版底部文字带无墨", out)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    unittest.main()
