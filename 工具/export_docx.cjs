const fs = require('node:fs');
const path = require('node:path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, WidthType, BorderStyle,
  ShadingType, TableOfContents, PageNumber, LevelFormat,
} = require('docx');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, '钛湖城城市设定集-完整合订本.md'), 'utf8');
// 封面计数从名录现取，与 compile_book.py 的副标题同口径；名录扩容后不必手改这里。
const registry = JSON.parse(fs.readFileSync(path.join(root, '数据', '城市空间名录.json'), 'utf8'));
const countBy = {};
for (const e of registry.entries) countBy[e.type] = (countBy[e.type] || 0) + 1;
const settlementCount = countBy['产业小镇'] + countBy['特色村落'];
const interiorCount = countBy['功能区'] + countBy['标志性建筑'];
const totalEntries = registry.entries.length;
const contentWidth = 9906;
const columns = [2600, 7306];
const body = [];

function columnsFor(count) {
  if (count === 2) return columns;
  if (count === 3) return [1200, 5306, 3400];
  if (count === 4) return [600, 1900, 5906, 1500];
  const even = Math.floor(contentWidth / count);
  const widths = Array.from({ length: count }, (_, i) => i === count - 1 ? contentWidth - even * (count - 1) : even);
  return count > 1 ? widths : [contentWidth];
}

function runs(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(part => new TextRun({
    text: part.startsWith('**') ? part.slice(2, -2) : part.replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1'),
    bold: part.startsWith('**'),
  }));
}

function metadataTable(lines) {
  const border = { style: BorderStyle.SINGLE, size: 2, color: 'D9E1DD' };
  const headerCells = lines[0].trim().slice(1, -1).split('|').length;
  const widths = columnsFor(headerCells);
  const rows = lines.filter(line => !/^\|[\s:|-]+\|$/.test(line)).map((line, rowIndex) => {
    const cells = line.trim().slice(1, -1).split('|').map(cell => cell.trim());
    return new TableRow({ cantSplit: true, children: cells.map((text, i) => new TableCell({
      width: { size: widths[i] || widths[widths.length - 1], type: WidthType.DXA },
      borders: { top: border, bottom: border, left: border, right: border },
      shading: { fill: rowIndex === 0 ? 'E5EDE8' : 'FAFBF9', type: ShadingType.CLEAR },
      margins: { top: 45, bottom: 45, left: 110, right: 110 },
      children: [new Paragraph({ spacing: { before: 0, after: 0, line: 240 }, children: [new TextRun({ text, size: 18, bold: rowIndex === 0 })] })],
    })) });
  });
  return new Table({ width: { size: contentWidth, type: WidthType.DXA }, columnWidths: widths, rows });
}

body.push(new Paragraph({ spacing: { before: 1200, after: 280 }, children: [new TextRun({ text: '钛湖城', size: 72, bold: true, color: '243F3C' })] }));
body.push(new Paragraph({ spacing: { after: 360 }, children: [new TextRun({ text: '城市设定集 · 完整合订本', size: 36, color: '344B4E' })] }));
body.push(new Paragraph({ children: [new TextRun({ text: `${settlementCount} 个外围聚落  /  ${interiorCount} 项城市空间  /  ${countBy['居民区']} 个著名居民区`, size: 24 })] }));
body.push(new Paragraph({ children: [new TextRun({ text: '2013 年原创虚构城市正典 · 版本 1.0', size: 22 })] }));
body.push(new Paragraph({ spacing: { before: 500 }, children: runs('中心有湖，河流延伸，四面环山。以空间参数、可绘制外观和真实生活节奏，建立可持续创作的山水城市。') }));
body.push(new Paragraph({ children: runs('使用本书前先阅读城市总纲的面积与人口口径。空间索引图、全域村镇图、可检索JSON与单卷文件随交付包提供。') }));
body.push(new Paragraph({ pageBreakBefore: true, heading: HeadingLevel.HEADING_1, children: [new TextRun('卷目导航')] }));
body.push(new Paragraph({ children: runs(`可使用Word左侧导航窗格按地点ID查找。本文件已设置打开时自动更新域：Word会询问是否更新目录，选"是"即可刷新页码；若未弹出提示，全选后按F9。正文及全部${totalEntries}个地点已完整写入，不依赖目录刷新。`) }));
body.push(new TableOfContents('目录', { hyperlink: true, headingStyleRange: '1-1' }));

const lines = source.split(/\r?\n/);
for (let i = 0; i < lines.length; i++) {
  const line = lines[i].trim();
  if (!line || line === '---') continue;
  if (line.startsWith('|')) {
    const tableLines = [];
    while (i < lines.length && lines[i].trim().startsWith('|')) tableLines.push(lines[i++]);
    i--;
    body.push(metadataTable(tableLines));
    body.push(new Paragraph({ spacing: { after: 30 }, children: [] }));
    continue;
  }
  const heading = /^(#{1,3})\s+(.+)$/.exec(line);
  if (heading) {
    if (i === 0) continue;
    const level = heading[1].length;
    body.push(new Paragraph({
      heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][level - 1],
      pageBreakBefore: level === 1,
      keepNext: true,
      children: runs(heading[2]),
    }));
  } else if (line.startsWith('- ')) {
    body.push(new Paragraph({ numbering: { reference: 'body-bullets', level: 0 }, children: runs(line.slice(2)) }));
  } else {
    body.push(new Paragraph({ widowControl: true, children: runs(line.replace(/^>\s?/, '')) }));
  }
}

const document = new Document({
  features: { updateFields: true },
  creator: '钛湖城城市设定项目',
  title: '钛湖城城市设定集：完整合订本',
  subject: '原创虚构城市空间、产业、建筑、居住与AI创作正典',
  description: `包含${totalEntries}个独立地点详档及城市总纲、AI创作手册。`,
  styles: {
    default: { document: { run: { font: 'Microsoft YaHei', size: 21, color: '24312E' }, paragraph: { spacing: { after: 85, line: 300 } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: 'Microsoft YaHei', size: 34, bold: true, color: '000000' }, paragraph: { outlineLevel: 0, spacing: { before: 320, after: 240 }, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: 'Microsoft YaHei', size: 28, bold: true, color: '000000' }, paragraph: { outlineLevel: 1, spacing: { before: 260, after: 160 }, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { font: 'Microsoft YaHei', size: 24, bold: true }, paragraph: { outlineLevel: 2, spacing: { before: 160, after: 100 }, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: 'body-bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 350, hanging: 180 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1050, bottom: 1050, left: 1000, right: 1000 } } },
    headers: { default: new Header({ children: [new Paragraph({ children: [new TextRun({ text: '钛湖城  /  城市空间与生活设定', size: 17, color: '61746B' })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: '原创虚构设定  ·  ', size: 16 }), new TextRun({ children: [PageNumber.CURRENT], size: 16 })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(document).then(buffer => {
  const output = path.join(root, '钛湖城城市设定集-完整合订本.docx');
  fs.writeFileSync(output, buffer);
  console.log(JSON.stringify({ output, bytes: buffer.length, bodyBlocks: body.length }));
}).catch(error => { console.error(error); process.exitCode = 1; });
