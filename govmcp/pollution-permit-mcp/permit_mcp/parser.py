"""HTML 解析层：列表页、详情页、AES 加密点位、证后管理、法规全文解析。"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from . import config


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("|", strip=True)
    text = re.sub(r"\|+", "|", text)
    return text


# ---------- 许可信息公开列表 ----------
def parse_license_list(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    table = soup.find("table")
    if table:
        trs = table.find_all("tr")
        for tr in trs[1:]:  # 跳过表头
            tds = tr.find_all("td")
            if len(tds) < 9:
                continue
            link = tds[-1].find("a")
            dataid = None
            if link and link.get("href"):
                m = re.search(r"dataid=([0-9a-f]{32})", link["href"])
                dataid = m.group(1) if m else None
            rows.append({
                "province": tds[0].get_text(strip=True),
                "city": tds[1].get_text(strip=True),
                "license_no": tds[2].get_text(strip=True),
                "company_name": tds[3].get_text(strip=True),
                "industry": tds[4].get_text(strip=True),
                "valid_period": tds[5].get_text(strip=True),
                "issue_date": tds[6].get_text(strip=True),
                "manage_type": tds[7].get_text(strip=True),
                "dataid": dataid,
            })
    # 总页数
    total_pages = None
    m = re.search(r"共(\d+)页", html)
    if m:
        total_pages = int(m.group(1))
    return {"total_pages": total_pages, "count": len(rows), "items": rows}


# ---------- 许可证详情 ----------
def parse_license_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # 企业基础信息（大字号标题 + 概览行）
    company_name = None
    p = soup.find("p", style=re.compile(r"font-size:\s*36px"))
    if p:
        company_name = p.get_text(strip=True)

    overview = ""
    text = _strip_html(html)
    m = re.search(r"生产经营场所地址：(.*?)(?:排污许可证正本|$)", text)
    if m:
        overview = m.group(1).strip("| ")

    # 隐藏字段：经纬度
    def hidden_val(hid: str) -> str | None:
        node = soup.find("input", {"id": hid})
        return node.get("value") if node else None

    # 正本版本列表（表格：许可证编号/业务类型/版本/办结日期/有效期限）
    versions = []
    for table in soup.find_all("table"):
        header = [th.get_text(strip=True) for th in table.find_all("th")]
        if "许可证编号" in header and "业务类型" in header:
            for tr in table.find_all("tr")[1:]:
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(tds) >= 5:
                    versions.append({
                        "license_no": tds[0],
                        "biz_type": tds[1],
                        "version": tds[2],
                        "finish_date": tds[3],
                        "valid_period": tds[4],
                    })
            break

    # 副本摘要
    summary = {}
    for label in ["主要污染物类别", "大气主要污染物种类", "大气污染物排放规律",
                  "大气污染物排放执行标准", "废水主要污染物种类", "废水污染物排放规律",
                  "废水污染物排放执行标准", "排污权使用和交易信息"]:
        m = re.search(re.escape(label) + r"[:：]\s*(.*?)(?:\|)", text)
        if m:
            summary[label] = m.group(1).strip()

    # 排放口点位（AES 解密）
    points = decrypt_point_data(html)

    return {
        "company_name": company_name,
        "overview": overview,
        "longitude": hidden_val("longitude"),
        "latitude": hidden_val("latitude"),
        "lng_dms": {
            "d": hidden_val("opelngd"), "f": hidden_val("opelngf"), "m": hidden_val("opelngm"),
        },
        "lat_dms": {
            "d": hidden_val("opelatd"), "f": hidden_val("opelatf"), "m": hidden_val("opelatm"),
        },
        "versions": versions,
        "summary": summary,
        "discharge_points": points,
        "point_count": len(points),
    }


def decrypt_point_data(html: str) -> list[dict]:
    """解密详情页内 AES-128-ECB 加密的排放口经纬度点位数据。"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    m_pwd = re.search(config.AES_PWD_RE, html)
    m_word = re.search(config.AES_WORD_RE, html)
    if not m_pwd or not m_word:
        return []
    try:
        key = m_pwd.group(1).encode("utf-8")
        cipher = AES.new(key, AES.MODE_ECB)
        raw = unpad(cipher.decrypt(base64.b64decode(m_word.group(1))), AES.block_size)
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception:  # noqa: BLE001
        return []


