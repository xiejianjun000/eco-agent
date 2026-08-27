#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入仓-入库：把旧库112篇搬进新库，按旧库领域逻辑重建结构，
并把我已建的36篇原子文档并入对应位置。copy-first（旧库不删，验证后由用户确认删除）。"""
import os, shutil, re

OLD = "/Users/mac/Documents/eco-knowledge/wiki/案卷评查知识库"
NEW = "/Users/mac/执法督察评查知识库"
TODAY = "2026-07-16"

# ---------- 旧库顶层文件 → 目标路径 映射 ----------
def target_for_old_top(fname):
    # 单行法 40_ 重名 → 02_法律法规体系/40_单行法/<真名>
    if fname.startswith("40_中华人民共和国"):
        law = fname[3:]  # 去掉 40_
        return f"02_法律法规体系/40_单行法/{law}"
    if fname.startswith("40_"):
        return f"02_法律法规体系/40_单行法/{fname[3:]}"
    # 日期型典型案例
    if re.match(r"典型案例_2026-", fname):
        return f"04_典型案例/按日期/{fname}"
    # 实务经验_*
    if fname.startswith("实务经验_"):
        return f"06_实务经验与学习/实务经验/{fname}"
    # 新法更新_*
    if fname.startswith("新法更新_"):
        return f"07_新法更新与程序法/新法更新/{fname}"
    # 法律法规更新_*
    if fname.startswith("法律法规更新_"):
        return f"07_新法更新与程序法/法律法规更新/{fname}"
    # 程序法解读_*
    if fname.startswith("程序法解读_"):
        return f"07_新法更新与程序法/程序法解读/{fname}"
    # 生态环境法典_* 对照类
    if fname.startswith("生态环境法典_") or fname.startswith("中华人民共和国生态环境法典_2026全文"):
        return f"02_法律法规体系/法典对照/{fname}"
    # 编号核心文档 → 按号段归域
    num_map = {
        "01_评查标准体系.md":"01_评查标准与细则",
        "02_常见错误与问题.md":"01_评查标准与细则",
        "05_评查实务要点.md":"01_评查标准与细则",
        "07_评查细则全文（2024年版）.md":"01_评查标准与细则",
        "03_法律法规索引.md":"02_法律法规体系",
        "06_生态环境法典衔接指南.md":"02_法律法规体系",
        "17_生态环境法典-法律责任编.md":"02_法律法规体系",
        "18_生态环境法典-总则编.md":"02_法律法规体系",
        "36_已废止-环境保护法.md":"02_法律法规体系",
        "41_生态环境法典（2026）.md":"02_法律法规体系",
        "42_生态环境监测条例（2026）.md":"02_法律法规体系",
        "21_生态环境行政处罚办法.md":"03_处罚办法与文书",
        "22_生态环境行政处罚办法-图解.md":"03_处罚办法与文书",
        "23_生态环境行政执法文书制作指南.md":"03_处罚办法与文书",
        "24_按日连续处罚办法.md":"03_处罚办法与文书",
        "25_排污许可执法检查通用清单.md":"03_处罚办法与文书",
        "26_排污许可执法监管指导意见.md":"03_处罚办法与文书",
        "27_行政处罚办法解读1-严格规范公正文明执法.md":"03_处罚办法与文书",
        "28_行政处罚办法解读2-规范高效实施.md":"03_处罚办法与文书",
        "29_行政处罚办法解读3-助力基层执法效能.md":"03_处罚办法与文书",
        "30_行政处罚办法解读4-说理式执法.md":"03_处罚办法与文书",
        "33_规范执法助力优化营商环境.md":"03_处罚办法与文书",
        "31_2024年执法大练兵图解.md":"03_处罚办法与文书/练兵图解",
        "32_2025年执法大练兵图解.md":"03_处罚办法与文书/练兵图解",
        "生态环境法典核心解读_执法评查视角.md":"02_法律法规体系/法典对照",
        "34_查封扣押办法.md":"03_处罚办法与文书",
        "35_限产停产办法.md":"03_处罚办法与文书",
        "37_违法排污行政拘留意见.md":"03_处罚办法与文书",
        "38_规范适用行政处罚自由裁量权指导意见.md":"03_处罚办法与文书",
        "39_规范行政处罚自由裁量权若干意见.md":"03_处罚办法与文书",
        "08_湖南省裁量权基准（2021版）.md":"03_处罚办法与文书",
        "04_典型案例索引.md":"04_典型案例",
        "19_湖南省省级环保督察典型案例.md":"04_典型案例",
        "43_2026年典型案例汇编.md":"04_典型案例",
        "20_湖南省省级环保督察体系总览.md":"05_督察实战",
        "44_2026年06月22日学习记录.md":"06_实务经验与学习",
        "README.md":"__ROOT__",
    }
    if fname in num_map:
        d = num_map[fname]
        return fname if d == "__ROOT__" else f"{d}/{fname}"
    return None  # 未匹配

# ---------- 旧库子目录 → 目标 ----------
def target_for_old_sub(fname):
    # 子目录文件直接对应
    sub_map = {
        "实务经验": "06_实务经验与学习/实务经验",
        "新法速递": "07_新法更新与程序法/新法速递",
        "法律更新": "07_新法更新与程序法/法律更新",
        "评查技巧": "01_评查标准与细则/评查技巧",
    }
    for s, d in sub_map.items():
        if fname.startswith(s + "/"):
            return fname.replace(s + "/", d + "/", 1)
    return None

# ---------- 我的36篇 → 目标（并入旧结构） ----------
def target_for_mine(path):
    rel = path.replace(NEW + "/", "")
    if rel == "00-能力地图.md":
        return "00_首页与导航/首页与导航.md"
    if rel.startswith("01-新手入门/"):
        return "新手入门/" + rel.split("/",1)[1]
    if rel.startswith("02-单项能力SOP/"):
        return "01_评查标准与细则/SOP/" + rel.split("/",1)[1]
    if rel.startswith("03-实战全流程/"):
        return "03_处罚办法与文书/案卷评查实战/" + rel.split("/",1)[1]
    if rel.startswith("04-督察实战/"):
        return "05_督察实战/" + rel.split("/",1)[1]
    if rel.startswith("05-工具资源/"):
        return "工具资源/" + rel.split("/",1)[1]
    if rel.startswith("06-法律更新预警/"):
        return "07_新法更新与程序法/法律预警/" + rel.split("/",1)[1]
    if rel.startswith("10_元文档/"):
        return "10_元文档/" + rel.split("/",1)[1]
    if rel.startswith("99_持续运营/"):
        return "99_持续运营/" + rel.split("/",1)[1]
    if rel.startswith("_templates/"):
        return "_templates/" + rel.split("/",1)[1]
    return None

def add_frontmatter_if_missing(src, dst):
    txt = open(src, encoding="utf-8").read()
    if txt.startswith("---"):
        return txt  # 已有 frontmatter（多为我的36篇）
    # 推断 layer/type
    parts = dst.replace(NEW+"/","").split("/")
    top = parts[0]
    layer_map = {
        "01_评查标准与细则":"01-评查标准","02_法律法规体系":"02-法律法规",
        "03_处罚办法与文书":"03-处罚办法","04_典型案例":"04-案例",
        "05_督察实战":"05-督察","06_实务经验与学习":"06-实务",
        "07_新法更新与程序法":"07-新法","新手入门":"01-评查标准",
        "工具资源":"07-新法","10_元文档":"10-元文档","99_持续运营":"99-运营",
        "00_首页与导航":"00-导航",
    }
    layer = layer_map.get(top, "07-新法")
    title = os.path.splitext(os.path.basename(dst))[0]
    type_ = "law" if ("法典" in title or "法" in title or "条例" in title or "办法" in title) else "doc"
    if "案例" in title: type_="case"
    if "细则" in title or "标准" in title: type_="sop"
    tags = f"[{layer}, 现行]"
    fm = (f"---\n标题: {title}\nlayer: {layer}\ntype: {type_}\n"
          f"触发词: []\n适用场景: []\n关联法条: []\n调用skill: [eco-review-kb]\n"
          f"风险等级: 🟡\nversion: 1.0\nstatus: 现行\nupdated: {TODAY}\ntags: {tags}\n---\n\n")
    return fm + txt

# ============ 执行 ============
DRY = os.environ.get("DRY_RUN") == "1"
if DRY:
    print("🔍 DRY-RUN 模式：仅预览，不写文件")
log = []
# 1) 旧库入仓
for root, dirs, files in os.walk(OLD):
    if ".obsidian" in root: continue
    rel = os.path.relpath(root, OLD)
    for fn in files:
        if not fn.endswith(".md"): continue
        src = os.path.join(root, fn)
        if rel == ".":
            t = target_for_old_top(fn)
            if t is None:
                # 兜底：放进 07_新法更新与程序法/其他
                t = f"07_新法更新与程序法/其他/{fn}"
                log.append(f"⚠️ 未匹配旧库顶层文件，兜底: {fn}")
        else:
            t = target_for_old_sub(rel + "/" + fn)
            if t is None:
                t = f"07_新法更新与程序法/其他/{rel}/{fn}"
                log.append(f"⚠️ 未匹配旧库子目录文件，兜底: {rel}/{fn}")
        dst = os.path.join(NEW, t)
        if DRY:
            log.append(f"✅ 入仓: {t}"); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        content = add_frontmatter_if_missing(src, dst)
        open(dst, "w", encoding="utf-8").write(content)
        log.append(f"✅ 入仓: {t}")

# 2) 我的36篇并入
for root, dirs, files in os.walk(NEW):
    if ".obsidian" in root: continue
    for fn in files:
        if not fn.endswith(".md"): continue
        full = os.path.join(root, fn)
        rel = full.replace(NEW+"/","")
        if rel.startswith(("01-新手入门/","02-单项能力SOP/","03-实战全流程/",
                           "04-督察实战/","05-工具资源/","06-法律更新预警/",
                           "00-能力地图.md")):
            t = target_for_mine(full)
            if t is None: continue
            dst = os.path.join(NEW, t)
            if DRY:
                log.append(f"🔄 并入: {rel} → {t}"); continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(full, dst)
            log.append(f"🔄 并入: {rel} → {t}")

# 3) 清理被搬空的旧顶层目录（我的36篇原位置）
for d in ["00-能力地图","01-新手入门","02-单项能力SOP","03-实战全流程","04-督察实战","05-工具资源","06-法律更新预警"]:
    p = os.path.join(NEW, d)
    if os.path.isdir(p) and not os.listdir(p):
        if DRY: log.append(f"🗑️ 清空旧层目录: {d}")
        else: os.rmdir(p); log.append(f"🗑️ 清空旧层目录: {d}")

open("/Users/mac/.qclaw/workspace-agent-6458195c/_migrate_log.txt","w",encoding="utf-8").write("\n".join(log))
print(f"入仓+并入完成，操作 {len(log)} 项")
print("未匹配/兜底项数:", sum(1 for l in log if '⚠️' in l))
for l in log:
    if '⚠️' in l: print(l)
