const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, PageNumber, PageBreak, TabStopType, TabStopPosition
} = require("docx");

const OUT = "C:/Users/Administrator/WorkBuddy/执法督察评查专家团";

// ── Helpers ──
const border = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

function heading1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text, bold: true, size: 32, font: "SimHei", color: "1A5276" })], spacing: { before: 360, after: 200 } });
}
function heading2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, bold: true, size: 28, font: "SimHei", color: "D35400" })], spacing: { before: 280, after: 160 } });
}
function heading3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text, bold: true, size: 24, font: "KaiTi" })], spacing: { before: 200, after: 120 } });
}
function para(text, opts = {}) {
  return new Paragraph({ spacing: { after: 120, line: 360 }, children: [new TextRun({ text, font: "SimSun", size: 21, ...opts })] });
}
function boldPara(text) {
  return new Paragraph({ spacing: { after: 120, line: 360 }, children: [new TextRun({ text, font: "SimSun", size: 21, bold: true })] });
}
function cell(text, width, opts = {}) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA }, margins: cellMargins,
    shading: opts.shade ? { fill: opts.shade, type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text, font: "SimSun", size: 18, bold: opts.bold, color: opts.color })] })]
  });
}
function infoRow(label, value, widths = [2800, 6560]) {
  return new TableRow({ children: [cell(label, widths[0], { bold: true, shade: "F0F4F8" }), cell(value, widths[1])] });
}

// ── Veto scan results ──
const vetoResults = {
  passed: true,
  notes: [
    { category: "程序类", id: "V09", name: "法制审核缺失/流于形式", status: "需核实", detail: "处罚决定书提到'经我局2026年第1次案审会研究决定'，但案卷中未见独立的法制审核意见书。根据《行政处罚法》第58条，重大处罚决定作出前须经法制审核。罚款29,000元是否属于'重大'取决于娄底市生态环境局的内部规定。" },
  ],
  allClear: "其余24项一票否决项均未触发。执法程序、证据链、法律适用、主体管辖、文书规范等各方面经扫描未发现否决级问题。"
};

// ── Scoring ──
const scoring = {
  dimensions: [
    { name: "一、立案审批", full: 10, score: 10, deductions: [] },
    { name: "二、调查取证", full: 25, score: 23, deductions: [{ item: "D1", desc: "询问笔录中刘忠于对部分问题回答'不清楚，要公司领导才知道'，虽不影响违法事实认定，但调查深度可进一步加强", pts: 2 }] },
    { name: "三、告知与陈述申辩", full: 15, score: 15, deductions: [] },
    { name: "四、法制审核与集体讨论", full: 10, score: 7, deductions: [{ item: "D2", desc: "案卷中未见独立的《法制审核意见书》，仅处罚决定书提到案审会研究决定，法制审核程序材料不完整", pts: 3 }] },
    { name: "五、行政处罚决定", full: 15, score: 14, deductions: [{ item: "D3", desc: "决定书第3页罚款金额OCR识别为'黯万玖仟元'，应为'肆万玖仟元'的OCR误差，但如原文确实有误则需补正", pts: 1 }] },
    { name: "六、文书送达与归档", full: 10, score: 9, deductions: [{ item: "D4", desc: "送达回证OCR模糊，签收日期不清晰，归档材料可读性需保证", pts: 1 }] },
    { name: "七、法律适用", full: 15, score: 14, deductions: [{ item: "D5", desc: "引用《大气污染防治法》时为2026年8月15日前的过渡期，现行有效；建议增加法典对应条文双标注", pts: 1 }] },
  ],
  totalFull: 100,
  totalScore: 92,
};

