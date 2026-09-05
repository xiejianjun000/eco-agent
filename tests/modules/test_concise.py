"""规则19 确定性执行（要点式回答硬上限）单测：句边界截断 / 条文引用豁免 / 表格豁免。"""

from server.api.chat import _cut_at_boundary, _enforce_concise, _normalize_markdown, _sanitize_thinking


def test_normalize_markdown_broken_bold():
    # v4-pro 常见缺陷：** 与文字分行的断裂加粗 → 合并回同行
    bad = "✅ ** \n第1107条：超标排放的罚则。 \n** \n\n\n原文：…"
    out = _normalize_markdown(bad)
    assert "**第1107条：超标排放的罚则。**" in out
    assert out.count("**") == 2  # 仅剩一对加粗符
    assert "\n\n\n" not in out


def test_normalize_markdown_standalone_asterisks():
    out = _normalize_markdown("第一行\n**\n第二行")
    assert "**\n" not in out


def test_normalize_markdown_both_sides_split():
    # 变体：开合符均跨行（**法典\n第1107条：…。\n**）
    out = _normalize_markdown("✅ **法典\n第1107条：超标排放的处罚条款。\n**")
    assert out == "✅ **法典第1107条：超标排放的处罚条款。**"


def test_normalize_markdown_bold_internal_newline():
    # 变体：加粗内部换行（**《法典》\n第一千一百零七条**）
    out = _normalize_markdown("✅ **《生态环境法典》\n第一千一百零七条**——罚则。")
    assert out == "✅ **《生态环境法典》第一千一百零七条**——罚则。"


def test_normalize_markdown_inline_close_variant():
    # 变体：** 后换行、闭合符在行内（✅ **\n第1107条**：…）
    out = _normalize_markdown("✅ **\n第1107条**：超标排放的处罚条款。")
    assert out == "✅ **第1107条**：超标排放的处罚条款。"


def test_sanitize_thinking_strips_rule_recital():
    # 规则20：'规则19：…'式背书句剥掉，笔记句保留
    text = (
        "用户只是打了个招呼。根据规则19和身份说明，自我介绍类提问用一句话身份"
        "+至多3项能力，总长不超过100字，结尾问一句。不需要调用工具。直接简洁回应。"
    )
    out = _sanitize_thinking(text)
    assert "规则19" not in out and "根据规则" not in out
    assert "不需要调用工具" in out and "直接简洁回应" in out


def test_sanitize_thinking_keeps_statute_citations():
    # '第X条'是法规条款实质引用，必须保留（区别于行为规则背书）
    text = "第45条罚则10万至50万元，需核实。"
    out = _sanitize_thinking(text)
    assert "第45条" in out


def test_sanitize_thinking_keeps_real_reasoning():
    # 对标 DSH：'我应该/根据规则'式自我说服是真实推理，原样保留；
    # 只有'规则N'背书句整句删除。条文'第X条'引用不受影响。
    text = "根据规则，我应该先查法条。我应该先用 analyze_document 读取第1054条。"
    out = _sanitize_thinking(text)
    assert "根据规则，我应该先查法条。" in out  # 真实推理保留
    assert "我应该先用 analyze_document 读取第1054条。" in out
    assert "第1054条" in out


def test_sanitize_thinking_keeps_reasoning_over_old_cap():
    # 旧实现 cap=100 会把真实推理截断到 100 字；新实现保留完整深度思考（≤3000）
    text = "先拆解问题。" + "核实依据、调用工具、交叉验证、给出结论与下一步。" * 20
    out = _sanitize_thinking(text)
    assert len(out) > 100


def test_enforce_concise_keeps_code_block_whole():
    # 代码块（```...```）必须整体保留、绝不拦腰截断——否则模型贴的脚本被
    # 500 字预算切断，输出"乱七八糟的半截代码"（实测 v4-pro 会直接在回答里贴脚本）
    code = "import httpx\n" + "url = 'https://air.cnemc.cn:18007/x'\n" * 40 + "print('done')\n"
    answer = "我来实测。\n\n```python\n" + code + "\n```\n"
    out, cut = _enforce_concise(answer)
    assert "print('done')" in out  # 代码尾部完整保留
    assert out.rstrip().endswith("```")  # 闭合围栏在
    assert "url = 'https://air.cnemc.cn" in out


def test_short_text_untouched():
    assert _enforce_concise("一句话回答。") == ("一句话回答。", False)


def test_long_prose_cut_at_boundary():
    # 。边界位于 cap 附近（~283）→ 应在句边界截断
    text = "开头。" + "内容" * 140 + "。" + "内容" * 140 + "。"
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    assert len(out) <= 480
    body = out.rstrip()
    assert body.endswith("。")


def test_long_prose_no_boundary_hard_cut():
    # 无句边界可用 → 硬截断于 cap
    text = "开头。" + "内容" * 200 + "。结尾句。"
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    body = out.rstrip()
    assert len(body) <= 300
    assert text.startswith(body)  # 截断体是原文前缀（未截到边界时）


def test_legal_citation_exempt():
    text = (
        "《条例》第45条原文："
        + "　" * 400  # 条文主体（含"第45条"行）
        + "\n第四十五条　接受委托开展监测服务的技术服务机构对监测数据弄虚作假的，"
        "由生态环境主管部门处10万元以上50万元以下的罚款。" + "解读分析。" + "细节" * 300 + "。"
    )
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    assert "第四十五条" in out and "10万元以上50万元以下" in out  # 条文完整保留
    # 条文豁免：非引用内容（解读分析）截断，条文句本身完整
    assert "解读分析。" in out


def test_table_exempt_budget():
    # 表格是证据主体：整表豁免（800字封顶），叙述按 300 字预算截断
    text = "| 能力 | 说明 |\n| --- | --- |\n| 查法条 | 好 |\n| 算数据 | 好 |\n" + "其他叙述。" + "细节" * 400 + "。"
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    # 表格完整保留（不漏行、不中途切断）
    for row in ("| 能力 | 说明 |", "| --- | --- |", "| 查法条 | 好 |", "| 算数据 | 好 |"):
        assert row in out
        # 叙述部分 ≤ 300 + 表格豁免
    body = out.rstrip()
    prose = "\n".join(line for line in body.split("\n") if not line.startswith("|"))
    assert len(prose) <= 305


def test_url_preserved_after_truncation():
    # 被截掉的 docs.qq.com 链接必须补挂到文末（右侧预览面板依赖）
    text = "开头说明。" + "细节" * 300 + "。\n在线文档：https://docs.qq.com/page/ABC123 请查收。"
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    assert "https://docs.qq.com/page/ABC123" in out


def test_dangling_header_stripped():
    # 截断后末尾不得残留悬空标题行（用户实测缺陷：'**二、xxx**'下面空无一物）
    # 设计：预算恰好在标题行耗尽，其后内容不再纳入
    text = "我是 ECO AGENT。" + "细节" * 260 + "\n**二、真实执行能力（本轮会话可直接调用）**\n- 查法条\n- 算数据"
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    assert "**二、真实执行能力" not in out  # 悬空标题被清洗


def test_intro_line_stripped():
    # '如下：'引导行成为末尾残留（其后无内容）时应被去掉
    text = "开头段。" + "细节" * 280 + "\n结论如下：\n" + "内容" * 100
    out, cut = _enforce_concise(text, cap=300)
    assert cut is True
    assert "结论如下：" not in out


def test_cut_at_boundary_fallback():
    # 无句边界的长串 → 回退硬截断
    assert _cut_at_boundary("x" * 1000, 300) == 300
