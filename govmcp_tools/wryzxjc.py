#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
govmcp_tools/wryzxjc.py
娄底市污染源在线监测系统（重点污染源自动监控平台）govmcp 工具集

来源：私有仓库 xiejianjun000/eco-wryzxjc-mcp（博安达平台逆向），
按 govmcp_tools 格式（@govmcp_tool 装饰器）转换后挂载到 eco-agent。

平台: http://218.77.102.213:12369/wryzxjc/
认证: 明文密码 POST /login.do（无验证码），会话持久化到 ECO_DIR/sessions/。
账号: 冷水江市(XZQH=431381)辖区账号，通过环境变量
      WRYZXJC_USERNAME / WRYZXJC_PASSWORD 提供（本机直连政务平台，不上公网）。

只读查询能力（执法核心数据）:
  - 污染源列表/详情、预警报警台账(超标证据)、自动监控设备(断线线索)
  - 实时监测数据(废水FS/废气FQ)、监测点树、历史监测数据(分钟/时/日)

安全说明: 全部只读查询；raw_query 通用接口仅在 govmcp 注册表暴露
（不进聊天工具表），且要求已登录会话。
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Any

import requests
import urllib3

from govmcp.tools.registry import ToolRegistry, govmcp_tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = os.environ.get(
    "WRYZXJC_BASE", "http://218.77.102.213:12369/wryzxjc"
).rstrip("/")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 行政区划（区县代码）
REGIONS = {
    "娄底市": "4313",
    "市辖区": "431301",
    "娄星区": "431302",
    "冷水江市": "431381",
    "涟源市": "431382",
    "经济开发区": "431383",
    "万新区": "431384",
    "双峰县": "431321",
    "新化县": "431322",
}

REQUEST_TIMEOUT = 25.0

# ─── 会话状态（进程内 + 可选持久化）───────────────────────────

_lock = threading.Lock()
_session: requests.Session | None = None
_logged_in = False
_login_user: str | None = None
_last_password: str | None = None


def _session_dir() -> str | None:
    """会话持久化目录：ECO_DIR/sessions（无写权限时降级为纯内存会话）。"""
    base = os.environ.get("ECO_DIR") or os.path.expanduser("~/.eco")
    d = os.path.join(base, "sessions")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return None


def _session_file() -> str | None:
    d = _session_dir()
    return os.path.join(d, "wryzxjc_session.json") if d else None


def _save_session() -> None:
    """持久化登录态（cookie 含 JSESSIONID），失败静默降级。"""
    global _session, _login_user, _last_password
    path = _session_file()
    if not _session or not path:
        return
    try:
        cookies = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in _session.cookies
        ]
        state = {"username": _login_user, "password": _last_password, "cookies": cookies}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _load_session() -> bool:
    """从持久化文件恢复会话。"""
    global _session, _logged_in, _login_user, _last_password
    path = _session_file()
    if not path or not os.path.exists(path):
        return False
    try:
        state = json.load(open(path, encoding="utf-8"))
        s = requests.Session()
        s.verify = False
        s.headers.update({"User-Agent": UA})
        for c in state.get("cookies", []):
            s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path"))
        _login_user = state.get("username")
        _last_password = state.get("password")
        _session = s
        _logged_in = _check_session_valid(s)
        return _logged_in
    except Exception:
        return False


def _check_session_valid(s: requests.Session) -> bool:
    """访问需登录列表页判断会话是否有效。"""
    try:
        r = s.get(BASE + "/pages/zxjc/wry/jbxx/TZxjcWryJbxxList.jsp", timeout=15)
        if r.status_code == 200 and "污染源列表信息" in r.text and "login.do" not in r.url:
            return True
    except Exception:
        pass
    return False


def _do_login(username: str, password: str) -> bool:
    """明文密码登录，成功返回 True 并持久化会话。"""
    global _session, _logged_in, _login_user, _last_password
    s = requests.Session()
    s.verify = False
    s.headers.update({"User-Agent": UA})
    try:
        r = s.get(BASE + "/", timeout=20)
        token = re.search(
            r'name="org\.apache\.struts\.taglib\.html\.TOKEN" value="([^"]+)"', r.text
        )
        if not token:
            return False
        data = {
            "method": "authenticate",
            "userid": username,
            "password": password,
            "needValicode": "false",
            "org.apache.struts.taglib.html.TOKEN": token.group(1),
        }
        r2 = s.post(BASE + "/login.do", data=data, timeout=20, allow_redirects=True)
        if "loginSuccess.jsp" in (r2.url or "") or "loginSuccess" in r2.text[:2000]:
            _session = s
            _logged_in = True
            _login_user = username
            _last_password = password
            _save_session()
            return True
        return False
    except Exception:
        return False


