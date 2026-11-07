# -*- coding: utf-8 -*-
"""C139 代签验收的申报判据与签署状态派生：闸门侧与工作单侧共用这一份，不各抄一遍抬头正则。

为什么单独成模块：判据挂在 工具/test_image_assets.py（闸门），而「视觉复验」列要按真实签署状态
渲染进 工具/verify_image_assets.py（产物）。两边各写一份抬头正则就会漂——判据改了而工作单还按
旧抬头认申报，等于把「已验收但没申报」渲染成「已验收（机械代签）」：闸门红了，产物却在替它洗白。

口径来源：数据/设定裁定记录.json 的 C139。守卫是「没申报不许签」，不是「不许签」；
accepted 只表示机械判据验收通过，不表示人工逐张目视通过。
"""
import re

SIGN_DECL = re.compile(r'^C139代签验收([A-Z]+\d+)：')
SIGN_ELEMENTS = ('执行人', '委托来源', '依据', '人工逐张目视未执行')


def declaration_rows(rows):
    """按抬头取申报行（不按位置：同一 ID 之后还会被追加别类人工读数）。"""
    return [r for r in (rows or []) if SIGN_DECL.match(r)]


def check_sign_declaration(item, rows):
    """已验收条目的代签申报判据，返回违例清单（空＝达标）。

    申报行必须点名本条 ID、写齐执行人／委托来源／依据／「人工逐张目视未执行」四要素，
    并复述当前绑定摘要的前 12 位。少任一项，accepted 就会被下一轮读成「画风已人工过关」，
    或者把一份绑在别的文件上的验收洗成本条的验收。"""
    bound = str(item.get('image_prompt_sha256') or '')
    decl = declaration_rows(rows)
    if not decl:
        return ['已验收但没有 C139 代签申报行']
    d = decl[-1]
    bad = []
    if SIGN_DECL.match(d).group(1) != item['id']:
        bad.append('代签申报点名的 ID 与本条不符')
    for tok in SIGN_ELEMENTS:
        if tok not in d:
            bad.append('代签申报缺要素:' + tok)
    if not bound or bound[:12] not in d:
        bad.append('代签申报没复述绑定摘要前 12 位')
    # 申报行还必须点名清单当前在册的那一格。少这一句，「上一轮的申报行」就能顶替「本轮的申报行」：
    # 2026-11-07 补投把 39 条的定档格换成新画风枚，旧申报行复述的绑定摘要前 12 位一点没变
    # （C135 绑的是提示词串，串没换），要素也齐，只看要素与摘要就会让那份绑在被替换旧格上的
    # 验收继续宣称本轮过关——摘要对得上格，才叫对得上本条。
    cells = [str(c or '').replace('\\', '/').rsplit('/', 1)[-1] for c in (item.get('image_file') or [])]
    cells = [c for c in cells if c]
    if cells and not any(c in d for c in cells):
        bad.append('代签申报没点名当前在册的格（点名的那格已被后一轮替换，旧验收不能顶本轮）')
    return bad


def visual_column(item):
    """工作单「视觉复验」列：按真实状态派生，不再恒写待人工复验（C139）。

    已验收且申报合规格 ⇒ 机械代签、人工目视未执行（申报合规格本身就要求写明这一句）；
    已验收但申报不合规格 ⇒ 直接把闸门结论写进产物，不让工作单替它宣称验收成立。"""
    if not item.get('image_file') or item.get('status') == '待开图':
        return '无图，待开图'
    if item.get('status') == '已验收':
        if check_sign_declaration(item, item.get('review_note_history') or []):
            return '已验收（代签申报不合规格，闸门判红）'
        return '已验收（机械代签）／人工目视未执行'
    return '待人工复验'