# ---------- 证后管理（执行报告/监督执法/自行监测） ----------
def parse_post_permit_status(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = _strip_html(html)

    def section_rows(keyword: str) -> list[dict]:
        rows = []
        for table in soup.find_all("table"):
            header = [th.get_text(strip=True) for th in table.find_all("th")]
            if not header or keyword not in "|".join(header):
                continue
            for tr in table.find_all("tr")[1:]:
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if tds:
                    rows.append(dict(zip(header, tds)))
            break
        return rows

    result = {
        "execution_reports": section_rows("报告类型"),
        "supervision": section_rows("核查日期"),
        "monitoring_note": "",
    }
    # 自行监测信息：详情页嵌入 wryjc 平台 iframe
    m = re.search(r'<iframe[^>]+src="(https://wryjc\.mee\.gov\.cn[^"]+)"', html)
    if m:
        result["monitoring_url"] = m.group(1)
    if "自行监测信息" in text:
        result["monitoring_note"] = "自行监测信息由全国污染源监测信息管理共享平台提供（wryjc.mee.gov.cn）"
    return result


# ---------- 公告 / 通知 / 法规列表（通用新闻列表） ----------
def parse_news_list(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "getNewsDetail.action" in href:
            m = re.search(r"pkid=([0-9a-fA-F-]+)", href)
            title = a.get_text(strip=True)
            if m and title:
                items.append({"pkid": m.group(1), "title": title, "url": href})
    # 去重
    seen, uniq = set(), []
    for it in items:
        if it["pkid"] not in seen:
            seen.add(it["pkid"])
            uniq.append(it)
    total_pages = None
    m = re.search(r"共(\d+)页", html)
    if m:
        total_pages = int(m.group(1))
    return {"total_pages": total_pages, "count": len(uniq), "items": uniq}


# ---------- 公告（注销/撤销/遗失/重要通知）表格列表 ----------
def parse_announce_list(html: str) -> dict:
    """解析公告类表格列表（无详情链接，列头动态映射）。"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    items = []
    if table:
        trs = table.find_all("tr")
        header = [th.get_text(strip=True) for th in (trs[0].find_all(["th", "td"]) if trs else [])]
        for tr in trs[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not tds or "暂无数据" in "".join(tds):
                continue
            row = {}
            for idx, h in enumerate(header):
                if idx < len(tds):
                    row[h] = tds[idx]
            items.append(row)
    total_pages = None
    m = re.search(r"共(\d+)页", html)
    if m:
        total_pages = int(m.group(1))
    return {"total_pages": total_pages, "count": len(items), "items": items}


# ---------- 新闻 / 法规详情 ----------
def parse_news_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # 标题与日期：详情容器 .file-top
    title = ""
    pub_date = None
    file_top = soup.find("div", class_="file-top")
    if file_top:
        p_title = file_top.find("p", class_=re.compile(r"font-18"))
        if p_title:
            title = p_title.get_text(strip=True)
        m_date = re.search(r"(\d{4}-\d{2}-\d{2})", file_top.get_text())
        if m_date:
            pub_date = m_date.group(1)
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)

    # 正文区域：.file-bottom（优先），否则整页文本
    body_text = ""
    file_bottom = soup.find("div", class_="file-bottom")
    if file_bottom:
        body_text = _strip_html(str(file_bottom))
    else:
        body_text = _strip_html(html)
    body_text = body_text.strip("| ")

    # 附件
    attachments = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"\.(pdf|doc|docx|wps|txt)(\?|$)", href, re.I):
            attachments.append({
                "name": a.get_text(strip=True) or href.split("/")[-1],
                "url": href if href.startswith("http") else "https://permit.mee.gov.cn" + href,
            })
    return {"title": title, "publish_date": pub_date,
            "attachments": attachments, "content": body_text}


# ---------- 法规标准列表 ----------
def parse_laws_list(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "getNewsDetail.action" in href:
            m = re.search(r"pkid=([0-9a-fA-F-]+)", href)
            title = a.get_text(strip=True)
            if m and title:
                items.append({"pkid": m.group(1), "title": title})
    return {"count": len(items), "items": items}