def _need_login() -> str | None:
    """确保已登录：现有会话 → 恢复持久化会话 → 环境变量自动重登。"""
    global _session, _logged_in, _login_user, _last_password
    if _logged_in and _session and _check_session_valid(_session):
        return None
    if _load_session():
        return None
    env_u = os.environ.get("WRYZXJC_USERNAME", "")
    env_p = os.environ.get("WRYZXJC_PASSWORD", "")
    if env_u and env_p and _do_login(env_u, env_p):
        return None
    return (
        "未登录，请先调用 wryzxjc_login 工具，或设置环境变量 "
        "WRYZXJC_USERNAME / WRYZXJC_PASSWORD"
    )


# ─── HTML 解析（与原 MCP 一致）────────────────────────────────

def _strip(tag: str) -> str:
    return re.sub(r"<[^>]+>", "", tag).replace("&nbsp;", "").strip()


def _parse_rows(html: str) -> list[dict]:
    """解析列表 HTML 中 <tr id='tridN'> 数据行，返回 [{xh, cells:[...]}]。

    跳过操作列（icon 图标/查看/导出/编辑/删除），保留空单元格
    （避免 pH 等无量纲因子错位）。
    """
    rows = re.findall(r'<tr id="trid\d+"([^>]*)>(.*?)</tr>', html, re.S)
    out = []
    for attrs, body in rows:
        xh = ""
        m = re.search(r"XH=([\w]+)", attrs)
        if m:
            xh = m.group(1)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)
        cells = []
        for t in tds:
            if (
                '<i class="icon' in t
                or "查看" in t
                or "详细情况" in t
                or "导出" in t
                or "编辑" in t
                or "删除" in t
                or "loadOut" in t
            ):
                continue  # 操作列
            cells.append(_strip(t))
        out.append({"xh": xh, "cells": cells})
    return out


def _get_total(html: str) -> int:
    m = re.search(r'P_RECORD_COUNT[^>]*value="(\d+)"', html)
    return int(m.group(1)) if m else 0


def _query_list(jsp_path: str, params: dict | None = None,
                page: int = 1, pagesize: int = 50) -> tuple[list, int, str]:
    """通用列表查询: POST 列表JSP (method=query) → 解析 rows + total。"""
    data = {
        "FROM_SELF": "true", "EXPORT_FLAG": "false", "q_SEARCH_HEIGHT": "44",
        "q_cloumnhide": "", "q_SHENG": "43", "q_SHI": "4313", "q_QX": "",
        "q_MORE": "NO", "method": "query",
        "P_CURRENT": str(page), "P_PAGESIZE": str(pagesize),
    }
    if params:
        data.update(params)
    r = _session.post(BASE + jsp_path, data=data, timeout=30)
    if r.status_code != 200:
        return [], 0, ""
    return _parse_rows(r.text), _get_total(r.text), r.text


# ─── govmcp 工具定义 ─────────────────────────────────────────

CATEGORY = "执法平台-污染源在线监测"
TAGS = ["执法平台", "在线监测", "污染源", "自动监控", "博安达", "娄底"]


@govmcp_tool(
    name="wryzxjc_login",
    description="登录娄底市污染源在线监测系统(明文密码,无验证码)。账号密码可通过参数传入,或设置环境变量 WRYZXJC_USERNAME/WRYZXJC_PASSWORD",
    category=CATEGORY,
    tags=TAGS + ["auth"],
)
def wryzxjc_login(username: str = "", password: str = "") -> dict:
    """登录平台（会话持久化，重启免重登）。"""
    username = username or os.environ.get("WRYZXJC_USERNAME", "")
    password = password or os.environ.get("WRYZXJC_PASSWORD", "")
    if not username or not password:
        return {"success": False,
                "message": "请提供账号密码，或设置环境变量 WRYZXJC_USERNAME/WRYZXJC_PASSWORD"}
    global _logged_in
    with _lock:
        ok = _do_login(username, password)
    return {"success": ok, "username": username, "session_persisted": bool(_session_file())}


