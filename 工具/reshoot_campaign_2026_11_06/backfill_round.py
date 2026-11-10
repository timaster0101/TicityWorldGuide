# -*- coding: utf-8 -*-
"""投后核验通过（机械项）的条目：把本轮枚替换上格，并把机械对账读数打进备注。

与 batch9g 那轮回填共用一套纪律，口径五条：
1. 只回填 verify_round 判绿的条目。判绿＝逐字相等且尺寸符且容器在位（caBX／iTXt 至少其一，C136）；
    红项（如 2026-11-07 复投前的 F027／L037 送入串非逐字）一律不占格、不写备注，名单由读数派生，脚本不手抄。
2. 占格口径＝替换 replaced_cell 那一格（台账里已钉死），不追加、不动其余格；
    清单那一格里 `replaced_cell` 与本轮新文件恰有其一才继续——都没有（或都有）说明清单被别处动过，停手。
    replaced_cell 为 None（补投面里此前零图的那批）时占格口径改为「新增首格」：清单格面必须是空、
    或已经恰好只挂本轮那一枚（幂等），读数里逐字写「本条此前无格为首占」，判据侧拿这句核格数。
3. image_prompt_sha256 一律不写、status 不改、acceptance 不签：绑定摘要属人工验收动作，
    脚本代签等于把未经复验的图洗成已验收（工具/build_prompts.py 的清单声明与 test_image_assets 同口径）。
    唯一的状态例外是「待开图 → 待复验」（补投面里此前零图的那批）：有了本轮枚它就不再是待开图，
    挪记只是把它送进复验队列，验收仍归签署通道；备注里逐字写明「挪状态不是验收」。
    摘要分档：绑的串与当前 prompt_sha256 相同 → 写「维持原绑定＋串未变则摘要未过期」（C135 绑的是串不是格），
    不同 → 仍写「摘要已过期、重绑归人工」；两档字面量被 test_image_assets 与 verify_prompt_baseline 共用。
    例外通道 occupy_all（仅 R1，用户 2026-11-07「1 回填」并裁定「全部 264 都占格」）：
    已带人工绑定摘要的条目也照常占格，但脚本既不撤也不改那串摘要——它绑的是被替换前的旧文件，
    备注里必须逐字写明「维持原绑定＋摘要已过期＋重绑或撤销归人工」，否则占格会把一份过期验收悄悄洗成在册。
    这条通道只放宽占格，不放宽签署：R2 未拿到该裁定，仍按原禁则停手。
4. 本轮的人工逐张目视未执行（用户 2026-11-07「图不用检验，全出完我自己检验」＋「你直接回填」），
    备注里必须把「执行人／委托来源／未目视」三件事写明，读数目视未执行＝只含机械项。
5. 幂等：同一抬头（档串＋条目）的备注再跑一次是改写而不是追加；抬头变了说明占格口径动过，停手让人复核。
6. 判绿枚先从仓外出图目录（ImageGen 现落点＝仓库同级 `c8c10ff8/vibe_images/`）逐字节对拍请进仓内
    交付落点 `数据/图集/<条目ID>/`（C141，2026-11-07 用户「图集目录下，放到各个文件夹里」），仓外原件不删——
    清单挂的是仓内相对路径，不请进来那一格就是死链。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/backfill_round.py <R1|R2|R4> [--only 送入串台账.json]
     --only 把回填范围收到那一份台账的键面上（R1 组读数面已含 264＋5＋48 三份合成，不限范围就会把
     上一轮已写过的行按本轮的委托原句重打——抬头判据拦的是占格口径变了，拦不住正文被顶掉）。
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
# C141（2026-11-07）：仓内交付落点＝图集下按条目 ID 分的文件夹，档名不改
GALLERY = os.path.join(ROOT, '数据', '图集')
GALLERY_PREFIX = '数据/图集/'
NOTES = os.path.join(ROOT, '数据', '开图验收备注.json')

ROUNDS = {
    'R2': {'readings': 'round_readings.json', 'suffix': 'C133冻结重投-v01',
           'prefix': 'C133冻结重投', 'head': 'C133冻结重投%s（v01）', 'occupy_all': False,
           'statuses': ('待复验',)},
    'R1': {'readings': 'round_readings_r1.json', 'suffix': 'C138主向重投-v01',
           'prefix': 'C138主向重投', 'head': 'C138主向重投%s（v01）', 'occupy_all': True,
           # 补投组（catchup 台账 48 条）里两种既有状态都要放行：39 条挂着已代签验收的旧画风定档格（替换它），
           # 9 条此前零图（新增首格）。放行不等于改写结论——已验收那批的状态与绑定原样不动，
           # 只是把「申报行没点名当前格」这件事写进备注并交给 sign_acceptance 复核（见 CATCHUP 面）。
           'statuses': ('待复验', '已验收', '待开图'),
           'catchup': 'send_bodies_r1_catchup.json'},
    # R4＝画风母图臂重投（310 条目视判废的主向格）。占格范围与 R1 同为「全部占格」：
    # 这 310 条现读全部带 image_prompt_sha256，但绑的是 C153 换档前的串摘要（未过期档实测 0 条），
    # 所以本组备注全部走「维持原绑定＋摘要已过期＋重绑归人工」那一档——占格不洗绑定。
    # 状态面现算单一：310 条 status_before 全是「待复验」（待开图／已验收各 0），不放行那两档。
    'R4': {'readings': 'round_readings_r4.json', 'suffix': 'C154母图重投-v01',
           'prefix': 'C154母图重投', 'head': 'C154母图重投%s（v01）', 'occupy_all': True,
           'statuses': ('待复验',)},
}
GUARD = ('image_prompt_sha256 留空、状态按清单派生为待复验，不代签验收')
GUARD_KEPT = ('image_prompt_sha256 维持原绑定 %s（本轮不撤不签），该摘要绑的是被替换前的旧文件、已过期，'
              '重绑或撤销归人工复验；状态维持待复验，不代签验收')
# 补投面那 39 条不同：它们的绑定按 C135 绑的是提示词串（image_prompt_sha256＝prompt_sha256），本轮串没换，
# 摘要就还没过期——把「已过期」那句话套到它们头上是假申报，会把一条仍然成立的绑定说成待重绑。
# 判据侧靠「已过期／未过期」这个字面量分档（test_image_assets 的 stale_declared 与 verify_prompt_baseline 同口径）。
GUARD_KEPT_SAME = ('image_prompt_sha256 维持原绑定 %s（本轮不撤不签；C135 绑的是提示词串，串未变则摘要未过期），'
                   '本轮替换掉的是那一格的图，代签依据须由 sign_acceptance 按本轮新枚复核')
# 备注正文末句按占格时的状态分档写死成三选一：写成一句通用话就会把「已验收」那批说成「未签」，
# 而备注是闸门读的真源，一句假话就是一条静默的洗白路径（2026-11-07 复跑时 264 行会被整批顶成这句）。
ACCEPTED_FACE = {
    '待复验': 'accepted 未签，状态维持待复验。',
    '待开图': ('accepted 未签；本条投放前零图（状态待开图），本轮占格为新增首格，状态挪记待复验——'
              '挪状态只是把它送进复验队列，不是验收。'),
    '已验收': ('accepted 维持已验收：该验收按 C139 代签在先，绑的是提示词串（C135 image_prompt_sha256＝prompt_sha256，'
              '本轮串未变）；本轮替换掉的正是那份申报点名过的旧画风定档格，代签依据须由 sign_acceptance 按本轮新枚'
              '重新摊开——申报行没点名当前格就不算过关。'),
}
PROVENANCE = {
    'R2': ('执行人：Qoder 会话代理，受用户 2026-11-07「你直接回填」委托执行机械项回填；'
           '同轮用户豁免逐张目视（「图不用检验，全出完我自己检验」），故本条只含机械对账项、'
           '人工目视未执行。'),
    'R1': ('执行人：Qoder 会话代理，受用户 2026-11-07「1 回填」委托执行机械项回填；占格范围按同轮裁定'
           '「全部 264 都占格」——该裁定推翻了「已绑摘要不占格」与「串外不占格」两条既有禁则，'
           '本组因此已带绑定摘要的条目也占格（摘要原样保留，见上），非逐字串的两条按「2 复投」补投达标后才进。'
           '同轮用户豁免逐张目视（「图不用检验，全出完我自己检验」），故本条只含机械对账项、'
           '人工目视未执行。'),
    'R4': ('执行人：Qoder 会话代理，受用户 2026-11-09「卡面 85 枚＋R1 310 枚判废后的重投（花钱调用，'
           '方向已锁死「无框主图＋不烤文案」） 去做」委托执行机械项回填；投放臂按同轮四枚双臂探针定为'
           '「现串正文逐字＋跨题材画风母图」（图生图），裸串臂已判废。同轮用户豁免逐张目视'
           '（常设原话「图不用检验，全出完我自己检验」），故本条只含机械对账项、人工目视未执行。'),
}
# catchup 那 48 条的委托来源原句，只加在补投面上：把这句混进全组通用文字会顶掉 264 行历史正文的原文。
CATCHUP_DELEGATION = ('补投范围依据用户 2026-11-07 裁定「只要不是新画风生成的或者缺少的，都开」＋「3 补」'
                      '（＝清单现算没有一枚 C138主向重投 格的 48 条，串面在 %s，核验并读进 R1 组发送面）。')


def bring_in(green):
    """把本轮判绿枚从仓外出图目录请进仓内交付落点 `数据/图集/<条目ID>/`，逐枚按 sha256 对拍后才算落地。

    为什么要这一步：本轮图落在仓库同级的 `c8c10ff8/vibe_images/`（ImageGen 现在的默认落点，
    也是 verify_round 与 container_profile 钉的统计面），而清单的 image_file 一律是仓内相对路径，
    `test_image_assets.test_gallery_extension_is_normalised` 与 on_disk 都只在仓内与 backup/ 两支找文件；
    图不搬进来，回填出来的那一格就指向一个仓内不存在的文件——闸门会红，人眼点开也是死链。
    仓外原件一个都不删：那是投后核验的取数面，删了下轮无从复核。
    2026-11-05 那几轮不需要这一步，因为当时会话的工作区根就是仓库本身，图直接落在仓内。
    落点为什么是图集按 ID 分文件夹而不是仓内 vibe_images/ 平铺：C141（用户 2026-11-07「图集目录下，
    放到各个文件夹里」）把交付面统一到了 数据/图集/<ID>/，本函数与登记路径必须同向走，
    否则回填一轮就把上一轮迁好的目录形态顶回去一次，而闸门按文件名比对，看不见这种退化。"""
    copied = already = 0
    for r in sorted(green, key=lambda x: x['id']):
        dst_dir = os.path.join(GALLERY, r['id'])
        src = os.path.join(WORKSPACE, 'vibe_images', r['file'])
        tgt = os.path.join(dst_dir, r['file'])
        assert os.path.isfile(src), (r['id'], '仓外原件不在盘，读数与盘面对不上')
        if os.path.isfile(tgt):
            with io.open(src, 'rb') as fp:
                h1 = hashlib.sha256(fp.read()).hexdigest()
            with io.open(tgt, 'rb') as fh:
                h2 = hashlib.sha256(fh.read()).hexdigest()
            assert h1 == h2, (r['id'], '仓内同名文件与仓外原件字节不同，停手人工复核')
            already += 1
            continue
        # 上一档落点里已有同名原件时不重复占盘：先校验它确实就是本轮这一枚，再把它挪进图集目录。
        legacy = os.path.join(ROOT, 'vibe_images', r['file'])
        if os.path.isfile(legacy):
            with io.open(src, 'rb') as _fh:
                h1 = hashlib.sha256(_fh.read()).hexdigest()
            with io.open(legacy, 'rb') as _fp:
                h2 = hashlib.sha256(_fp.read()).hexdigest()
            assert h1 == h2, (r['id'], '仓内旧落点的同名文件与仓外原件字节不同，停手人工复核')
            os.makedirs(dst_dir, exist_ok=True)
            os.replace(legacy, tgt)
            already += 1
            continue
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, tgt)
        with io.open(tgt, 'rb') as _handle:
            assert hashlib.sha256(_handle.read()).hexdigest().startswith(r['sha256_12']), \
                (r['id'], '落仓后前 12 位与投后核验读数不一致')
        copied += 1
    return copied, already


def main(group, only=None):
    cfg = ROUNDS[group]
    with io.open(os.path.join(HERE, cfg['readings']), encoding='utf-8') as _h155:
        rows = json.load(_h155)['rows']
    # --only 把回填范围收到某一份送入串台账的键上。本组读取面已经是「264 主向＋5 证据＋48 补投」三份合成，
    # 不做这个限制，补投那一轮会把 264 行的历史正文一并重打——抬头没变但正文里的委托原句会变，
    # 那就是拿本轮的话覆盖上一轮的话。
    face = None
    if only:
        with io.open(os.path.join(HERE, only), encoding='utf-8') as _h162:
            face = set(json.load(_h162))
        assert face, (only, '补充台账是空的，回填范围收到空集等于什么都不做')
        rows = [r for r in rows if r['id'] in face]
        assert rows, (only, '读数里没有一条落在 %s 的键面上：先跑 verify_round 再谈回填' % only)
    with io.open(os.path.join(HERE, cfg['catchup']), encoding='utf-8') as _h167:
        catchup = set(json.load(_h167)) \
            if cfg.get('catchup') and os.path.exists(os.path.join(HERE, cfg['catchup'])) else set()
    green, red = [], []
    for r in rows:
        cont = r['container']
        ok = (r['逐字相等'] and r['size_match'] and (cont['cabx'] >= 1 or cont['itxt'] >= 1)
              # 母图相符只有画风母图臂那一组才有这一列（R1／R2 裸串组读数里没这个键，取默认不判）。
              # 它是 R4 唯一的「漏传 images」防线：裸串的 prompt 与母图串只差前导一行，逐字列拦不住。
              and r.get('母图相符', True))
        (green if ok else red).append(r)
    copied, already = bring_in(green)
    with io.open(MANIFEST, encoding='utf-8') as _h179:
        man = json.load(_h179)
    items = {it['id']: it for it in man['items']}
    with io.open(NOTES, encoding='utf-8') as _h182:
        notes = json.load(_h182)

    added = resynced = 0
    appended = retained = 0
    kept = []
    promoted = []
    for r in sorted(green, key=lambda x: x['id']):
        eid, old, new = r['id'], r['replaced_cell'], GALLERY_PREFIX + r['id'] + '/' + r['file']
        files = list(items[eid]['image_file'] or [])
        if old is None:
            # 补投面里「此前零图」那 9 条没有可替换的格：占格口径只能是新增首格，读数里逐字写「为首占」，
            # 判据侧（test_image_assets.CELL_PAT 走不到就走 '为首占' 分支）拿这句去核清单实际格数。
            # 幂等：重跑时那一格挂的已经是本轮新文件，此时「无旧格可替」与「新格已在册」两者只能有其一。
            assert (not files) or files == [new], (eid, '零图条目的清单格面不是「空」也不是「恰好本轮那一格」：%s'
                                                       % files)
            slot = 1
            if not files:
                appended += 1
            occupy = '本条此前无格为首占第1格'
        else:
            # 已回填过的那一格挂的是本轮新文件；没回填过的挂的是旧文件。两者恰有其一才继续，
            # 都不是说明清单被别处动过（或本轮文件换了名），停手让人复核。
            assert (old in files) != (new in files), (eid, 'replaced_cell 与本轮新格不同在/不同在清单里：'
                                                           '清单被别处动过，先人工复核')
            slot = (files.index(new) if new in files else files.index(old)) + 1
            occupy = '替换第%d格 %s' % (slot, old)
        status = items[eid]['status']
        assert status in cfg['statuses'], (eid, '状态「%s」不在本组回填口径 %s 里，回填不覆盖其它结论'
                                           % (status, '／'.join(cfg['statuses'])))
        bound = items[eid].get('image_prompt_sha256')
        if bound:
            assert cfg['occupy_all'], (eid, '该条已绑定摘要，本组没有「全部占格」裁定，停手人工裁决')
            kept.append(eid)
        if bound and bound == items[eid].get('prompt_sha256'):
            guard = GUARD_KEPT_SAME % bound[:12]
            retained += 1
        elif bound:
            guard = GUARD_KEPT % str(bound)[:12]
        else:
            guard = GUARD
        if status == '待开图':
            # 零图条目拿到本轮枚就不再是「待开图」；挪到待复验只是进复验队列，不是验收（验收归签署通道）。
            items[eid]['status'] = '待复验'
            promoted.append(eid)
        cont = r['container']
        head = (cfg['head'] % eid) + '投后机械对账读数（%s，%s，%s，%d字节，sha12=%s，caBX=%d、iTXt=%d；%s）：%s'
        note = head % (
            new, occupy, r['dims'], r['bytes'], r['sha256_12'], cont['cabx'], cont['itxt'], guard,
            '%s%s 实发串逐字相等：本轮发起 %d 次（逐字 %d／非逐字 %d，登记作废发起 %d）；'
            '落盘 %d 枚（冻结带内，ts=%s）；尺寸与清单声明一致（%s）。'
            '占格为%s，其余 %d 格原样保留、旧文件不删。%s'
            % (PROVENANCE[group], (CATCHUP_DELEGATION % cfg['catchup']) if eid in catchup else '',
               r['投次'], r['逐字发起数'], r['非逐字发起数'], r['登记作废发起数'],
               1, r['ts_text'], r['dims'],
               '新增首格' if old is None else '替换第 %d 格' % slot,
               0 if old is None else len(files) - 1,
               ACCEPTED_FACE[status]))
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
        if old is None:
            if not files:
                files.append(new)   # 新增首格：这一条此前零图，本轮枚就是它的第 1 格
        else:
            files[slot - 1] = new   # 已回填过时这一行是原地重写，不改格位
        items[eid]['image_file'] = files
        items[eid]['batch'] = '%s-%s%s' % (items[eid]['type'], eid, cfg['suffix'])

    with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as _h263:
        _h263.write(json.dumps(notes, ensure_ascii=False, indent=2) + '\n')
    with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as _h265:
        _h265.write(json.dumps(man, ensure_ascii=False, indent=2) + '\n')
    print('%s 组回填：%d 条（新增 %d／改口重打 %d），判绿未回填 0，判红不回填 %d 条：%s'
          % (group, len(green), added, resynced, len(red), ' '.join(x['id'] for x in red) or '—'))
    print('范围收束：--only %s → 本轮只动 %d 条（其余判绿行原样不重打，历史正文的委托原句不被本轮顶掉）'
          % (only or '（未限制＝读数全量）', len(green)))
    print('占格口径：替换旧格 %d 条／新增首格（此前零图）%d 条；零图条目状态由待开图挪记待复验 %d 条（挪状态不是验收）'
          % (len(green) - appended, appended, len(promoted)))
    print('绑定摘要分档：维持原绑定且串未变（摘要未过期）%d 条／维持原绑定但摘要已过期（重绑归人工）%d 条／留空 %d 条'
          % (retained, len(kept) - retained, len(green) - len(kept)))
    print('读数来源 %s｜档串 %s｜image_prompt_sha256 脚本一律不写不撤'
          % (cfg['readings'], cfg['suffix']))
    print('请进仓内图集交付落点 数据/图集/<ID>/：新拷 %d 枚／已在仓内且逐字节相符 %d 枚（仓外原件 0 删）' % (copied, already))
    if cfg['occupy_all']:
        print('「全部占格」例外通道：已带绑定摘要仍占格 %d 条（摘要原样保留，过期与否见上一行分档）：%s'
              % (len(kept), ' '.join(sorted(kept)) or '—'))
    return 0


if __name__ == '__main__':
    if len(sys.argv) not in (2, 4) or sys.argv[1] not in ROUNDS \
            or (len(sys.argv) == 4 and sys.argv[2] != '--only'):
        print('用法：backfill_round.py <R1|R2|R4> [--only 送入串台账文件名]')
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[3] if len(sys.argv) == 4 else None))
