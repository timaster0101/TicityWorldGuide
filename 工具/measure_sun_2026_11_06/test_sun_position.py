# -*- coding: utf-8 -*-
"""sun_position.py 的单测（正测 + 违例负测，全部内存构造，盘上零残留）。

夹具口径：numpy 直接生成「L」图喂 PIL，正常路径不落盘；唯一必须落盘的路径
（main() 按文件路径读 PNG）走 tempfile.TemporaryDirectory，tearDown 强制删除
并复核目录确已消失。

负测的「绿→红」结构申报：本项目硬规矩要求负测不是「只断言不报错」，
每条负测都同时给出两面——
① 本判据在该形态下必须给指定读数（哨兵全 None / 下半区 0 / 取最大块）；
② 同数据用「违例口径」旁算（整图不切半区 / 首个块优先 / 把无检出读成 (0,0)）
   必然得到不同的数——即这条判据不注入违例时是绿的、注入后必须红。
"""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import sun_position as sp  # noqa: E402


def gray_image(arr):
    return Image.fromarray(arr, mode="L")


def blob(ny, nx, y0, x0, h, w, value=255):
    """在上半区放一个 h x w 实心亮块（夹具自检：整块必须落在 ny//2 以上）。"""
    assert 0 <= y0 and y0 + h <= ny // 2, "夹具违例：块越出上半区"
    assert x0 + w <= nx
    a = np.full((ny, nx), 10, dtype=np.uint8)
    a[y0:y0 + h, x0:x0 + w] = value
    return a


def ellipse_disk(ny, nx, cx, cy, rx, ry, value=255):
    yy, xx = np.mgrid[0:ny, 0:nx]
    m = ((xx - cx) / float(rx)) ** 2 + ((yy - cy) / float(ry)) ** 2 <= 1.0
    return np.where(m, value, 10).astype(np.uint8)


