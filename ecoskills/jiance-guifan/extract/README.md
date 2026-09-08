# 抽取管线（可复现）

《生态环境监测技术规范清单（2026.7）》PDF 原件 → `../kb/` 知识库的完整生成链路。
原件不入库（39MB），置于 `raw/规范清单2026.7.pdf` 后按序执行：

| 步骤 | 脚本 | 产出 |
|---|---|---|
| 1 目录抽取 | `extract_catalog.py` | `catalog_raw.json`（209 条，x 分列 + 行锚点） |
| 2 目录审计 | `audit.py` | 逐页逐字段回溯原文，`AUDIT PASS` |
| 3 附录抽取 | `extract_appendix.py` | `appendix.json`（8 份法规 205 条，含字形缺陷修复） |
| 4 附录审计 | `audit_appendix.py` | 条号连续性，`APPENDIX PASS` |
| 5 交叉验证 | `crosscheck.py` | 与 mee.gov.cn 权威全文比对，条例 49/49 一致 |
| 6 规范化 | `normalize.py` | `catalog.json`（分类/序列含义/同名多版本） |
| 7 建库 | `build_kb.py` | `../kb/` 全部产物 |
| 8 题库 | `build_quiz.py` | `../kb/学习题库.json`（496 题） |
| 9 评测集 | `build_evalsuite.py` | `../../../evals/jiance-{standards,laws}.md` |

## 原件已知缺陷

条号中的「十」被以 ArialMT / SimSun-ExtB 的 `H` 字形输出，且紧随其后的个位数字
整格丢失（x 轴留一个字宽空档、无 span）。`extract_appendix.py` 按字形几何探测空档、
按条序还原，涉及条例第三十一/四十一条与监督管理办法第二十一条。
