# -*- coding: utf-8 -*-
"""早于 E1 定档归档闸门的自证：真盘对拍必须绿、注入必须红、零命中必须判红、引用同步必须落进文本层。

跑法：python -m unittest discover -s 工具 -p "test_pre_e1_archive.py"
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '工具'))
import verify_pre_e1_archive as G  # noqa: E402

GATE = str(ROOT / '工具' / 'verify_pre_e1_archive.py')
DETAIL = ROOT / 'backup' / '归档明细_早于定档_20261106.json'


def run(args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-X', 'utf8', GATE] + args, capture_output=True,
                          text=True, encoding='utf-8', env=env, cwd=str(ROOT))


class ArchiveGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = json.loads(DETAIL.read_text(encoding='utf-8'))['明细']

    def test_real_archive_and_refs_are_consistent(self):
        """盘上真图逐张对拍：这是唯一能证明 178.9MB 搬迁没搬丢、引用没留在旧路径的读数来源。"""
        proc = run([])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        readings = json.loads(proc.stdout.split('\n\n')[0])
        self.assertEqual(readings['明细条数'], 187)
        self.assertEqual(readings['明细状态'], '完成')
        self.assertEqual((readings['原路径仍占位'], readings['backup 缺失']), (0, 0))
        self.assertEqual(readings['backup 在盘'], 187)
        self.assertEqual(readings['活引用违例'], 0)
        self.assertGreaterEqual(readings['豁免命中']['数据/生成输入记录/'], 1)
        self.assertEqual((readings['素材枚数'], readings['素材未同步'], readings['素材取不到']), (5, 0, 0))
        self.assertEqual(readings['下界'], '2026-11-03 01:50:02.152000')
        self.assertEqual(readings['下界取证枚数'], 10)
        self.assertEqual(sum(readings['分域'].values()), 187)

    def test_negtest_catches_every_kind_without_residue(self):
        proc = run(['--negtest'])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('判据总数: %d，注入并命中: %d' % (len(G.ALL_KINDS), len(G.ALL_KINDS)), proc.stdout)
        self.assertIn('负测结论: %d 类判据全部捕获' % len(G.ALL_KINDS), proc.stdout)
        self.assertIn('临时夹具残留复核: 0', proc.stdout)
        self.assertNotIn('假绿', proc.stdout)

    def test_injection_face_covers_every_judgement_constant(self):
        """判据名做成常量后，注入面必须与 ALL_KINDS 一一对应；漏一类就是闸门里那条判据从此无人守。"""
        self.assertEqual(sorted(G.ALL_KINDS), sorted(G.INJECT))

    def test_pre_move_project_relative_material_is_caught(self):
        """2026-11-06 那次同步前的真实形态（工程 JSON 仍写项目相对路径）必须判成未同步，而不是判成取不到。"""
        tmp = Path(tempfile.mkdtemp(prefix='archive_mat_test_'))
        try:
            proj = tmp / G.PROJECT_ROOT / '钛湖城城市介绍片' / '项目文件'
            proj.mkdir(parents=True)
            (tmp / G.DETAIL_REL).parent.mkdir(parents=True)
            (tmp / G.DETAIL_REL).write_text(DETAIL.read_text(encoding='utf-8'), encoding='utf-8')
            old = '钛湖城城市介绍片/设定库/场景/L007-钛湖之脊-锚点.jpg'
            (proj / 'shots.json').write_text(json.dumps([{'materials': [old]}], ensure_ascii=False),
                                             encoding='utf-8')
            bad, cells, stale, unresolved = G.check_materials(tmp)
            self.assertEqual((cells, stale, unresolved), (1, 1, 0), bad)
            self.assertEqual({k for k, _ in bad}, {G.K_MATERIAL_UNARCHIVED})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            self.assertFalse(tmp.exists())

    def test_zero_hit_faces_are_red_not_green(self):
        """空扫描面与空素材面各判一条惰性违例；正则读出 0 条照样打印通过是本仓库明令禁止的假绿形态。"""
        tmp = Path(tempfile.mkdtemp(prefix='archive_inert_test_'))
        try:
            bad, scanned, hits, _ = G.scan_refs(self.items, tmp)
            self.assertEqual((scanned, hits), (0, 0))
            self.assertIn(G.K_SCAN_INERT, {k for k, _ in bad})
            self.assertIn(G.K_EXEMPT_INERT, {k for k, _ in bad})
            bad2, cells, _s, _u = G.check_materials(tmp)
            self.assertEqual(cells, 0)
            self.assertIn(G.K_MATERIALS_INERT, {k for k, _ in bad2})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            self.assertFalse(tmp.exists())

    def test_reference_sync_landed_in_the_text_layer(self):
        """引用同步是这轮唯一的交付物之一，文本层必须留得下证据：三处口径各自钉一条，防止回退成旧路径。"""
        shots = json.loads((ROOT / '数据/影像作品/工程文件/钛湖城城市介绍片/项目文件/shots.json')
                           .read_text(encoding='utf-8'))
        vals = [v for s in shots for v in (s.get('materials') or [])]
        anchors = [s['continuity_context']['scene_anchor'] for s in shots
                   if (s.get('continuity_context') or {}).get('scene_anchor')]
        self.assertTrue(all(v.startswith('backup/') for v in vals + anchors), vals + anchors)
        for rel in ('数据/影像作品/工程文件/钛湖60秒城市介绍/项目文件/shots_login_tour.json',
                    '数据/影像作品/工程文件/钛湖60秒城市介绍/项目文件/shots_logo_anim.json'):
            data = json.loads((ROOT / rel).read_text(encoding='utf-8'))
            mats = [m for s in data for m in (s.get('materials') or [])]
            self.assertTrue(mats and all(m.startswith('backup/') for m in mats), (rel, mats))
        for rel, token in (('数据/影像作品/00-归档说明.md', '2026-11-06 归档补记'),
                           ('设计/2026-10-31-卡面标准样式规范.md', 'backup/数据/视觉控制资产/卡牌/'),
                           ('设计/2026-10-31-成就卡打卡套系-设计.md', 'backup/数据/视觉控制资产/卡牌/'),
                           ('AI创作使用手册.md', '定标样本7张现存放于 backup/数据/视觉控制资产/E1半写实厚涂/'),
                           ('钛湖城城市设定集-完整合订本.md', '定标样本7张现存放于 backup/数据/视觉控制资产/E1半写实厚涂/')):
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn(token, text, rel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