// ── Issues ──
const issues = [
  { no: "1", level: "中", category: "程序规范", desc: "法制审核材料不完整：案卷中未见独立的法制审核意见书。《行政处罚法》第58条规定特定情形须经法制审核，处罚决定书仅提及案审会研究决定，未说明是否已通过法制审核程序", ref: "《行政处罚法》第58条、《环境行政处罚办法》第52条", suggest: "补充法制审核意见书或书面说明法制审核情况，明确审查结论" },
  { no: "2", level: "低", category: "调查取证", desc: "调查深度可加强：对刘忠于的询问中，部分关键问题（如环评手续、历史处罚等）回答为'不清楚'，未进一步向了解情况的其他人员调查核实", ref: "《环境行政处罚办法》第26条", suggest: "对重要事实应尽可能向多名知情人调查核实，避免以单一回答作为调查终点" },
  { no: "3", level: "低", category: "法律适用", desc: "法典过渡期双标注缺失：引用《大气污染防治法》第48条第2款和第108条第5项，未按过渡期管理要求标注法典对应条文", ref: "生态环境法典过渡期管理指南", suggest: "增加法典双标注：《大气污染防治法》第48条第2款（→《生态环境法典》第11X0条）；第108条第5项（→《生态环境法典》第11X0条）" },
  { no: "4", level: "低", category: "文书规范", desc: "送达回证日期可读性问题：OCR扫描件中送达回证的签收日期模糊，可能影响原件查阅时的程序确认", ref: "案卷归档管理规定", suggest: "确保送达回证等关键文书原件清晰可读，必要时重新制作或标注" },
];

// ── Legal citation chain ──
const legalChain = [
  { level: 1, law: "《中华人民共和国大气污染防治法》", article: "第四十八条第二款", content: "工业企业应当采取密闭、围挡、遮盖、清扫、洒水等措施，减少内部物料的堆存、传输、装卸等环节产生的粉尘和气态污染物的排放。", role: "禁止性规范（义务条款）", transition: "→ 《生态环境法典》（2026.8.15施行）对应条款" },
  { level: 1, law: "《中华人民共和国大气污染防治法》", article: "第一百零八条第五项", content: "违反本法规定，钢铁、建材、有色金属、石油、化工、制药、矿产开采等企业，未采取集中收集处理、密闭、围挡、遮盖、清扫、洒水等措施，控制、减少粉尘和气态污染物排放的，由县级以上人民政府生态环境主管部门责令改正，处二万元以上二十万元以下的罚款；拒不改正的，责令停产整治。", role: "罚则", transition: "→ 《生态环境法典》对应条款" },
  { level: 2, law: "《中华人民共和国行政处罚法》", article: "第二十八条", content: "行政机关实施行政处罚时，应当责令当事人改正或者限期改正违法行为。", role: "责令改正依据" },
  { level: 2, law: "《中华人民共和国行政处罚法》", article: "第四十四条", content: "行政机关在作出行政处罚决定之前，应当告知当事人拟作出的行政处罚内容及事实、理由、依据，并告知当事人依法享有的陈述、申辩、要求听证等权利。", role: "告知程序依据" },
  { level: 2, law: "《中华人民共和国行政处罚法》", article: "第五十八条", content: "有下列情形之一，在行政机关负责人作出行政处罚的决定之前，应当由从事行政处罚决定法制审核的人员进行法制审核……", role: "法制审核依据" },
  { level: 2, law: "《中华人民共和国行政处罚法》", article: "第七十二条第一款第一项", content: "当事人逾期不履行行政处罚决定的，作出行政处罚决定的行政机关可以每日按罚款数额的百分之三加处罚款。", role: "逾期加罚依据" },
  { level: 3, law: "《湖南省生态环境保护行政处罚裁量权基准规定（2021版）》", article: "表13通用裁量表", content: "裁量起点Y=法定最低/法定最高×100%=10%，罚款=[Y+裁量百分值累加×(1-Y)]×最高罚款=29,000元", role: "裁量计算依据" },
  { level: 3, law: "《中华人民共和国行政复议法》", article: "第九条", content: "公民、法人或者其他组织认为具体行政行为侵犯其合法权益的，可以自知道该具体行政行为之日起六十日内提出行政复议申请。", role: "复议权利告知依据" },
  { level: 3, law: "《中华人民共和国行政诉讼法》", article: "第四十六条", content: "公民、法人或者其他组织直接向人民法院提起诉讼的，应当自知道或者应当知道作出行政行为之日起六个月内提出。", role: "诉讼权利告知依据" },
];

// ── Build Document ──
const fullWidth = 9360;
const halfWidth = 4680;

const children = [];

