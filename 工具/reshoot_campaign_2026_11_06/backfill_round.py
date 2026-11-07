# -*- coding: utf-8 -*-
"""投后核验通过（机械项）的条目：把本轮枚替换上格，并把机械对账读数打进备注。

与 batch9g 那轮回填共用一套纪律，口径五条：
1. 只回填 verify_round 判绿的条目。判绿＝逐字相等且尺寸符且容器在位（caBX／iTXt 至少其一，C136）；
    红项（如 2026-11-07 复投前的 F027／L037 送入串非逐字）一律不占格、不写备注，名单由读数派生，脚本不手抄。
2. 占格口径＝替换 replaced_cell 那一格（台账里已钉死），不追加、不动其余格；
    清单那一格里 `replaced_cell` 与本轮新文件恰有其一才继续——都没有（或都有）说明清单被别处动过，停手。
3. image_prompt_sha256 一律不写、status 不改、acceptance 不签：绑定摘要属人工验收动作，
    脚本代签等于把未经复验的图洗成已验收（工具/build_prompts.py 的清单声明与 test_image_assets 同口径）。
    例外通道 occupy_all（仅 R1，用户 2026-11-07「1 回填」并裁定「全部 264 都占格」）：
    已带人工绑定摘要的条目也照常占格，但脚本既不撤也不改那串摘要——它绑的是被替换前的旧文件，
    备注里必须逐字写明「维持原绑定＋摘要已过期＋重绑或撤销归人工」，否则占格会把一份过期验收悄悄洗成在册。
    这条通道只放宽占格，不放宽签署：R2 未拿到该裁定，仍按原禁则停手。
4. 本轮的人工逐张目视未执行（用户 2026-11-07「图不用检验，全出完我自己检验」＋「你直接回填」），
    备注里必须把「执行人／委托来源／未目视」三件事写明，读数目视未执行＝只含机械项。
5. 幂等：同一抬头（档串＋条目）的备注再跑一次是改写而不是追加；抬头变了说明占格口径动过，停手让人复核。
6. 判绿枚先从仓外出图目录（ImageGen 现落点＝仓库同级 `c8c10ff8/vibe_images/`）逐字节对拍请进仓内
    `vibe_images/`，仓外原件不删——清单挂的是仓内相对路径，不请进来那一格就是死链。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/backfill_round.py <R1|R2>（工作目录＝设定集根）
"""
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
MANIFEST = os.path.join(ROOT, '数据', '开图清单.json')
NOTES = os.path.join(ROOT, '数据', '开图验收备注.json')

ROUNDS = {
    'R2': {'readings': 'round_readings.json', 'suffix': 'C133冻结重投-v01',
           'prefix': 'C133冻结重投', 'head': 'C133冻结重投%s（v01）', 'occupy_all': False},
    'R1': {'readings': 'round_readings_r1.json', 'suffix': 'C138主向重投-v01',
           'prefix': 'C138主向重投', 'head': 'C138主向重投%s（v01）', 'occupy_all': True},
}
GUARD = ('image_prompt_sha256 留空、状态按清单派生为待复验，不代签验收')
GUARD_KEPT = ('image_prompt_sha256 维持原绑定 %s（本轮不撤不签），该摘要绑的是被替换前的旧文件、已过期，'
              '重绑或撤销归人工复验；状态维持待复验，不代签验收')
PROVENANCE = {
    'R2': ('执行人：Qoder 会话代理，受用户 2026-11-07「你直接回填」委托执行机械项回填；'
           '同轮用户豁免逐张目视（「图不用检验，全出完我自己检验」），故本条只含机械对账项、'
           '人工目视未执行，accepted 未签，状态维持待复验。'),
    'R1': ('执行人：Qoder 会话代理，受用户 2026-11-07「1 回填」委托执行机械项回填；占格范围按同轮裁定'
           '「全部 264 都占格」——该裁定推翻了「已绑摘要不占格」与「串外不占格」两条既有禁则，'
           '本组因此已带绑定摘要的条目也占格（摘要原样保留，见上），非逐字串的两条按「2 复投」补投达标后才进。'
           '同轮用户豁免逐张目视（「图不用检验，全出完我自己检验」），故本条只含机械对账项、'
           '人工目视未执行，accepted 未签，状态维持待复验。'),
}


def bring_in(green):
    """把本轮判绿枚从仓外出图目录请进仓内 `vibe_images/`，逐枚按 sha256 对拍后才算落地。

    为什么要这一步：本轮图落在仓库同级的 `c8c10ff8/vibe_images/`（ImageGen 现在的默认落点，
    也是 verify_round 与 container_profile 钉的统计面），而清单的 image_file 一律是仓内相对路径，
    `test_image_assets.test_gallery_extension_is_normalised` 与 on_disk 都只在仓内与 backup/ 两支找文件；
    图不搬进来，回填出来的那一格就指向一个仓内不存在的文件——闸门会红，人眼点开也是死链。
    仓外原件一个都不删：那是投后核验的取数面，删了下轮无从复核。
    2026-11-05 那几轮不需要这一步，因为当时会话的工作区根就是仓库本身，图直接落在仓内。"""
    dst = os.path.join(ROOT, 'vibe_images')
    if not os.path.isdir(dst):
        os.makedirs(dst)
    copied = already = 0
    for r in sorted(green, key=lambda x: x['id']):
        src, tgt = os.path.join(WORKSPACE, 'vibe_images', r['file']), os.path.join(dst, r['file'])
        assert os.path.isfile(src), (r['id'], '仓外原件不在盘，读数与盘面对不上')
        if os.path.isfile(tgt):
            h1 = hashlib.sha256(io.open(src, 'rb').read()).hexdigest()
            h2 = hashlib.sha256(io.open(tgt, 'rb').read()).hexdigest()
            assert h1 == h2, (r['id'], '仓内同名文件与仓外原件字节不同，停手人工复核')
            already += 1
            continue
        shutil.copy2(src, tgt)
        assert hashlib.sha256(io.open(tgt, 'rb').read()).hexdigest().startswith(r['sha256_12']), \
            (r['id'], '落仓后前 12 位与投后核验读数不一致')
        copied += 1
    return copied, already


