# -*- coding: utf-8 -*-
"""图片资产核验生成物过期闸门（`verify_asset_report_freshness.py`）自身的判据。

背景：2026-11-07 的假绿形态是判据代码按 C136 改了、盘上两份产物没重跑，
`test_image_assets.py` 直接读那份过期产物，于是「产物 1116/1116 全通过」与「现算 58 格判红」同时成立，
而全量单测照常全绿。本文件把「读真实落盘产物并对回现算」这条判据钉进单测：正检绿、注入红、判据非惰性。
真实仓库只读，注入全部在内存里做；唯一写盘的是 HEAD 过期件复制到临时目录（用完即删）。
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))
import verify_asset_report_freshness as gate  # noqa: E402

MARKER = 'asset_freshness_'


def git_show(rel):
    """取 HEAD 里那份产物原文（2026-11-06 20:59 落盘的旧判据读数），不碰工作树。"""
    r = subprocess.run(['git', '-C', str(ROOT), 'show', 'HEAD:' + rel], capture_output=True)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'replace')
    return r.stdout.decode('utf-8')


class AssetReportFreshnessTests(unittest.TestCase):
    def run_gate(self, *args):
        return subprocess.run([sys.executable, '-B', str(ROOT / '工具' / 'verify_asset_report_freshness.py')]
                              + list(args), cwd=ROOT, capture_output=True, text=True,
                              encoding='utf-8', timeout=300)

    def test_generated_artifacts_in_the_repo_are_fresh(self):
        """正检：盘上两份产物与现算逐字段一致，且现算本身没判红。"""
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for line in ('清单直数格数: 1116', '现算文件格数: 1116', '现算失败格数: 0',
                     '数字漂移字段数: 0', '口径漂移字段数: 0'):
            self.assertIn(line, result.stdout)

    def test_gate_is_not_inert(self):
        """负测自证：六类判据逐条注入必须全部命中，且原样数据对照 0 违例。"""
        result = self.run_gate('--negtest')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('负测结论: 六类判据全部捕获', result.stdout)
        self.assertIn('判据总数: %d，注入并命中: %d' % (len(gate.ALL_KINDS), len(gate.ALL_KINDS)), result.stdout)
        self.assertNotIn('假绿', result.stdout)

    def test_head_stale_artifact_is_caught_as_real_sample(self):
        """变异对照：把 HEAD 里那份 2026-11-06 的过期产物（旧判据文本＋C2PA 在位 60）放进临时目录，
        闸门必须同时报出口径过期与数字漂移；同一套机制拿当前产物做对照必须 0 违例，
        否则这条对照什么都没证明（红是机制自己红，不是产物红）。

        这一轮的真实教训就藏在这里：过期件与现算的 文件格数／通过格数／失败格数 三个数完全相同，
        只比数字会放行，必须让口径散文也进对拍面。
        """
        stale_json, stale_md = git_show(gate.REL_JSON), git_show(gate.REL_MD)
        fresh_json = (ROOT / gate.REL_JSON).read_text(encoding='utf-8')
        fresh_md = (ROOT / gate.REL_MD).read_text(encoding='utf-8')
        stale = json.loads(stale_json)
        self.assertEqual([stale['文件格数'], stale['通过格数'], stale['失败格数']], [1116, 1116, 0])
        self.assertEqual(json.loads(fresh_json)['失败格数'], 0)
        self.assertNotEqual(stale['判据'], json.loads(fresh_json)['判据'], 'HEAD 与现档判据已同文，对照失效')

        tmp = Path(tempfile.mkdtemp(prefix=MARKER))
        try:
            for name, text in ((Path(gate.REL_JSON).name, stale_json), (Path(gate.REL_MD).name, stale_md)):
                (tmp / '数据').mkdir(exist_ok=True)
                (tmp / '数据' / name).write_text(text, encoding='utf-8')
            hit = self.run_gate('--root', str(tmp))
            self.assertEqual(hit.returncode, 1, hit.stdout + hit.stderr)
            self.assertIn(gate.K_CRITERION_STALE, hit.stdout)
            self.assertIn(gate.K_COUNT_DRIFT, hit.stdout)
            self.assertIn('C2PA在位格数', hit.stdout)

            (tmp / '数据' / Path(gate.REL_JSON).name).write_text(fresh_json, encoding='utf-8')
            (tmp / '数据' / Path(gate.REL_MD).name).write_text(fresh_md, encoding='utf-8')
            ok = self.run_gate('--root', str(tmp))
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_gate_reads_only_and_leaves_no_residue(self):
        """闸门不许改被守护的产物，也不许在临时区留壳；残留口径连自己用的前缀一起数。"""
        before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                  for p in (gate.REL_JSON, gate.REL_MD, gate.REL_MANIFEST)}
        self.run_gate()
        self.run_gate('--negtest')
        after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                 for p in (gate.REL_JSON, gate.REL_MD, gate.REL_MANIFEST)}
        self.assertEqual(before, after, '闸门改写了被守护的产物或真源')
        leftover = [d for d in Path(tempfile.gettempdir()).iterdir() if d.name.startswith(MARKER)]
        self.assertEqual(leftover, [], '临时夹具泄漏：%s' % [str(d) for d in leftover])


if __name__ == '__main__':
    unittest.main()
