const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel, BorderStyle,
  WidthType, ShadingType, VerticalAlign, PageNumber, PageBreak, UnderlineType
} = require('docx');
const fs = require('fs');

// ===== 颜色常量 =====
const RED     = "C0392B";
const ORANGE  = "D35400";
const YELLOW  = "F39C12";
const GREEN   = "1E8449";
const BLUE    = "1A5276";
const DARK    = "1C2833";
const GRAY    = "7F8C8D";
const LTGRAY  = "ECF0F1";
const MTGRAY  = "BDC3C7";
const WHITE   = "FFFFFF";
const LTBLUE  = "D6EAF8";
const LTYELL  = "FEF9E7";
const LTRED   = "FDEDEC";
const LTGRN   = "EAFAF1";

// ===== 边框 =====
const bdr = (color = MTGRAY) => ({ style: BorderStyle.SINGLE, size: 4, color });
const borders = (c) => ({ top: bdr(c), bottom: bdr(c), left: bdr(c), right: bdr(c) });
const noBdr = () => ({ top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } });

// ===== 单元格 =====
function cell(text, width, opts = {}) {
  const {
    bold = false, color = DARK, bg = null, align = AlignmentType.LEFT,
    vAlign = VerticalAlign.CENTER, size = 20, italic = false, borders: b = borders()
  } = opts;
  const run = new TextRun({ text, bold, color, font: "Arial", size, italics: italic });
  const para = new Paragraph({
    alignment: align,
    spacing: { before: 60, after: 60 },
    children: [run]
  });
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders: b,
    shading: bg ? { fill: bg, type: ShadingType.CLEAR } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: vAlign,
    children: [para]
  });
}

function hdrCell(text, width, bg = BLUE) {
  return cell(text, width, { bold: true, color: WHITE, bg, align: AlignmentType.CENTER, size: 20 });
}

function hCell(text, width) {
  return hdrCell(text, width, BLUE);
}

// ===== 段落辅助 =====
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: true,
    children: [new TextRun({ text, bold: true, font: "Arial", size: 32, color: WHITE })]
  });
}

function h2(text, pageBreak = false) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    pageBreakBefore: pageBreak,
    children: [new TextRun({ text, bold: true, font: "Arial", size: 26, color: BLUE })]
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, bold: true, font: "Arial", size: 22, color: ORANGE })]
  });
}

function para(runs, opts = {}) {
  const { spacing = { before: 80, after: 80 }, align = AlignmentType.LEFT, indent } = opts;
  return new Paragraph({
    alignment: align,
    spacing,
    indent,
    children: Array.isArray(runs) ? runs : [new TextRun({ text: runs, font: "Arial", size: 20 })]
  });
}

function bold(text, color = DARK) {
  return new TextRun({ text, bold: true, font: "Arial", size: 20, color });
}

function run(text, opts = {}) {
  return new TextRun({ text, font: "Arial", size: 20, ...opts });
}

function note(text, color = RED) {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    indent: { left: 360 },
    children: [
      new TextRun({ text: "⚠  ", font: "Arial", size: 20, bold: true, color }),
      new TextRun({ text, font: "Arial", size: 20, italics: true, color })
    ]
  });
}

function bullet(text, level = 0, ref = "bullets") {
  return new Paragraph({
    numbering: { reference: ref, level },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Arial", size: 20 })]
  });
}

function numbered(text, level = 0) {
  return bullet(text, level, "numbers");
}

function spacer(before = 120) {
  return new Paragraph({ spacing: { before, after: 0 }, children: [new TextRun("")] });
}

function divider(color = MTGRAY) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color } },
    children: [new TextRun("")]
  });
}

function callout(text, bg = LTBLUE, borderColor = BLUE) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [
      new TableCell({
        width: { size: 9360, type: WidthType.DXA },
        borders: { top: { style: BorderStyle.SINGLE, size: 12, color: borderColor }, bottom: bdr(borderColor), left: { style: BorderStyle.SINGLE, size: 20, color: borderColor }, right: bdr(borderColor) },
        shading: { fill: bg, type: ShadingType.CLEAR },
        margins: { top: 100, bottom: 100, left: 200, right: 200 },
        children: [new Paragraph({ spacing: { before: 60, after: 60 }, children: [new TextRun({ text, font: "Arial", size: 20 })] })]
      })
    ]})]
  });
}

// ===== 封面区块 =====
function coverBlock() {
  return [
    new Paragraph({ spacing: { before: 400, after: 0 }, children: [new TextRun("")] }),
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [9360],
      rows: [new TableRow({ children: [
        new TableCell({
          width: { size: 9360, type: WidthType.DXA },
          borders: noBdr(),
          shading: { fill: DARK, type: ShadingType.CLEAR },
          margins: { top: 400, bottom: 400, left: 400, right: 400 },
          children: [
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 160 }, children: [
              new TextRun({ text: "MF0001/MF0002 回转窑", bold: true, font: "Arial", size: 40, color: WHITE })
            ]}),
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 160 }, children: [
              new TextRun({ text: "脱硫设施专项现场核查要点", bold: true, font: "Arial", size: 44, color: YELLOW })
            ]}),
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 }, children: [
              new TextRun({ text: "——双碱法工艺 + 自动监测异常深度推演", font: "Arial", size: 24, color: MTGRAY })
            ]}),
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 0 }, children: [
              new TextRun({ text: "线索来源：自动监测异常线索（2026-03） + 排污许可合规检查（2026-07）", font: "Arial", size: 20, color: GRAY })
            ]}),
            new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 0 }, children: [
              new TextRun({ text: "编制日期：2026-07-18    适用法律：现行有效（至 2026-08-14）", font: "Arial", size: 20, color: GRAY })
            ]}),
          ]
        })
      ]})]
    }),
    spacer(300),
  ];
}