// === COVER ===
children.push(new Paragraph({ spacing: { before: 3000 }, children: [] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "生态环境行政执法案卷", font: "SimHei", size: 36, color: "1A5276" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: "评 查 报 告", font: "SimHei", size: 52, bold: true, color: "1A5276" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 800, after: 200 }, children: [new TextRun({ text: "━━━━━━━━━━━━━━━━━━━━━━", font: "SimSun", size: 21, color: "AAAAAA" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "案卷编号：娄环罚(冷)〔2026〕2号", font: "SimSun", size: 24 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "当事人：湖南省煤业集团金竹山矿业有限公司", font: "SimSun", size: 24 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "处罚机关：娄底市生态环境局", font: "SimSun", size: 24 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 }, children: [new TextRun({ text: "评查日期：2026年8月4日", font: "SimSun", size: 24 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400 }, children: [new TextRun({ text: "密级：内部 ● 不公开", font: "SimSun", size: 21, color: "CC0000" })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 300 }, children: [new TextRun({ text: "评查单位：执法督察评查专家团（AI辅助评查）", font: "SimSun", size: 20, color: "888888" })] }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// === MODULE 1: 案卷概况 ===
children.push(heading1("一、案卷概况"));
const overviewTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [2800, 6560],
  rows: [
    infoRow("案卷编号", "娄环罚(冷)〔2026〕2号"),
    infoRow("案件类型", "一般行政处罚案卷"),
    infoRow("当事人", "湖南省煤业集团金竹山矿业有限公司"),
    infoRow("统一社会信用代码", "914300001875251560"),
    infoRow("法定代表人", "刘文"),
    infoRow("注册地址", "冷水江市金竹西路"),
    infoRow("违法行为", "一平硐煤矿工业广场露天堆放次煤约1000吨、占地约200平方米，未采取密闭、围挡、遮盖等防尘措施"),
    infoRow("违反条款", "《大气污染防治法》第四十八条第二款（禁止性规范）"),
    infoRow("处罚条款", "《大气污染防治法》第一百零八条第五项（罚则）"),
    infoRow("处罚内容", "罚款人民币肆万玖仟元整（¥29,000）"),
    infoRow("处罚机关", "娄底市生态环境局"),
    infoRow("立案日期", "2025年12月16日（娄环冷立字[2025]47号）"),
    infoRow("决定日期", "2026年（案审会第1次会议研究决定，具体日期需核实）"),
    infoRow("裁量依据", "《湖南省生态环境保护行政处罚裁量权基准规定（2021版）》表13通用裁量表"),
    infoRow("案件来源", "上级交办（2025年12月11日交办问题线索核查）"),
  ]
});
children.push(overviewTable);
children.push(para(""));

// === MODULE 2: 评查依据 ===
children.push(heading1("二、评查依据"));
children.push(para("本次评查依据以下法律法规及规范性文件："));
children.push(para("1. 《中华人民共和国行政处罚法》（2021年修订）"));
children.push(para("2. 《中华人民共和国大气污染防治法》（2018年修订）"));
children.push(para("3. 《中华人民共和国行政复议法》（2023年修订）"));
children.push(para("4. 《中华人民共和国行政诉讼法》（2017年修订）"));
children.push(para("5. 《环境行政处罚办法》（环境保护部令第8号）"));
children.push(para("6. 《生态环境行政执法案卷评查细则（2024年修订版）》（环执法发〔2024〕4号）"));
children.push(para("7. 《湖南省生态环境保护行政处罚裁量权基准规定（2021版）》"));
children.push(para("8. 《生态环境法典》（2026年8月15日施行，过渡期双标注适用）"));
children.push(para(""));

// === MODULE 3: 25项一票否决扫描 ===
children.push(heading1("三、25项一票否决扫描结果"));
children.push(boldPara("扫描结论：✅ 未命中一票否决项（1项需核实，但不足以触发否决）"));
children.push(para(""));

children.push(heading2("3.1 扫描详情"));
const vetoTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [800, 1200, 1600, 5760],
  rows: [
    new TableRow({ children: [
      cell("类别", 800, { bold: true, shade: "D5E8F0" }),
      cell("编号", 1200, { bold: true, shade: "D5E8F0" }),
      cell("名称", 1600, { bold: true, shade: "D5E8F0" }),
      cell("结果", 5760, { bold: true, shade: "D5E8F0" }),
    ] }),
    ...(["V01-V10 程序类|全部通过：告知在决定之前(2026.2.2告知→案审会后决定)、两人执法(颜志强+杨程云)、亮证执法(现场笔录记载)、救济途径已告知、追诉时效未超(违法行为2025.12、2年内)、集体讨论(案审会)、听证不涉及(罚款<公民5千/法人5万标准)",
       "V11-V15 证据类|全部通过：证据链完整(现场笔录+照片4张+勘察图+2份询问笔录+营业执照+排污登记+环评批复+历史处罚决定书)、无采样/监测涉及、笔录签字完整",
       "V16-V18 法律适用类|全部通过：引用《大气污染防治法》在过渡期内现行有效、法条对应正确(第48条第2款→第108条第5项)、裁量计算与金额一致(¥29,000=14.5%×¥200,000)",
       "V19-V20 定性移送类|全部通过：不涉及移送公安(仅为未遮盖堆料)、不涉及查封扣押",
       "V21-V22 主体管辖类|全部通过：被处罚主体适格(统一社会信用代码可查)、娄底市生态环境局有管辖权",
       "V23-V25 文书期限类|全部通过：决定书要素齐全、不涉及强制执行",
    ].map(s => {
      const [cat, det] = s.split("|");
      return new TableRow({ children: [cell(cat, 800), cell("—", 1200), cell("全部通过", 1600), cell(det, 5760)] });
    })),
    new TableRow({ children: [
      cell("⚠️ 程序类", 800, { color: "CC6600" }),
      cell("V09", 1200, { color: "CC6600" }),
      cell("法制审核", 1600, { color: "CC6600" }),
      cell("需核实：案卷中未见独立的《法制审核意见书》。处罚决定书提及案审会研究决定，但法制审核程序材料不完整，建议补充。罚款29,000元的法制审核要求取决于娄底市局内部规定。", 5760, { color: "CC6600" }),
    ] }),
  ]
});
children.push(vetoTable);

// === MODULE 4: 规范性评分 ===
children.push(para(""));
children.push(heading1("四、规范性评分"));

const scoreTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [2200, 900, 900, 900, 1200, 3260],
  rows: [
    new TableRow({ children: [
      cell("评查维度", 2200, { bold: true, shade: "1A5276", color: "FFFFFF" }),
      cell("满分", 900, { bold: true, shade: "1A5276", color: "FFFFFF" }),
      cell("得分", 900, { bold: true, shade: "1A5276", color: "FFFFFF" }),
      cell("扣分", 900, { bold: true, shade: "1A5276", color: "FFFFFF" }),
      cell("得分率", 1200, { bold: true, shade: "1A5276", color: "FFFFFF" }),
      cell("备注", 3260, { bold: true, shade: "1A5276", color: "FFFFFF" }),
    ] }),
    ...scoring.dimensions.map((d, i) => new TableRow({ children: [
      cell(d.name, 2200),
      cell(String(d.full), 900),
      cell(String(d.score), 900),
      cell(d.deductions.length > 0 ? `-${d.deductions.reduce((s, x) => s + x.pts, 0)}` : "0", 900),
      cell(Math.round(d.score / d.full * 100) + "%", 1200),
      cell(d.deductions.map(x => `${x.item}: ${x.desc}`).join("；") || "—", 3260),
    ] })),
    new TableRow({ children: [
      cell("合 计", 2200, { bold: true, shade: "E8F0FE" }),
      cell(String(scoring.totalFull), 900, { bold: true, shade: "E8F0FE" }),
      cell(String(scoring.totalScore), 900, { bold: true, shade: "E8F0FE" }),
      cell(`-${scoring.totalFull - scoring.totalScore}`, 900, { bold: true, shade: "E8F0FE" }),
      cell(Math.round(scoring.totalScore / scoring.totalFull * 100) + "%", 1200, { bold: true, shade: "E8F0FE" }),
      cell("合格", 3260, { bold: true, shade: "E8F0FE" }),
    ] }),
  ]
});
children.push(scoreTable);

