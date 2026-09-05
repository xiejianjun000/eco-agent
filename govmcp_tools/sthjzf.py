#!/usr/bin/env python3
"""
govmcp_tools/sthjzf.py
国家生态环境保护综合执法监管平台（四平台）govmcp 工具集

来源：私有仓库 xiejianjun000/eco-sthjzf-mcp（四平台统一 CAS 逆向），
按 govmcp_tools 格式（@govmcp_tool 装饰器）转换后挂载到 eco-agent。

统一 CAS: https://sthjzf.lem.org.cn:8090（账号 431381，密码 AES-128-ECB 加密）
一次登录 → 跨平台 SSO 打通三个业务子系统（会话持久化，重启免重登）:
  1. 规范涉企行政检查系统  (sthjzf.lem.org.cn:8090/gfsqzz, Boanda, URL ?token=)
  2. 行政处罚系统          (eap.lem.org.cn, BladeX, header blade-auth: bearer JWT)
  3. 水环境非现场执法平台   (jkzx.envsc.cn, Spring, header Authorization: Bearer)
  4. 新化学物质监管         (瑞数反爬虫，纯 HTTP 暂不支持)

认证要点:
  - CAS: 密码 AES-128-ECB-Pkcs7(key=boandaxxjsgfyxgs) + Kaptcha 验证码(ddddocr)
    + lt/execution 票据；CASTGC(TGT) 全局票据跨平台复用，单点免密。
  - 凭证经环境变量 STHJZF_USERNAME / STHJZF_PASSWORD 注入，代码不硬编码。

安全: 查询类工具 L1 只读；水环境线索核实/确认两个写入工具
approval_required=True + confirm=true 双重闸门，不进聊天工具表。
"""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import threading
from typing import Any
from urllib.parse import urljoin

import requests
import urllib3

from govmcp.tools.registry import ToolRegistry, govmcp_tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CAS_BASE = os.environ.get("STHJZF_CAS_BASE", "https://sthjzf.lem.org.cn:8090").rstrip("/")
EAP_BASE = os.environ.get("STHJZF_EAP_BASE", "https://eap.lem.org.cn").rstrip("/")
WATER_BASE = os.environ.get("STHJZF_WATER_BASE", "https://jkzx.envsc.cn").rstrip("/")
AES_KEY = b"boandaxxjsgfyxgs"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# 规范涉企检查业务视图
VIEWS = {
    "线索反馈情况": "1746772895680063266816",
    "本级线索排查情况": "1745805853647122126336",
    "问题整改情况": "1753685081349056225792",
    "线索问题台账": "1748504668191125300736",
    "地方动态": "1749693798350043876352",
}

# 水环境线索类型 → 台账 API 路径
LEDGER_MAP = {
    "A": "ledger/autoMonitor/page",
    "B": "ledger/section/page",
    "C": "waterSource/task/page",
    "D": "ledger/internet/page",
    "E": "ledger/shoreline/page",
    "F": "ledger/satellite/page",
    "G": "ledger/heavyMetal/page",
    "H": "ledger/pwxk/page",
    "I": "ledger/siteAssistance/page",
    "J": "ledger/marineEnvEnforcement/page",
}

TASK_TYPE_NAMES = {
    "A": "自动监测线索",
    "B": "异常断面溯源线索",
    "C": "饮用水水源地线索",
    "D": "涉水环境违法网络线索",
    "E": "重点岸线管控线索",
    "F": "卫星遥感线索",
    "G": "涉重金属排放线索",
    "H": "排污许可线索",
    "I": "现场帮扶发现线索",
    "J": "海洋环境执法线索",
}

SOURCE_TYPE_NAMES = {
    "01": "日常执法检查",
    "02": "信访举报",
    "03": "专项执法行动",
    "04": "上级交办转办及领导批示",
    "09": "其他部门移交",
    "10": "中央环保督察",
    "11": "其他来源",
}

CLUE_VERIFY_API = {
    "B": "saveOrUpdatedClueSection",
    "C": "saveOrUpdatedClueWaterSource",
    "D": "saveOrUpdatedClueInternetPublicOpinion",
    "E": "saveOrUpdatedClueShorelineControl",
    "G": "saveOrUpdatedClueHeavyMetal",
    "H": "saveCluePsSavePwxkTask",
}
TASK_CHECK_TYPES = {"A", "F", "I", "J"}

REQUEST_TIMEOUT = 25.0

# ─── 会话状态 ────────────────────────────────────────────────

_lock = threading.Lock()
_session: requests.Session | None = None
_token_gfsqzz: str | None = None
_token_eap: str | None = None
_token_water: str | None = None
_logged_in = False
_last_username: str | None = None
_last_password: str | None = None