// ===== 两列信息表 =====
function infoTable(rows, widths = [3000, 6360]) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map(([label, value, bg]) =>
      new TableRow({ children: [
        cell(label, widths[0], { bold: true, bg: bg || LTBLUE, borders: borders(MTGRAY) }),
        cell(value, widths[1], { bg: bg ? "F8F9FA" : WHITE, borders: borders(MTGRAY) })
      ]})
    )
  });
}

// ===== 多列表头 =====
function multiHeaderTable(headers, rows, colWidths, headerBg = BLUE) {
  const total = colWidths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({ children: headers.map((h, i) => hdrCell(h, colWidths[i], headerBg)) }),
      ...rows.map(r => new TableRow({ children: r.map((v, i) => {
        const isObj = typeof v === 'object' && v !== null && 'text' in v;
        return cell(isObj ? v.text : v, colWidths[i], isObj ? v : {});
      })}))
    ]
  });
}

// ===== 检查项 =====
function checkTable(groups) {
  // groups: [{ title, bg, items: [[text, subtext], ...] }]
  const allRows = [];
  for (const g of groups) {
    // 标题行
    allRows.push(new TableRow({ children: [
      new TableCell({
        columnSpan: 2,
        width: { size: 9360, type: WidthType.DXA },
        borders: borders(BLUE),
        shading: { fill: g.bg || BLUE, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 160, right: 160 },
        children: [new Paragraph({ spacing: { before: 40, after: 40 }, children: [
          new TextRun({ text: g.title, bold: true, font: "Arial", size: 22, color: WHITE })
        ]})]
      })
    ]}));
    for (const item of g.items) {
      const [main, sub, rowBg] = item;
      allRows.push(new TableRow({ children: [
        new TableCell({
          width: { size: 720, type: WidthType.DXA },
          borders: borders(MTGRAY),
          shading: { fill: rowBg || WHITE, type: ShadingType.CLEAR },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          verticalAlign: VerticalAlign.CENTER,
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "□", font: "Arial", size: 22 })] })]
        }),
        new TableCell({
          width: { size: 8640, type: WidthType.DXA },
          borders: borders(MTGRAY),
          shading: { fill: rowBg || WHITE, type: ShadingType.CLEAR },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [
            new Paragraph({ spacing: { before: 30, after: sub ? 20 : 30 }, children: [new TextRun({ text: main, font: "Arial", size: 20 })] }),
            ...(sub ? [new Paragraph({ spacing: { before: 0, after: 30 }, children: [new TextRun({ text: sub, font: "Arial", size: 18, italics: true, color: GRAY })] })] : [])
          ]
        })
      ]}));
    }
  }
  return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [720, 8640], rows: allRows });
}