// === MODULE 5: 裁量审查 ===
children.push(para(""));
children.push(heading1("五、裁量审查"));
children.push(heading2("5.1 裁量表选择"));
children.push(para("☑ 正确：该违法行为不属于29张专用裁量表所列类型，适用表13通用裁量表。"));

children.push(heading2("5.2 裁量因素逐项核验"));
const discTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [1800, 2200, 1200, 4160],
  rows: [
    new TableRow({ children: [
      cell("裁量因素", 1800, { bold: true, shade: "D5E8F0" }),
      cell("案卷认定因子", 2200, { bold: true, shade: "D5E8F0" }),
      cell("百分值", 1200, { bold: true, shade: "D5E8F0" }),
      cell("证据支撑", 4160, { bold: true, shade: "D5E8F0" }),
    ] }),
    new TableRow({ children: [cell("裁量起点Y", 1800), cell("2万÷20万×100%", 2200), cell("10%", 1200), cell("《大气污染防治法》第108条法定罚款幅度2万-20万", 4160)] }),
    new TableRow({ children: [cell("①区域影响", 1800), cell("县级行政区域内", 2200, { shade: "F5F5F5" }), cell("0%", 1200, { shade: "F5F5F5" }), cell("询问笔录确认：冷水江市金竹山镇太中村", 4160, { shade: "F5F5F5" })] }),
    new TableRow({ children: [cell("②持续时间", 1800), cell("不足3个月", 2200), cell("0%", 1200), cell("询问笔录：堆放约30天左右", 4160)] }),
    new TableRow({ children: [cell("③发生地点", 1800), cell("生态保护红线区域外", 2200, { shade: "F5F5F5" }), cell("0%", 1200, { shade: "F5F5F5" }), cell("询问笔录确认：不属于生态保护红线区域", 4160, { shade: "F5F5F5" })] }),
    new TableRow({ children: [cell("④违法次数(两年内含本次)", 1800), cell("2次", 2200), cell("5%", 1200), cell("2024年5月31日被处罚（娄环罚决字(冷)(2024)1号），本次为2次", 4160)] }),
    new TableRow({ children: [cell("⑤不良影响(一年内)", 1800), cell("无", 2200, { shade: "F5F5F5" }), cell("0%", 1200, { shade: "F5F5F5" }), cell("询问笔录确认：无投诉", 4160, { shade: "F5F5F5" })] }),
  ]
});
children.push(discTable);

