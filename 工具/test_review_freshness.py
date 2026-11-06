# -*- coding: utf-8 -*-
"""复看套件生成物过期闸门（`verify_review_freshness.py`）自身的判据。

背景：2026-11-06 清单侧按 B 前置裁定把 `image_file` 整体改挂 `backup/`，仓库里的 工作单.md 与
联络表/ 没有跟着重跑，人眼打开联络表看到的是 1116 个碎图标，而全量单测照常全绿——
因为既有测试跑的是生成器在临时目录里现算的那份，从不读仓库里已落盘的产物。
本文件把「读真实落盘产物」这条判据钉进单测：正检必须绿、注入必须红、判据必须非惰性。
真实仓库只读，注入全部在内存里做。
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))
import verify_review_freshness as gate  # noqa: E402


class ReviewFreshnessTests(unittest.TestCase):
    def read_real_sheet(self):
        return (ROOT / gate.REL_SHEET).read_text(encoding='utf-8')

    def test_generated_artifacts_in_the_repo_are_fresh(self):
        """正检：仓库里的工作单/联络表与 数据/开图清单.json 逐格一致，且每个引用都落盘。"""
        result = subprocess.run([sys.executable, '-B', str(ROOT / '工具' / 'verify_review_freshness.py')],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in ('清单格数: 1116', '工作单格数: 1116', '联络表引用数: 1116', '联络表页面数: 39'):
            self.assertIn(line, result.stdout)

    def test_gate_is_not_inert(self):
        """负测自证：八类判据逐条注入必须逐条命中，且原样数据对照 0 违例。"""
        result = subprocess.run([sys.executable, '-B', str(ROOT / '工具' / 'verify_review_freshness.py'),
                                 '--negtest'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('负测结论: 八类判据全部捕获', result.stdout)
        self.assertNotIn('假绿', result.stdout)
        self.assertIn('判据总数: %d，注入并命中: %d' % (len(gate.ALL_KINDS), len(gate.ALL_KINDS)), result.stdout)

    def test_2026_11_06_real_staleness_shape_is_caught(self):
        """变异对照：拿真实产物文本还原上一轮那次断链的形态（`backup/数据/图集/` → `数据/图集/`），
        判据必须同时报出逐格漂移与格不在盘上；原文必须 0 违例，否则这条对照什么都没证明。
        注入只改内存里的文本，仓库文件不动。"""
        cells = gate.manifest_cells()
        refs = gate.html_refs(ROOT / gate.REL_PAGES)
        pristine = self.read_real_sheet()
        _, pristine_bad = gate.compare(cells, gate.sheet_cells(pristine), refs)
        self.assertEqual(pristine_bad, [], '真实产物本应 0 违例，先修产物再谈判据')

        stale = pristine.replace('backup/数据/图集/', '数据/图集/')
        self.assertGreater(pristine.count('backup/数据/图集/'), 0, '注入锚点在这份产物里不存在')
        readings, bad = gate.compare(cells, gate.sheet_cells(stale), refs)
        kinds = {k for k, _ in bad}
        self.assertIn(gate.K_SEQ_DRIFT, kinds, str(bad))
        self.assertIn(gate.K_SHEET_DEAD, kinds, str(bad))
        self.assertEqual(readings['工作单格数'], readings['清单格数'],
                         '只换路径根不该改变格数，变了说明注入越界')

    def test_zero_hit_parser_cannot_pass_as_fresh(self):
        """违例负测：联络表一条 src 也没解析出来（正则失效／目录换名）时，必须判红而不是当成通过。"""
        cells = gate.manifest_cells()
        sheet = {k: list(v) for k, v in cells.items()}
        _, bad = gate.compare(cells, sheet, [])
        self.assertIn(gate.K_HTML_INERT, {k for k, _ in bad}, str(bad))


if __name__ == '__main__':
    unittest.main()