def _session_dir() -> str | None:
    base = os.environ.get("ECO_DIR") or os.path.expanduser("~/.eco")
    d = os.path.join(base, "sessions")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return None


def _session_file() -> str | None:
    d = _session_dir()
    return os.path.join(d, "sthjzf_session.json") if d else None


# ─── 认证底层 ────────────────────────────────────────────────


def _encrypt_password(pwd: str) -> str:
    """CAS 密码加密：AES-128-ECB-Pkcs7 + base64（key=boandaxxjsgfyxgs）。"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(pwd.encode("utf-8"), 16))).decode()


def _ocr_captcha(img_bytes: bytes) -> str:
    import ddddocr

    return ddddocr.DdddOcr(show_ad=False).classification(img_bytes).strip()


def _do_sso(session: requests.Session, username: str, password: str) -> bool:
    """CAS 登录，拿到 CASTGC。"""
    try:
        r0 = session.get(f"{CAS_BASE}/", timeout=25, allow_redirects=False)
        loc = r0.headers.get("Location", "")
        if not loc:
            return False
        r1 = session.get(loc if loc.startswith("http") else CAS_BASE + loc, timeout=25, allow_redirects=True)
        lt = re.search(r'name="lt" value="([^"]+)"', r1.text)
        ex = re.search(r'name="execution" value="([^"]+)"', r1.text)
        if not lt or not ex:
            return False
        cap = _ocr_captcha(session.get(f"{CAS_BASE}/cas/kaptcha.jpg", timeout=25).content)
        data = {
            "username": username,
            "password": _encrypt_password(password),
            "captcha": cap,
            "lt": lt.group(1),
            "execution": ex.group(1),
            "_eventId": "submit",
            "submit": "登 录",
        }
        r2 = session.post(f"{CAS_BASE}/cas/login", data=data, timeout=25, allow_redirects=False)
        if r2.status_code in (301, 302, 303, 307):
            session.get(r2.headers["Location"], timeout=25, allow_redirects=True)
            return True
        return False
    except Exception:
        return False


def _sso_follow(session: requests.Session, service_url: str) -> str:
    """用 CASTGC 换取 service 的最终跳转 URL，返回含 token 的最终 URL。"""
    cas_url = f"{CAS_BASE}/cas?service={requests.utils.quote(service_url, safe='')}"
    url = cas_url
    try:
        for _ in range(12):  # 最多 12 跳
            r = session.get(url, timeout=25, allow_redirects=False)
            if r.status_code in (301, 302, 303, 307):
                loc = r.headers.get("Location", "")
                if not loc:
                    return url
                url = urljoin(url, loc)
            else:
                return url
    except Exception:
        pass
    return url


def _fetch_gfsqzz_token(session: requests.Session) -> str:
    try:
        r = session.get(f"{CAS_BASE}/gfsqzz", timeout=25, allow_redirects=True)
        m = re.search(r"TOKEN\s*=\s*'([^']+)'", r.text)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _sso_all_platforms(session: requests.Session) -> tuple[str, str, str]:
    """用 CAS 会话换取三平台 token。"""
    gtoken = _fetch_gfsqzz_token(session)
    eap_final = _sso_follow(session, "http://eap.lem.org.cn/cas_client/")
    eap_m = re.search(r"token=([^&\"']+)", eap_final)
    eap_token = eap_m.group(1) if eap_m else ""
    water_final = _sso_follow(session, "https://jkzx.envsc.cn/automonitor-sso/cas/ssoLogin")
    water_m = re.search(r"t__=([^&\"']+)", water_final)
    water_token = water_m.group(1) if water_m else ""
    return gtoken, eap_token, water_token


def _save_session() -> None:
    """保存登录态（cookie 含 CASTGC + 凭证）到 ECO_DIR/sessions/。"""
    global _session, _last_username, _last_password
    path = _session_file()
    if not _session or not path:
        return
    try:
        cookies = [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path} for c in _session.cookies]
        state = {
            "username": _last_username,
            "password": _last_password,
            "cookies": cookies,
            "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def _load_session() -> bool:
    """从持久化文件恢复会话，用 CASTGC 免密换取三平台 token。"""
    global _session, _token_gfsqzz, _token_eap, _token_water
    global _logged_in, _last_username, _last_password
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
        _last_username = state.get("username")
        _last_password = state.get("password")
        gtoken, eap_token, water_token = _sso_all_platforms(s)
        if not gtoken:
            return False
        _session, _token_gfsqzz = s, gtoken
        _token_eap, _token_water = eap_token, water_token
        _logged_in = True
        return True
    except Exception:
        return False


def _do_login(username: str, password: str) -> bool:
    """核心登录：CAS + 三平台 SSO + 持久化。验证码最多重试 6 次。"""
    global _session, _token_gfsqzz, _token_eap, _token_water
    global _logged_in, _last_username, _last_password
    s = requests.Session()
    s.verify = False
    s.headers.update({"User-Agent": UA})
    for _ in range(6):
        if _do_sso(s, username, password):
            gtoken, eap_token, water_token = _sso_all_platforms(s)
            if not gtoken:
                continue
            _session, _token_gfsqzz = s, gtoken
            _token_eap, _token_water = eap_token, water_token
            _logged_in = True
            _last_username, _last_password = username, password
            _save_session()
            return True
    return False


def _need_login() -> str | None:
    """确保已登录：现有会话 → 恢复持久化会话 → 环境变量自动重登。"""
    global _logged_in, _last_username, _last_password
    if _logged_in and _session and _token_gfsqzz:
        return None
    if _load_session():
        return None
    env_u = os.environ.get("STHJZF_USERNAME", "")
    env_p = os.environ.get("STHJZF_PASSWORD", "")
    if env_u and env_p and _do_login(env_u, env_p):
        return None
    return "未登录，请先调用 sthjzf_login 工具，或设置环境变量 STHJZF_USERNAME / STHJZF_PASSWORD"


def _platform_status() -> dict:
    return {
        "logged_in": _logged_in,
        "gfsqzz_规范涉企检查": bool(_token_gfsqzz),
        "eap_行政处罚": bool(_token_eap),
        "water_水环境": bool(_token_water),
        "hxp_新化学物质": False,  # 瑞数反爬虫，纯 HTTP 暂不支持
        "username": _last_username or "",
    }


# ─── govmcp 工具定义 ─────────────────────────────────────────

CATEGORY = "执法平台-国家四平台"
TAGS = ["执法平台", "国家四平台", "行政处罚", "水环境", "非现场执法", "规范涉企检查"]


@govmcp_tool(
    name="sthjzf_login",
    description="一键登录国家生态环境综合执法监管平台(自动CAS认证+AES加密+验证码识别+跨平台SSO+会话持久化)。账号密码可通过参数传入,或设置环境变量 STHJZF_USERNAME/STHJZF_PASSWORD",  # noqa: E501
    category=CATEGORY,
    tags=TAGS + ["auth"],
)
def sthjzf_login(username: str = "", password: str = "") -> dict:
    """登录四平台（自动 SSO 到 规范涉企检查/行政处罚/水环境 三平台）。"""
    username = username or os.environ.get("STHJZF_USERNAME", "")
    password = password or os.environ.get("STHJZF_PASSWORD", "")
    if not username or not password:
        return {"success": False, "message": "请提供账号密码，或设置环境变量 STHJZF_USERNAME/STHJZF_PASSWORD"}
    with _lock:
        ok = _do_login(username, password)
    result = {
        "success": ok,
        "username": username,
        "gfsqzz_token": bool(_token_gfsqzz),
        "eap_token": bool(_token_eap),
        "water_token": bool(_token_water),
        "session_persisted": bool(_session_file()),
        "note": "新化学物质平台(瑞数反爬虫)暂不支持纯HTTP登录",
    }
    return result


@govmcp_tool(
    name="sthjzf_status",
    description="获取国家四平台登录状态",
    category=CATEGORY,
    tags=TAGS,
)
def sthjzf_status() -> dict:
    """四平台登录状态。"""
    return _platform_status()


@govmcp_tool(
    name="sthjzf_list_views",
    description="列出规范涉企检查系统的业务视图(线索反馈情况/本级线索排查情况/问题整改情况/线索问题台账/地方动态)",
    category=CATEGORY,
    tags=TAGS,
)
def sthjzf_list_views() -> dict:
    """规范涉企检查业务视图清单。"""
    return {"success": True, "views": VIEWS}


@govmcp_tool(
    name="sthjzf_query_view",
    description="查询规范涉企行政检查系统数据(线索/整改/台账/地方动态)。view传名称或ID,page_num页码,page_size每页条数",
    category=CATEGORY,
    tags=TAGS,
)
def sthjzf_query_view(view: str, page_num: int = 1, page_size: int = 20, url_params: str = "{}") -> dict:
    """规范涉企检查业务视图数据查询。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    vid = VIEWS.get(view, view)
    try:
        up = json.loads(url_params) if url_params else {}
    except Exception:
        return {"success": False, "error": "url_params 不是合法 JSON"}
    up.update({"isImmediatelyQuery": True, "isView": "", "token": _token_gfsqzz, "multi": True})
    body = {
        "xh": vid,
        "urlParams": up,
        "pageSize": page_size,
        "pageNum": page_num,
        "executeQuery": {"conditions": []},
        "extendParam": {},
    }
    url = f"{CAS_BASE}/gfsqzz/platform/component/queryservice/analysis/analysiscontroller/query/{vid}"
    try:
        r = _session.post(url, json=body, timeout=30)
        j = r.json()
        return {"success": True, "view": view, "total": j.get("total"), "rows": j.get("list", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_get_menu",
    description="获取规范涉企检查系统菜单树。system子系统标识(空=规范涉企检查系统)",
    category=CATEGORY,
    tags=TAGS,
)
def sthjzf_get_menu(system: str = "") -> dict:
    """规范涉企检查系统菜单树（system 预留多系统标识，当前仅 gfsqzz）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    try:
        r = _session.post(f"{CAS_BASE}/gfsqzz/main/findcurrentusermenu?token={_token_gfsqzz}", timeout=25)
        return {"success": True, "system": system or "gfsqzz", "menu": r.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_get_view_config",
    description="获取规范涉企检查视图配置(字段定义+SQL)。view传名称或ID",
    category=CATEGORY,
    tags=TAGS,
)
def sthjzf_get_view_config(view: str) -> dict:
    """规范涉企检查视图配置（字段 + SQL 定义）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    vid = VIEWS.get(view, view)
    url = f"{CAS_BASE}/gfsqzz/platform/component/queryservice/analysis/analysiscontroller/showview/{vid}?token={_token_gfsqzz}"
    try:
        html = _session.get(url, timeout=25).text
        i = html.find("var listConfig")
        if i < 0:
            return {"success": False, "error": "未找到 listConfig"}
        j = html.find("{", i)
        obj, _ = json.JSONDecoder().raw_decode(html[j:])
        td = obj.get("targetData", {})
        cols = [
            {
                "字段": c.get("zd"),
                "类型": c.get("zdlx"),
                "中文名": c.get("zdm"),
                "展示": c.get("isChecked"),
                "可导出": c.get("isExport"),
            }
            for c in obj.get("targetColumns", [])
        ]
        return {
            "success": True,
            "view": view,
            "viewId": vid,
            "sql": td.get("select"),
            "where": td.get("where"),
            "orderBy": td.get("orderBy"),
            "columns": cols,
        }
    except Exception as e:
        return {"success": False, "error": f"解析失败: {e}"}


@govmcp_tool(
    name="sthjzf_query_cases",
    description="查询行政处罚案件列表(全国环境行政处罚案件管理信息系统)。page_num页码,page_size每页条数",
    category=CATEGORY,
    tags=TAGS + ["行政处罚"],
)
def sthjzf_query_cases(page_num: int = 1, page_size: int = 20) -> dict:
    """行政处罚案件登记列表。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_eap:
        return {"success": False, "error": "行政处罚系统未登录(SSO失败)"}
    headers = {"blade-auth": f"bearer {_token_eap}"}
    url = f"{EAP_BASE}/api/td-punish/caseRegist/list?current={page_num}&size={page_size}"
    try:
        j = _session.get(url, headers=headers, timeout=30).json()
        data = j.get("data", {})
        return {"success": True, "total": data.get("total"), "records": data.get("records", [])}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_list_depts",
    description="查询行政处罚部门树(全国生态环境部门)。parent_id上级部门ID(空=顶层部门树)",
    category=CATEGORY,
    tags=TAGS + ["行政处罚"],
)
def sthjzf_list_depts(parent_id: str = "") -> dict:
    """行政处罚部门树。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_eap:
        return {"success": False, "error": "行政处罚系统未登录(SSO失败)"}
    headers = {"blade-auth": f"bearer {_token_eap}"}
    params = {"parentId": parent_id} if parent_id else None
    try:
        j = _session.get(f"{EAP_BASE}/api/td-system/dept/list", headers=headers, params=params, timeout=30).json()
        data = j.get("data", [])
        return {"success": True, "count": len(data), "rows": data[:200]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_query_case_detail",
    description="查询行政处罚案件详情(按案件id)。case_id从sthjzf_query_cases结果的id字段获取",
    category=CATEGORY,
    tags=TAGS + ["行政处罚"],
)
def sthjzf_query_case_detail(case_id: str) -> dict:
    """行政处罚案件详情。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_eap:
        return {"success": False, "error": "行政处罚系统未登录(SSO失败)"}
    headers = {"blade-auth": f"bearer {_token_eap}"}
    try:
        j = _session.get(f"{EAP_BASE}/api/td-punish/caseRegist/detail?id={case_id}", headers=headers, timeout=30).json()
        return {"success": True, "detail": j.get("data", {})}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_query_case_statistics",
    description="查询行政处罚案件来源类型统计。source_type:01日常执法检查/02信访举报/03专项行动/04上级交办/09其他部门/10中央督察/11其他;area_code行政区划代码;start_date/end_date统计周期",
    category=CATEGORY,
    tags=TAGS + ["行政处罚"],
)
def sthjzf_query_case_statistics(
    source_type: str = "01", area_code: str = "", start_date: str = "2026-01-01", end_date: str = ""
) -> dict:
    """行政处罚案件来源类型统计。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_eap:
        return {"success": False, "error": "行政处罚系统未登录(SSO失败)"}
    if not end_date:
        end_date = datetime.date.today().strftime("%Y-%m-%d")
    headers = {"blade-auth": f"bearer {_token_eap}"}
    params = {"sourceType": source_type, "startDate": start_date, "endDate": end_date}
    if area_code:
        params["areaCode"] = area_code
    try:
        j = _session.get(
            f"{EAP_BASE}/api/td-punish/caseDetailVisual/caseDetailSourceTypeStatistics",
            headers=headers,
            params=params,
            timeout=30,
        ).json()
        data = j.get("data", {})
        return {
            "success": True,
            "来源类型": SOURCE_TYPE_NAMES.get(source_type, source_type),
            "areaCode": area_code or "全国",
            "period": f"{start_date} ~ {end_date}",
            "案件数": data.get("total"),
            "records": data.get("records", []),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_water_current_user",
    description="获取水环境非现场执法平台当前登录用户信息。include_ext是否返回完整原始信息(默认False精简)",
    category=CATEGORY,
    tags=TAGS + ["水环境"],
)
def sthjzf_water_current_user(include_ext: bool = False) -> dict:
    """水环境平台当前用户。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    headers = {"Authorization": f"Bearer {_token_water}"}
    try:
        r = _session.get(f"{WATER_BASE}/api/uiam-users/get/current-user", headers=headers, timeout=25)
        data = r.json()
        if include_ext:
            return {"success": True, "data": data}
        d = data.get("data", data)
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k not in ("roles", "perms", "authorities")}
        return {"success": True, "data": d}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_water_task_statistics",
    description="查询水环境非现场执法问题推送统计(任务总计/待核实/待确认/已办结/属实/立案/处罚金额及按10类线索类型分布)。region_code默认431381=冷水江市;start_time/end_time统计周期",
    category=CATEGORY,
    tags=TAGS + ["水环境"],
)
def sthjzf_water_task_statistics(region_code: str = "431381", start_time: str = "2026-01-01", end_time: str = "") -> dict:
    """水环境非现场执法'工作进展情况'统计（问题推送）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    if not end_time:
        end_time = datetime.date.today().strftime("%Y-%m-%d")
    headers = {"Authorization": f"Bearer {_token_water}", "Content-Type": "application/json"}
    body = {"regionCode": region_code, "startTime": start_time, "endTime": end_time}
    try:
        r = _session.post(f"{WATER_BASE}/water-law-platform/home/statisticsLeft", headers=headers, json=body, timeout=30)
        j = r.json()
        data = j.get("data", {})
        top = data.get("rightTopVo", {})
        types = data.get("taskTypeStatisticsVos", [])
        return {
            "success": True,
            "regionCode": region_code,
            "period": f"{start_time} ~ {end_time}",
            "任务总计": top.get("taskCount"),
            "待核实": top.get("checkCount"),
            "待确认": top.get("confirmCount"),
            "已办结": top.get("ybjCount"),
            "属实": top.get("trueCount"),
            "属实率": top.get("trueRate"),
            "不属实": top.get("notTrueCount"),
            "违法": top.get("illegalCount"),
            "立案": top.get("filedCaseCount"),
            "处罚金额": top.get("penaltyAmount"),
            "按线索类型": [
                {
                    "类型": t.get("name"),
                    "总数": t.get("taskCount"),
                    "待核实": t.get("checkCount"),
                    "待确认": t.get("confirmCount"),
                    "已办结": t.get("ybjCount"),
                }
                for t in types
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_water_task_list",
    description="查询水环境任务办理明细台账。task_type传线索类型(A-J:A自动监测 B断面溯源 C水源地 D违法网络 E岸线 F遥感 G重金属 H排污许可 I帮扶 J海洋);task_status:-1全部/10待区县核实/20待市级确认/30待最终认定/40已完成;is_true:-1全部/1属实/0不属实",  # noqa: E501
    category=CATEGORY,
    tags=TAGS + ["水环境"],
)
def sthjzf_water_task_list(
    task_type: str = "A",
    page_num: int = 1,
    page_size: int = 20,
    region_code: str = "431381000",
    start_time: str = "2026-01-01",
    end_time: str = "",
    task_status: str = "-1",
    company_name: str = "",
    is_true: int = -1,
) -> dict:
    """水环境非现场执法任务办理台账（10 类线索全支持）。"""
    if task_type not in LEDGER_MAP:
        return {
            "success": False,
            "error": f"线索类型 task_type 应为 A-J 之一，支持: {json.dumps(TASK_TYPE_NAMES, ensure_ascii=False)}",
        }
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    if not end_time:
        end_time = datetime.date.today().strftime("%Y-%m-%d")
    path = LEDGER_MAP[task_type]
    headers = {"Authorization": f"Bearer {_token_water}", "Content-Type": "application/json"}
    body = {
        "pageNum": page_num,
        "pageSize": page_size,
        "regionCode": region_code,
        "valleyCode": "-1",
        "taskNum": "",
        "importProblemNum": "",
        "taskStatus": task_status,
        "rectificationStatus": "-1",
        "isTrue": is_true,
        "isIllegal": -1,
        "taskSendStartTime": start_time,
        "taskSendEndTime": end_time,
        "onlyCurrentLevelPendingVerify": 0,
        "onlyCurrentLevelPendingConfirm": 0,
        "onlyCurrentLevelPendingRectification": 0,
        "clueType": "-1",
        "companyName": company_name,
        "mpName": "",
        "isFiling": None,
    }
    try:
        r = _session.post(f"{WATER_BASE}/water-law-platform/{path}", headers=headers, json=body, timeout=30)
        j = r.json()
        data = j.get("data", {})
        page = data.get("page", {})
        return {
            "success": True,
            "线索类型": TASK_TYPE_NAMES.get(task_type, task_type),
            "total": page.get("total"),
            "todoCount": data.get("todoCount"),
            "rows": page.get("rows", []),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_water_supervise_statistics",
    description="查询水环境非现场执法监督统计(监督线索总数/未处理/处理中/已处理/违法/排污口/处罚金额)",
    category=CATEGORY,
    tags=TAGS + ["水环境"],
)
def sthjzf_water_supervise_statistics(start_time: str = "2026-01-01", end_time: str = "") -> dict:
    """水环境非现场执法监督统计。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    if not end_time:
        end_time = datetime.date.today().strftime("%Y-%m-%d")
    headers = {"Authorization": f"Bearer {_token_water}"}
    try:
        j = _session.get(
            f"{WATER_BASE}/water-platform/offSceneEnforcementWork/OffSceneEnforcementWorkStatistics",
            headers=headers,
            params={"startTime": start_time, "endTime": end_time},
            timeout=30,
        ).json()
        d = j.get("data", {})
        return {
            "success": True,
            "监督线索总数": d.get("superviseNum"),
            "未处理": d.get("notProcessedNum"),
            "未处理占比": d.get("notProcessedProportion"),
            "处理中": d.get("processingInProcessedNum"),
            "处理中占比": d.get("processingInProcessedProportion"),
            "已处理": d.get("alreadyProcessedNum"),
            "违法": d.get("illegalNum"),
            "排污口": d.get("dischargeOutletNum"),
            "处罚金额": d.get("penaltyAmount"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── 写入类工具（approval_required + confirm 双重闸门，不进聊天表）──


@govmcp_tool(
    name="sthjzf_water_clue_verify",
    description="水环境线索核实写入(敏感操作,需审批)。task_type支持A自动监测/F遥感/I帮扶/J海洋/B断面/C水源地/D违法网络/E岸线/G重金属/H排污许可;is_true:1属实/2部分属实/0不属实;需confirm=true才执行",
    category=CATEGORY,
    tags=TAGS + ["水环境", "写入", "敏感"],
    approval_required=True,
)
def sthjzf_water_clue_verify(
    clue_id: str,
    task_type: str = "A",
    is_true: int = 0,
    is_illegal: int = 0,
    situation: str = "",
    is_filing: int = 0,
    confirm: bool = False,
) -> dict:
    """水环境非现场执法线索核实提交（写入平台，敏感操作）。"""
    if not confirm:
        return {"blocked": True, "message": "写入操作需人工授权，请确认后设置 confirm=true 重新调用"}
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    headers = {"Authorization": f"Bearer {_token_water}", "Content-Type": "application/json"}
    if task_type in TASK_CHECK_TYPES:
        api = "task/taskCheck"
        body = {
            "commitType": 1,
            "taskAssignId": clue_id,
            "taskType": task_type,
            "taskVerifyRecords": [
                {
                    "isTrue": is_true,
                    "isIllegal": is_illegal,
                    "clueVerificationSituationDescription": situation,
                    "isFiling": is_filing,
                }
            ],
            "taskPunishmentRecords": [],
        }
        r = _session.post(f"{WATER_BASE}/water-law-platform/{api}", headers=headers, json=body, timeout=30)
    else:
        if task_type not in CLUE_VERIFY_API:
            return {"success": False, "error": "线索类型 task_type 应为 A/B/C/D/E/F/G/H/I/J 之一"}
        api = f"clueChange/{CLUE_VERIFY_API[task_type]}"
        body = {
            "id": clue_id,
            "clueId": clue_id,
            "isTrue": is_true,
            "isIllegal": is_illegal,
            "situationDescribe": situation,
            "isFiling": is_filing,
        }
        r = _session.post(f"{WATER_BASE}/water-law-platform/{api}", headers=headers, json=body, timeout=30)
    try:
        j = r.json()
        return {"success": j.get("code") == 0, "api": api, "code": j.get("code"), "msg": j.get("msg"), "data": j.get("data")}
    except Exception:
        return {"success": False, "raw": r.text[:2000]}


@govmcp_tool(
    name="sthjzf_water_clue_confirm",
    description="水环境线索确认写入(敏感操作,需审批)。市级/省级对已核实线索做确认。is_pass:1通过/0驳回;需confirm=true才执行",
    category=CATEGORY,
    tags=TAGS + ["水环境", "写入", "敏感"],
    approval_required=True,
)
def sthjzf_water_clue_confirm(task_id: str, is_pass: int = 1, confirm_describe: str = "", confirm: bool = False) -> dict:
    """水环境线索确认（待确认状态任务 taskStatus=20）。"""
    if not confirm:
        return {"blocked": True, "message": "写入操作需人工授权，请确认后设置 confirm=true 重新调用"}
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录(SSO失败)"}
    headers = {"Authorization": f"Bearer {_token_water}", "Content-Type": "application/json"}
    body = {"isPass": is_pass, "confirmDescribe": confirm_describe, "id": task_id}
    try:
        r = _session.post(f"{WATER_BASE}/water-law-platform/task/taskConfirm", headers=headers, json=body, timeout=30)
        j = r.json()
        return {
            "success": j.get("code") == 0,
            "api": "task/taskConfirm",
            "code": j.get("code"),
            "msg": j.get("msg"),
            "data": j.get("data"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="sthjzf_water_api",
    description="调用水环境平台 API(仅已登录会话)。path传完整路径(如 /water-law-platform/xxx 或 /water-platform/xxx 或 /api/xxx)",  # noqa: E501
    category=CATEGORY,
    tags=TAGS + ["水环境", "raw"],
)
def sthjzf_water_api(path: str, method: str = "GET", body: str = "{}") -> dict:
    """通用水环境 API（govmcp 注册表可见；不进聊天工具表）。"""
    err = _need_login()
    if err:
        return {"success": False, "error": err}
    if not _token_water:
        return {"success": False, "error": "水环境平台未登录"}
    headers = {"Authorization": f"Bearer {_token_water}"}
    url = WATER_BASE + (path if path.startswith("/") else "/" + path)
    try:
        if method.upper() == "GET":
            r = _session.get(url, headers=headers, timeout=30)
        else:
            r = _session.post(url, headers=headers, json=json.loads(body), timeout=30)
        try:
            return {"success": True, "data": r.json()}
        except Exception:
            return {"success": True, "raw": r.text[:4000]}
    except Exception as e:
        return {"success": False, "error": f"调用失败: {e}"}


# ─── 注册入口 ────────────────────────────────────────────────

_TOOLS: list[Any] = [
    sthjzf_login,
    sthjzf_status,
    sthjzf_list_views,
    sthjzf_query_view,
    sthjzf_get_menu,
    sthjzf_get_view_config,
    sthjzf_query_cases,
    sthjzf_list_depts,
    sthjzf_query_case_detail,
    sthjzf_query_case_statistics,
    sthjzf_water_current_user,
    sthjzf_water_task_statistics,
    sthjzf_water_task_list,
    sthjzf_water_supervise_statistics,
    sthjzf_water_clue_verify,
    sthjzf_water_clue_confirm,
    sthjzf_water_api,
]


def register_sthjzf(reg: ToolRegistry) -> ToolRegistry:
    """注册国家四平台 govmcp 工具。"""
    reg.register_batch(_TOOLS)
    return reg


# ─── 聊天通道暴露（只读子集，L1 权限闸门）─────────────────────
# 登录/写入类/raw 不进聊天表（凭证不进聊天参数，写入走审批+confirm 双闸）。


def _p(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


CHAT_TOOLS: dict[str, dict] = {
    "sthjzf_query_view": {
        "description": "国家四平台-规范涉企行政检查系统数据查询(线索反馈/本级线索排查/问题整改/线索问题台账/地方动态)。view传名称或ID。",  # noqa: E501
        "parameters": _p(
            {
                "view": {"type": "string", "description": "视图名称(如 线索问题台账)或ID"},
                "page_num": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
            },
            ["view"],
        ),
        "handler": sthjzf_query_view,
    },
    "sthjzf_get_menu": {
        "description": "国家四平台-规范涉企检查系统菜单树。",
        "parameters": _p(
            {"system": {"type": "string", "description": "子系统标识(空=规范涉企检查系统)"}},
            [],
        ),
        "handler": sthjzf_get_menu,
    },
    "sthjzf_get_view_config": {
        "description": "国家四平台-规范涉企检查视图配置(字段定义+SQL)。view传名称或ID。",
        "parameters": _p(
            {"view": {"type": "string", "description": "视图名称或ID"}},
            ["view"],
        ),
        "handler": sthjzf_get_view_config,
    },
    "sthjzf_query_cases": {
        "description": "国家四平台-行政处罚案件列表(全国环境行政处罚案件管理信息系统)。",
        "parameters": _p(
            {
                "page_num": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
            },
            [],
        ),
        "handler": sthjzf_query_cases,
    },
    "sthjzf_list_depts": {
        "description": "国家四平台-行政处罚部门树(全国生态环境部门)。",
        "parameters": _p(
            {"parent_id": {"type": "string", "description": "上级部门ID(空=顶层部门树)"}},
            [],
        ),
        "handler": sthjzf_list_depts,
    },
    "sthjzf_query_case_detail": {
        "description": "国家四平台-行政处罚案件详情。case_id从案件列表结果id字段获取。",
        "parameters": _p(
            {"case_id": {"type": "string", "description": "案件id"}},
            ["case_id"],
        ),
        "handler": sthjzf_query_case_detail,
    },
    "sthjzf_query_case_statistics": {
        "description": "国家四平台-行政处罚案件来源类型统计(01日常执法检查/02信访举报/03专项行动/04上级交办/09其他部门/10中央督察/11其他)。",  # noqa: E501
        "parameters": _p(
            {
                "source_type": {"type": "string", "description": "来源类型(01-11)"},
                "area_code": {"type": "string", "description": "行政区划代码(空=全国)"},
                "start_date": {"type": "string", "description": "开始日期(YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "结束日期(YYYY-MM-DD)"},
            },
            [],
        ),
        "handler": sthjzf_query_case_statistics,
    },
    "sthjzf_water_task_statistics": {
        "description": "国家四平台-水环境非现场执法问题推送统计(任务总计/待核实/待确认/已办结/属实/立案/处罚金额及10类线索分布)。region_code默认431381=冷水江市。",  # noqa: E501
        "parameters": _p(
            {
                "region_code": {"type": "string", "description": "行政区划代码(默认431381冷水江市)"},
                "start_time": {"type": "string", "description": "开始日期(YYYY-MM-DD)"},
                "end_time": {"type": "string", "description": "结束日期(YYYY-MM-DD)"},
            },
            [],
        ),
        "handler": sthjzf_water_task_statistics,
    },
    "sthjzf_water_task_list": {
        "description": "国家四平台-水环境任务办理明细台账(10类线索:A自动监测/B断面溯源/C水源地/D违法网络/E岸线/F遥感/G重金属/H排污许可/I帮扶/J海洋)。task_status:-1全部/10待区县核实/20待市级确认/30待最终认定/40已完成。",  # noqa: E501
        "parameters": _p(
            {
                "task_type": {"type": "string", "description": "线索类型(A-J)"},
                "page_num": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
                "region_code": {"type": "string", "description": "行政区划代码(默认431381000)"},
                "start_time": {"type": "string", "description": "任务下发开始日期(YYYY-MM-DD)"},
                "end_time": {"type": "string", "description": "任务下发结束日期(YYYY-MM-DD)"},
                "task_status": {
                    "type": "string",
                    "description": "任务状态(-1全部/10待区县核实/20待市级确认/30待最终认定/40已完成)",
                },
                "company_name": {"type": "string", "description": "企业名称模糊查询"},
                "is_true": {"type": "integer", "description": "是否属实(-1全部/1属实/0不属实)"},
            },
            [],
        ),
        "handler": sthjzf_water_task_list,
    },
    "sthjzf_water_supervise_statistics": {
        "description": "国家四平台-水环境非现场执法监督统计(监督线索总数/未处理/处理中/已处理/违法/排污口/处罚金额)。",
        "parameters": _p(
            {
                "start_time": {"type": "string", "description": "开始日期(YYYY-MM-DD)"},
                "end_time": {"type": "string", "description": "结束日期(YYYY-MM-DD)"},
            },
            [],
        ),
        "handler": sthjzf_water_supervise_statistics,
    },
    "sthjzf_water_current_user": {
        "description": "国家四平台-水环境平台当前登录用户信息。",
        "parameters": _p(
            {"include_ext": {"type": "boolean", "description": "是否返回完整原始信息(默认False精简)"}},
            [],
        ),
        "handler": sthjzf_water_current_user,
    },
}

# 聊天工具表顺序（wiring_manifest 同步）
CHAT_NAMES: list[str] = list(CHAT_TOOLS.keys())