def main(group):
    cfg = ROUNDS[group]
    rows = json.load(io.open(os.path.join(HERE, cfg['readings']), encoding='utf-8'))['rows']
    green, red = [], []
    for r in rows:
        cont = r['container']
        ok = (r['逐字相等'] and r['size_match'] and (cont['cabx'] >= 1 or cont['itxt'] >= 1))
        (green if ok else red).append(r)
    copied, already = bring_in(green)
    man = json.load(io.open(MANIFEST, encoding='utf-8'))
    items = {it['id']: it for it in man['items']}
    notes = json.load(io.open(NOTES, encoding='utf-8'))

    added = resynced = 0
    kept = []
    for r in sorted(green, key=lambda x: x['id']):
        eid, old, new = r['id'], r['replaced_cell'], 'vibe_images/' + r['file']
        files = items[eid]['image_file'] or []
        # 已回填过的那一格挂的是本轮新文件；没回填过的挂的是旧文件。两者恰有其一才继续，
        # 都不是说明清单被别处动过（或本轮文件换了名），停手让人复核。
        assert (old in files) != (new in files), (eid, 'replaced_cell 与本轮新格不同在/不同在清单里：'
                                                       '清单被别处动过，先人工复核')
        done = new in files
        slot = (files.index(new) if done else files.index(old)) + 1
        assert items[eid]['status'] == '待复验', (eid, '状态不是待复验，回填口径不覆盖既有结论')
        bound = items[eid].get('image_prompt_sha256')
        if bound:
            assert cfg['occupy_all'], (eid, '该条已绑定摘要，本组没有「全部占格」裁定，停手人工裁决')
            kept.append(eid)
        guard = (GUARD_KEPT % str(bound)[:12]) if bound else GUARD
        cont = r['container']
        head = (cfg['head'] % eid) + '投后机械对账读数（%s，替换第%d格 %s，%s，%d字节，sha12=%s，caBX=%d、iTXt=%d；%s）：%s'
        note = head % (
            new, slot, old, r['dims'], r['bytes'], r['sha256_12'], cont['cabx'], cont['itxt'], guard,
            '%s 实发串逐字相等：本轮发起 %d 次（逐字 %d／非逐字 %d，登记作废发起 %d）；'
            '落盘 %d 枚（冻结带内，ts=%s）；尺寸与清单声明一致（%s）。'
            '占格为替换第 %d 格，其余 %d 格原样保留、旧文件不删。'
            % (PROVENANCE[group], r['投次'], r['逐字发起数'], r['非逐字发起数'], r['登记作废发起数'],
               1, r['ts_text'], r['dims'], slot, len(files) - 1))
        # 抬头必须逐字落进占格判据认的那一轮：2026-11-07 首跑时 `head_fmt % '{}'` 把 %s 换成了字面 '{}'，
        # 备注写进真源后 test_image_assets 的按轮次选行选不中它、判据回落到上一轮，58 条全判红——
        # 格式串静默跑偏的代价是「回填做了但闸门不认」，所以在这里当场钉抬头，不让它进真源。
        assert note.startswith('%s%s（v01）' % (cfg['prefix'], eid)), (eid, note[:60])
        notes['备注'].setdefault(eid, [])
        at = [i for i, prev in enumerate(notes['备注'][eid]) if prev.startswith(cfg['prefix'])]
        if at:
            assert len(at) == 1, (eid, at)
            prev = notes['备注'][eid][at[0]]
            assert prev[:prev.index('）：')] == note[:note.index('）：')], (eid, '抬头变了＝占格口径动过，停手人工复核')
            notes['备注'][eid][at[0]] = note
            resynced += 1
        else:
            notes['备注'][eid].append(note)
            added += 1
        files[slot - 1] = new      # 已回填过时这一行是原地重写，不改格位
        items[eid]['image_file'] = files
        items[eid]['batch'] = '%s-%s%s' % (items[eid]['type'], eid, cfg['suffix'])

    io.open(NOTES, 'w', encoding='utf-8', newline='\n').write(json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
    io.open(MANIFEST, 'w', encoding='utf-8', newline='\n').write(json.dumps(man, ensure_ascii=False, indent=2) + '\n')
    print('%s 组回填：%d 条（新增 %d／改口重打 %d），判绿未回填 0，判红不回填 %d 条：%s'
          % (group, len(green), added, resynced, len(red), ' '.join(x['id'] for x in red) or '—'))
    print('读数来源 %s｜档串 %s｜格位为替换第N格（旧文件不删）｜image_prompt_sha256 脚本一律不写不撤｜status 全部待复验'
          % (cfg['readings'], cfg['suffix']))
    print('请进仓内 vibe_images/：新拷 %d 枚／已在仓内且逐字节相符 %d 枚（仓外原件 0 删）' % (copied, already))
    if cfg['occupy_all']:
        print('「全部占格」例外通道：已带绑定摘要仍占格 %d 条（摘要原样保留、备注点名其已过期）：%s'
              % (len(kept), ' '.join(sorted(kept)) or '—'))
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ROUNDS:
        print('用法：backfill_round.py <R1|R2>')
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
