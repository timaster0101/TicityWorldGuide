# -*- coding: utf-8 -*-
"""印章素材漂移闸门（工具/verify_seal_asset.py）的正负测。

夹具一律建在 tempfile 目录里，只从仓库**读**真素材当原料，不往被守护目录写任何东西。
负测覆盖：素材缺失／外接框漂移／全透明三种违例，并先证干净夹具判绿（闸门非恒红）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(HERE, "verify_seal_asset.py")
sys.path.insert(0, HERE)
ASSET_REL = os.path.join("数据", "运行时资产", "印章-已获得-酒红.png")
REAL_ASSET = os.path.join(ROOT, ASSET_REL)


def run(root):
    p = subprocess.run([sys.executable, "-X", "utf8", GATE, "--root", root],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def put_asset(root, img):
    p = os.path.join(root, ASSET_REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p)
    return p


def synthetic_seal(box):
    im = Image.new("RGBA", (720, 720), (0, 0, 0, 0))
    if box is not None:
        ImageDraw.Draw(im).rectangle(box, fill=(160, 39, 57, 255))
    return im


class SealAssetGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_真仓素材必须判绿(self):
        code, out = run(ROOT)
        self.assertEqual(code, 0, out)
        self.assertIn("印章素材漂移闸门：通过", out)

    def test_干净夹具必须判绿(self):
        shutil.copyfile(REAL_ASSET, put_asset(self.root, Image.open(REAL_ASSET).convert("RGBA")))
        code, out = run(self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("通过", out)

    def test_素材缺失必须判红(self):
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("缺少印章素材", out)

    def test_素材外接框漂移必须判红(self):
        # 墨迹框挪到 (10,10,710,710)，占比 (0.014,0.014,0.986,0.986)，逐边偏离 SEAL_VIS >0.04
        put_asset(self.root, synthetic_seal((10, 10, 710, 710)))
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("偏离 SEAL_VIS", out)

    def test_全透明素材必须判红(self):
        put_asset(self.root, synthetic_seal(None))
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("全透明", out)


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    unittest.main()