// ===== 主文档 =====
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "\u25CF", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 480, hanging: 280 }, spacing: { before: 40, after: 40 } },
                   run: { font: "Arial", size: 20, color: BLUE } } },
        { level: 1, format: LevelFormat.BULLET, text: "\u25CB", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 900, hanging: 280 }, spacing: { before: 30, after: 30 } },
                   run: { font: "Arial", size: 18, color: ORANGE } } },
        { level: 2, format: LevelFormat.BULLET, text: "\u25A0", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1320, hanging: 280 }, spacing: { before: 30, after: 30 } },
                   run: { font: "Arial", size: 16, color: GREEN } } },
      ]},
      { reference: "numbers", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 480, hanging: 280 }, spacing: { before: 40, after: 40 } },
                   run: { font: "Arial", size: 20 } } },
        { level: 1, format: LevelFormat.DECIMAL, text: "%1.%2.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 900, hanging: 320 }, spacing: { before: 30, after: 30 } },
                   run: { font: "Arial", size: 18 } } },
      ]},
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: WHITE },
        paragraph: { spacing: { before: 240, after: 160 }, outlineLevel: 0,
          shading: { fill: BLUE, type: ShadingType.CLEAR },
          indent: { left: 200, right: 200 } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: WHITE },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1,
          shading: { fill: BLUE, type: ShadingType.CLEAR },
          indent: { left: 160, right: 160 } } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: ORANGE },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: ORANGE } } } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 } // ~2cm
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: MTGRAY } },
          spacing: { before: 0, after: 80 },
          children: [
            new TextRun({ text: "MF0001/MF0002回转窑脱硫设施专项现场核查要点  |  2026-07-18  |  现行有效", font: "Arial", size: 16, color: GRAY })
          ]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: MTGRAY } },
          spacing: { before: 80, after: 0 },
          children: [
            new TextRun({ text: "第 ", font: "Arial", size: 16, color: GRAY }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: GRAY }),
            new TextRun({ text: " 页 / 共 ", font: "Arial", size: 16, color: GRAY }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: "Arial", size: 16, color: GRAY }),
            new TextRun({ text: " 页", font: "Arial", size: 16, color: GRAY }),
          ]
        })]
      })
    },
    children: [

      // ===== 封面 =====
      ...coverBlock(),

      // ===== 法律时效声明 =====
      h2("⚖ 法律时效声明", false),
      callout(
        "本清单依据截至 2026-07-18 的现行有效法律编制。主要适用：《大气污染防治法》《排污许可管理条例》《污染源自动监控管理办法》（原国家总局令第28号）。" +
        "\n《生态环境法典》于 2026-08-15 正式施行，届时相关法条将全面替换。8月15日后办理的案件，须改引法典条文（第1113-1134条等）。",
        LTRED, RED
      ),
      spacer(120),

      // ===== 线索综合研判 =====
      h2("一、两条线索的综合研判", false),
      para([
        bold("线索1（2026年3月）："), run("自动监测异常——2026年1-2月累计超标18次（颗粒物13次+SO₂1次+NOₓ4次），工况标记18次（停炉8次+启炉10次），"),
        bold("100%关联。"), run("超标期间涉及工况标记18次。")
      ]),
      spacer(60),
      para([
        bold("线索2（2026年7月）："), run("排污许可合规检查——MF0001/MF0002回转窑均采用"),
        bold("双碱法脱硫", RED), run("，疑似难以稳定达标排放。")
      ]),
      spacer(120),
      h3("1.1 两条线索的真实关系"),
      callout(
        "这不是两个独立事件，这是一个链条。\n" +
        "双碱法工艺本身能力不足（线索2）→ 长期运行时脱硫效率不稳定（日常积累）→ " +
        "2026年1-2月集中爆发（线索1：超标18次）→ " +
        "企业用'工况标记'策略性覆盖（线索1：100%关联）→ " +
        "7月核查时发现工艺本身问题（线索2）。" +
        "\n真正的问题在链条上游（工艺选型），真正的问题出口在链条下游（工况标记）。",
        LTBLUE, BLUE
      ),
      spacer(120),
      h3("1.2 工况标记100%关联的三种成因分析"),
      multiHeaderTable(
        ["成因类型", "技术特征", "核查突破口"],
        [
          ["① 真实工况驱动", "超标集中在启停炉前后1-2小时内，正常工况数据平稳", "剔除标记时段后，正常工况是否还有超标"],
          ["② 标记被当作「合规盾牌」", "标记时段超过实际启停需要；正常工况下也超标，趁标记期间「合法化」", "DCS曲线：标记时长 vs 实际启停时长逐一比对"],
          ["③ 数据造假（最恶劣）", "工况标记真实，但超标数据被人为调节；数采仪参数被设置", "标定记录时间轴：超标发生前后是否恰好没有校准"],
        ],
        [2800, 3580, 2980], BLUE
      ),
      spacer(120),
      note("关键判断标准：18次超标中，只要有任何一次发生在'工况稳定运行2小时以后'，成因①就不成立。"),
      spacer(120),

      h3("1.3 双碱法用于回转窑的本质缺陷"),
      para([bold("双碱法脱硫的核心缺陷："), run("对入口SO₂浓度波动极为敏感，不是一个'稳定的达标工艺'，而是一个'需要高频运维才能勉强达标的工艺'。")]),
      spacer(80),
      multiHeaderTable(
        ["运行状态", "脱硫效率", "出口SO₂表现"],
        [
          ["药剂充足 + 稳定运行", "75-85%", "稳定达标"],
          ["药剂消耗后未及时补充", "骤降至30-50%", "瞬间超标"],
          ["喷嘴堵塞/结垢", "持续下降至10-20%", "长期超标"],
          ["回转窑原料硫含量突然升高", "超出设计能力", "溢出式超标（最危险）"],
        ],
        [3500, 2800, 3060], BLUE
      ),
      spacer(80),
      note("双碱法通常适用于入口SO₂浓度 < 2000 mg/m³的场景。危废/化工回转窑的入口SO₂浓度常高达数千至数万mg/m³——这正是工艺适配性的根本疑问所在。"),
      spacer(120),

      // ===== 现场核查四步推演 =====
      h2("二、现场核查四步推演", false),
      h3("2.1 第一步：查链条——从工况标记的'出口'往上游查"),
      para([bold("核心原则："), run("不要先查设备，先查链条。从工况标记的'出口'往上游查，证据链最清晰。")]),
      spacer(80),
      para([bold("现场第一个动作："), run("要求企业提供2026年1月-2月完整DCS历史曲线，在现场实时核查。盯着屏幕做三件事：")]),
      spacer(60),
      multiHeaderTable(
        ["核查动作", "DCS应出现的特征信号", "信号缺失意味着什么"],
        [
          ["核查A：停炉标记真实性", "炉膛温度从运行温度持续下降；引风机电流下降；燃料停止供给", "DCS无降温曲线 → 标记虚假"],
          ["核查B：启炉标记真实性", "炉膛温度从常温/低温持续上升；引风机电流上升；燃料恢复供给", "DCS无升温曲线 → 标记虚假"],
          ["核查C：循环泵启停逻辑", "脱硫循环泵启停与回转窑启停的联锁记录", "回转窑运行但循环泵停 → 设施不正常运行"],
        ],
        [2100, 4130, 3130], BLUE
      ),
      spacer(80),
      h3("核心动作：剔除标记时段后，正常工况下是否还有超标"),
      callout(
        "这是整个核查的核心动作。如果18次超标全部发生在标记时段，且标记时段与DCS完全吻合——" +
        "工况标记本身可能是真实的，问题就集中在工艺选型（线索2）。" +
        "\n但如果剔除标记时段后，正常工况还有超标——工况标记就涉嫌被当作'数据保护工具'使用。",
        LTBLUE, BLUE
      ),
      spacer(80),
      h3("2.2 第二步：脱硫塔核查——三组数据同时比对"),
      para([bold("关键原则："), run("不要只看pH值，pH只是最浅层。真正有价值的是三组数据的同时比对。")]),
      spacer(80),
      multiHeaderTable(
        ["数据类型", "核查要点", "发现异常意味着什么"],
        [
          ["脱硫浆液pH（实测）", "在循环泵出口取样实测，记录读数；与运行记录对比", "pH偏低 → 药剂不足；与记录不符 → 记录造假"],
          ["脱硫塔入口SO₂（便携仪）", "与在线监测出口数据同时读数；计算实测脱硫效率", "效率低于设计值 → 设施能力不足或低效运行"],
          ["循环泵电流（钳表实测）", "实测运行电流，与运行记录对比", "电流偏低 → 泵出力不足；与记录不符 → 记录造假"],
        ],
        [2500, 3700, 3160], BLUE
      ),
      spacer(80),
      para([bold("实测脱硫效率计算公式：")]),
      callout("脱硫效率 =（入口SO₂ - 出口SO₂）/ 入口SO₂ × 100%\n双碱法设计效率通常为65-80%。若实测效率只有30-40%，直接证明设施能力不足或严重低效运行。", LTYELL, YELLOW),
      spacer(80),
      note("实用技巧：将实测效率与企业排污许可证执行报告中的'脱硫效率'对比。如果执行报告写的是'脱硫效率75%'，但你实测只有35%——这就是最直接的超标故意认定证据。企业不可能不知道自己的设施效率。", RED),
      spacer(120),

      h3("2.3 第三步：在线监测设备——时间轴交叉比对法"),
      para([bold("制作一张时间轴图：")]),
      spacer(60),
      bullet("横轴：2026年1-7月"),
      bullet("纵轴叠压5条线：① 超标发生时间（18次） ② 工况标记时间（18次） ③ 在线监测设备校准时间 ④ 手工比对监测时间 ⑤ 脱硫剂采购/投加时间"),
      spacer(80),
      para([bold("时间轴比对的典型发现模式：")]),
      multiHeaderTable(
        ["发现模式", "典型含义", "证据意义"],
        [
          ["超标发生前后恰好没有校准记录", "刻意制造的'数据空白期'", "涉嫌监测数据造假"],
          ["比对监测报告偏差恰好控制在±10%以内", "人为调校在线设备", "第三方比对报告可信度低"],
          ["每次超标后都有一次标定记录（时间倒签）", "事后补做标定", "标定记录不具有证据效力"],
        ],
        [3000, 3200, 3160], BLUE
      ),
      spacer(80),
      para([bold("具体核查动作：")]),
      bullet("调取所有标定记录，逐一检查标气钢瓶标签上的有效期截止日"),
      bullet("检查是否有'超标发生 → 事后补做标定记录 → 标定时间倒签'模式"),
      bullet("检查比对监测报告（手工采样 vs 在线数据），偏差是否刻意控制在±10%以内"),
      spacer(120),

      h3("2.4 第四步：历史档案——环评/许可证/验收三对照"),
      para([bold("核心问题："), run("为什么当初选了双碱法？查三个历史节点：")]),
      spacer(80),
      multiHeaderTable(
        ["历史节点", "核查内容", "发现的问题"],
        [
          ["环评报告阶段", "环评批复的脱硫工艺认定；环评预测的入口SO₂浓度；双碱法选型依据", "环评预测值 vs 实际运行值是否存在显著差异"],
          ["许可证核发阶段", "许可排放量计算基础（环评预测值/设计值/实测值）；许可下达时是否重新核算处理能力", "许可工艺与实际能力是否匹配"],
          ["验收阶段", "三同时'性能测试报告；测试时的脱硫效率数据；测试条件（入口SO₂浓度）", "验收时设施是否达到设计效率"],
        ],
        [2200, 4000, 3160], BLUE
      ),
      spacer(80),
      callout(
        "三组数据通常存在逐级放大问题：\n" +
        "环评预测入口SO₂ 800 mg/m³ → 许可证按设计值核算 → " +
        "实际运行时原料变化导致入口SO₂ 2000-3000 mg/m³ → 双碱法超出处理能力。\n" +
        "这是系统性工艺失配——企业长期运行中应该发现并向许可机关报告。未报告继续排放，涉嫌'明知能力不足仍继续排放'。",
        LTRED, ORANGE
      ),
      spacer(120),

      // ===== 核查清单 =====
      h2("三、现场核查要点清单", false),
      h3("3.1 核查前准备"),
      checkTable([{
        title: "【文件类】提前调取（到达现场前完成）",
        bg: BLUE,
        items: [
          ["排污许可证（副本）——重点关注：许可工艺、许可排放量、排放限值", null, LTGRAY],
          ["环评批复 + 环评报告书/表（脱硫工艺认定章节）", null, WHITE],
          ["环保「三同时」验收报告（脱硫设施是否与环评一致）", null, LTGRAY],
          ["2026年1-7月自动监测数据全量报告（含工况标记记录）", null, WHITE],
          ["DCS系统历史曲线（炉膛温度/蒸汽流量/引风机电流/脱硫系统启停信号）", null, LTGRAY],
          ["在线监测设备校准记录、标气有效期记录（2026年1-7月）", null, WHITE],
          ["2026年排污许可执行报告", null, LTGRAY],
          ["企业自行监测报告（手工监测比对数据）", null, WHITE],
          ["脱硫剂（NaOH/石灰）采购入库记录、投加记录（2026年1-7月）", null, LTGRAY],
          ["脱硫塔巡检记录（pH值、循环泵电流等运行参数）", null, WHITE],
        ]
      }, {
        title: "【设备类】现场携带",
        bg: BLUE,
        items: [
          ["执法记录仪（满电、存储卡充足）", null, LTGRAY],
          ["便携式烟气分析仪（现场比对在线监测数据）", null, WHITE],
          ["便携式pH计 + pH试纸（测量脱硫浆液pH）", null, LTGRAY],
          ["温枪/红外测温仪（核查炉膛实际温度 vs DCS记录）", null, WHITE],
          ["钳形电流表（核查循环泵实际电流 vs 运行记录）", null, LTGRAY],
          ["照相机（含长焦，拍摄设备铭牌参数）", null, WHITE],
          ["GPS定位仪（拍摄排放口坐标，核对许可证附件）", null, LTGRAY],
          ["个人防护装备（安全帽、防毒面具、反光背心）", null, WHITE],
        ]
      }]),
      spacer(120),

      h3("3.2 自动监测异常专项核查（线索1）"),
      checkTable([{
        title: "A区：工况标记真实性核查（100%关联的核心验证）",
        bg: RED,
        items: [
          ["调取2026年1月1日—2月24日完整DCS历史曲线（不可仅要复印件）", "在企业控制室实时查看，逐一核查18次标记的起止时间", LTRED],
          ["逐一核查18次工况标记的DCS特征信号", "停炉：炉膛温度持续下降；启炉：炉膛温度持续上升；缺信号即标记虚假", LTGRAY],
          ["核查启炉/停炉标记时长是否超过实际需要", "实际启炉只需3小时，标记了8小时 → 刻意延长标记时段覆盖正常工况超标", WHITE],
          ["剔除标记时段后，单独提取正常工况时段的SO₂/颗粒物/NOₓ数据", "若正常工况存在未标记超标 → 涉嫌故意漏标 → 工况标记被当作数据保护工具", LTGRAY],
          ["核查循环泵启停记录与超标时段的交叉比对", "若循环泵停运时段与超标时段高度吻合 → 设施不正常运行", WHITE],
        ]
      }, {
        title: "B区：在线监测设备合规性核查",
        bg: ORANGE,
        items: [
          ["检查采样探头是否堵塞/破损（拍照固定）", "采样管路是否全程伴热（≥120℃），有无打折/泄漏", LTGRAY],
          ["调取2026年1-7月全部标定记录，逐一检查标气钢瓶有效期", "过期标气 → 该次校准无效 → 对应时段数据合法性存疑", WHITE],
          ["核查标定频次是否符合规范（HJ 355：SO₂每24h自动标定/每周全量程标定）", "缺失记录 → 设备运行不规范", LTGRAY],
          ["制作5条线时间轴（超标/标记/校准/比对/投加）", "寻找'数据空白期'模式：超标前后恰好无校准记录", WHITE],
          ["使用便携式烟气分析仪现场比对在线监测数据（同时读数）", "偏差超过±15% → 在线监测数据准确性存疑", LTGRAY],
          ["核查数采仪日志，查看是否存在数据掉线/补录/异常断连记录", "补录数据需特别关注：是否有事后人工干预", WHITE],
        ]
      }]),
      spacer(120),

      h3("3.3 排污许可工艺合规性专项核查（线索2）"),
      checkTable([{
        title: "C区：许可工艺与实际工艺一致性",
        bg: GREEN,
        items: [
          ["许可证记载工艺 vs 现场实际工艺 vs 环评批复工艺——三对照", "三者一致 → 合规；任一不一致 → 需深入定性（批建不符/批非所建）", LTGRN],
          ["环评批复对脱硫工艺的认定是什么？", "环评预测的入口SO₂浓度是多少？双碱法选型依据是什么？", LTGRAY],
          ["许可证核发时，是否重新核算了脱硫设施的处理能力？", "许可排放量计算基础：环评预测值 vs 设计值 vs 实测值", WHITE],
          ["「三同时」验收时，脱硫设施是否进行了性能测试？测试效率数据是多少？", "性能测试报告中的脱硫效率 vs 实际运行效率", LTGRAY],
        ]
      }, {
        title: "D区：双碱法脱硫设施运行状态（最关键）",
        bg: GREEN,
        items: [
          ["实测脱硫塔入口SO₂浓度（便携仪） + 出口浓度（在线监测）→ 计算效率", "实测效率 vs 设计效率（65-80%）：低于40% → 严重低效运行", LTGRN],
          ["在脱硫塔浆液池或循环泵出口取样，现场实测pH值", "正常范围8-9；pH < 8 → 药剂不足或循环异常（拍照+记录实测值）", LTGRAY],
          ["查看NaOH/石灰石料仓存量（拍照），调取2026年1-7月投加记录", "与超标时段逐一交叉比对：超标时段投加量偏低 → 设施不正常运行", WHITE],
          ["用钳形电流表实测循环泵运行电流，与运行记录对比", "电流偏低 → 泵出力不足；与记录不符 → 台账造假", LTGRAY],
          ["查看脱硫塔塔壁腐蚀/结垢情况、喷嘴堵塞情况（拍照特写）", "结垢厚度超设计允许值 + 运行记录显示'定期清理' → 台账与DCS矛盾", WHITE],
          ["查看脱硫系统与回转窑的联锁逻辑记录", "回转窑运行但脱硫系统未同步启动 → 设施不正常运行", LTGRAY],
        ]
      }]),
      spacer(120),

      // ===== 类案镜鉴 =====
      h2("四、类案镜鉴（三个最接近的真实案例）", true),
      h3("4.1 类案一：某危废焚烧回转窑工况标记造假案（2023年）"),
      multiHeaderTable(
        ["要素", "内容"],
        [
          ["情形", "双碱法脱硫 + 频繁工况标记 + 长期超标，高度相似"],
          ["关键突破", "调取DCS曲线发现，标记为'停炉'的时段内，炉膛温度从未降至停炉阈值。企业辩称'减产运行'，但DCS显示引风机电流与正常运行无异"],
          ["认定结论", "工况标记虚假，以逃避监管方式定性"],
          ["法律适用", "《大气污染防治法》第108条（篡改监测数据）"],
          ["处理结果", "移送公安，追究刑事责任"],
          ["本案启示", "DCS曲线是工况标记真实性的终极验证。不要只看台账，不要只看标记记录——回到DCS参数。"],
        ],
        [1800, 7560], BLUE
      ),
      spacer(100),

      h3("4.2 类案二：某水泥回转窑在线监测数据造假案（2024年，珠三角）"),
      multiHeaderTable(
        ["要素", "内容"],
        [
          ["情形", "脱硫工艺选型不当 + 在线监测数据长期稳定在标准限值90-95%，恰好不超过标准"],
          ["关键突破", "开展为期一周的高频手工监测，发现实际排放值显著高于在线监测数据。最终确认在线监测设备被'调试'在标准限值下运行"],
          ["认定结论", "在线监测数据造假，第三方监测机构参与比对，偏差超过±20%"],
          ["处理结果", "第三方监测机构被处罚；涉案企业被责令停产整治"],
          ["本案启示", "工况数据过于'精准稳定'本身就是异常信号。便携仪现场比对是破解之道。"],
        ],
        [1800, 7560], BLUE
      ),
      spacer(100),

      h3("4.3 类案三：某化工回转窑台账造假案（2025年）"),
      multiHeaderTable(
        ["要素", "内容"],
        [
          ["情形", "工况标记与实际启停时间不符 + 脱硫塔结垢严重但运行记录均为'正常'"],
          ["关键突破", "现场核查脱硫塔时发现喷嘴堵塞、塔壁结垢厚度超设计允许值。企业运行记录显示'定期清理'，但DCS没有清理作业记录。台账与DCS矛盾"],
          ["认定结论", "设施不正常运行 + 台账造假，合并处罚"],
          ["处理结果", "行政处罚，并处限期整改"],
          ["本案启示", "设施运行台账与DCS记录的交叉验证，是发现台账造假的有效手段。两者不一致 → 必有一方造假。"],
        ],
        [1800, 7560], BLUE
      ),
      spacer(100),

      // ===== 败诉风险 =====
      h2("五、败诉风险评估与定性逻辑", true),
      h3("5.1 两条败诉路径"),
      multiHeaderTable(
        ["败诉路径", "触发条件", "企业抗辩点", "破解方法"],
        [
          ["路径一：只查设备不查链条\n证据链断裂",
           "仅凭在线监测超标+工况标记直接认定违法",
           "工况标记期间排放符合豁免条件；设施正常运行；数据已如实上传",
           "必须拿出DCS曲线证明标记时段不合理；剔除标记后证明正常工况也有超标"],
          ["路径二：定性过度\n从重认定错误",
           "将'工况标记'直接定性为'监测数据造假'",
           "提交完整DCS曲线证明所有标记均与实际工况吻合 → 定性依据不成立",
           "工况标记本身不违法，违法的是标记时段是否真实。标记真实则问题回到工艺选型和设施效率"],
        ],
        [2200, 2400, 2400, 2360], RED
      ),
      spacer(100),
      callout(
        "正确逻辑：工况标记本身不违法 → 违法的是标记时段是否真实 → 真实则问题回到工艺选型和设施效率。" +
        "\n定性建议：先以'超标排放 + 设施不正常运行'立案（DCS+实测效率）；" +
        "若确认标记虚假，再加重认定为'篡改监测数据'。",
        LTRED, RED
      ),
      spacer(100),

      h3("5.2 核查结论的三个层次"),
      multiHeaderTable(
        ["层次", "事实认定", "法律定性", "证据要求", "处置方向"],
        [
          ["层次一\n（最确定）",
           "实测脱硫效率低于设计值",
           "设施低效运行\n→ 超标排放\n→ 不正常运行防治设施",
           "现场实测pH值+入口/出口SO₂；DCS与台账交叉比对；脱硫塔内部状况照片",
           "行政处罚"],
          ["层次二\n（需要深入）",
           "工况标记时段与DCS参数不完全吻合",
           "标记时段不合理\n→ 数据保护工具使用\n→ 篡改监测数据（加重）",
           "2026年1-2月完整DCS曲线；启停炉时长与标记时长逐一比对；循环泵启停记录",
           "如确认 → 加重处罚\n如无法确认 → 退回层次一"],
          ["层次三\n（需要判断）",
           "双碱法从一开始就不适合这个回转窑",
           "明知能力不足仍继续排放\n→ 主观故意认定",
           "环评/许可证/验收三对照；许可下达时工艺可行性论证；企业是否向许可机关报告",
           "如确认 → 移送公安\n（涉嫌环境污染犯罪）"],
        ],
        [1500, 2400, 2200, 2200, 1060], BLUE
      ),
      spacer(80),
      note("处置逻辑：层次一定性为基础 → 层次二若确认则加重 → 层次三若确认则移送公安。三个层次层层递进，证据支撑到哪层，定性就到哪层。"),
      spacer(100),

      // ===== 现行法律依据 =====
      h2("六、现行有效法律依据速查", true),
      multiHeaderTable(
        ["发现的异常", "涉嫌违法", "现行有效法律依据"],
        [
          ["双碱法设施不正常运行（pH低/药剂不足/循环泵停）导致超标", "超标排放 + 不正常运行防治污染设施", "《大气污染防治法》第99条（超标排放）+ 第108条（不正常运行）"],
          ["工况标记时段与DCS实际不符（虚标）", "篡改监测数据（不正常运行防治设施的特殊形态）", "《大气污染防治法》第108条；《污染源自动监控管理办法》第18条"],
          ["工况标记100%覆盖所有超标，正常工况数据刻意不标记", "故意遗漏监测数据", "《大气污染防治法》第108条（篡改）；HJ 355规范"],
          ["许可证工艺与实际工艺不符", "未按排污许可证规定运行污染防治设施", "《排污许可管理条例》第17条"],
          ["在线监测设备未按频次校准", "污染源自动监控设施运行不规范", "HJ 355规范（技术规范）；《污染源自动监控管理办法》"],
          ["超标后未按1小时报告", "未履行自动监测异常报告义务", "《大气污染防治法》第24条"],
          ["超标18次，逾期未改正", "拒不改正 → 按日连续处罚", "《行政处罚法》第72条；《大气污染防治法》第99条"],
        ],
        [3200, 3200, 2960], BLUE
      ),
      spacer(80),

      // ===== 核查时间轴 =====
      h2("七、现场核查操作时间轴（建议）", true),
      multiHeaderTable(
        ["阶段", "时长", "核查内容", "注意事项"],
        [
          ["出发前", "出发前完成", "调取DCS数据下载权限；便携仪充电；文件准备", "不要通知企业具体查什么"],
          ["第一次现场（侦察）", "2-4小时", "收集DCS曲线（只看不带走）；脱硫塔现场实测（pH/入口SO₂/循环泵电流）；在线监测设备外观检查", "侦察性质，不要亮底牌；让企业看到你在做什么但不完全理解你在查什么"],
          ["回单位分析", "1-2天", "分析DCS曲线；计算实测脱硫效率；制作5条线时间轴；制定第二次现场精准打击方案", "形成完整证据链判断；确定是否需要第二次现场"],
          ["第二次现场（收网）", "2-3小时", "精准锁定问题环节；固化关键证据；制作现场检查笔录；企业签字确认", "带着分析结论来；直接针对已发现的问题点；注意程序合规（2人以上、出示证件、权利告知）"],
        ],
        [1800, 1800, 3400, 2360], GREEN
      ),
      spacer(80),
      note("核心原则：第一次去是侦察，不是收网。很多人第一次检查时就让企业知道你在查什么——企业会立刻补齐台账、补充药剂、修改DCS记录。", RED),
      spacer(100),

      // ===== 证据固定清单 =====
      h2("八、证据固定清单", true),
      h3("8.1 照片/视频证据"),
      checkTable([{
        title: "【在线监测类】",
        bg: BLUE,
        items: [
          ["在线监测站房全景（含设备铭牌参数）", null, LTGRAY],
          ["采样探头安装位置照片（含参照物，显示与排放口的距离）", null, WHITE],
          ["伴热管线完整路径（检查有无打折/泄漏）", null, LTGRAY],
          ["数采仪屏幕数据（当场打印/拍照，显示时间戳）", null, WHITE],
          ["便携式烟气分析仪比对读数（与在线监测同时读数，照片中两者同框）", null, LTGRAY],
          ["DCS曲线屏幕截图（超标时段 + 工况标记时段，显示完整时间轴）", null, WHITE],
        ]
      }, {
        title: "【脱硫设施类】",
        bg: BLUE,
        items: [
          ["脱硫塔外观 + 铭牌参数（处理能力/设计效率）", null, LTGRAY],
          ["脱硫浆液取样照片 + pH计读数（特写，显示实测值）", null, WHITE],
          ["循环泵铭牌 + 电流实测值（钳表读数照片）", null, LTGRAY],
          ["脱硫剂料仓存量（标注库存量，拍照）", null, WHITE],
          ["喷嘴堵塞/塔壁结垢情况（特写，多角度）", null, LTGRAY],
          ["脱硫塔内部检查（如进入受限空间，须做好安全防护并记录）", null, WHITE],
        ]
      }, {
        title: "【台账记录类】",
        bg: BLUE,
        items: [
          ["脱硫剂投加记录（2026年1-7月原件或盖章件）", null, LTGRAY],
          ["脱硫塔巡检记录（pH值/循环泵电流等运行参数）", null, WHITE],
          ["工况标记审批记录（谁标记、谁批准）", null, LTGRAY],
          ["标定校准记录（原件，标气钢瓶标签照片）", null, WHITE],
          ["企业提供的台账/记录文件（现场核对后拍照，注意骑缝章）", null, LTGRAY],
        ]
      }]),
      spacer(100),

      h3("8.2 笔录要点（现场检查笔录）"),
      checkTable([{
        title: "【笔录必须记录的内容】",
        bg: ORANGE,
        items: [
          ["检查时间、地点、天气", "精确到分钟；天气影响采样条件需说明"],
          ["执法人员信息 + 出示证件情况", "≥2名执法人员，记录证件编号"],
          ["企业陪同人员信息 + 职务", "企业负责人或环保负责人签字"],
          ["18次超标时段逐一记录", "时间/污染物/超标倍数/DCS标记类型，逐一对应"],
          ["工况标记合理性判断", "启炉/停炉时长 vs DCS实际曲线的比对结论（当场得出）"],
          ["脱硫设施运行参数实测记录", "pH值/循环泵电流/脱硫效率（现场计算并记录）"],
          ["企业人员对超标原因的解释", "逐字记录，不加工、不概括"],
          ["现场发现的异常情况", "设备故障/药剂不足/数据不一致，逐一列明"],
          ["企业负责人签字确认", "逐页签字 + 骑缝签字；拒绝签字注明原因 + 见证人签字"],
        ]
      }]),
      spacer(80),
      note("笔录现场性原则：现场制作的笔录必须现场完成，不得回到单位后补做。每次修改处须企业人员签字或盖章确认。", RED),
      spacer(100),

      // ===== 核查结论框架 =====
      h2("九、核查结论框架（模板）", true),
      callout(
        "【MF0001/MF0002回转窑脱硫设施专项核查报告】\n\n" +
        "一、基本情况\n" +
        "企业名称：______ | 回转窑编号：MF0001/MF0002\n" +
        "许可工艺：双碱法脱硫 | 许可排放量：______ t/a\n" +
        "超标历史：2026年1-2月累计超标18次（颗粒物13+SO₂1+NOₓ4）\n\n" +
        "二、核查发现\n" +
        "（一）手续合规性\n" +
        "□ 排污许可证与环评批复一致  □ 存在批小建大/批非所建\n" +
        "□ 许可工艺与实际不符（许可证：______  实际：______）\n\n" +
        "（二）设施运行状态\n" +
        "□ 双碱法药剂补充正常  □ 存在药剂断供/循环泵停运\n" +
        "□ pH值持续偏低（实测：______，正常≥8）  □ 脱硫塔存在腐蚀/堵塞\n" +
        "□ 脱硫效率（实测）：______%（设计：______%）\n\n" +
        "（三）自动监测数据\n" +
        "□ 工况标记合理（启炉/停炉时长与DCS一致）\n" +
        "□ 工况标记存在虚标（标记时长 > DCS实际时长，差：______h）\n" +
        "□ 正常工况存在未标记超标：______次\n" +
        "□ 在线监测数据与比对监测偏差≤±15% / 偏差>±15%（实测：______%）\n\n" +
        "（四）在线监测设备\n" +
        "□ 校准记录完整（2026年1-7月）  □ 标气在有效期内\n" +
        "□ 存在未按频次校准情形（缺失：______次）\n\n" +
        "三、涉嫌违法行为\n" +
        "1. _________ — 依据：《大气污染防治法》第____条（现行有效）\n" +
        "2. _________ — 依据：《排污许可管理条例》第____条\n\n" +
        "四、处置建议\n" +
        "□ 立案调查  □ 责令限期整改  □ 责令限制生产/停产整治\n" +
        "□ 按日连续处罚（如拒不改正）  □ 移送公安（涉嫌犯罪）\n" +
        "□ 向许可核发机关反馈许可证工艺问题",
        LTBLUE, BLUE
      ),
      spacer(100),

      // ===== 附件 =====
      h2("十、附件：关键数据当场比对表", true),
      multiHeaderTable(
        ["比对项", "在线监测数据", "便携仪实测/DCS数据", "偏差", "判定"],
        [
          ["SO₂出口浓度（mg/m³）", "", "", "±______%", "≤±15%正常"],
          ["脱硫效率（%）", "（执行报告记载）", "（现场计算）", "差______%", "设计65-80%"],
          ["工况标记启炉时长", "标记：______h", "DCS：______h", "差：______h", ">0存疑"],
          ["工况标记停炉时长", "标记：______h", "DCS：______h", "差：______h", ">0存疑"],
          ["循环泵电流（A）", "记录：______A", "实测：______A", "差：______A", ">0存疑"],
          ["脱硫浆液pH值", "记录：______", "实测：______", "差：______", "<8异常"],
          ["标气有效期", "有效期至：______", "当前：______", "是否过期", "过期禁用"],
        ],
        [2600, 2200, 2200, 1200, 1160], BLUE
      ),
      spacer(100),

      // ===== 注意事项 =====
      h2("十一、现场执法注意事项", true),
      h3("程序合规（最容易导致败诉的程序问题）"),
      checkTable([{
        title: "【必查项】程序合规性检查",
        bg: RED,
        items: [
          ["执法人员≥2人，出示执法证件（记录证件编号）", "单人执法 → 程序违法 → 证据效力存疑"],
          ["现场检查笔录须现场制作完成，不得回单位后补做", "事后补做 → 程序违法 → 证据效力存疑"],
          ["每一次修改处须企业人员签字确认（骑缝签字）", "涂改处无签字 → 真实性存疑"],
          ["现场检查笔录须当事人逐页签字，拒绝签字注明原因+见证人签字", "拒绝签字处理不规范 → 送达效力存疑"],
          ["照片/视频证据须显示时间戳（执法记录仪自动生成）", "无时间戳 → 证据关联性存疑"],
          ["采样须当事人或见证人在场并签字确认", "无见证人 → 采样程序合法性存疑"],
        ]
      }]),
      spacer(80),
      h3("特别提示"),
      multiHeaderTable(
        ["提示事项", "内容"],
        [
          ["法典衔接倒计时", "2026年8月15日《生态环境法典》施行，本案8月15日前结案适用现行法；8月15日后改引法典第1113-1134条"],
          ["追责期限", "超标排放：2年（无危害后果）/ 5年（有危害后果）。2026年1-7月违法行为仍在追责期内"],
          ["按日连续处罚条件", "超标18次 + 责令限期改正后仍超标 → 满足按日连续处罚条件。重点关注：责令改正通知书是否已送达"],
          ["移送公安条件", "实测超标3倍以上（重金属）：移送公安。本案SO₂/颗粒物/NOₓ需结合排放标准计算是否达到3倍"],
        ],
        [2400, 6960], BLUE
      ),

      spacer(200),
      divider(),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 120, after: 60 },
        children: [new TextRun({ text: "本清单依据截至2026-07-18的现行有效法律编制，仅供参考，不替代正式行政程序。", font: "Arial", size: 18, italics: true, color: GRAY })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 40, after: 0 },
        children: [new TextRun({ text: "——《生态环境执法督察评查专家》v5.0  2026-07-18", font: "Arial", size: 18, italics: true, color: GRAY })]
      }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  const outPath = "/Users/mac/Desktop/FlowWiki/ops/monitoring/MF0001_MF0002回转窑脱硫设施专项现场核查要点_2026-07-18.docx";
  fs.writeFileSync(outPath, buffer);
  console.log("OK: " + outPath);
}).catch(e => { console.error(e); process.exit(1); });