@govmcp_tool(
    name="wryzxjc_status",
    description="获取娄底市污染源在线监测系统当前登录状态",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_status() -> dict:
    """登录状态（不发起网络请求）。"""
    return {
        "logged_in": _logged_in,
        "username": _login_user or "",
        "session_persisted": bool(_session_file() and os.path.exists(_session_file())),
        "base": BASE,
    }


@govmcp_tool(
    name="wryzxjc_list_regions",
    description="查询行政区划列表。parent_code传地市代码(娄底市=4313)，返回下级区县代码与名称",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_list_regions(parent_code: str = "4313") -> dict:
    """行政区划查询（纯 JSON 接口）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    try:
        r = _session.post(BASE + "/pages/queryXzqh.do",
                          data={"parentCode": parent_code}, timeout=20)
        return {"success": True, "rows": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="wryzxjc_list_pollution_sources",
    description="查询污染源(重点排污企业)列表。qx传区县代码(冷水江=431381,空=娄底全市),wrymc污染源名称模糊查询,hylx行业类型,jgjb监管级别(国控/省控/市控)。返回企业名称/区县/地址/监管级别/法人/环保联系人等",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_list_pollution_sources(qx: str = "", wrymc: str = "", jgjb: str = "",
                                   hylx: str = "", page: int = 1, pagesize: int = 50) -> dict:
    """污染源列表（重点排污企业基本信息）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    params = {"q_QX": qx, "q_WRYMC": wrymc, "q_JGJB": jgjb, "q_HYLX": hylx, "q_SFYX": "YES"}
    rows, total, _ = _query_list("/pages/zxjc/wry/jbxx/TZxjcWryJbxxList.jsp",
                                 params, page, pagesize)
    cols = ["污染源名称", "行政区划", "单位地址", "监管级别", "法人代表",
            "联系电话", "环保联系人", "环保联系人电话", "企业状态"]
    result = []
    for r in rows:
        cells = r["cells"]
        item = {"xh": r["xh"]}
        for i, c in enumerate(cols):
            item[c] = cells[i] if i < len(cells) else ""
        result.append(item)
    return {"success": True, "total": total, "page": page,
            "count": len(result), "rows": result}


@govmcp_tool(
    name="wryzxjc_get_pollution_source",
    description="查询单个污染源详情(编号/名称/经纬度/法人/企业规模/企业状态/环保联系人等)。xh从wryzxjc_list_pollution_sources结果的xh字段获取",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_get_pollution_source(xh: str = "") -> dict:
    """污染源详情。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not xh:
        return {"success": False, "error": "请提供 xh(污染源编号, 先调用 wryzxjc_list_pollution_sources 获取)"}
    try:
        r = _session.get(BASE + "/pages/zxjc/wry/jbxx/TZxjcWryJbxxView.jsp",
                         params={"XH": xh}, timeout=25)
        pairs = re.findall(r"<td[^>]*>([^<]{2,30})</td>\s*<td[^>]*>(.*?)</td>", r.text, re.S)
        info = {}
        for k, v in pairs:
            k, v = k.strip(), _strip(v)
            if k and v and k not in ("", ":", "：", "&nbsp;"):
                info[k] = v[:200]
        return {"success": True, "xh": xh, "detail": info}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="wryzxjc_list_alarms",
    description="查询预警报警台账(超标/异常监测数据,执法督察核心证据)。qx区县,sjzt数据状态(超标/异常/正常),pwlx排放类型(废水/废气)。返回污染源/监测点/监测时间/污染物/监测值/标准值/单位等",
    category=CATEGORY,
    tags=TAGS + ["执法证据"],
)
def wryzxjc_list_alarms(qx: str = "", sjzt: str = "", pwlx: str = "",
                        page: int = 1, pagesize: int = 50) -> dict:
    """预警报警台账（超标/异常数据，执法核心证据）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    params = {"q_QX": qx}
    if sjzt:
        params["q_SJZT"] = sjzt
    if pwlx:
        params["q_PWLX"] = pwlx
    rows, total, _ = _query_list("/pages/zxjc/yjbj/yjbjt/TZxjcYjbjYjbjtList.jsp",
                                 params, page, pagesize)
    cols = ["污染源名称", "监测点", "行政区划", "监测时间", "污染物名称",
            "监测值", "标准值", "单位"]
    result = []
    for r in rows:
        cells = r["cells"]
        item = {}
        for i, c in enumerate(cols):
            item[c] = cells[i] if i < len(cells) else ""
        result.append(item)
    return {"success": True, "total": total, "count": len(result), "rows": result}


@govmcp_tool(
    name="wryzxjc_list_devices",
    description="查询自动监控设备列表及在线状态。返回污染源/监测点/设备MN号/设备状态(在线/断线/停运)。断线设备是'涉嫌干扰自动监测'的重要线索",
    category=CATEGORY,
    tags=TAGS + ["执法证据"],
)
def wryzxjc_list_devices(qx: str = "", wrymc: str = "", sbzt: str = "",
                         page: int = 1, pagesize: int = 100) -> dict:
    """自动监控设备列表（断线=干扰自动监测线索）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    params = {"q_QX": qx, "q_WRYMC": wrymc}
    if sbzt:
        params["q_SBZT"] = sbzt
    rows, total, _ = _query_list("/pages/zxjc/ssjk/sbssjk/TZxjcWrySbxxList.jsp",
                                 params, page, pagesize)
    cols = ["污染源名称", "监测点", "行政区划", "设备MN号", "设备状态"]
    result = []
    for r in rows:
        cells = r["cells"]
        item = {}
        for i, c in enumerate(cols):
            item[c] = cells[i] if i < len(cells) else ""
        result.append(item)
    return {"success": True, "total": total, "count": len(result), "rows": result}


@govmcp_tool(
    name="wryzxjc_list_realtime_data",
    description="查询实时监测数据(废水/废气,最近1小时)。pwkzl排污口种类(FS废水/FQ废气),qx区县,wrymc污染源名称。返回污染源/监测点/各监测因子(氨氮/化学需氧量等)浓度与数据状态(超标标记)",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_list_realtime_data(pwkzl: str = "FS", qx: str = "", wrymc: str = "",
                               page: int = 1, pagesize: int = 50) -> dict:
    """实时监测数据（废水/废气，最近 1 小时）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    params = {"q_PWKZL": pwkzl, "q_QX": qx, "q_WRYMC": wrymc}
    rows, total, raw = _query_list("/pages/zxjc/ssjk/ssjksj/TZxjcWrySsjksjList.jsp",
                                   params, page, pagesize)
    result = [r["cells"] for r in rows]
    head_cols = re.findall(r'column="([^"]+)"[^>]*>([^<]{1,40})<', raw)
    factors = [h[1].replace("\n", "").strip() for h in head_cols if h[0] != "XM"]
    return {"success": True, "total": total, "pwkzl": pwkzl,
            "factor_columns": factors, "count": len(result), "rows": result}


@govmcp_tool(
    name="wryzxjc_list_jcd_tree",
    description="查询监测点树(污染源->监测点层级)。yzlx因子类型(空=全部/FS废水/FQ废气),qx区县,wrymc污染源名称。返回监测点序号JCDXH与类型JCDLX,用于历史数据查询",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_list_jcd_tree(yzlx: str = "", qx: str = "", wrymc: str = "") -> dict:
    """监测点树（jstree JSON）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    try:
        data = {"method": "generateJcdTree3", "YHID": _login_user or "",
                "QX": qx, "YZLX": yzlx, "WRYMC": wrymc, "WRYXH": "#"}
        r = _session.post(BASE + "/pages/zxjc/ssjk/sssjview/jcdProcessor.jsp",
                          data=data, timeout=25)
        return {"success": True, "tree": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="wryzxjc_list_history_data",
    description="查询单个监测点的历史监测数据(分钟/时/日)。jcdxh监测点序号,jcdlx类型(FS废水/FQ废气),sjlx数据类型(FZSJ分钟/SSJ时/RSJ日),quick快捷时段(如-24近24小时),或start_time/end_time自定义时间(格式'yyyy-MM-dd HH',需配合quick='GD')。返回该排放口各污染物历史监测值",
    category=CATEGORY,
    tags=TAGS,
)
def wryzxjc_list_history_data(jcdxh: str = "", jcdlx: str = "FQ", sjlx: str = "SSJ",
                              quick: str = "-24", start_time: str = "", end_time: str = "",
                              pagesize: int = 200) -> dict:
    """单监测点历史监测数据（分钟/时/日）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not jcdxh:
        return {"success": False,
                "error": "请提供 jcdxh(监测点序号, 从 wryzxjc_list_jcd_tree 或实时数据列表获取)"}
    url = BASE + "/pages/zxjc/ssjk/sssjview/TZxjcWryLssjListNew.jsp"
    data = {"FROM_SELF": "true", "EXPORT_FLAG": "false", "q_SEARCH_HEIGHT": "44",
            "q_cloumnhide": "", "q_SJLX": sjlx, "q_JCSJ": quick,
            "q_startTime": start_time, "q_endTime": end_time,
            "method": "query", "P_CURRENT": "1", "P_PAGESIZE": str(pagesize)}
    try:
        r = _session.post(url, params={"JCDXH": jcdxh, "JCDLX": jcdlx},
                          data=data, timeout=60)
        rows = _parse_rows(r.text)
        total = _get_total(r.text)
        return {"success": True, "jcdxh": jcdxh, "jcdlx": jcdlx, "sjlx": sjlx,
                "total": total, "count": len(rows),
                "rows": [row["cells"] for row in rows]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="wryzxjc_raw_query",
    description="调用平台任意接口(仅已登录会话内只读调用)。path传完整路径(如 /pages/queryXzqh.do 或 /pages/zxjc/xxx/xxxProcessor.jsp)。method仅GET/POST。POST参数用form_data传JSON字符串",
    category=CATEGORY,
    tags=TAGS + ["raw"],
)
def wryzxjc_raw_query(path: str, method: str = "GET", form_data: str = "{}") -> dict:
    """通用原始查询（govmcp 注册表可见；不进聊天工具表）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    url = BASE + (path if path.startswith("/") else "/" + path)
    try:
        if method.upper() == "GET":
            r = _session.get(url, timeout=30)
        else:
            r = _session.post(url, data=json.loads(form_data), timeout=30)
        try:
            return {"success": True, "data": r.json()}
        except Exception:
            return {"success": True, "raw_html": r.text[:4000]}
    except Exception as e:
        return {"success": False, "error": f"调用失败: {e}"}


# ─── 注册入口 ────────────────────────────────────────────────

_TOOLS: list[Any] = [
    wryzxjc_login, wryzxjc_status, wryzxjc_list_regions,
    wryzxjc_list_pollution_sources, wryzxjc_get_pollution_source,
    wryzxjc_list_alarms, wryzxjc_list_devices, wryzxjc_list_realtime_data,
    wryzxjc_list_jcd_tree, wryzxjc_list_history_data, wryzxjc_raw_query,
]


def register_wryzxjc(reg: ToolRegistry) -> ToolRegistry:
    """注册娄底市污染源在线监测 govmcp 工具。"""
    reg.register_batch(_TOOLS)
    return reg


# ─── 聊天通道暴露（只读子集，L1 权限闸门）─────────────────────
# CHAT_TOOLS: name -> {"description", "parameters", "handler"}
# 登录/status/raw_query 不进聊天表（凭证不出现在聊天参数中）。


def _p(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


CHAT_TOOLS: dict[str, dict] = {
    "wryzxjc_list_regions": {
        "description": "娄底市污染源在线监测系统-行政区划查询（区县代码表）。",
        "parameters": _p(
            {"parent_code": {"type": "string", "description": "地市代码(娄底市=4313)"}},
            [],
        ),
        "handler": wryzxjc_list_regions,
    },
    "wryzxjc_list_pollution_sources": {
        "description": "娄底市污染源在线监测系统-重点排污企业列表(名称/地址/监管级别/法人/联系人)。qx区县(冷水江=431381)，wrymc名称模糊查询，jgjb监管级别(国控/省控/市控)。",
        "parameters": _p(
            {
                "qx": {"type": "string", "description": "区县代码(冷水江市=431381,空=娄底全市)"},
                "wrymc": {"type": "string", "description": "污染源名称模糊查询"},
                "jgjb": {"type": "string", "description": "监管级别(国控/省控/市控)"},
                "page": {"type": "integer", "description": "页码"},
                "pagesize": {"type": "integer", "description": "每页条数(默认50)"},
            },
            [],
        ),
        "handler": wryzxjc_list_pollution_sources,
    },
    "wryzxjc_get_pollution_source": {
        "description": "娄底市污染源在线监测系统-单个污染源详情(经纬度/法人/企业规模等)。xh从污染源列表获取。",
        "parameters": _p(
            {"xh": {"type": "string", "description": "污染源编号(列表结果xh字段)"}},
            ["xh"],
        ),
        "handler": wryzxjc_get_pollution_source,
    },
    "wryzxjc_list_alarms": {
        "description": "娄底市污染源在线监测系统-预警报警台账(超标/异常监测数据,执法核心证据)。sjzt数据状态(超标/异常/正常),pwlx排放类型(废水/废气)。",
        "parameters": _p(
            {
                "qx": {"type": "string", "description": "区县代码(冷水江市=431381)"},
                "sjzt": {"type": "string", "description": "数据状态(超标/异常/正常)"},
                "pwlx": {"type": "string", "description": "排放类型(废水/废气)"},
                "page": {"type": "integer", "description": "页码"},
                "pagesize": {"type": "integer", "description": "每页条数(默认50)"},
            },
            [],
        ),
        "handler": wryzxjc_list_alarms,
    },
    "wryzxjc_list_devices": {
        "description": "娄底市污染源在线监测系统-自动监控设备列表及在线状态。断线设备是'涉嫌干扰自动监测'的重要执法线索。",
        "parameters": _p(
            {
                "qx": {"type": "string", "description": "区县代码(冷水江市=431381)"},
                "wrymc": {"type": "string", "description": "污染源名称模糊查询"},
                "sbzt": {"type": "string", "description": "设备状态(在线/断线/停运)"},
                "page": {"type": "integer", "description": "页码"},
                "pagesize": {"type": "integer", "description": "每页条数(默认100)"},
            },
            [],
        ),
        "handler": wryzxjc_list_devices,
    },
    "wryzxjc_list_realtime_data": {
        "description": "娄底市污染源在线监测系统-实时监测数据(最近1小时)。pwkzl排污口种类(FS废水/FQ废气)。返回各监测因子浓度与超标标记。",
        "parameters": _p(
            {
                "pwkzl": {"type": "string", "description": "排污口种类(FS废水/FQ废气)"},
                "qx": {"type": "string", "description": "区县代码(冷水江市=431381)"},
                "wrymc": {"type": "string", "description": "污染源名称模糊查询"},
                "page": {"type": "integer", "description": "页码"},
                "pagesize": {"type": "integer", "description": "每页条数(默认50)"},
            },
            [],
        ),
        "handler": wryzxjc_list_realtime_data,
    },
    "wryzxjc_list_jcd_tree": {
        "description": "娄底市污染源在线监测系统-监测点树(污染源→监测点)。返回JCDXH监测点序号与JCDLX类型，供历史数据查询。",
        "parameters": _p(
            {
                "yzlx": {"type": "string", "description": "因子类型(空=全部/FS废水/FQ废气)"},
                "qx": {"type": "string", "description": "区县代码(冷水江市=431381)"},
                "wrymc": {"type": "string", "description": "污染源名称模糊查询"},
            },
            [],
        ),
        "handler": wryzxjc_list_jcd_tree,
    },
    "wryzxjc_list_history_data": {
        "description": "娄底市污染源在线监测系统-单监测点历史监测数据。sjlx数据类型(FZSJ分钟/SSJ时/RSJ日)，quick快捷时段(如-24近24小时/GD自定义)。返回各污染物历史监测值。",
        "parameters": _p(
            {
                "jcdxh": {"type": "string", "description": "监测点序号(从监测点树获取)"},
                "jcdlx": {"type": "string", "description": "类型(FS废水/FQ废气)"},
                "sjlx": {"type": "string", "description": "数据类型(FZSJ分钟/SSJ时/RSJ日)"},
                "quick": {"type": "string", "description": "快捷时段(如-24近24小时/GD自定义)"},
                "start_time": {"type": "string", "description": "自定义开始时间(yyyy-MM-dd HH)"},
                "end_time": {"type": "string", "description": "自定义结束时间(yyyy-MM-dd HH)"},
            },
            ["jcdxh"],
        ),
        "handler": wryzxjc_list_history_data,
    },
}

# 聊天工具表顺序（wiring_manifest 同步）
CHAT_NAMES: list[str] = list(CHAT_TOOLS.keys())
