# -*- coding: utf-8 -*-
"""docx 的官方 XSD 模式校验（ECMA-376 第五版 Part 1 Transitional + OPC 件面）。

为什么单独有这一支：`工具/verify_docx.py` 核的是「合订本 md 的块面与 docx 的 body 块面逐块对得上、
渲染没有把内联标记漏成正文」，它不判 XML 是否符合官方模式——一份结构上合法、内容对得上但违反 wml 模式的
docx 在 Word 里可能直接报「无法打开」。这一支补的就是那层官方模式判定，取件件面对官方件校验。

模式件在哪：`工具/官方模式/`（36 件，逐件字节数与 sha256 见 `工具/官方模式/取源与校验.json`）。
其中 30 件是 ECMA 官方发布件（26 件 Transitional 主套件＋4 件 OPC 套件），逐字未改；
`xml.xsd`／`dc.xsd`／`dcterms.xsd`／`dcmitype.xsd` 是官方件引用的外部命名空间（W3C 与 Dublin Core），
按官方件自己的 schemaLocation 取回，也逐字未改；
`driver_wml.xsd`／`driver_core.xsd` **是我方自建的接入件**，不改变任何模式语义，只把「官方件里那两条
没有写 schemaLocation 的 import」和「写了远端 http 地址的 import」在离线环境里指到本地同名件——
libxml 对同一个 schema 构造内已加载的命名空间会复用，于是校验时不再联网。

MCE 那一层怎么算（口径写明，不装成已过关）：ECMA-376 Part 1 的 `wml.xsd` 不声明 Part 3 的 `mc:` 属性，
也不声明被 `mc:Ignorable` 点名那些扩展命名空间里的属性（本轮实测：`word/numbering.xml` 上有 2 个
`w14:restartNumberingAfterBreak`），所以未做消费视图的原件按 Part 1 校验必报未声明。本轮把两档读数都记下来：
`原样校验违例数` 档保留这条事实，`通过` 档＝先按 Part 3 的 Ignorable 规则做出合规消费者视图
（把件内 `mc:Ignorable` 自己点名的那些前缀所映射命名空间里的属性与元素按不存在处理，`mc:` 属性同剥），
再逐件校验。判定只认后者，但前者必须非空可查，否则「剥掉了才过」这件事就没人看得见。
件内若出现 `mc:AlternateContent` 这类 Part 3 结构元素，本校验器不实现 Choice 解析，当场判违例交人工，
不默认放行（本轮实测 0 个）。

跑法：python -X utf8 工具/validate_docx_xsd.py [--out 数据/Word模式校验.json]
退出码：违例件面数＝0 且 未覆盖命名空间＝0 → 0；否则非零。
"""
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
SCHEMA_DIR = os.path.join(HERE, '官方模式')
DOCX = os.path.join(ROOT, '钛湖城城市设定集-完整合订本.docx')
DEFAULT_OUT = os.path.join(ROOT, '数据', 'Word模式校验.json')

MC_NS = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
# 命名空间 → 模式件。接入件（driver）只出现在官方件自带无定位 import 的那两支上。
NS_TO_SCHEMA = {
    'http://schemas.openxmlformats.org/wordprocessingml/2006/main': 'driver_wml.xsd',
    'http://schemas.openxmlformats.org/drawingml/2006/main': 'dml-main.xsd',
    'http://schemas.openxmlformats.org/package/2006/relationships': 'opc-relationships.xsd',
    'http://schemas.openxmlformats.org/package/2006/content-types': 'opc-contentTypes.xsd',
    'http://schemas.openxmlformats.org/package/2006/metadata/core-properties': 'driver_core.xsd',
    'http://schemas.openxmlformats.org/officeDocument/2006/custom-properties': 'shared-documentPropertiesCustom.xsd',
    'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties': 'shared-documentPropertiesExtended.xsd',
}
_cache = {}


