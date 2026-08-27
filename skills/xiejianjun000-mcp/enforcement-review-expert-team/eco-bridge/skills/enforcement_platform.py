"""
执法办案系统 Skill — 湖南生态环境智慧执法办案系统 标准化驱动
================================================================

SOP 六阶段标准化流程：
  DISCOVER → CONNECT → SCAN → SYNC → INSPECT → ACT

本模块是「平台无关」的标准化实现，通过 VIEW_IDS 映射适配具体平台。
换到其他 Boanda queryservice 框架平台只需修改 VIEW_IDS 和 BASE_URL。

依赖: requests, pycryptodome (AES), playwright (可选, 用于Chrome会话复用)
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import requests

# ═══════════════════════════════════════════════════════════════════
# 常量配置
# ═══════════════════════════════════════════════════════════════════

BASE_URL = "https://pwq.sthjt.hunan.gov.cn:8507/zfyth"
AES_KEY = os.environ.get(
    "ECOAEGIS_BOANDA_AES_KEY",
    "boandaxxjsgfyxgs",  # Boanda 框架默认 AES-128-ECB 密钥（公开框架常量，非用户凭证）
).encode()

# queryservice 框架 viewId 映射
VIEW_IDS: dict[str, str] = {
    "case_ledger":     "1754959717916057053184",   # 案卷台账 (69条)
    "case_filing":     "1673837582954019816448",   # 案件填报
    "document_repo":   "1734685867064022155264",   # 文书管理 (74条)
}

# API 端点（注意：不带前导 /，由 urljoin 与 BASE_URL 拼接）
API = {
    "login":      "login",
    "captcha":    "code",
    "query":      "platform/component/queryservice/analysis/analysiscontroller/query/{viewId}",
    "export":     "platform/component/excel/commonexcelcontroller/exportData",
    "download":   "platform/file/filemanagecontroller/downloadfilebyid/{fileId}",
    "case_detail":"general/punishment/ybcfinfo/{xh}/{lcdybh}/1",
    "enterprises": "zfsjk/wry/new/wrylist",
}

# 案卷字段映射：平台字段 → EcoAegis 标准字段
# 实际 API 返回的字段名（基于 Playwright 拦截的真实数据）
CASE_FIELD_MAP: dict[str, str] = {
    "XH":       "platformId",     # 内部ID
    "XZXDRMC":  "party",          # 行政相对人名称
    "MC":       "companyName",    # 企业名称
    "LAH":      "caseNo",         # 立案号
    "CFZT":     "enforcementBody", # 处罚主体（如"娄底市生态环境局"）
    "RWZT":     "taskStatus",     # 任务状态（如"未办结"）
    "XZQH":     "district",       # 行政区划
    "ORGID":    "orgId",          # 组织机构ID
    "CJSJ":     "createdAt",      # 创建时间
    "LASJ":     "filingDate",     # 立案时间
    "ND":       "year",           # 年度
    # 以下字段来自详情页，列表页可能不返回
    "DSRMC":    "party",          # 当事人名称（详情页）
    "BZJD":     "stage",          # 步骤阶段
    "AJDCY":    "handler",        # 案件调查人员
    "CFJE":     "penaltyAmount",  # 处罚金额
    "LARQ":     "filingDate",     # 立案日期（详情页）
    "WFAJLX":   "caseType",       # 违法案件类型
    "AJLX":     "recordType",     # 案卷类型
    "SSDS":     "city",           # 所属地市
    "SSQX":     "district",       # 所属区县（详情页）
    "ZJSFZT":   "auditStatus",    # 专家审核状态
    "JDSX":     "decisionNo",     # 决定书文号
    "AJJJ":     "summary",        # 案情简介及立案理由
    "LCDYBH":   "processId",      # 流程定义编号
    "RWBH":     "taskNo",         # 任务编号
}

# 步骤阶段枚举映射
STAGE_MAP: dict[str, str] = {
    "立案审批":   "filing",
    "调查终结":   "investigation",
    "处罚告知":   "notice",
    "处罚决定":   "decision",
    "执行结案":   "enforcement",
    "撤销立案":   "cancelled",
    "查封扣押决定阶段": "seizure",
    "决定阶段（解除查封扣押）": "release_seizure",
}

# 审核状态映射
AUDIT_STATUS_MAP: dict[str, str] = {
    "待复核":  "pending_review",
    "待审核":  "pending_audit",
    "通过":    "approved",
    "不通过":  "rejected",
}


def _ensure_event_loop():
    """确保当前线程有事件循环（ThreadingHTTPServer 工作线程默认没有）。

    必须在 import playwright 之前调用，否则 sync_playwright 会因缺少事件循环而失败。
    """
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _get_sync_playwright():
    """获取 sync_playwright 函数。在调用前必须先 _ensure_event_loop()。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None

# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CaseItem:
    """标准化案卷"""
    platformId: str = ""
    party: str = ""           # 当事人名称（列表页用 XZXDRMC，详情页用 DSRMC）
    companyName: str = ""     # 企业名称（MC）
    caseNo: str = ""
    stage: str = ""
    enforcementBody: str = "" # 处罚主体（CFZT，如"娄底市生态环境局"）
    taskStatus: str = ""      # 任务状态（RWZT）
    handler: str = ""
    penaltyAmount: float = 0
    createdAt: str = ""
    filingDate: str = ""
    caseType: str = ""
    recordType: str = ""
    city: str = ""
    district: str = ""
    orgId: str = ""           # 组织机构ID
    year: str = ""            # 年度
    auditStatus: str = ""
    decisionNo: str = ""
    summary: str = ""
    processId: str = ""
    taskNo: str = ""
    raw: dict = field(default_factory=dict)

@dataclass
class DocumentItem:
    """标准化文书"""
    fileId: str = ""
    name: str = ""
    uploadTime: str = ""
    updateTime: str = ""

@dataclass
class EnterpriseItem:
    """标准化企业"""
    id: str = ""
    name: str = ""
    legalPerson: str = ""
    creditCode: str = ""
    permitNo: str = ""
    industry: str = ""
    address: str = ""
    status: str = ""          # 生产状态
    isKeySource: bool = False
    riskLevel: str = ""       # 监管级别
    pollutionTypes: list = field(default_factory=list)
    inspectionCount: int = 0
    penaltyCount: int = 0
    penaltyAmount: float = 0

@dataclass
class PlatformManifest:
    """平台扫描清单"""
    platformName: str = ""
    platformType: str = "boanda-queryservice"
    baseUrl: str = ""
    scannedAt: str = ""
    modules: list = field(default_factory=list)
    totalCases: int = 0
    totalDocuments: int = 0
    totalEnterprises: int = 0

@dataclass
class InspectionReport:
    """巡检报告"""
    platformId: str = ""
    date: str = ""
    summary: str = "巡检正常"
    newCases: int = 0
    statusChanges: int = 0
    newDocuments: int = 0
    alerts: list = field(default_factory=list)
    casesActive: int = 0
    casesClosed: int = 0

# ═══════════════════════════════════════════════════════════════════
# 核心驱动类
# ═══════════════════════════════════════════════════════════════════

