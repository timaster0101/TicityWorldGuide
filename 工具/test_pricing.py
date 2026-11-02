# -*- coding: utf-8 -*-
"""标准库回归测试；仅在临时项目中执行真实定价脚本，不导入生产脚本。"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "工具" / "build_pricing.py"
REGISTRY = ROOT / "数据" / "城市空间名录.json"
OFFICE_IDS = {"L007", "L009", "L025", "L034", "L038", "L040", "L055", "L061", "L063", "L066", "L067", "L068", "L069", "L070", "L071", "L072", "L073", "L076", "L080", "L082", "L083", "L084", "L085", "L086", "L091", "L092", "L093", "L096", "L102", "L103", "L107"}  # 31条：原7条＋阶段2新增24条，逐条点名，不靠名称推断
SHOP_IDS = {"L010", "L011", "L012", "L016", "L017", "L023", "L052", "L065", "L074", "L075", "L079", "L081", "L089", "L094", "L101", "L104", "L105"}  # 17条：原7条＋阶段2新增10条
PRICE_SCOPES = {
    "residential": "住宅", "office": "办公", "retail": "商业", "street_retail": "底商",
}


def run_pricing(registry):
    """脚本通过 __file__ 定位根目录，故连脚本也必须复制到临时项目。"""
    with tempfile.TemporaryDirectory(prefix="pricing-test-") as tmp:
        root = Path(tmp)
        tools = root / "工具"
        data = root / "数据"
        tools.mkdir()
        data.mkdir()
        script = tools / SCRIPT.name
        shutil.copyfile(SCRIPT, script)
        source = data / REGISTRY.name
        source.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        original = source.read_bytes()
        result = subprocess.run(
            [sys.executable, "-B", str(script)], cwd=root, capture_output=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise AssertionError(f"临时生成失败：{result.stdout}\n{result.stderr}")
        if source.read_bytes() != original:
            raise AssertionError("生成器改写了输入名录")
        generated = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        expected = {
            "工具/build_pricing.py", "数据/城市空间名录.json",
            "数据/参考房价租金.json", "数据/参考房价租金总表.md",
        }
        if generated != expected:
            raise AssertionError(f"非预期生成物：{generated ^ expected}")
        output = json.loads((data / "参考房价租金.json").read_text(encoding="utf-8"))
        table = (data / "参考房价租金总表.md").read_text(encoding="utf-8")
        return output, table


def small_registry(registry):
    """保留四圈层与脚本所需 L007，D01 仅两个不同 GFA 的住宅样本。"""
    ids = {"D01", "D02", "F001", "F003", "R001", "R002", "R007", "L007", "S01", "S17"}
    entries = [copy.deepcopy(e) for e in registry["entries"] if e["id"] in ids]
    for e in entries:
        eid = e["id"]
        if eid.startswith("S"):
            continue
        e["focus"] = "公共治理、法务与市民服务"
        inner = eid in {"D01", "F001", "R001", "R002"}
        e["ring"] = "内湖环" if inner else "外城环"
        e["distance_to_lake_center_km"] = 5.8 if inner else 10.2
        e["population"] = 100 if inner else 200
        if not eid.startswith("D"):
            e["parent"] = "D01" if inner else "D02"
        if eid.startswith("F"):
            e["daily_workers"] = 0 if inner else 100
        if eid.startswith("R"):
            e["gross_floor_area_m2"] = {"R001": 10000, "R002": 30000, "R007": 80000}[eid]
            e["floor_area_ratio"] = 0.3 if eid == "R002" else 0.8
            e["height_limit_m"] = 30
            e["households"] = 100
        if eid == "L007":
            e["gross_floor_area_m2"] = 0
    return {"entries": entries}


class PricingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.output, cls.table = run_pricing(cls.registry)
        cls.rows = {r["id"]: r for r in cls.output["records"]}

    def test_district_coefficients_use_own_district_features(self):
        # 捕获 D 因 parent=CITY 被错误赋值为两个 1.0 的分支。
        districts = [r for r in self.rows.values() if r["type"] == "城市片区"]
        for field in ("就业拉力系数", "片区成熟度系数"):
            self.assertGreater(len({r["basis"][field] for r in districts}), 1)
            for row in self.rows.values():
                if row["parent"] in self.rows:
                    self.assertEqual(row["basis"][field], self.rows[row["parent"]]["basis"][field])

    def test_parent_jobs_change_district_and_children_not_settlements(self):
        changed = copy.deepcopy(self.registry)
        next(e for e in changed["entries"] if e["id"] == "F001")["daily_workers"] += 100000
        output, _ = run_pricing(changed)
        rows = {r["id"]: r for r in output["records"]}
        self.assertGreater(rows["D01"]["basis"]["就业拉力系数"], self.rows["D01"]["basis"]["就业拉力系数"])
        for eid in ("D01", "R001", "F001", "L001"):
            self.assertEqual(rows[eid]["basis"]["就业拉力系数"], rows["D01"]["basis"]["就业拉力系数"])
            self.assertGreater(rows[eid]["office" if eid == "L001" else "residential"]["sale_tt_per_m2"],
                               self.rows[eid]["office" if eid == "L001" else "residential"]["sale_tt_per_m2"])
        for eid, row in self.rows.items():
            if eid.startswith("S"):
                self.assertEqual(rows[eid], row)

    def test_hand_calculated_residential_sample_weighting_is_order_independent(self):
        # D01 jobs/GFA/pop 均为最小值，故就业=.90、成熟度=1。
        # R001: 10000*1.32*.90=11880 ->11900；R002 再乘1.10 ->13050。
        # 权重1:3：(11900+13050*3)/4=12762.5 ->12750；月租=22.8。
        fixture = small_registry(self.registry)
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                if reverse:
                    fixture["entries"].reverse()
                output, _ = run_pricing(fixture)
                rows = {r["id"]: r for r in output["records"]}
                self.assertEqual(rows["R001"]["residential"]["sale_tt_per_m2"], 11900)
                self.assertEqual(rows["R002"]["residential"]["sale_tt_per_m2"], 13050)
                home = rows["D01"]["residential"]
                self.assertEqual(home["sale_tt_per_m2"], 12750)
                self.assertEqual(home["rent_tt_per_m2_month"], 22.8)
                self.assertEqual(home["gross_yield"], 0.0215)
                self.assertEqual(home.get("sample_ids"), ["R001", "R002"])
                self.assertEqual(home.get("sample_weight_gfa_m2"), 40000)

    def test_canonical_d01_sample_price_and_trace(self):
        home = self.rows["D01"]["residential"]
        self.assertEqual(home["sale_tt_per_m2"], 13950)
        self.assertEqual(home.get("sample_ids"), [f"R{i:03d}" for i in range(1, 7)])
        weights = [e["gross_floor_area_m2"] for e in self.registry["entries"]
                   if e["type"] == "居民区" and e["parent"] == "D01"]
        self.assertEqual(home.get("sample_weight_gfa_m2"), sum(weights))

    def test_no_sample_does_not_invent_district_residential_price(self):
        fixture = small_registry(self.registry)
        for e in fixture["entries"]:
            if e["id"] in ("R001", "R002"):
                e["parent"] = "D02"
        output, _ = run_pricing(fixture)
        district = next(r for r in output["records"] if r["id"] == "D01")
        self.assertNotIn("residential", district)
        self.assertNotIn("住宅", district["scope"])

    def test_commercial_section_rows_are_unique_and_match_shop_ids(self):
        section = next(s for s in self.table.split("\n## ") if s.startswith("商业区（"))
        ids = [line.split("|")[1].strip() for line in section.splitlines()
               if line.startswith("| ") and line.split("|")[1].strip() != "ID"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), SHOP_IDS | {"F008", "F016"})
        self.assertIn(f"（{len(SHOP_IDS) + 2}条）", section.splitlines()[0])

    def test_scope_matches_only_present_price_classes(self):
        mismatches = []
        for row in self.rows.values():
            expected = {label for key, label in PRICE_SCOPES.items() if key in row}
            if set(row["scope"]) != expected or len(row["scope"]) != len(expected):
                mismatches.append(row["id"])
        self.assertEqual(mismatches, [])
        for eid in OFFICE_IDS | SHOP_IDS:
            self.assertNotIn("residential", self.rows[eid])

    def test_asset_use_depends_on_id_not_name(self):
        changed = copy.deepcopy(self.registry)
        for e in changed["entries"]:
            if e["type"] in ("标志性建筑", "功能区", "城市片区"):
                e["name"] = "中性名称" if e["id"] in OFFICE_IDS | SHOP_IDS | {"F008", "F016"} else "总部会客厅酒店市场"
        output, _ = run_pricing(changed)
        for row in output["records"]:
            if row["type"] in ("标志性建筑", "功能区", "城市片区"):
                with self.subTest(id=row["id"]):
                    self.assertEqual(row["asset_use"], self.rows[row["id"]]["asset_use"])
                    self.assertEqual(row["reference_only"], self.rows[row["id"]]["reference_only"])

    def test_all_canonical_ids_and_explicit_landmark_uses_are_preserved(self):
        self.assertEqual(self.output["record_count"], 312)
        self.assertEqual(len(self.rows), 312)
        self.assertEqual(set(self.rows), {e["id"] for e in self.registry["entries"]})
        landmarks = [r for r in self.rows.values() if r["type"] == "标志性建筑"]
        self.assertEqual(Counter(r["asset_use"] for r in landmarks), {"办公": 31, "商业": 17, "公共自用": 60})
        self.assertEqual({r["id"] for r in landmarks if r["asset_use"] == "办公"}, OFFICE_IDS)
        self.assertEqual({r["id"] for r in landmarks if r["asset_use"] == "商业"}, SHOP_IDS)
        for row in self.rows.values():
            if row["type"] in ("城市片区", "功能区"):
                self.assertEqual(row["asset_use"], "商业" if row["id"] in {"F008", "F016"} else "混合")

    def test_peripheral_lake_factor_stays_one_even_at_zero_distance(self):
        changed = copy.deepcopy(self.registry)
        for e in changed["entries"]:
            if e["id"].startswith("S"):
                e["distance_to_lake_center_km"] = 0
        output, _ = run_pricing(changed)
        settlements = [r for r in output["records"] if r["id"].startswith("S")]
        self.assertEqual(len(settlements), 24)
        for row in settlements:
            self.assertEqual(row["basis"]["湖景系数"], 1.0)
            self.assertEqual(row["residential"], self.rows[row["id"]]["residential"])
            self.assertEqual(row["street_retail"], self.rows[row["id"]]["street_retail"])

    def test_basis_exposes_bases_yields_and_applied_office_factors(self):
        sources = {e["id"]: e for e in self.registry["entries"]}
        yields = {"内湖环": 0.0215, "外城环": 0.0255, "产业小镇": 0.031, "特色村落": 0.035}
        for row in self.rows.values():
            basis = row["basis"]
            self.assertEqual(basis.get("基准单价_钛币每平方米"), {"住宅": 10000, "办公": 11500, "商业": 12800})
            self.assertEqual(basis.get("毛租金收益率"), {"住宅": yields[row["ring"]], "办公": 0.045, "商业": 0.052})
            if "office" in row:
                source = sources[row["id"]]
                high = source["type"] == "标志性建筑" and (source.get("height_m") or 0) >= 90
                self.assertEqual(basis.get("办公高度系数"), 1.10 if high else 1.0)
                self.assertEqual(basis.get("办公地标系数"), 1.25 if row["id"] == "L007" else 1.0)
        # 原有分步取整应保留：22550 -> 24800 -> 31000，合并乘数会变价。
        self.assertEqual(self.rows["L007"]["office"]["sale_tt_per_m2"], 31000)
        # 日租金由取整后的售价派生：31000 × 0.045 ÷ 365 = 3.82 → 3.8。
        self.assertEqual(self.rows["L007"]["office"]["rent_tt_per_m2_day"], 3.8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