def schema_for(fname):
    if fname not in _cache:
        with io.open(os.path.join(SCHEMA_DIR, fname), 'rb') as fp:
            _cache[fname] = etree.XMLSchema(etree.parse(fp))
    return _cache[fname]


def strip_mce(root):
    """按 Part 3 的 Ignorable 消费规则做出「合规消费者视图」，返回读数（原件不受影响）。

    规则取自本件自己的 `mc:Ignorable`：那一串前缀映射出的命名空间属于「消费者必须忽略的扩展层」，
    所以那些命名空间里的属性与元素都按不存在处理；`mc:` 自身的属性也只服务分发层，一并剥掉。
    `mc:AlternateContent` 不在这里处理——那要按 Choice 的 Requires 判定选支，本校验器不实现 Part 3 的
    Choice 解析，遇到就判「需人工」而不是猜一支。
    """
    ignorable = root.get('{%s}Ignorable' % MC_NS) or ''
    prefixes = ignorable.split()
    nss = set()
    for p in prefixes:
        uri = (root.nsmap or {}).get(p)
        if uri:
            nss.add(uri)
    nss.discard(None)
    mc_prefix = '{%s}' % MC_NS
    removed_mc = removed_attrs = removed_elems = mc_elems = 0
    for el in list(root.iter()):
        if isinstance(el.tag, str) and el.tag.startswith(mc_prefix):
            mc_elems += 1
        for k in list(el.attrib):
            if k.startswith(mc_prefix):
                del el.attrib[k]
                removed_mc += 1
            elif any(k.startswith('{%s}' % n) for n in nss):
                del el.attrib[k]
                removed_attrs += 1
    for el in list(root.iter()):
        if isinstance(el.tag, str) and any(el.tag.startswith('{%s}' % n) for n in nss):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                removed_elems += 1
    return {'ignorable前缀': prefixes, 'ignorable命名空间数': len(nss),
            '剥掉的ignorable属性数': removed_attrs, '剥掉的ignorable元素数': removed_elems,
            '剥掉的mc属性数': removed_mc, 'mc元素数': mc_elems}