children.push(para(""));
children.push(heading2("5.3 计算公式复核"));
children.push(para("裁量百分值累计之和 = 0% + 0% + 0% + 5% + 0% = 5%", { bold: true }));
children.push(para("罚款金额 = [Y + (裁量百分值累计) × (1-Y)] × 法定最高罚款数额", { bold: true }));
children.push(para("         = [10% + 5% × (1-10%)] × 200,000"));
children.push(para("         = [0.10 + 0.05 × 0.90] × 200,000"));
children.push(para("         = 0.145 × 200,000"));
children.push(para("         = ¥29,000  ☑ 计算正确", { color: "008000" }));

// === MODULE 6: 程序节点验证 ===
children.push(para(""));
children.push(heading1("六、程序节点验证"));
children.push(para("按'五步法'程序节点逐一核验："));
const procTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [1500, 2000, 1500, 4360],
  rows: [
    new TableRow({ children: [cell("节点", 1500, { bold: true, shade: "D5E8F0" }), cell("时间/文书", 2000, { bold: true, shade: "D5E8F0" }), cell("状态", 1500, { bold: true, shade: "D5E8F0" }), cell("核验结论", 4360, { bold: true, shade: "D5E8F0" })] }),
    new TableRow({ children: [cell("①立案", 1500), cell("2025.12.16\n娄环冷立字[2025]47号", 2000), cell("☑ 合规", 1500, { color: "008000" }), cell("当天现场检查当天立案审批，符合7日内审批要求", 4360)] }),
    new TableRow({ children: [cell("②调查取证", 1500), cell("2025.12.16现场\n2025.12.18询问", 2000, { shade: "F5F5F5" }), cell("☑ 合规", 1500, { color: "008000", shade: "F5F5F5" }), cell("现场检查+询问笔录+拍照取证+提取书证，证据链完整", 4360, { shade: "F5F5F5" })] }),
    new TableRow({ children: [cell("③责令改正", 1500), cell("娄环冷改(2025)47号\n2025.12.21送达", 2000), cell("☑ 合规", 1500, { color: "008000" }), cell("责令改正决定书依法下达并送达", 4360)] }),
    new TableRow({ children: [cell("④事先告知", 1500), cell("娄环罚告(冷)(2026)2号\n2026.2.2送达", 2000, { shade: "F5F5F5" }), cell("☑ 合规", 1500, { color: "008000", shade: "F5F5F5" }), cell("告知书载明事实、理由、依据、处罚内容及陈述申辩权利", 4360, { shade: "F5F5F5" })] }),
    new TableRow({ children: [cell("⑤陈述申辩", 1500), cell("法定期间内\n未提出", 2000), cell("☑ 合规", 1500, { color: "008000" }), cell("视为放弃陈述申辩权利，程序合法", 4360)] }),
    new TableRow({ children: [cell("⑥案审会", 1500), cell("2026年第1次\n案审会", 2000, { shade: "F5F5F5" }), cell("⚠ 需核实", 1500, { color: "CC6600", shade: "F5F5F5" }), cell("案审会记录未在OCR材料中；法制审核意见书缺失", 4360, { shade: "F5F5F5" })] }),
    new TableRow({ children: [cell("⑦处罚决定", 1500), cell("娄环罚(冷)〔2026〕2号", 2000), cell("☑ 合规", 1500, { color: "008000" }), cell("决定书要素齐全，包含复议诉讼告知", 4360)] }),
    new TableRow({ children: [cell("⑧送达", 1500), cell("送达回证\n签收日期待确认", 2000, { shade: "F5F5F5" }), cell("⚠ 待核实", 1500, { color: "CC6600", shade: "F5F5F5" }), cell("送达回证有签字但日期模糊，需核实原件", 4360, { shade: "F5F5F5" })] }),
  ]
});
children.push(procTable);