class EnforcementPlatform:
    """湖南生态环境智慧执法办案系统 标准化驱动

    使用方式:
        # 方式1：复用 Chrome 已有登录会话
        p = EnforcementPlatform()
        p.connect_via_chrome()
        cases = p.get_cases()

        # 方式2：API 登录
        p = EnforcementPlatform()
        p.connect(os.environ["ENFORCEMENT_USERNAME"], os.environ["ENFORCEMENT_PASSWORD"])
        cases = p.get_cases()
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/") + "/"  # 保留尾部 / 确保 urljoin 正确拼接
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        self._connected = False
        self._manifest: Optional[PlatformManifest] = None

        # Playwright 浏览器实例（用于通过 UI 点击触发 Angular AJAX）
        # 注意：Playwright sync API 使用 greenlet，绑定创建线程，跨线程会崩溃。
        # 使用线程本地存储隔离每个线程的 Playwright 实例。
        self._jsessionid: Optional[str] = None
        self._pw_local = threading.local()  # 每个线程独立的 {pw, browser, context, page}

    # ── Phase 2: CONNECT ──────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    def connect_via_chrome(self, port: int = 9222) -> bool:
        """通过 Chrome 数据复用已有登录会话。

        优先级：
          1. CDP 连接（需 --remote-debugging-port）
          2. 直接读取 Chrome Cookie 数据库（最快，无需启动浏览器）
          3. Playwright Persistent Context（兜底）
        """
        # 方式 1：CDP 连接
        if self._try_cdp_connect(port):
            return True

        # 方式 2：读取 Chrome Cookie SQLite 数据库（最快）
        if self._try_cookie_db():
            return True

        # 方式 3：Playwright Persistent Context（较慢但稳定）
        return self._try_persistent_connect()

    def _try_cookie_db(self) -> bool:
        """直接从 Chrome Cookie SQLite 数据库读取 JSESSIONID

        Chrome 在 macOS 上把 Cookie 存储在:
          ~/Library/Application Support/Google/Chrome/Default/Cookies (SQLite)
        """
        import sqlite3
        import shutil
        import tempfile

        cookie_db = os.path.expanduser(
            "~/Library/Application Support/Google/Chrome/Default/Cookies"
        )
        if not os.path.isfile(cookie_db):
            return False

        tmp_db = None
        try:
            # Chrome 运行时 Cookies 被锁定，用 NamedTemporaryFile + chmod 0600 (CVE-07)
            fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="chrome_cookies_")
            os.close(fd)
            shutil.copy2(cookie_db, tmp_db)
            os.chmod(tmp_db, 0o600)

            conn = sqlite3.connect(tmp_db)
            cursor = conn.cursor()

            # 查询 JSESSIONID cookie
            cursor.execute(
                "SELECT value, host_key FROM cookies "
                "WHERE name = 'JSESSIONID' AND host_key LIKE '%sthjt.hunan.gov.cn%' "
                "ORDER BY last_access_utc DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                jsessionid, host = row
                domain = host.lstrip(".")
                self.session.cookies.set("JSESSIONID", jsessionid, domain=domain)
                self._connected = self._health_check()
                return self._connected
        except Exception:
            pass
        finally:
            if tmp_db and os.path.isfile(tmp_db):
                try:
                    os.unlink(tmp_db)
                except OSError:
                    pass

        return False

    def _try_cdp_connect(self, port: int = 9222) -> bool:
        """尝试通过 CDP 连接 Chrome"""
        _ensure_event_loop()
        sync_playwright = _get_sync_playwright()

        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
                for context in browser.contexts:
                    for page in context.pages:
                        if "sthjt.hunan.gov.cn" in page.url:
                            cookies = context.cookies()
                            for c in cookies:
                                if c["name"] == "JSESSIONID":
                                    self.session.cookies.set(
                                        "JSESSIONID", c["value"],
                                        domain="pwq.sthjt.hunan.gov.cn"
                                    )
                                    self._connected = True
                                    return True
                browser.close()
        except Exception:
            pass

        return False

    def _try_persistent_connect(self) -> bool:
        """通过 Playwright Persistent Context 复用 Chrome 用户目录"""
        _ensure_event_loop()
        sync_playwright = _get_sync_playwright()

        user_data_dir = os.path.expanduser(
            "~/Library/Application Support/Google/Chrome"
        )
        if not os.path.isdir(user_data_dir):
            return False

        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=True,
                    args=[
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-extensions",
                    ],
                )
                page = context.new_page()

                # 直接访问 queryservice API 验证会话
                view_id = VIEW_IDS["case_ledger"]
                api_url = f"{self.base_url}platform/component/queryservice/analysis/analysiscontroller/query/{view_id}"
                page.goto(api_url, timeout=15000)

                # 获取页面文本内容
                body_text = page.evaluate("() => document.body.innerText")

                # 如果返回 JSON（非登录页），则会话有效
                if body_text.strip().startswith("{") or body_text.strip().startswith("["):
                    cookies = context.cookies()
                    for c in cookies:
                        if c["name"] == "JSESSIONID":
                            self.session.cookies.set(
                                "JSESSIONID", c["value"],
                                domain=c.get("domain", "pwq.sthjt.hunan.gov.cn"),
                                path=c.get("path", "/"),
                            )
                            self._connected = True
                            context.close()
                            return True

                context.close()
        except Exception as e:
            pass

        return False

    def connect(self, username: str, password: str) -> dict:
        """完整登录流程：获取验证码 → 加密密码 → 提交登录"""
        # 1. 获取验证码图片
        captcha_url = urljoin(self.base_url, API["captcha"])
        resp = self.session.get(captcha_url, params={"_": int(time.time() * 1000)})
        captcha_img = resp.content

        # 2. OCR 识别算术验证码
        captcha_text = self._ocr_arithmetic(captcha_img)
        if not captcha_text:
            return {"ok": False, "error": "captcha_ocr_failed", "message": "验证码识别失败"}

        # 3. AES 加密密码
        encrypted_pwd = self._encrypt_password(password)

        # 4. 提交登录
        login_url = urljoin(self.base_url, API["login"])
        login_data = {
            "XTZH": username,
            "YHMM": encrypted_pwd,
            "validateCode": captcha_text,
        }
        resp = self.session.post(login_url, data=login_data, allow_redirects=True)

        # 5. 验证登录结果
        if "JSESSIONID" in {c.name for c in self.session.cookies}:
            self._connected = True
            return {"ok": True, "status": "connected"}
        else:
            return {"ok": False, "error": "login_failed", "message": "登录失败，请检查账号密码"}

    def connect_with_session(self, jsessionid: str) -> bool:
        """直接使用已知的 JSESSIONID 建立连接"""
        self._jsessionid = jsessionid
        # 同时设置 requests Session 的 Cookie（用于 download / case_detail 等非 query 端点）
        self.session.cookies.set(
            "JSESSIONID", jsessionid,
            domain="pwq.sthjt.hunan.gov.cn"
        )
        # 通过 Playwright 导航到 index 验证会话有效性
        self._connected = self._health_check()
        return self._connected

    def _ensure_angular_context(self) -> bool:
        """启动 Playwright 浏览器，导航到 index 页面建立 Angular 宿主上下文。

        Playwright sync API 使用 greenlet，绑定创建线程，跨线程访问会崩溃。
        使用 threading.local() 为每个线程保存独立的 Playwright 实例。
        """
        # 检查当前线程是否已有有效 page
        tls = getattr(self._pw_local, "data", None)
        if tls is not None:
            try:
                page = tls.get("page")
                if page is not None and not page.is_closed():
                    return True
            except Exception:
                pass

        # 创建新实例
        _ensure_event_loop()
        sync_playwright = _get_sync_playwright()
        if sync_playwright is None:
            return False

        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()

            if self._jsessionid:
                context.add_cookies([{
                    "name": "JSESSIONID", "value": self._jsessionid,
                    "domain": "pwq.sthjt.hunan.gov.cn", "path": "/",
                    "httpOnly": True, "secure": True,
                }])

            page = context.new_page()

            # 导航到 index 页面
            resp = page.goto(
                f"{self.base_url}index", timeout=30000,
                wait_until="networkidle"
            )
            if resp is None:
                return False

            # 检查是否成功
            title = page.title()
            if "执法办案" in title:
                self._pw_local.data = {
                    "pw": pw, "browser": browser,
                    "context": context, "page": page,
                }
                return True

            return False
        except Exception:
            return False

    @property
    def _page(self):
        """获取当前线程的 Playwright Page 对象"""
        tls = getattr(self._pw_local, "data", None)
        return tls["page"] if tls else None

    def _health_check(self) -> bool:
        """验证当前会话是否有效：启动 Playwright 导航到 index 页面"""
        return self._ensure_angular_context()

    def close(self):
        """清理当前线程的 Playwright 资源"""
        tls = getattr(self._pw_local, "data", None)
        if tls:
            try:
                if tls.get("context"):
                    tls["context"].close()
            except Exception:
                pass
            try:
                if tls.get("browser"):
                    tls["browser"].close()
            except Exception:
                pass
            try:
                if tls.get("pw"):
                    tls["pw"].stop()
            except Exception:
                pass
            self._pw_local.data = None

    # ── Phase 3: SCAN ─────────────────────────────────────────────

    def scan(self) -> PlatformManifest:
        """扫描平台所有模块，生成标准化 Manifest"""
        if not self._connected:
            raise RuntimeError("未连接平台，请先调用 connect() 或 connect_via_chrome()")

        modules = []

        # 扫描案卷台账
        try:
            cases = self._query_view("case_ledger", page=1, rows=1)
            modules.append({
                "name": "案卷台账",
                "type": "case_ledger",
                "viewId": VIEW_IDS["case_ledger"],
                "endpoint": API["query"].format(viewId=VIEW_IDS["case_ledger"]),
                "totalRecords": cases.get("total", 0),
                "fields": [
                    {"name": k, "mapsTo": CASE_FIELD_MAP.get(k, "")}
                    for k in CASE_FIELD_MAP
                ],
            })
        except Exception as e:
            modules.append({
                "name": "案卷台账",
                "type": "case_ledger",
                "error": str(e),
            })

        # 扫描文书管理
        try:
            docs = self._query_view("document_repo", page=1, rows=1)
            modules.append({
                "name": "文书管理",
                "type": "document_repo",
                "viewId": VIEW_IDS["document_repo"],
                "endpoint": API["query"].format(viewId=VIEW_IDS["document_repo"]),
                "totalRecords": docs.get("total", 0),
            })
        except Exception as e:
            modules.append({
                "name": "文书管理",
                "type": "document_repo",
                "error": str(e),
            })

        # 扫描一源一档（Vue SPA，非 queryservice 框架，标记为需特殊处理）
        modules.append({
            "name": "一源一档",
            "type": "enterprise_registry",
            "url": API["enterprises"],
            "framework": "vue-spa",
            "note": "非 queryservice 框架，需独立抓取逻辑",
        })

        self._manifest = PlatformManifest(
            platformName="湖南生态环境智慧执法办案系统",
            platformType="boanda-queryservice",
            baseUrl=self.base_url,
            scannedAt=datetime.now().isoformat(),
            modules=modules,
            totalCases=next((m.get("totalRecords", 0) for m in modules if m["type"] == "case_ledger"), 0),
            totalDocuments=next((m.get("totalRecords", 0) for m in modules if m["type"] == "document_repo"), 0),
            totalEnterprises=0,  # 需单独扫描
        )
        return self._manifest

    # ── Phase 4: SYNC ─────────────────────────────────────────────

    def get_cases(self, page: int = 1, rows: int = 100, **filters) -> dict:
        """获取案卷台账列表，返回标准化 CaseItem 列表"""
        raw = self._query_view("case_ledger", page=page, rows=rows, filters=filters)
        cases = []
        for row in raw.get("rows", []):
            c = self._normalize_case(row)
            cases.append(c)
        return {
            "total": raw.get("total", 0),
            "page": page,
            "rows": len(cases),
            "cases": [asdict(c) for c in cases],
        }

    def get_case_detail(self, xh: str, lcdybh: str) -> dict:
        """获取单个案卷详情（含文书树 + 表单数据）"""
        url = urljoin(self.base_url, API["case_detail"].format(xh=xh, lcdybh=lcdybh))
        resp = self.session.get(url)
        resp.raise_for_status()
        return {
            "xh": xh,
            "lcdybh": lcdybh,
            "html": resp.text[:5000],  # 截断，详情页是完整 HTML
            "url": url,
        }

    def get_documents(self, page: int = 1, rows: int = 100) -> dict:
        """获取文书管理列表"""
        raw = self._query_view("document_repo", page=page, rows=rows)
        docs = []
        for row in raw.get("rows", []):
            docs.append(DocumentItem(
                fileId=row.get("WJID", ""),
                name=row.get("WJMC", ""),
                uploadTime=row.get("SCSJ", row.get("CJSJ", "")),
                updateTime=row.get("XGSJ", row.get("SCSJ", "")),
            ))
        return {
            "total": raw.get("total", 0),
            "page": page,
            "documents": [asdict(d) for d in docs],
        }

    def download_document(self, file_id: str, save_dir: str) -> str:
        """下载单份文书文件"""
        url = urljoin(self.base_url, API["download"].format(fileId=file_id))
        resp = self.session.get(url, stream=True)
        resp.raise_for_status()

        # 从 Content-Disposition 获取文件名
        cd = resp.headers.get("Content-Disposition", "")
        filename = f"{file_id}.doc"
        match = re.search(r'filename[^;=\n]*=((["\']).*?\2|[^;\n]*)', cd)
        if match:
            filename = match.group(1).strip('"\'')
            # URL 解码
            from urllib.parse import unquote
            filename = unquote(filename)

        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return filepath

    def download_all_documents(self, save_dir: str) -> list[dict]:
        """批量下载全部文书"""
        docs_data = self.get_documents(page=1, rows=200)
        results = []
        for doc in docs_data["documents"]:
            try:
                path = self.download_document(doc["fileId"], save_dir)
                results.append({"name": doc["name"], "path": path, "ok": True})
            except Exception as e:
                results.append({"name": doc["name"], "error": str(e), "ok": False})
        return results

    def get_enterprises(self, page: int = 1, rows: int = 20) -> dict:
        """获取一源一档企业列表（Vue SPA，通过 API 抓取）"""
        # 一源一档是独立 Vue 应用，需要通过其内部 API 获取数据
        # 尝试已知的 API 端点
        api_base = urljoin(self.base_url, "/zfsjk")
        url = f"{api_base}/wry/new/wrylist"

        # 这个端点返回的是 Vue SPA 页面，实际数据通过内嵌 API 加载
        # 先获取页面，再尝试找到内嵌的 API 端点
        resp = self.session.get(url)
        resp.raise_for_status()

        # 尝试直接调污染源列表 API
        list_url = f"{api_base}/api/wry/list"  # 推测的 API 端点
        try:
            data_resp = self.session.post(
                list_url,
                json={"page": page, "size": rows},
                headers={"Content-Type": "application/json"},
            )
            if data_resp.status_code == 200:
                return data_resp.json()
        except Exception:
            pass

        return {
            "total": 496,
            "note": "一源一档为 Vue SPA，数据抓取需进一步对接其内部 API",
            "url": url,
        }

    def export_excel(self, module: str = "case_ledger", save_path: Optional[str] = None) -> str:
        """导出为 Excel 文件"""
        view_id = VIEW_IDS.get(module)
        if not view_id:
            raise ValueError(f"未知模块: {module}")

        url = urljoin(self.base_url, API["export"])
        resp = self.session.post(url, data={
            "viewId": view_id,
            "fileName": f"{module}_export",
        })
        resp.raise_for_status()

        if save_path is None:
            save_path = f"/tmp/{module}_export_{int(time.time())}.xlsx"

        with open(save_path, "wb") as f:
            f.write(resp.content)

        return save_path

    def sync_all(self, output_dir: str = "/tmp/eco-aegis-sync") -> dict:
        """全量同步：拉取案卷、文书、企业全部数据"""
        if not self._connected:
            raise RuntimeError("未连接平台")

        os.makedirs(output_dir, exist_ok=True)
        result = {"ok": True, "outputDir": output_dir, "modules": {}}

        # 案卷
        cases_data = self.get_cases(page=1, rows=500)
        cases_path = os.path.join(output_dir, "cases.json")
        with open(cases_path, "w", encoding="utf-8") as f:
            json.dump(cases_data, f, ensure_ascii=False, indent=2)
        result["modules"]["case_ledger"] = {
            "total": cases_data["total"],
            "path": cases_path,
        }

        # 文书
        docs_data = self.get_documents(page=1, rows=500)
        docs_path = os.path.join(output_dir, "documents.json")
        with open(docs_path, "w", encoding="utf-8") as f:
            json.dump(docs_data, f, ensure_ascii=False, indent=2)
        result["modules"]["document_repo"] = {
            "total": docs_data["total"],
            "path": docs_path,
        }

        # 批量下载文书文件
        dl_dir = os.path.join(output_dir, "document_files")
        dl_results = self.download_all_documents(dl_dir)
        result["modules"]["document_files"] = {
            "downloaded": sum(1 for r in dl_results if r["ok"]),
            "failed": sum(1 for r in dl_results if not r["ok"]),
            "dir": dl_dir,
        }

        # 企业（Vue SPA，有限支持）
        ent_data = self.get_enterprises()
        ent_path = os.path.join(output_dir, "enterprises.json")
        with open(ent_path, "w", encoding="utf-8") as f:
            json.dump(ent_data, f, ensure_ascii=False, indent=2)
        result["modules"]["enterprise_registry"] = {
            "path": ent_path,
            "note": "Vue SPA 模块，部分数据需进一步对接",
        }

        return result

    # ── Phase 5: INSPECT ──────────────────────────────────────────

    def inspect(self, last_sync_path: Optional[str] = None) -> InspectionReport:
        """日常巡检：对比上次同步结果，生成巡检报告"""
        if not self._connected:
            raise RuntimeError("未连接平台")

        cases = self.get_cases(page=1, rows=500)

        # 加载上次同步数据做对比
        last_cases = {}
        if last_sync_path and os.path.exists(last_sync_path):
            with open(last_sync_path, encoding="utf-8") as f:
                last_data = json.load(f)
                last_cases = {
                    c["platformId"]: c for c in last_data.get("cases", [])
                }

        # 统计分析
        new_cases = 0
        status_changes = 0
        alerts: list[dict] = []

        current_cases = cases.get("cases", [])
        for c in current_cases:
            pid = c.get("platformId", "")
            if pid not in last_cases:
                new_cases += 1
            elif last_cases[pid].get("stage") != c.get("stage"):
                status_changes += 1

            # 告警检测
            if c.get("auditStatus") == "rejected":
                alerts.append({
                    "type": "audit_rejected",
                    "caseNo": c.get("caseNo"),
                    "party": c.get("party"),
                    "message": f"案卷 {c.get('caseNo')} 审核被驳回",
                })

        # 结案统计
        closed = sum(
            1 for c in current_cases
            if c.get("stage") in ("enforcement", "cancelled")
        )

        return InspectionReport(
            platformId="hn-zfyth",
            date=datetime.now().strftime("%Y-%m-%d"),
            summary="巡检正常" if not alerts else f"发现 {len(alerts)} 项异常",
            newCases=new_cases,
            statusChanges=status_changes,
            newDocuments=0,  # 需单独比对
            alerts=alerts,
            casesActive=len(current_cases) - closed,
            casesClosed=closed,
        )

    # ── 内部辅助方法 ──────────────────────────────────────────────

    # 模块名 → 综合办案下子菜单文本映射
    _MODULE_MENU: dict[str, str] = {
        "case_ledger":   "案卷台账",
        "document_repo": "文书管理",
        "case_filing":   "案件填报",
    }

    def _query_view(self, module: str, page: int = 1, rows: int = 20,
                    filters: Optional[dict] = None) -> dict:
        """调用 queryservice 框架的 query API — 通过 Playwright UI 点击触发 Angular AJAX。

        Boanda queryservice 的 query API 必须由 Angular $http 服务发起，
        独立 HTTP 调用始终返回 error 90000。实际流程：
        1. 点击「综合办案 → 案卷台账/文书管理」菜单
        2. Angular 将 queryservice 加载到 iframe（ifr_center）中
        3. 在 iframe 中注入 XHR 拦截器
        4. 点击 iframe 内的「查询」按钮触发 Angular AJAX
        5. 从 iframe 的 JS 全局变量读取拦截到的数据
        """
        if not self._connected:
            raise RuntimeError("未连接平台")

        if not self._ensure_angular_context():
            raise RuntimeError("无法启动 Playwright 浏览器")

        menu_text = self._MODULE_MENU.get(module)
        if not menu_text:
            raise ValueError(f"未知模块: {module}（可用: {list(self._MODULE_MENU.keys())}）")

        # Step 1: 点击主菜单「综合办案」展开子菜单
        try:
            self._page.click('li:has-text("综合办案")', timeout=5000)
            self._page.wait_for_timeout(800)
        except Exception:
            pass  # 菜单可能已经展开

        # Step 2: 点击目标子菜单（如「案卷台账」「文书管理」）
        try:
            self._page.click(f"text={menu_text}", timeout=5000)
        except Exception as e:
            raise RuntimeError(f"菜单点击失败 [{module}]: {e}")

        # Step 3: 等待 ifr_center iframe 加载 queryservice 页面
        self._page.wait_for_timeout(4000)
        iframe = self._page.frame(name="ifr_center")
        if iframe is None:
            raise RuntimeError(f"未找到 queryservice iframe（ifr_center）")

        # Step 4: 在 iframe 中注入 XHR 拦截器
        iframe.evaluate("""() => {
            window.__eco_captured = [];
            if (!window.__eco_xhr_hooked) {
                window.__eco_xhr_hooked = true;
                const origOpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function() {
                    this.addEventListener('load', function() {
                        try {
                            if (this.responseURL && this.responseURL.indexOf('analysiscontroller/query') >= 0) {
                                const data = JSON.parse(this.responseText);
                                if (data && data.total != null) {
                                    window.__eco_captured.push(data);
                                }
                            }
                        } catch(e) {}
                    });
                    return origOpen.apply(this, arguments);
                };
            }
        }""")

        # Step 5: 点击 iframe 内的「查询」按钮触发 Angular AJAX
        try:
            iframe.click('button:has-text("查询")', timeout=5000)
        except Exception:
            try:
                iframe.click('text=查询', timeout=5000)
            except Exception as e:
                raise RuntimeError(f"iframe 内查询按钮点击失败: {e}")

        # Step 6: 等待查询完成，读取拦截数据
        self._page.wait_for_timeout(5000)
        captured = iframe.evaluate("() => window.__eco_captured")
        if not captured:
            return {"total": 0, "page": page, "rows": []}

        # 找到目标响应
        target = None
        for c in captured:
            items = c.get("list", [])
            if not items:
                continue
            first = items[0]
            if module == "case_ledger" and "LAH" in first:
                target = c
                break
            elif module == "document_repo" and "WJMC" in first:
                target = c
                break
            elif module == "case_filing":
                target = c
                break

        if target is None:
            target = max(captured, key=lambda x: x.get("total", 0))

        return {
            "total": target.get("total", 0),
            "page": target.get("pageNum", page),
            "rows": target.get("list", []),
            "pageSize": target.get("pageSize", rows),
            "pages": target.get("pages", 0),
        }

    def _normalize_case(self, row: dict) -> CaseItem:
        """将平台原始字段映射为标准化 CaseItem"""
        def get_field(eco_field: str) -> Any:
            # 多个平台字段可能映射到同一标准字段（如 XZXDRMC 和 DSRMC → party），
            # 返回第一个非空值
            val = ""
            for plat_key, eco_key in CASE_FIELD_MAP.items():
                if eco_key == eco_field:
                    v = row.get(plat_key, "")
                    if v and not val:
                        val = v
            return val

        stage_raw = get_field("stage")
        audit_raw = get_field("auditStatus")

        return CaseItem(
            platformId=get_field("platformId"),
            party=get_field("party"),
            companyName=get_field("companyName"),
            caseNo=get_field("caseNo"),
            stage=STAGE_MAP.get(stage_raw, stage_raw),
            enforcementBody=get_field("enforcementBody"),
            taskStatus=get_field("taskStatus"),
            handler=get_field("handler"),
            penaltyAmount=float(get_field("penaltyAmount") or 0),
            createdAt=get_field("createdAt"),
            filingDate=get_field("filingDate"),
            caseType=get_field("caseType"),
            recordType=get_field("recordType"),
            city=get_field("city"),
            district=get_field("district"),
            orgId=get_field("orgId"),
            year=get_field("year"),
            auditStatus=AUDIT_STATUS_MAP.get(audit_raw, audit_raw),
            decisionNo=get_field("decisionNo"),
            summary=get_field("summary"),
            processId=get_field("processId"),
            taskNo=get_field("taskNo"),
            raw=row,
        )

    def _encrypt_password(self, password: str) -> str:
        """Boanda 框架 AES-ECB 密码加密"""
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise RuntimeError("需要 pycryptodome: pip install pycryptodome")

        # 1. Base64 编码
        b64 = base64.b64encode(password.encode()).decode()
        # 2. PKCS7 填充到 16 字节
        pad_len = 16 - (len(b64) % 16)
        padded = b64 + chr(pad_len) * pad_len
        # 3. AES-ECB 加密
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        encrypted = cipher.encrypt(padded.encode())
        # 4. Base64 编码结果
        return base64.b64encode(encrypted).decode()

    def _ocr_arithmetic(self, image_bytes: bytes) -> Optional[str]:
        """OCR 识别算术验证码（如 5+29 → 34）"""
        # 尝试使用本地 OCR 引擎
        try:
            import ddddocr
            ocr = ddddocr.DdddOcr(show_ad=False)
            text = ocr.classification(image_bytes)
            # 计算算术表达式
            text = text.strip().replace(" ", "").replace("？", "?").replace("＝", "=")
            # 识别加减法: 5+29, 34-12 等
            match = re.match(r"(\d+)\s*([+\-])\s*(\d+)", text)
            if match:
                a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
                return str(a + b if op == "+" else a - b)
            # 纯数字验证码: 直接返回
            if text.isdigit():
                return text
        except ImportError:
            pass
        except Exception:
            pass

        return None

    def _connect_via_playwright_login(self, username: str, password: str) -> bool:
        """通过 Playwright 执行完整浏览器登录流程（备选方案）"""
        _ensure_event_loop()
        sync_playwright = _get_sync_playwright()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # 导航到登录页
            page.goto(f"{self.base_url}/index", timeout=30000)
            page.wait_for_load_state("networkidle")

            # 填写账号密码
            page.fill('input[placeholder*="账号"]', username)
            page.fill('input[placeholder*="密码"]', password)

            # 截取验证码
            captcha_elem = page.locator('img[src*="code"]')
            captcha_bytes = captcha_elem.screenshot()

            # OCR
            captcha_text = self._ocr_arithmetic(captcha_bytes)
            if captcha_text:
                page.fill('input[placeholder*="验证码"]', captcha_text)
                page.click('button:has-text("登录")')
                page.wait_for_timeout(3000)

                # 提取 cookie
                cookies = context.cookies()
                for c in cookies:
                    if c["name"] == "JSESSIONID":
                        self.session.cookies.set(
                            "JSESSIONID", c["value"],
                            domain="pwq.sthjt.hunan.gov.cn"
                        )
                        self._connected = True

            browser.close()
            return self._connected


# ═══════════════════════════════════════════════════════════════════
# 便捷工厂函数
# ═══════════════════════════════════════════════════════════════════

def create_platform(jsessionid: Optional[str] = None) -> EnforcementPlatform:
    """快速创建平台实例

    Args:
        jsessionid: 已有的 JSESSIONID。不提供则需调用 connect() 或 connect_via_chrome()
    """
    p = EnforcementPlatform()
    if jsessionid:
        p.connect_with_session(jsessionid)
    return p


def quick_sync(jsessionid: str, output_dir: str = "/tmp/eco-aegis-sync") -> dict:
    """一键全量同步"""
    p = create_platform(jsessionid)
    return p.sync_all(output_dir)


def quick_inspect(jsessionid: str) -> dict:
    """一键巡检"""
    p = create_platform(jsessionid)
    report = p.inspect()
    return asdict(report)
