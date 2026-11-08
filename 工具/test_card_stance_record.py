# -*- coding: utf-8 -*-
"""卡面主图画风判废结论件（数据/卡面主图画风目视.json）的过期闸门。

守的是「目视结论跟着某一版主图走」这条断链：主图 zip 一旦重建，台账的
归档sha256_12 会变，本件绑定的摘要就对不上，结论必须重签而不是继续当证据。
覆盖面同样对回落点件的 114 键（与 verify_readout_stance.py 的 K_CARD_COVERAGE 同口径），
逐枚行的 p_photo 与机器侧对回 CLIP 表，汇总数由逐枚行现算——手抄的第二份数一漂就红。

夹具一律在 tempfile 目录里造，只从仓库读真件当原料；负测先证未改坏的副本判绿，
再逐条改坏要求判红，证明这些断言不是恒绿。
"""
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RECORD_REL = os.path.join('数据', '卡面主图画风目视.json')
LANDING_REL = os.path.join('数据', '卡面主图提示词3x4', '主图3x4落点.json')
LEDGER_REL = os.path.join('数据', '卡面主图备份台账.json')
TSV_REL = os.path.join('工具', 'reshoot_campaign_2026_11_06', 'clip_style_scores_card3x4.tsv')
THRESHOLD = 0.9023535


def load_json(path):
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, obj):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def tsv_rows(root):
    with io.open(os.path.join(root, TSV_REL), encoding='utf-8') as f:
        hdr = f.readline().rstrip('\n').split('\t')
        return [dict(zip(hdr, line.rstrip('\n').split('\t'))) for line in f if line.strip()]


def check(root):
    """返回违例串列表；空列表＝通过。缺件直接判红，不许当空集绿。"""
    viol = []
    for rel in (RECORD_REL, LANDING_REL, LEDGER_REL, TSV_REL):
        if not os.path.exists(os.path.join(root, rel)):
            viol.append('缺件：%s' % rel)
    if viol:
        return viol
    rec = load_json(os.path.join(root, RECORD_REL))
    land = load_json(os.path.join(root, LANDING_REL))
    led = load_json(os.path.join(root, LEDGER_REL))
    tsv = {r['file']: r for r in tsv_rows(root)}

    bound = rec.get('绑定还原点', {})
    if bound.get('zip_sha256_12') != led.get('归档sha256_12'):
        viol.append('结论件绑定摘要 %s 与台账当前还原点 %s 不符——主图已重建，本件过期须重签'
                    % (bound.get('zip_sha256_12'), led.get('归档sha256_12')))
    if bound.get('枚数') != led.get('文件数'):
        viol.append('结论件绑定枚数 %s 与台账文件数 %s 不符' % (bound.get('枚数'), led.get('文件数')))

    rows = rec.get('逐枚', [])
    files = [r['file'] for r in rows]
    want = sorted(os.path.basename(v) for v in land.values())
    if len(files) != len(set(files)):
        viol.append('逐枚行有重枚：%d 行 / %d 个文件名' % (len(files), len(set(files))))
    missing = sorted(set(want) - set(files))
    stray = sorted(set(files) - set(want))
    if missing or stray:
        viol.append('覆盖面与落点件对不上：缺 %d 枚 %s，多 %d 枚 %s'
                    % (len(missing), missing[:3], len(stray), stray[:3]))

    for r in rows:
        src = tsv.get(r['file'])
        if src is None:
            viol.append('逐枚行在 CLIP 表里没有对应：%s' % r['file'])
            continue
        if abs(float(r['p_photo']) - float(src['p_photo'])) > 1e-6:
            viol.append('p_photo 与 CLIP 表不符：%s 件%s 表%s'
                        % (r['file'], r['p_photo'], src['p_photo']))
        want_side = '照片侧' if float(src['p_photo']) >= THRESHOLD else '绘画侧'
        if r['机器侧'] != want_side:
            viol.append('机器侧与阈值 %s 复算不符：%s 记%s 应为%s'
                        % (THRESHOLD, r['file'], r['机器侧'], want_side))
        if r['判定'] != ('放行' if r['目视侧'].startswith('厚涂') else '判废'):
            viol.append('判定与目视侧不自洽：%s 目视「%s」却判%s'
                        % (r['file'], r['目视侧'], r['判定']))

    agg = rec.get('汇总', {})
    recomputed = {
        '枚数': len(rows),
        '目视判照片质感': sum(1 for r in rows if r['目视侧'].startswith('照片')),
        '目视判厚涂绘画': sum(1 for r in rows if r['目视侧'].startswith('厚涂')),
        '放行': sum(1 for r in rows if r['判定'] == '放行'),
        '判废': sum(1 for r in rows if r['判定'] == '判废'),
        '机器判绘画而目视判照片的错分枚数': sum(1 for r in rows
                                        if r['机器侧'] == '绘画侧' and r['目视侧'].startswith('照片')),
    }
    for k, v in recomputed.items():
        if agg.get(k) != v:
            viol.append('汇总.%s 抄的是 %s，逐枚行现算是 %s' % (k, agg.get(k), v))
    want_mis = sorted(r['file'] for r in rows if r['机器侧'] == '绘画侧')
    if sorted(agg.get('错分名单', [])) != want_mis:
        viol.append('错分名单与逐枚行的绘画侧集合不符')
    return viol


class CardStanceRecordTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        for rel in (RECORD_REL, LANDING_REL, LEDGER_REL, TSV_REL):
            dst = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), dst)

    def tearDown(self):
        self._tmp.cleanup()

    def record(self):
        return load_json(os.path.join(self.root, RECORD_REL))

    def write(self, rec):
        write_json(os.path.join(self.root, RECORD_REL), rec)

    def test_真仓结论件判绿(self):
        self.assertEqual(check(ROOT), [])

    def test_干净夹具判绿以证非恒红(self):
        self.assertEqual(check(self.root), [])

    def test_主图重建后旧结论必须判红(self):
        led = load_json(os.path.join(self.root, LEDGER_REL))
        led['归档sha256_12'] = 'deadbeef0000'
        write_json(os.path.join(self.root, LEDGER_REL), led)
        viol = check(self.root)
        self.assertEqual(len(viol), 1, viol)
        self.assertIn('本件过期须重签', viol[0])

    def test_逐枚行截短必须同时打覆盖面与汇总(self):
        rec = self.record()
        rec['逐枚'] = rec['逐枚'][:-1]
        self.write(rec)
        viol = check(self.root)
        self.assertTrue(any('覆盖面与落点件对不上' in v for v in viol), viol)
        self.assertTrue(any('汇总.枚数' in v for v in viol), viol)

    def test_汇总数手抄必须被逐枚行现算顶回(self):
        rec = self.record()
        rec['汇总']['判废'] = 0
        self.write(rec)
        viol = check(self.root)
        self.assertEqual(len(viol), 1, viol)
        self.assertIn('汇总.判废', viol[0])

    def test_结论件缺件不得空转判绿(self):
        os.remove(os.path.join(self.root, RECORD_REL))
        viol = check(self.root)
        self.assertEqual(len(viol), 1, viol)
        self.assertIn('缺件', viol[0])


if __name__ == '__main__':
    unittest.main()