def cell_mean_of(mask2d):
    """降采样格中心均值口径（被本实现否决的那种），供负测对照。"""
    ys, xs = np.nonzero(mask2d)
    cells = {(y // 4, x // 4) for y, x in zip(ys, xs)}
    return (np.mean([c[1] * 4 + 2 for c in cells]), np.mean([c[0] * 4 + 2 for c in cells]))


class SunPositionPositiveTests(unittest.TestCase):
    def test_known_disk_centroid_ratio_bbox_area(self):
        # 400x200（宽x高），上半区 rows 0..99；实心盘 rows 40..79, cols 160..199
        a = blob(200, 400, y0=40, x0=160, h=40, w=40)
        r = sp.sun_position(gray_image(a))
        ys, xs = np.nonzero(a[:100] >= 250)
        # 质心＝原始像素均值（申报口径）
        self.assertEqual(r["cx_px"], int(round(float(xs.mean()))))
        self.assertEqual(r["cy_px"], int(round(float(ys.mean()))))
        # 比例两位小数
        self.assertEqual(r["cx_ratio"], round(float(xs.mean()) / 400, 2))
        self.assertEqual(r["cy_ratio"], round(float(ys.mean()) / 200, 2))
        # 包围盒（原分辨率、右/下缘开区间）
        self.assertEqual(r["bbox"], [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1])
        self.assertEqual(r["bbox"], [160, 40, 200, 80])
        # 面积＝格口径 *16（恰好铺满 10x10 格）
        self.assertEqual(r["area_px"], 10 * 10 * 16)
        self.assertEqual((r["w"], r["h"]), (400, 200))

    def test_area_matches_reference_sun_blob(self):
        # 与历史脚本 sun_blob 对拍：同图同口径必须同数（三枚夹具含铺满/非对齐/整幅过阈）
        spec = importlib.util.spec_from_file_location(
            "measure_images_ref", HERE.parent / "reinject_2026_11_05" / "measure_images.py")
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
        fixtures = [blob(200, 400, 40, 160, 40, 40),
                    blob(140, 140, 6, 7, 26, 30),
                    ellipse_disk(200, 400, 190, 55, 26, 19)]
        for a in fixtures:
            img = gray_image(a)
            self.assertEqual(sp.sun_position(img)["area_px"], ref.sun_blob(img))

    def test_centroid_is_original_pixel_mean_not_cell_center_mean(self):
        # 偏心灵形盘：两种均值口径的取整读数必 differing（夹具先自证分歧存在）
        a = ellipse_disk(200, 400, 190, 55, 26, 19)
        top = a[:100]
        pm = (float(np.nonzero(top >= 250)[1].mean()), float(np.nonzero(top >= 250)[0].mean()))
        cm = cell_mean_of(top >= 250)
        self.assertTrue(int(round(pm[0])) != int(round(cm[0])) or int(round(pm[1])) != int(round(cm[1])),
                        "夹具失效：两口径未分歧，本测失去意义")
        r = sp.sun_position(gray_image(a))
        self.assertEqual((r["cx_px"], r["cy_px"]), (int(round(pm[0])), int(round(pm[1]))))
        # 反面对照：若实现错取格中心均值，读数会等于 cm——本实现必须与 cm 至少一轴不同
        self.assertTrue(r["cx_px"] != int(round(cm[0])) or r["cy_px"] != int(round(cm[1])))


class SentinelNegativeTests(unittest.TestCase):
    def test_no_bright_pixel_returns_explicit_none_not_zero_zero(self):
        # ① 违例负测：整图 249（合法灰度但不过阈）必须走哨兵。
        a = np.full((120, 160), 249, dtype=np.uint8)
        r = sp.sun_position(gray_image(a))
        self.assertEqual(r["area_px"], 0)
        self.assertEqual((r["cx_px"], r["cy_px"], r["bbox"]), (None, None, None))
        self.assertEqual((r["cx_ratio"], r["cy_ratio"]), (None, None))
        # 哨兵不得长得像「日面在左上」：断言它是 None 而不是可被误读的 0
        self.assertIsNotNone(r["w"] and r["h"], "尺寸字段仍须给出（哨兵只空位置）")
        self.assertNotEqual((r["cx_px"], r["cy_px"]), (0, 0))
        # 绿→红双向证据：同尺寸注入真盘后判据转「有读数」，证明哨兵分支不是恒真兜底
        r2 = sp.sun_position(gray_image(blob(120, 160, 10, 10, 16, 16)))
        self.assertIsNotNone(r2["cx_px"])
        self.assertGreater(r2["area_px"], 0)

    def test_upper_left_disk_gives_small_not_none(self):
        # 与哨兵形成可区分两极：左上角真有日盘时读数就应在 (0,0) 附近且非 None
        r = sp.sun_position(gray_image(blob(120, 160, 0, 0, 12, 12)))
        self.assertLess(r["cx_px"], 10)
        self.assertLess(r["cy_px"], 10)
        self.assertIsNotNone(r["bbox"])


class UpperHalfOnlyNegativeTests(unittest.TestCase):
    def test_lower_half_bright_block_must_not_count(self):
        # ② 违例负测：下半区放超亮大块（40x80），上半区口径必须给 0。
        a = np.zeros((200, 400), dtype=np.uint8)
        a[120:160, 200:280] = 255
        r = sp.sun_position(gray_image(a))
        self.assertEqual(r["area_px"], 0)
        self.assertIsNone(r["bbox"])
        # 「不切半区」的违例口径旁算：同图整图过阈像素 >0，
        # 证明 0 是半区限制产生的判据读数，不是这张图本来就没有极亮像素。
        self.assertGreater(int((a >= 250).sum()), 0)
        # 绿→红双向证据：把同一块镜像到上半区，判据必须转「有」
        a_top = np.zeros_like(a)
        a_top[40:80, 200:280] = 255
        self.assertEqual(sp.sun_position(gray_image(a_top))["area_px"], 10 * 20 * 16)

    def test_block_across_half_boundary_clipped_at_half_height(self):
        # 跨分界线块 rows 85..114：bbox 下缘必须恰停在 y=100（上半区上界），
        # 面积只计上半区侧格（rows 84..99 带内过阈像素）＝40 格 *16＝640。
        a = np.zeros((200, 400), dtype=np.uint8)
        a[85:115, 100:140] = 255
        r = sp.sun_position(gray_image(a))
        self.assertEqual(r["bbox"], [100, 85, 140, 100])
        self.assertEqual(r["area_px"], 640)
        self.assertLessEqual(r["bbox"][3], 200 // 2)


class LargestBlobNegativeTests(unittest.TestCase):
    def test_max_blob_chosen_not_first_encountered(self):
        # ③ 违例负测：左上 8x8 小块在洪水填充先见序在前，右下 40x60 大块在后。
        # 取「第一个遇到的」质心会落在 (6,6) 附近；必须证明取的是最大块。
        a = np.full((200, 400), 10, dtype=np.uint8)
        a[4:12, 4:12] = 255
        a[40:80, 300:360] = 255
        r = sp.sun_position(gray_image(a))
        self.assertEqual(r["area_px"], 10 * 15 * 16)
        self.assertEqual(r["bbox"], [300, 40, 360, 80])
        self.assertGreaterEqual(r["cx_px"], 325)
        small_centroid = sp.sun_position(gray_image(blob(200, 400, 4, 4, 8, 8)))
        self.assertLess(small_centroid["cx_px"], 10, "对照读数确认小块质心就在左上——两者不可混")
        # 绿→红双向证据：把两块面积对调（右下改小块、中部改大块），
        # 判据读数必须跟着翻到新的最大块，而不是钉死在某个位置或先见块。
        b = np.full((200, 400), 10, dtype=np.uint8)
        b[4:12, 4:12] = 255
        b[44:68, 304:328] = 255
        b[30:70, 100:200] = 255
        rb = sp.sun_position(gray_image(b))
        self.assertEqual(rb["bbox"][:2], [100, 30])
        self.assertGreater(rb["area_px"], r["area_px"])


class TempFileHygieneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sunpos_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertFalse(Path(self.tmp).exists(), "tearDown 复核：临时目录必须已删除")

    def test_cli_main_reads_png_from_tempfile_only(self):
        # 唯一落盘面：命令行按路径读 PNG。文件只进 tempfile，不进仓库。
        src = Path(self.tmp) / "fake.png"
        Image.fromarray(blob(200, 400, 40, 160, 40, 40)).save(src)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sp.main([str(src)])
        self.assertEqual(code, 0)
        line = json.loads(buf.getvalue().strip())
        self.assertEqual(line["file"], str(src))
        self.assertEqual(line["area_px"], 1600)
        self.assertEqual(line["cx_px"], 180)
        r = sp.sun_position_file(src)
        self.assertEqual((r["w"], r["h"]), (400, 200))


if __name__ == "__main__":
    unittest.main()
