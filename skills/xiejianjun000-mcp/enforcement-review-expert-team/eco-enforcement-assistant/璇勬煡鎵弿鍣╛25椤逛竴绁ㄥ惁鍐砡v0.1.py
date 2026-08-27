# -*- coding: utf-8 -*-
"""
25项一票否决扫描器 v0.1（引擎验证版）
=====================================
目的：验证扫描引擎能从案卷文本中识别一票否决级信号。

重要声明（准确率口径）：
- 本脚本使用的25项信号，部分来自本地记忆/SOUL中的已知类别，
  部分来自对《生态环境行政执法案卷评查细则（2024年修订版）》的知识。
- 权威25项清单全文当前未本地化（仅在MCP flowwiki，未加载），
  故本版为"引擎验证"而非"准确率验证"。
- 7份历史评查报告是AI自身输出，非独立专家真值，不能用于计算准确率。

信号设计原则：
每条信号 = (编号, 名称, 违规表现关键词, 关联法条/评查项)
扫描时输出：命中信号 + 文本证据片段 + 置信度(低/中/高)
"""

# ===== 25项一票否决信号库（v0.1，含置信度来源标注）=====
# source: "known"=本地记忆明确列出; "inferred"=根据评查细则常识推断
VETO_ITEMS = [
    # —— 程序类 ——
    ("V01", "告知在决定之后", ["告知书", "告知", "决定书", "先于", "之后送达", "倒置"],
     "行政处罚法第44/45条", "known"),
    ("V02", "单人执法取证", ["一名执法人员", "单人", "仅一名", "一人执法"],
     "行政处罚法第42条", "known"),
    ("V03", "未亮证执法", ["未出示", "未亮证", "执法证件", "未告知执法事由"],
     "行政处罚法第52条", "known"),
    ("V04", "逾期举证", ["超过15日", "逾期举证", "起诉状副本"],
     "行政诉讼法第67条", "known"),
    ("V05", "未依法送达", ["留置送达无见证人", "塞进门里", "送达回证", "公告送达未满"],
     "民事诉讼法送达条款", "known"),
    ("V06", "未告知救济途径", ["缺少复议", "未告知复议", "未告知诉讼", "救济途径"],
     "行政处罚法第44条", "known"),
    ("V07", "超追诉时效", ["超过2年", "超过五年", "追责期限", "时效"],
     "行政处罚法第36条 / 法典第1054条", "known"),
    ("V08", "未经集体讨论", ["未集体讨论", "应集体讨论", "重大复杂", "未经讨论"],
     "环境行政处罚办法第52条", "known"),
    ("V09", "法制审核缺失/流于形式", ["未法制审核", "已核拟同意", "法制审核意见", "流于形式"],
     "行政处罚法第58条", "known"),
    ("V10", "听证期限不足", ["听证期限不足", "告知当天", "未满5日", "未满三日"],
     "行政处罚法第63/64条", "inferred"),
    # —— 证据类 ——
    ("V11", "证据不足/单一证据", ["单一证据", "仅照片", "仅凭", "证据不足", "孤证"],
     "评查细则证据链闭环要求", "known"),
    ("V12", "采样程序违法", ["采样点位", "车间排放口", "采样孔", "6D", "3D", "未采样"],
     "监测规范/HJ标准", "known"),
    ("V13", "监测报告无资质/超期", ["无资质", "CMA", "计量认证", "超期未检定", "未盖章"],
     "计量法/监测管理办法", "inferred"),
    ("V14", "笔录无签字捺印", ["未签字", "无签字", "未捺印", "逐页签字"],
     "评查细则文书规范", "known"),
    ("V15", "复印件未核对", ["复印件", "未核对", "原件核对", "加盖核对章"],
     "评查细则证据规范", "inferred"),
    # —— 法律适用类 ——
    ("V16", "法律适用错误(引废止法)", ["已废止", "环境保护法", "水污染防治法", "固废法",
                                "大气污染防治法", "引用已废止", "8月15日"],
     "生态环境法典第1242条", "known"),
    ("V17", "法条引用错误(条款项)", ["条款项", "引用错误", "条文不符", "适用条款错误"],
     "评查细则法律适用项", "inferred"),
    ("V18", "裁量明显不当", ["裁量不当", "明显不当", "过罚失当", "未说明裁量理由"],
     "行政处罚法第5条过罚相当", "inferred"),
    # —— 案件定性/移送类 ——
    ("V19", "应移未移公安", ["应移送", "未移送", "涉嫌犯罪", "移送公安", "行政拘留未移"],
     "行刑衔接规定", "known"),
    ("V20", "查封扣押违法", ["查封扣押", "超期查封", "违法查封", "扣押清单"],
     "行政强制法", "inferred"),
    # —— 主体/管辖类 ——
    ("V21", "主体资格不适格", ["非适格主体", "主体错误", "被处罚人错误", "名称不一致"],
     "行政处罚法第4条", "inferred"),
    ("V22", "管辖权问题", ["无管辖权", "管辖错误", "越权", "级别管辖"],
     "行政处罚法地域/级别管辖", "inferred"),
    # —— 文书/期限类 ——
    ("V23", "期限超期(立案/办案)", ["超期办案", "立案超期", "超过90日", "办案期限"],
     "行政处罚程序规定", "inferred"),
    ("V24", "决定书要素缺失", ["决定书缺少", "要素缺失", "文号不规范", "缴款账户缺失"],
     "评查细则决定书规范", "known"),
    ("V25", "强制执行违法", ["强制执行", "未催告", "违法强制执行", "代履行"],
     "行政强制法", "inferred"),
]