// === MODULE 7: 问题清单 ===
children.push(para(""));
children.push(heading1("七、综合问题清单"));
const issueTable = new Table({
  width: { size: fullWidth, type: WidthType.DXA }, columnWidths: [500, 600, 1200, 3600, 1500, 1960],
  rows: [
    new TableRow({ children: [
      cell("序号", 500, { bold: true, shade: "D5E8F0" }), cell("等级", 600, { bold: true, shade: "D5E8F0" }), cell("类别", 1200, { bold: true, shade: "D5E8F0" }),
      cell("问题描述", 3600, { bold: true, shade: "D5E8F0" }), cell("法规依据", 1500, { bold: true, shade: "D5E8F0" }), cell("整改建议", 1960, { bold: true, shade: "D5E8F0" }),
    ] }),
    ...issues.map(i => new TableRow({ children: [
      cell(i.no, 500), cell(i.level === "高" ? "🔴 高" : i.level === "中" ? "🟡 中" : "🔵 低", 600),
      cell(i.category, 1200), cell(i.desc, 3600), cell(i.ref, 1500), cell(i.suggest, 1960),
    ] })),
  ]
});
children.push(issueTable);

// === MODULE 8: 证据链完整性审查 ===
children.push(para(""));
children.push(heading1("八、证据链完整性审查"));
children.push(para("按'五步法'第2步逐项审查证据链闭环情况："));
children.push(boldPara("1. 证明违法主体的证据（☑ 齐全）"));
children.push(para("   • 营业执照复印件一份"));
children.push(para("   • 法定代表人身份证信息"));
children.push(para("   • 授权委托书一份（谭珂、刘忠于）"));
children.push(boldPara("2. 证明违法事实的证据（☑ 充分）"));
children.push(para("   • 现场检查（勘察）笔录：记载露天堆放次煤约1000吨、占地约200平方米、未采取覆盖等防尘措施"));
children.push(para("   • 现场照片4张：拍摄于2025.12.16，展示露天堆放状态"));
children.push(para("   • 现场勘察平面图：标注堆放位置"));
children.push(para("   • 询问笔录2份：谭珂、刘忠于均确认堆放事实"));
children.push(boldPara("3. 证据链闭环验证（☑ 闭环）"));
children.push(para("   时间：2025.12.16（现场笔录+照片+勘察图）→ 2025.12.18（询问笔录）→ 时间线连贯"));
children.push(para("   地点：一平硐煤矿工业广场（各证据一致）"));
children.push(para("   人物：金竹山矿业公司（统一社会信用代码一致）"));
children.push(para("   事实：露天堆放次煤未遮盖（各证据相互印证）"));
children.push(boldPara("结论：证据链完整闭环，无孤证定案问题。"));

