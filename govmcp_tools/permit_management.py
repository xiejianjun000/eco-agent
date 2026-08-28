#!/usr/bin/env python3
"""
govmcp_tools/permit_management.py
全国排污许可证管理信息平台-管理端 govmcp 工具集

来源：私有仓库 xiejianjun000/permit-management-mcp（内网平台逆向，只读查询），
按 govmcp_tools 格式（@govmcp_tool 装饰器）转换后挂载到 eco-agent。

覆盖两大系统：
  1. 主系统（许可证核发/档案，Struts2）    PERMIT_BASE=/permit/
  2. 实施与监管系统（Vue SPA）             PERMIT_JGZF_BASE=/lawweb/

认证（已逆向验证）：
  主系统登录: POST LoginAction.do(actionType=login)
    - RSA-1024 raw 无 padding 加密密码，指数 0x10001，chunkSize=126，小端 pow()
    - modulus 每次 GET login.jsp 动态生成，实时提取
    - 4 位字母数字验证码，ddddocr 识别
    - 强制改密页自动绕过（新旧密码相同提交）
  实施监管系统 SSO: 主系统跳转 → autoLogin 换 token
    - sign = MD5(version + timestamp + token + dataString + key)，version="1.0"
    - key = PERMIT_JGZF_KEY（前端硬编码，环境变量提供）

配置（环境变量）：
  PERMIT_BASE / PERMIT_JGZF_BASE / PERMIT_JGZF_KEY / PERMIT_USERNAME / PERMIT_PASSWORD
  目标系统为内网地址，不硬编码；本机直连平台，数据不上公网。

安全：全部工具只读查询（绝不修改/删除数据）；登录工具不进聊天工具表，
自动登录从环境变量取凭证。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import datetime
import threading
from typing import Any

import requests

from govmcp.tools.registry import ToolRegistry, govmcp_tool

BASE = os.environ.get("PERMIT_BASE", "").rstrip("/")
JGZF_BASE = os.environ.get("PERMIT_JGZF_BASE", "").rstrip("/")
E = 0x10001
CHUNK = 126
JGZF_VERSION = "1.0"
JGZF_KEY = os.environ.get("PERMIT_JGZF_KEY", "")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

REQUEST_TIMEOUT = 25.0

_lock = threading.Lock()
_client: PermitClient | None = None


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
    return os.path.join(d, "permit_session.json") if d else None


# ─── RSA 加密（复现前端 RSAUtils.encryptedString: raw RSA no padding）──

def rsa_encrypt(pwd: str, modulus: str) -> str:
    """RSA-1024 raw 无 padding，指数 0x10001，chunk 126，小端字节序 pow()。"""
    m = int(modulus, 16)
    data = pwd.encode("utf-8")
    a = list(data) + [0] * (CHUNK - len(data))
    block_int = int.from_bytes(bytes(a), "little")
    c = pow(block_int, E, m)
    return hex(c)[2:]


def extract_modulus(html: str) -> str | None:
    """从登录页提取动态 RSA modulus。"""
    m = re.search(r'getKeyPair\(\s*"10001"\s*,\s*""\s*,\s*"([0-9a-fA-F]+)"\s*\)', html)
    if m:
        return m.group(1)
    m = re.search(r'"10001"\s*,\s*""\s*,\s*"([0-9a-fA-F]{128,})"', html)
    return m.group(1) if m else None


def extract_error(html: str) -> str:
    """提取登录页红色错误提示。"""
    for color in ("#FF0000", "red"):
        m = re.search(r'<font[^>]*color\s*=\s*["\']' + color + r'["\'][^>]*>\s*(.*?)\s*</font>',
                      html, re.S)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def jgzf_sign(token: str, data_string: str) -> dict:
    """实施监管系统签名：sign=MD5(version+timestamp+token+dataString+key)。"""
    ts = int(time.time())
    raw = JGZF_VERSION + str(ts) + (token or "") + data_string + JGZF_KEY
    sg = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return {"sign": sg, "timestamp": str(ts), "token": token or "", "version": JGZF_VERSION}


# ─── 平台客户端 ──────────────────────────────────────────────

class PermitClient:
    """排污许可平台客户端（主系统 + 实施监管系统 SSO）。"""

    def __init__(self, base: str = BASE):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.logged_in = False
        self.username: str | None = None
        self.password: str | None = None
        self.jgzf_token: str | None = None
        self.jgzf_user: dict | None = None
        self._load_session()

    # ---------- 会话持久化 ----------
    def save_session(self) -> None:
        path = _session_file()
        if not path:
            return
        try:
            cookies = [
                {"name": ck.name, "value": ck.value, "domain": ck.domain, "path": ck.path}
                for ck in self.s.cookies
            ]
            data = {"username": self.username, "password": self.password,
                    "cookies": cookies, "jgzf_token": self.jgzf_token,
                    "jgzf_user": self.jgzf_user}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_session(self) -> None:
        path = _session_file()
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.username = data.get("username")
            self.password = data.get("password")
            self.jgzf_token = data.get("jgzf_token")
            self.jgzf_user = data.get("jgzf_user")
            for ck in data.get("cookies", []):
                self.s.cookies.set(ck.get("name"), ck.get("value"),
                                   domain=ck.get("domain"), path=ck.get("path"))
            if self._verify_session():
                self.logged_in = True
        except Exception:
            pass

    def _verify_session(self) -> bool:
        try:
            r = self.s.get(self.base + "/default.jsp", timeout=10, allow_redirects=False)
            return r.status_code in (200, 302)
        except Exception:
            return False

    # ---------- 主系统登录 ----------
    def login(self, username: str, password: str, max_retries: int = 6) -> dict:
        """登录主系统（自动处理强制改密：新旧密码相同提交绕过后端）。"""
        for attempt in range(1, max_retries + 1):
            try:
                r = self.s.get(self.base + "/login.jsp", timeout=20)
            except Exception:
                return {"success": False, "error": "无法访问 PERMIT_BASE，请检查内网连通性与环境变量配置"}
            modulus = extract_modulus(r.text)
            if not modulus:
                time.sleep(0.5)
                continue
            try:
                r = self.s.get(self.base + "/ValidateCodeLoginImageServlet", timeout=20)
                import ddddocr
                code = ddddocr.DdddOcr(show_ad=False).classification(r.content).strip()
            except Exception:
                return {"success": False, "error": "验证码识别组件不可用"}
            if not code or len(code) != 4:
                time.sleep(0.5)
                continue
            data = {"actionType": "login", "pwd": rsa_encrypt(password, modulus),
                    "cmd": "", "usercode": username, "pwds": "", "verCode": code}
            try:
                r = self.s.post(self.base + "/LoginAction.do", data=data,
                                timeout=30, allow_redirects=True)
            except Exception as e:
                return {"success": False, "error": str(e)}
            err = extract_error(r.text)
            title_m = re.search(r"<title>([^<]*)</title>", r.text)
            title = title_m.group(1) if title_m else ""

            if "超过五次" in err or "后再登录" in err:
                m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", err)
                return {"success": False, "locked": True, "error": err,
                        "until": m.group(1) if m else None}
            if "验证码" in err:
                time.sleep(0.3)
                continue
            if "密码" in err or "用户名" in err or "账号" in err or "禁用" in err:
                return {"success": False, "error": err}

            # 强制改密页
            if title == "修改密码":
                mod2 = extract_modulus(r.text)
                if not mod2:
                    continue
                data2 = {"actionType": "updated", "cmd": "", "id": username,
                         "pwdRSA": rsa_encrypt(password, mod2),
                         "newpwdRSA": rsa_encrypt(password, mod2)}
                r2 = self.s.post(self.base + "/LoginAction.do", data=data2,
                                 timeout=30, allow_redirects=True)
                err2 = extract_error(r2.text)
                title2_m = re.search(r"<title>([^<]*)</title>", r2.text)
                title2 = title2_m.group(1) if title2_m else ""
                if "修改密码" in title2:
                    return {"success": False, "error": err2 or "改密失败"}
                self.logged_in = True
                self.username, self.password = username, password
                self.save_session()
                return {"success": True, "username": username, "changed_password": True,
                        "session": self.s.cookies.get("JSESSIONID", ""), "attempts": attempt}

            self.logged_in = True
            self.username, self.password = username, password
            self.save_session()
            return {"success": True, "username": username, "changed_password": False,
                    "session": self.s.cookies.get("JSESSIONID", ""), "attempts": attempt}
        return {"success": False, "error": "验证码识别失败次数过多"}

    def ensure_logged_in(self) -> bool:
        if not self.base:
            return False
        if not self.logged_in:
            if not self.username or not self.password:
                return False
            return bool(self.login(self.username, self.password).get("success"))
        if not self._verify_session():
            if not self.username or not self.password:
                self.logged_in = False
                return False
            return bool(self.login(self.username, self.password).get("success"))
        return True

    # ---------- 实施监管系统 SSO ----------
    def jgzf_sso_login(self) -> dict:
        try:
            r = self.s.get(self.base + "/jgzf/jgzf!jgzf.action",
                           timeout=30, allow_redirects=False)
        except Exception as e:
            return {"success": False, "error": str(e)}
        location = r.headers.get("Location", "")
        if not location:
            try:
                r2 = self.s.get(self.base + "/jgzf/jgzf!jgzf.action",
                                timeout=30, allow_redirects=True)
                location = str(r2.url or "")
            except Exception:
                location = ""
        m = re.search(r"userAccount=([^&]+)&userRole=([^&]+)&tokenid=([^&]+)", location)
        if not m:
            m_ua = re.search(r"userAccount=([^&]+)", location)
            m_ur = re.search(r"userRole=([^&]+)", location)
            m_tk = re.search(r"tokenid=([^&]+)", location)
            if not (m_ua and m_ur and m_tk):
                return {"success": False, "error": "未能获取 SSO 跳转参数"}
            user_account = requests.utils.unquote(m_ua.group(1))
            user_role, tokenid = m_ur.group(1), requests.utils.unquote(m_tk.group(1))
        else:
            user_account = requests.utils.unquote(m.group(1))
            user_role, tokenid = m.group(2), requests.utils.unquote(m.group(3))
        data = {"userRole": user_role, "userAccount": user_account, "tokenid": tokenid}
        data_string = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        headers = jgzf_sign("", data_string)
        headers.update({"Content-Type": "application/json", "User-Agent": UA})
        try:
            r2 = requests.post(JGZF_BASE + "/law/api/login/v1/autoLogin",
                               data=data_string, headers=headers, timeout=30)
            j = r2.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
        if j.get("code") == 1:
            self.jgzf_token = j["data"]["token"]
            self.jgzf_user = j["data"]
            self.save_session()
            return {"success": True, "token": self.jgzf_token, "user": j["data"]}
        return {"success": False, "error": j.get("msg", "SSO 登录失败")}

    def jgzf_call(self, path: str, token: str | None = None, data: dict | None = None,
                  method: str = "POST", params: dict | None = None) -> requests.Response:
        token = token or self.jgzf_token
        data_string = (json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                       if data is not None else "")
        headers = jgzf_sign(token or "", data_string)
        headers.update({"Content-Type": "application/json", "User-Agent": UA})
        if method.upper() == "GET":
            return requests.get(JGZF_BASE + path, params=params,
                                headers=headers, timeout=30)
        return requests.post(JGZF_BASE + path, data=data_string,
                             headers=headers, timeout=30)

    def jgzf_ensure(self) -> dict:
        if not self.jgzf_token:
            return self.jgzf_sso_login()
        try:
            r = self.jgzf_call("/law/api/login/v1/getLoginInfo", data={})
            if r.json().get("code") == 1:
                return {"success": True}
        except Exception:
            pass
        return self.jgzf_sso_login()

    def status(self) -> dict:
        return {
            "logged_in": self.logged_in,
            "username": self.username or "",
            "session": self.s.cookies.get("JSESSIONID", "") if self.logged_in else "",
            "jgzf_token": bool(self.jgzf_token),
            "jgzf_user": (self.jgzf_user or {}).get("userName", "") if self.jgzf_user else "",
            "base": self.base,
            "jgzf_base": JGZF_BASE,
        }


# ─── 全局会话 ────────────────────────────────────────────────

def _get_client() -> PermitClient:
    global _client
    if _client is None:
        _client = PermitClient()
    return _client


def _not_configured() -> str | None:
    """未配置内网地址/凭证时的统一错误说明。"""
    missing = []
    if not BASE:
        missing.append("PERMIT_BASE")
    if not JGZF_BASE:
        missing.append("PERMIT_JGZF_BASE")
    if not os.environ.get("PERMIT_USERNAME"):
        missing.append("PERMIT_USERNAME")
    if not os.environ.get("PERMIT_PASSWORD"):
        missing.append("PERMIT_PASSWORD")
    if missing:
        return (f"排污许可平台未配置环境变量: {', '.join(missing)}。"
                "平台为内网系统，需本机直连内网并配置后使用（也可先调用 permit_login 传入账号密码，"
                "但 PERMIT_BASE/PERMIT_JGZF_BASE 必须先配置）")
    return None


def _ensure_logged_in(username: str = "", password: str = "") -> PermitClient:
    if not BASE:
        raise RuntimeError(_not_configured() or "PERMIT_BASE 未配置")
    c = _get_client()
    if username and password:
        result = c.login(username, password)
        if not result.get("success"):
            raise RuntimeError(f"登录失败: {result.get('error', '未知错误')}")
        return c
    env_u = os.environ.get("PERMIT_USERNAME", "")
    env_p = os.environ.get("PERMIT_PASSWORD", "")
    if env_u and env_p:
        c.username, c.password = env_u, env_p
    if not c.ensure_logged_in():
        raise RuntimeError(_not_configured() or "尚未登录或会话已失效，请先调用 permit_login 登录")
    return c


def _ensure_jgzf() -> PermitClient:
    if not JGZF_BASE:
        raise RuntimeError(_not_configured() or "PERMIT_JGZF_BASE 未配置")
    c = _get_client()
    if not c.logged_in and not c.ensure_logged_in():
        raise RuntimeError(_not_configured() or "主系统未登录，请先 permit_login")
    result = c.jgzf_ensure()
    if not result.get("success"):
        raise RuntimeError(f"实施监管系统 SSO 失败: {result.get('error')}")
    return c


# ─── govmcp 工具定义 ─────────────────────────────────────────

CATEGORY = "执法平台-排污许可管理"
TAGS = ["执法平台", "排污许可", "许可证核发", "实施与监管", "只读查询"]


@govmcp_tool(
    name="permit_login",
    description="登录排污许可管理平台。输入账号密码即可登录(自动破解4位验证码+RSA加密)。登录成功后自动打通实施与监管系统SSO。账号密码也可通过环境变量 PERMIT_USERNAME/PERMIT_PASSWORD 提供",
    category=CATEGORY,
    tags=TAGS + ["auth"],
)
def permit_login(username: str = "", password: str = "") -> dict:
    """登录主系统 + 打通实施监管系统 SSO。"""
    if not BASE:
        return {"success": False, "error": "PERMIT_BASE 未配置（内网地址经环境变量注入）"}
    c = _get_client()
    u = username or os.environ.get("PERMIT_USERNAME", "")
    p = password or os.environ.get("PERMIT_PASSWORD", "")
    if not u or not p:
        return {"success": False,
                "error": "请提供账号密码：permit_login(username, password) 或设置环境变量"}
    with _lock:
        result = c.login(u, p)
    if result.get("success"):
        sso = c.jgzf_sso_login()
        result["jgzf_sso"] = sso.get("success", False)
        if not sso.get("success"):
            result["jgzf_sso_error"] = sso.get("error", "")
        result["tip"] = ("登录成功。可用工具：permit_menu / permit_license_list / "
                         "permit_enterprise_list / permit_jgzf_license_execution 等")
    return result


@govmcp_tool(
    name="permit_status",
    description="查询当前登录状态(主系统 + 实施监管系统)",
    category=CATEGORY,
    tags=TAGS,
)
def permit_status() -> dict:
    """当前登录状态。"""
    return _get_client().status()


@govmcp_tool(
    name="permit_menu",
    description="获取主系统完整菜单树(业务审核/许可证档案/资料附件等模块及其子菜单URL)。systemid可指定单模块(ywsh/xkzan/pwxkxgzl/xinxiopen,空=全部)",
    category=CATEGORY,
    tags=TAGS,
)
def permit_menu(systemid: str = "") -> dict:
    """主系统菜单树。"""
    try:
        c = _ensure_logged_in()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    systems = {
        "ywsh": "业务审核", "xkzan": "许可证档案",
        "pwxkxgzl": "资料附件", "xinxiopen": "信息维护",
    }
    if systemid:
        systems = {systemid: systems.get(systemid, systemid)}
    result = {}
    try:
        for sysid, sysname in systems.items():
            r = c.s.get(c.base + f"/AjaxAction.do?actionType=outlook&systemid={sysid}"
                        f"&timestamp={int(time.time()*1000)}", timeout=20)
            result[sysname] = r.text
        return {"success": True, "menus": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_license_list",
    description="查询排污许可证库列表(服务端渲染分页)。nameuserd=单位名称,xkznum=许可证编号,treadcode=行业代码,page_no=页码",
    category=CATEGORY,
    tags=TAGS,
)
def permit_license_list(nameuserd: str = "", xkznum: str = "", treadcode: str = "",
                        page_no: int = 1) -> dict:
    """排污许可证库列表。"""
    try:
        c = _ensure_logged_in()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    data = {"nameuserd": nameuserd, "xkznum": xkznum,
            "treadcode": treadcode, "pageNo": str(page_no)}
    try:
        r = c.s.post(c.base + "/syssp/xkzda/xkzda!list.action", data=data, timeout=30)
        title_m = re.search(r"<title>([^<]*)</title>", r.text)
        return {"success": True, "http": r.status_code,
                "title": title_m.group(1) if title_m else "",
                "page_len": len(r.text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_enterprise_list",
    description="查询企业库列表。nameuserd=单位名称,xkznum=许可证编号,treadcode=行业代码,page_no=页码",
    category=CATEGORY,
    tags=TAGS,
)
def permit_enterprise_list(nameuserd: str = "", xkznum: str = "", treadcode: str = "",
                           page_no: int = 1) -> dict:
    """企业库列表。"""
    try:
        c = _ensure_logged_in()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    data = {"nameuserd": nameuserd, "xkznum": xkznum,
            "treadcode": treadcode, "pageNo": str(page_no)}
    try:
        r = c.s.post(c.base + "/syssp/xkzda/xkzda!listEnter.action",
                     data=data, timeout=30)
        title_m = re.search(r"<title>([^<]*)</title>", r.text)
        return {"success": True, "http": r.status_code,
                "title": title_m.group(1) if title_m else "",
                "page_len": len(r.text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_jgzf_menu",
    description="获取实施与监管系统菜单树(业务办理/实施档案库/资料附件)。user_id指定用户ID(空=当前登录用户)",
    category=CATEGORY,
    tags=TAGS,
)
def permit_jgzf_menu(user_id: str = "") -> dict:
    """实施与监管系统菜单树。"""
    try:
        c = _ensure_jgzf()
        uid = user_id or (c.jgzf_user or {}).get("userId", "")
        r = c.jgzf_call(f"/law/api/userInfo/v1/userMenu?id={uid}", data={})
        return {"success": True, "menu": r.json()}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_jgzf_license_execution",
    description="查询许可执行情况列表(年报/季报/月报提交情况)。enter_name=单位名称,xkznum=许可证编号,report_type=year/quarter/month,report_year=年份",
    category=CATEGORY,
    tags=TAGS,
)
def permit_jgzf_license_execution(enter_name: str = "", xkznum: str = "",
                                  report_type: str = "year", report_year: str = "",
                                  page: int = 1, page_size: int = 20) -> dict:
    """许可执行情况（年报/季报/月报提交情况）。"""
    try:
        c = _ensure_jgzf()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    if not report_year:
        report_year = str(datetime.datetime.now().year - 1)
    params = {
        "industryName": "", "industryCode": [], "xkznum": xkznum,
        "enterName": enter_name, "reportType": report_type, "reportTime": "",
        "fzETime": "", "fzSTime": "", "submitStatus": "", "enterStatus": "",
        "urgeFlag": "", "searchRange": "", "currPage": page, "pageSize": page_size,
        "provinceCode": (c.jgzf_user or {}).get("provinceCode", ""),
        "cityCode": (c.jgzf_user or {}).get("cityCode", ""),
        "countyCode": (c.jgzf_user or {}).get("countyCode", "") or "",
        "reportMonth": "", "reportYear": report_year, "reportQuarter": "",
        "handleFlag": "", "overSubmitFlag": "", "submitSTime": "",
        "submitETime": "", "stopFlag": "", "businessType": "ENV", "promptType": "",
    }
    try:
        r = c.jgzf_call("/law/api/licenseExecution/v1/list", data=params)
        j = r.json()
        if j.get("code") == 1:
            d = j.get("data") or {}
            return {"success": True, "total": d.get("totalCount"), "page": page,
                    "count": len(d.get("list", [])), "rows": d.get("list", [])}
        return {"success": False, "error": j.get("msg")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_jgzf_stop_production",
    description="查询停产管理列表。enter_name=单位名称,page=页码",
    category=CATEGORY,
    tags=TAGS,
)
def permit_jgzf_stop_production(enter_name: str = "", page: int = 1,
                                page_size: int = 20) -> dict:
    """停产管理列表。"""
    try:
        c = _ensure_jgzf()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    params = {"enterName": enter_name, "currPage": page, "pageSize": page_size}
    try:
        r = c.jgzf_call("/law/api/stopProduction/v1/list", data=params)
        j = r.json()
        if j.get("code") == 1:
            d = j.get("data") or {}
            return {"success": True, "total": d.get("totalCount"),
                    "rows": d.get("list", d.get("rows", []))}
        return {"success": False, "error": j.get("msg")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_jgzf_enterprise_archive",
    description="查询企业实施档案。enter_name=企业名称,page=页码",
    category=CATEGORY,
    tags=TAGS,
)
def permit_jgzf_enterprise_archive(enter_name: str = "", page: int = 1,
                                   page_size: int = 20) -> dict:
    """企业实施档案。"""
    try:
        c = _ensure_jgzf()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    params = {"enterName": enter_name, "currPage": page, "pageSize": page_size}
    try:
        r = c.jgzf_call("/law/api/archives/v1/reportCompanyList", data=params)
        j = r.json()
        if j.get("code") == 1:
            d = j.get("data") or {}
            return {"success": True, "total": d.get("totalCount"),
                    "rows": d.get("list", d.get("rows", []))}
        return {"success": False, "error": j.get("msg")}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_area_list",
    description="查询行政区划列表。area_level=province/city/county",
    category=CATEGORY,
    tags=TAGS,
)
def permit_area_list(area_level: str = "province") -> dict:
    """行政区划维度列表。"""
    try:
        c = _ensure_jgzf()
        r = c.jgzf_call("/law/api/dimInfo/v1/areaList", data=None,
                        method="GET", params={"areaLevel": area_level})
        j = r.json()
        if j.get("code") == 1:
            return {"success": True, "count": len(j.get("data", [])),
                    "rows": j.get("data", [])}
        return {"success": False, "error": j.get("msg")}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@govmcp_tool(
    name="permit_industry_list",
    description="查询行业维度列表(行业分类编码)。keyword行业关键词过滤(空=全部)",
    category=CATEGORY,
    tags=TAGS,
)
def permit_industry_list(keyword: str = "") -> dict:
    """行业维度列表。"""
    try:
        c = _ensure_jgzf()
        r = c.jgzf_call("/law/api/dimInfo/v1/industryDimList", data={})
        j = r.json()
        if j.get("code") == 1:
            rows = j.get("data", [])
            if keyword:
                rows = [row for row in rows
                        if keyword in json.dumps(row, ensure_ascii=False)]
            return {"success": True, "count": len(rows), "rows": rows}
        return {"success": False, "error": j.get("msg")}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── 注册入口 ────────────────────────────────────────────────

_TOOLS: list[Any] = [
    permit_login, permit_status, permit_menu, permit_license_list,
    permit_enterprise_list, permit_jgzf_menu, permit_jgzf_license_execution,
    permit_jgzf_stop_production, permit_jgzf_enterprise_archive,
    permit_area_list, permit_industry_list,
]


def register_permit(reg: ToolRegistry) -> ToolRegistry:
    """注册排污许可管理平台 govmcp 工具。"""
    reg.register_batch(_TOOLS)
    return reg


# ─── 聊天通道暴露（只读子集，L1 权限闸门）─────────────────────
# 登录/status 不进聊天表（凭证不进聊天参数）。


def _p(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


CHAT_TOOLS: dict[str, dict] = {
    "permit_menu": {
        "description": "排污许可管理平台-主系统完整菜单树(业务审核/许可证档案/资料附件等模块)。",
        "parameters": _p(
            {"systemid": {"type": "string", "description": "可选，指定单模块(ywsh业务审核/xkzan许可证档案/pwxkxgzl资料附件/xinxiopen信息维护,空=全部)"}},
            [],
        ),
        "handler": permit_menu,
    },
    "permit_license_list": {
        "description": "排污许可管理平台-排污许可证库列表查询。nameuserd单位名称模糊查询，xkznum许可证编号，treadcode行业代码。",
        "parameters": _p(
            {
                "nameuserd": {"type": "string", "description": "单位名称模糊查询"},
                "xkznum": {"type": "string", "description": "许可证编号"},
                "treadcode": {"type": "string", "description": "行业代码"},
                "page_no": {"type": "integer", "description": "页码(默认1)"},
            },
            [],
        ),
        "handler": permit_license_list,
    },
    "permit_enterprise_list": {
        "description": "排污许可管理平台-企业库列表查询(持证企业基本信息)。",
        "parameters": _p(
            {
                "nameuserd": {"type": "string", "description": "单位名称模糊查询"},
                "xkznum": {"type": "string", "description": "许可证编号"},
                "treadcode": {"type": "string", "description": "行业代码"},
                "page_no": {"type": "integer", "description": "页码(默认1)"},
            },
            [],
        ),
        "handler": permit_enterprise_list,
    },
    "permit_jgzf_menu": {
        "description": "排污许可管理平台-实施与监管系统菜单树(业务办理/实施档案库/资料附件)。",
        "parameters": _p(
            {"user_id": {"type": "string", "description": "可选，指定用户ID(空=当前登录用户)"}},
            [],
        ),
        "handler": permit_jgzf_menu,
    },
    "permit_jgzf_license_execution": {
        "description": "排污许可管理平台-许可执行情况列表(年报/季报/月报提交情况)。report_type:year/quarter/month。",
        "parameters": _p(
            {
                "enter_name": {"type": "string", "description": "单位名称"},
                "xkznum": {"type": "string", "description": "许可证编号"},
                "report_type": {"type": "string", "description": "年报year/季报quarter/月报month"},
                "report_year": {"type": "string", "description": "报告年度(如2026)"},
                "page": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
            },
            [],
        ),
        "handler": permit_jgzf_license_execution,
    },
    "permit_jgzf_stop_production": {
        "description": "排污许可管理平台-停产管理列表查询。",
        "parameters": _p(
            {
                "enter_name": {"type": "string", "description": "单位名称"},
                "page": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
            },
            [],
        ),
        "handler": permit_jgzf_stop_production,
    },
    "permit_jgzf_enterprise_archive": {
        "description": "排污许可管理平台-企业实施档案查询。",
        "parameters": _p(
            {
                "enter_name": {"type": "string", "description": "企业名称"},
                "page": {"type": "integer", "description": "页码(默认1)"},
                "page_size": {"type": "integer", "description": "每页条数(默认20)"},
            },
            [],
        ),
        "handler": permit_jgzf_enterprise_archive,
    },
    "permit_area_list": {
        "description": "排污许可管理平台-行政区划维度列表(province/city/county)。",
        "parameters": _p(
            {"area_level": {"type": "string", "description": "province/city/county"}},
            [],
        ),
        "handler": permit_area_list,
    },
    "permit_industry_list": {
        "description": "排污许可管理平台-行业维度列表(行业分类编码)。",
        "parameters": _p(
            {"keyword": {"type": "string", "description": "可选，行业关键词过滤(空=全部)"}},
            [],
        ),
        "handler": permit_industry_list,
    },
}

# 聊天工具表顺序（wiring_manifest 同步）
CHAT_NAMES: list[str] = list(CHAT_TOOLS.keys())
