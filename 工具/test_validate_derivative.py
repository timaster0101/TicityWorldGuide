# -*- coding: utf-8 -*-
"""`validate_derivative.py` 的判据测试：每条判据都要有「判红」与「不误判」两面。

只用 check_text 的纯函数面造夹具（不依赖真实正典的具体数值），
另加两条真实正典的接线测试与一条 CLI 退出码测试。
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_derivative as V  # noqa: E402

ENTRIES = {
    "D01": {"id": "D01", "name": "北湖政务片区", "type": "城市片区", "floors": None, "height_m": None},
    "D02": {"id": "D02", "name": "东北文教片区", "type": "城市片区"},
    "F001": {"id": "F001", "name": "湖政公共服务轴", "type": "功能区"},
    "L019": {"id": "L019", "name": "西声大剧院", "type": "标志性建筑", "floors": 6, "height_m": 32},
    "L021": {"id": "L021", "name": "风帆设计工坊", "type": "标志性建筑", "floors": 15, "height_m": 66},
    "L069": {"id": "L069", "name": "云浦结算中心", "type": "标志性建筑", "floors": 69, "height_m": 276},
    "R001": {"id": "R001", "name": "北湖第一居住区", "type": "居民区"},
}
RULINGS = {"C1", "C2", "C157"}
GLOBALS = {"region_area_km2": 4608, "regional_total": 3574200,
           "city_core": 3200000, "urban_radius_km": 10.2}


def run(text):
    return V.check_text(text, ENTRIES, RULINGS, GLOBALS)


def codes(text):
    return [f["code"] for f in run(text)]


class CleanText(unittest.TestCase):
    def test_plain_sentence_has_no_findings(self):
        t = "周敏从 R001 走到 F001，用了二十分钟。这件事发生在 2013 年的秋天。"
        self.assertEqual(run(t), [])

    def test_correct_scale_is_not_flagged(self):
        t = "云浦结算中心在正典里是 69 层、276 米。"
        self.assertEqual(codes(t), [])

    def test_tolerates_descriptive_noun_after_id(self):
        # 「D02 食品配送支持场馆」这类描述性写法不该判成名称错
        t = "D02 食品配送支持场馆的冷链货车不穿过广场。"
        self.assertNotIn("NAME_MISMATCH", codes(t))

    def test_tolerates_canon_name_as_prefix(self):
        t = "F001 湖政公共服务轴偏中心东南侧。"
        self.assertNotIn("NAME_MISMATCH", codes(t))


class UnknownId(unittest.TestCase):
    def test_reds(self):
        self.assertIn("UNKNOWN_ID", codes("新城 D21 在一片稻田上。"))

    def test_not_fooled_by_version_strings(self):
        self.assertEqual(codes("参照 SCHEMA 第 4 节与 LVL2 档。"), [])


class TypeMismatch(unittest.TestCase):
    def test_reds(self):
        self.assertIn("TYPE_MISMATCH", codes("居民区 L069 里住着三万人。"))

    def test_right_type_passes(self):
        self.assertNotIn("TYPE_MISMATCH", codes("居民区 R001 里住着两千人。"))


class NameMismatch(unittest.TestCase):
    def test_reds(self):
        self.assertIn("NAME_MISMATCH", codes("他在 D01 东湖金融片区上班。"))

    def test_right_name_passes(self):
        self.assertNotIn("NAME_MISMATCH", codes("他在 D01 北湖政务片区上班。"))


class ScaleConflict(unittest.TestCase):
    def test_floors_reds(self):
        found = [f for f in run("云浦结算中心只有 8 层。") if f["code"] == "SCALE_CONFLICT"]
        self.assertEqual(len(found), 1)
        self.assertIn("69", found[0]["message"])

    def test_height_reds(self):
        self.assertIn("SCALE_CONFLICT", codes("云浦结算中心高 40 米。"))

    def test_height_within_tolerance_passes(self):
        self.assertNotIn("SCALE_CONFLICT", codes("云浦结算中心高 270 米。"))

    def test_nearest_location_wins_in_a_list(self):
        # 一句里并列三方：每个数字只能算到它前面最近的那个地点
        t = "L019 为 6 层、32 米，L021 为 15 层、66 米。"
        self.assertEqual(codes(t), [])

    def test_list_with_one_wrong_item_reds_once(self):
        t = "L019 为 6 层、32 米，L021 为 9 层、66 米。"
        found = [f for f in run(t) if f["code"] == "SCALE_CONFLICT"]
        self.assertEqual(len(found), 1)
        self.assertIn("L021", found[0]["message"])


class GlobalNumbers(unittest.TestCase):
    def test_population_reds(self):
        self.assertIn("GLOBAL_NUMBER", codes("全市人口约 120 万。"))

    def test_population_correct_passes(self):
        self.assertNotIn("GLOBAL_NUMBER", codes("区域总人口 357 万。"))

    def test_city_core_is_allowed(self):
        self.assertNotIn("GLOBAL_NUMBER", codes("中心城人口 320 万。"))

    def test_area_reds(self):
        self.assertIn("GLOBAL_NUMBER", codes("区域面积 3000 平方公里。"))


class FictionAndRulings(unittest.TestCase):
    def test_fiction_break_reds(self):
        self.assertIn("FICTION_BREAK", codes("钛湖城是一座真实城市。"))

    def test_unknown_ruling_warns(self):
        found = [f for f in run("按 C200 的说法，这里该拆。") if f["code"] == "UNKNOWN_RULING"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["level"], "warn")

    def test_c2pa_is_not_read_as_a_ruling(self):
        self.assertEqual([c for c in codes("文件带 C2PA 容器。") if c.startswith("UNKNOWN_RULING")], [])

    def test_ruling_override_reds(self):
        self.assertIn("RULING_OVERRIDE", codes("按 C2 的裁定，红斗方应删除。"))

    def test_merely_citing_a_ruling_passes(self):
        self.assertEqual(codes("依 C2 的裁定，红斗方按节庆装饰字放行。"), [])


class RealCanon(unittest.TestCase):
    def test_canon_loads(self):
        entries, rulings, globals_ = V.load_canon(V.ROOT)
        self.assertEqual(len(entries), 312)
        self.assertEqual(len(rulings), 156)
        self.assertEqual(globals_["region_area_km2"], 4608)
        self.assertEqual(globals_["regional_total"], 3574200)
        self.assertEqual(entries["L069"]["floors"], 69)
        self.assertEqual(entries["L069"]["height_m"], 276)


class CliExitCodes(unittest.TestCase):
    def _run(self, text, *extra):
        fd, path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        with io.open(path, "w", encoding="utf-8") as fp:
            fp.write(text)
        try:
            return subprocess.run([sys.executable, "-X", "utf8",
                                   os.path.join(V.ROOT, "工具", "validate_derivative.py"), path]
                                  + list(extra),
                                  capture_output=True, text=True, encoding="utf-8"), path
        finally:
            pass

    def test_clean_file_exits_zero(self):
        r, path = self._run("R001 北湖第一居住区在 2013 年秋天很安静。\n")
        os.unlink(path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dirty_file_exits_one(self):
        r, path = self._run("新城 D21 在一片稻田上。\n")
        os.unlink(path)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("UNKNOWN_ID", r.stdout)

    def test_json_output_is_machine_readable(self):
        r, path = self._run("全市人口约 120 万。\n", "--json")
        os.unlink(path)
        doc = json.loads(r.stdout[r.stdout.index("{"):])
        self.assertGreaterEqual(doc["errors"], 1)
        self.assertEqual(doc["canon_entries"], 312)

    def test_missing_target_exits_two(self):
        r = subprocess.run([sys.executable, "-X", "utf8",
                            os.path.join(V.ROOT, "工具", "validate_derivative.py"),
                            os.path.join(tempfile.gettempdir(), "不存在的稿子_zzz.md")],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