def validate(docx=DOCX):
    t0 = time.time()
    with zipfile.ZipFile(docx) as z:
        names = z.namelist()
        parts, uncovered = [], []
        for name in sorted(names):
            if not (name.endswith('.xml') or name.endswith('.rels')):
                continue
            raw = z.read(name)
            root = etree.fromstring(raw)
            ns = root.tag.split('}')[0].lstrip('{')
            fname = NS_TO_SCHEMA.get(ns)
            if fname is None:
                uncovered.append({'件': name, '根命名空间': ns})
                continue
            sch = schema_for(fname)
            mirror = etree.fromstring(raw)
            sch.validate(mirror)
            raw_violations = len(sch.error_log)
            stripped = etree.fromstring(raw)
            mce = strip_mce(stripped)
            ok = sch.validate(stripped) and mce['mc元素数'] == 0
            errs = [str(e.message)[:220] for e in sch.error_log]
            if mce['mc元素数']:
                errs.insert(0, '件内出现 mc:AlternateContent 之类的 Part 3 结构元素 %d 个：'
                               '本校验器不实现 Choice 解析，交人工判定，不默认放行' % mce['mc元素数'])
            parts.append({
                '件': name, '字节': len(raw), '根命名空间': ns, '模式件': fname,
                '原样校验违例数': raw_violations,
                'mcIgnorable前缀': mce['ignorable前缀'],
                '剥掉的ignorable属性数': mce['剥掉的ignorable属性数'],
                '剥掉的ignorable元素数': mce['剥掉的ignorable元素数'],
                '剥掉的mc属性数': mce['剥掉的mc属性数'],
                'Part3结构元素数': mce['mc元素数'],
                '通过': ok,
                '违例': [] if ok else errs,
            })
    bad = [p for p in parts if not p['通过']]
    with io.open(docx, 'rb') as fp:
        docx_sha = hashlib.sha256(fp.read()).hexdigest()
    with io.open(os.path.join(SCHEMA_DIR, '取源与校验.json'), encoding='utf-8') as fp:
        prov = json.load(fp)
    return {
        '说明': 'docx 各 XML 件对 ECMA-376 第五版官方 XSD 的模式校验读数（Part 1 Transitional＋OPC 套件）。',
        '口径': ('判定认「按 Part 3 Ignorable 消费视图校验」那一档（件内 mc:Ignorable 点名的扩展命名空间'
                 '与 mc: 属性都按不存在处理后再校验）；「原样校验违例数」同时记录不隐藏——Part 1 模式既不声明'
                 ' mc: 属性也不声明那些扩展命名空间，这条非空是规范事实而不是本产物的缺陷。'
                 '出现 Part 3 结构元素（AlternateContent 等）不当通过，判违例交人工。'
                 '件面按根命名空间选模式件，不靠文件名猜；'
                 '出现映射外的命名空间一律记入 未覆盖命名空间 并让退出码非零，不当通过。'),
        'docx': os.path.basename(docx),
        'docx_sha256': docx_sha,
        'docx字节': os.path.getsize(docx),
        '模式套件': {'件数': prov['件数'], '官方件数': prov['官方件数'],
                 '接入件数': prov['接入件数'], '套件摘要前12位': prov['套件摘要前12位'],
                 '清单': '工具/官方模式/取源与校验.json'},
        '统计': {'XML件面': len(parts), '通过': len(parts) - len(bad), '违例': len(bad),
               '原样校验违例合计': sum(p['原样校验违例数'] for p in parts),
               '剥掉的ignorable属性合计': sum(p['剥掉的ignorable属性数'] for p in parts),
               '剥掉的ignorable元素合计': sum(p['剥掉的ignorable元素数'] for p in parts),
               '剥掉的mc属性合计': sum(p['剥掉的mc属性数'] for p in parts),
               'Part3结构元素合计': sum(p['Part3结构元素数'] for p in parts),
               '未覆盖命名空间': len(uncovered)},
        '件面': parts,
        '未覆盖命名空间': uncovered,
        '校验器': '工具/validate_docx_xsd.py',
        '用时秒': round(time.time() - t0, 2),
    }


def main(argv):
    out = DEFAULT_OUT
    args = [a for a in argv[1:]]
    if len(args) == 2 and args[0] == '--out':
        out = args[1]
    elif args:
        print('用法：validate_docx_xsd.py [--out 输出json]')
        return 2
    rep = validate()
    with io.open(out, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(rep, ensure_ascii=False, indent=2) + '\n')
    s = rep['统计']
    print('docx 模式校验：%d 件面／通过 %d／违例 %d｜原样档违例合计 %d（Part 1 不声明 mc: 与被 Ignorable 的扩展命名空间）'
          '｜剥掉的 ignorable 属性 %d／元素 %d｜剥掉的 mc 属性 %d｜Part 3 结构元素 %d｜未覆盖命名空间 %d'
          % (s['XML件面'], s['通过'], s['违例'], s['原样校验违例合计'],
             s['剥掉的ignorable属性合计'], s['剥掉的ignorable元素合计'], s['剥掉的mc属性合计'],
             s['Part3结构元素合计'], s['未覆盖命名空间']))
    for p in rep['件面']:
        if not p['通过']:
            print('  违例件 %s：%s' % (p['件'], p['违例'][:2]))
    for u in rep['未覆盖命名空间']:
        print('  未覆盖 %s（根命名空间 %s）' % (u['件'], u['根命名空间']))
    print('读数件：%s｜docx sha256 前12位 %s｜模式套件 %d 件（官方 %d＋接入 %d）'
          % (os.path.relpath(out, ROOT), rep['docx_sha256'][:12],
             rep['模式套件']['件数'], rep['模式套件']['官方件数'], rep['模式套件']['接入件数']))
    return 0 if s['违例'] == 0 and s['未覆盖命名空间'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