// === MODULE 9: 法律依据链 ===
children.push(para(""));
children.push(heading1("九、法律依据链"));
children.push(para("按效力层级从高到低排列："));
children.push(para(""));

children.push(heading2("第一层级：法律"));
legalChain.filter(l => l.level === 1).forEach(l => {
  children.push(boldPara(`☑ ${l.law} 第${l.article}（${l.role}）`));
  children.push(para(`  原文：${l.content}`));
  if (l.transition) children.push(para(`  过渡标注：${l.transition}`, { color: "1A5276" }));
  children.push(para(""));
});

children.push(heading2("第二层级：行政法规/部门规章"));
legalChain.filter(l => l.level === 2).forEach(l => {
  children.push(boldPara(`☑ ${l.law} 第${l.article}（${l.role}）`));
  children.push(para(`  原文：${l.content}`));
  children.push(para(""));
});

children.push(heading2("第三层级：地方规范性文件"));
legalChain.filter(l => l.level === 3).forEach(l => {
  children.push(boldPara(`☑ ${l.law} 第${l.article}（${l.role}）`));
  children.push(para(`  内容：${l.content}`));
  children.push(para(""));
});

// === MODULE 10: 评查结论 ===
children.push(heading1("十、评查结论与建议"));

children.push(heading2("10.1 综合评定"));
children.push(para("═══════════════════════════════════════"));
children.push(boldPara("综合评定：基本合法，需补正"));
children.push(para("═══════════════════════════════════════"));
children.push(para(""));
children.push(boldPara("评定理由："));
children.push(para("1. 25项一票否决全部未触发，案卷通过合法性审查。"));
children.push(para("2. 规范性评分92/100分，属于'合格'等级。"));
children.push(para("3. 扣分8分，其中法制审核材料不完整（9→7）为主要扣分项。"));
children.push(para("4. 需补正2项：补充法制审核材料 + 确保送达回证清晰可读。"));

children.push(heading2("10.2 退回补正项"));
children.push(boldPara("必须补正（2项）："));
children.push(para("  【补正1】补充法制审核意见书或书面说明法制审核情况。依据：《行政处罚法》第58条、《环境行政处罚办法》第52条。"));
children.push(para("  【补正2】确认送达回证签收日期清晰可辨，必要时重新制作。依据：案卷归档管理规定。"));

children.push(heading2("10.3 建议整改项"));
children.push(boldPara("建议优化（3项）："));
children.push(para("  【建议1】法典过渡期双标注：在引用法律条文时增加《生态环境法典》对应条款标注（2026.8.15前逐步实施）。"));
children.push(para("  【建议2】调查询问时可增加对环评批复中污染防治设施运行情况的核实，形成更全面的证据链。"));
children.push(para("  【建议3】案卷OCR/扫描件质量保障：确保关键文书（送达回证、法制审核、案审会记录）原件清晰。"));

children.push(heading2("10.4 风险提示"));
children.push(para("⚠ 2026年8月15日生态环境法典施行后，原引用的《大气污染防治法》第48条第2款和第108条第5项将被废止条款替代。建议："));
children.push(para("  • 在8月15日前完成案卷归档时标注法典对应条款"));
children.push(para("  • 如涉及后续复查或强制执行程序，8月15日后引用法典条文"));

// === Build and save ===
console.log("Building document...");
const doc = new Document({
  styles: {
    default: { document: { run: { font: "SimSun", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "SimHei", color: "1A5276" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "SimHei", color: "D35400" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "KaiTi" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ]
  },
  sections: [{
    properties: {
      page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1200, bottom: 1440, left: 1200 } }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: "密级：内部 ● 不公开", font: "SimSun", size: 14, color: "999999" })]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "第 ", font: "SimSun", size: 16 }), new TextRun({ children: [PageNumber.CURRENT], font: "SimSun", size: 16 }), new TextRun({ text: " 页", font: "SimSun", size: 16 })]
        })]
      })
    },
    children,
  }]
});

const outPath = `${OUT}/评查报告_娄环罚(冷)〔2026〕2号_20260804.docx`;
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log("Report saved to: " + outPath);
  console.log("Size: " + (buf.length / 1024).toFixed(1) + "KB");
});