def scan_text(text):
    """对单份文本扫描，返回命中列表（含否定上下文判断）"""
    hits = []
    # 否定/合规指示词：出现在信号词前60字内则判定为假阳性
    NEG_MARKERS = ["未", "否", "不", "无", "缺", "已告知", "已核", "合规",
                   "✅", "正确", "符合", "不存在", "无需", "不适用", "未超期",
                   "已进行", "已履行", "已依法", "已集体", "已法制"]
    for vid, name, kws, law, src in VETO_ITEMS:
        for kw in kws:
            idx = text.find(kw)
            if idx != -1:
                # 检查关键词前60字是否有否定标记
                pre = text[max(0, idx-60):idx]
                is_neg = any(m in pre for m in NEG_MARKERS)
                start = max(0, idx - 30)
                end = min(len(text), idx + len(kw) + 30)
                snippet = text[start:end].replace("\n", " ")
                hits.append({
                    "id": vid, "name": name, "kw": kw,
                    "law": law, "src": src, "snippet": snippet,
                    "neg": is_neg
                })
                break
    return hits


def main():
    import glob, os
    base = "/Users/mac/.qclaw/workspace-agent-6458195c/"
    files = sorted(glob.glob(base + "案卷评查报告_*.md"))
    # 排除非评查报告
    files = [f for f in files if "完整版" in f or "赢湖矿产品.md" in f
             or "瑞龙" in f or "禾青" in f or "金竹山" in f or "鑫顺" in f]

    print("=" * 70)
    print("25项一票否决扫描器 v0.1 — 引擎验证运行")
    print("扫描对象: 7份历史评查报告（AI自身输出，非独立真值）")
    print("=" * 70)

    total_hits = 0
    total_real = 0
    report_summary = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            text = fh.read()
        hits = scan_text(text)
        real_hits = [h for h in hits if not h["neg"]]
        total_hits += len(hits)
        total_real += len(real_hits)
        report_summary.append((os.path.basename(f), len(hits), len(real_hits)))
        print(f"\n📄 {os.path.basename(f)}")
        print(f"   原始命中: {len(hits)} 条 | 否定过滤后真实命中: {len(real_hits)} 条")
        seen = {}
        for h in real_hits:
            seen.setdefault(h["id"], h)
        for vid in sorted(seen.keys()):
            h = seen[vid]
            tag = "✓已知" if h["src"] == "known" else "∼推断"
            print(f"   [{vid}] {h['name']} ({tag})")
            print(f"        证据: …{h['snippet']}…")
        # 假阳性示例
        fp = [h for h in hits if h["neg"]]
        if fp:
            print(f"   ┄ 过滤掉 {len(fp)} 条假阳性(否定上下文)")

    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    for name, n, r in report_summary:
        print(f"  {n:>3} 条(真实{r})  -  {name}")
    print(f"\n总计原始命中: {total_hits} 条信号")
    print(f"否定过滤后真实命中: {total_real} 条信号")
    print(f"假阳性率(估算): {100*(total_hits-total_real)/total_hits:.0f}%" if total_hits else "")
    print(f"信号库规模: {len(VETO_ITEMS)} 项")
    print(f"已知来源: {sum(1 for v in VETO_ITEMS if v[4]=='known')} 项")
    print(f"推断来源: {sum(1 for v in VETO_ITEMS if v[4]=='inferred')} 项")
    print("\n⚠️ 准确率说明: 本次为引擎验证，非准确率验证。")
    print("   真准确率需: (1)flowwiki权威25项清单; (2)100+独立专家标注案卷")


if __name__ == "__main__":
    main()
