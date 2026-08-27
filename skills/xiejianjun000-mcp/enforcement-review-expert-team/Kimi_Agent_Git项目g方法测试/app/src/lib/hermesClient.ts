// hermesClient.ts — EcoAegis 前端 ↔ Hermes agent 基座的连接层
// ================================================================
// 架构链路：
//   React 前端 ──HTTP(fetch)──▶ eco-bridge 薄桥接(server.py)
//                                 └──▶ Hermes agent 核心
//                                       (agent/ + hermes_cli/ + 国内三渠道插件)
//
// Hermes agent 是 AI 引擎：它本质是「通道消息驱动」的运行时（飞书/企微/钉钉
// webhook 或 websocket），自身没有给前端直接调的 REST 接口。eco-bridge 就是
// 它的 HTTP 门面——只做请求转发与协议适配，不实现任何 AI 逻辑。
//
// 本文件同时内置 MOCK 模式（VITE_USE_MOCK=1）：不依赖后端即可跑通前端 UI。
// 部署联调时把该变量置 0，前端即直连真实桥接、由 Hermes agent 提供智能能力。
//
// 连接契约详见项目根 eco-bridge/README.md。

import { matchPlatform, type WhitelistPlatform } from '../data/whitelist';

const API_BASE: string = import.meta.env.VITE_BRIDGE_BASE ?? 'http://localhost:8787';
// 默认 MOCK（不依赖后端即可跑通 UI）；联调时把 VITE_USE_MOCK 设为 '0' 走真实 Hermes。
const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== '0';

/** 验证码载荷：AI 已识别态带 value；人工输入态仅 mode=manual */
export interface CaptchaPayload {
  mode: 'ai' | 'manual';
  value?: string; // AI 已识别出的验证码文本
  imageB64?: string; // 验证码图片(base64)，人工模式下前端展示
}

/** 登录接管结果 */
export interface LoginResult {
  ok: boolean;
  status: 'ai_managed' | 'error';
  message?: string;
}

/** 单次接入会话令牌：串起 匹配→验证码→登录 三步，后端据此关联状态 */
export function newSessionToken(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

/**
 * 步骤1：粘贴地址 → AI 识别匹配白名单平台。
 * 真实链路：eco-bridge 把地址交给 Hermes agent 做语义识别 + 字段推断。
 */
export async function matchPlatformRemote(address: string): Promise<WhitelistPlatform | null> {
  if (USE_MOCK) {
    await delay(650);
    return matchPlatform(address);
  }
  const data = await postJSON<{ matched: boolean; platform?: WhitelistPlatform | null; reason?: string; externalId?: string; note?: string }>(
    '/api/platform/match',
    { address },
  );
  if (data.matched) {
    if (data.platform) return data.platform;
    // AI 识别到了但白名单没有 — 返回 null 让调用方处理
    return null;
  }
  return null;
}

/**
 * 步骤2：取该平台的验证码。
 * 真实链路：Hermes agent 驱动浏览器抓取验证码图，AI 识别成功则回填 value，
 * 复杂/识别失败则回落人工输入（mode=manual，前端展示 imageB64）。
 */
export async function fetchCaptchaRemote(
  platformId: string,
  sessionToken: string,
): Promise<CaptchaPayload> {
  if (USE_MOCK) {
    await delay(500);
    // 演示：约 70% 平台可被 AI 自动识别
    const auto = Math.random() > 0.3;
    if (auto) {
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      let s = '';
      for (let i = 0; i < 4; i++) s += chars[Math.floor(Math.random() * chars.length)];
      return { mode: 'ai', value: s };
    }
    return { mode: 'manual' };
  }
  return postJSON<CaptchaPayload>('/api/platform/captcha', { platformId, sessionToken });
}

/**
 * 步骤3：提交凭据并完成登录接管。
 * 真实链路：Hermes agent 代填表单并提交，成功后进入 ai_managed 稳态。
 * 凭据加密保存由 Hermes agent 负责（不落明文）。
 */
export async function submitLoginRemote(args: {
  platformId: string;
  username: string;
  password: string;
  captcha?: string;
  remember: boolean;
  sessionToken: string;
}): Promise<LoginResult> {
  if (USE_MOCK) {
    await delay(800);
    return { ok: true, status: 'ai_managed', message: '已接管，后续由 AI 日常代管' };
  }
  return postJSON<LoginResult>('/api/platform/login', args);
}

/**
 * 新增平台到白名单（持久化）。
 * name / purpose 必填；keywords 可选，id 可选（后端自动生成）。
 */
export async function addPlatformRemote(payload: {
  name: string;
  purpose: string;
  keywords?: string[];
  fields?: { username: string; password: string; captcha: string };
  captchaAuto?: boolean;
  id?: string;
}): Promise<{ ok: boolean; platform: WhitelistPlatform }> {
  if (USE_MOCK) {
    await delay(400);
    return {
      ok: true,
      platform: {
        id: payload.id || `p-${Date.now().toString(36)}`,
        name: payload.name,
        purpose: payload.purpose,
        keywords: payload.keywords || [payload.name],
        fields: payload.fields || { username: '账号', password: '密码', captcha: '图形验证码' },
        captchaAuto: payload.captchaAuto ?? false,
      },
    };
  }
  return postJSON<{ ok: boolean; platform: WhitelistPlatform }>('/api/platform/add', payload);
}

/**
 * 从白名单中删除平台。
 */
export async function deletePlatformRemote(platformId: string): Promise<{ ok: boolean }> {
  if (USE_MOCK) {
    await delay(300);
    return { ok: true };
  }
  return postJSON<{ ok: boolean }>('/api/platform/delete', { id: platformId });
}

// ═══════════════════════════════════════════════════════════════════
// 执法办案 Skill 客户端
// ═══════════════════════════════════════════════════════════════════

/** 案卷标准化数据 */
export interface EnfCase {
  platformId: string;
  party: string;
  companyName: string;
  caseNo: string;
  stage: string;
  enforcementBody: string;
  taskStatus: string;
  handler: string;
  penaltyAmount: number;
  createdAt: string;
  filingDate: string;
  caseType: string;
  recordType: string;
  city: string;
  district: string;
  orgId: string;
  year: string;
  auditStatus: string;
  decisionNo: string;
  summary: string;
  processId: string;
  taskNo: string;
}

/** 文书 */
export interface EnfDocument {
  fileId: string;
  name: string;
  uploadTime: string;
  updateTime: string;
}

/** 案卷列表响应 */
export interface EnfCasesResponse {
  ok: boolean;
  total: number;
  page: number;
  rows: number;
  cases: EnfCase[];
}

/** 文书列表响应 */
export interface EnfDocumentsResponse {
  ok: boolean;
  total: number;
  page: number;
  documents: EnfDocument[];
}

/** 平台扫描 Manifest */
export interface EnfModuleInfo {
  name: string;
  type: string;
  viewId?: string;
  endpoint?: string;
  totalRecords?: number;
  fields?: { name: string; mapsTo: string }[];
  error?: string;
}

export interface EnfManifest {
  platformName: string;
  platformType: string;
  baseUrl: string;
  scannedAt: string;
  modules: EnfModuleInfo[];
  totalCases: number;
  totalDocuments: number;
  totalEnterprises: number;
}

/** 巡检报告 */
export interface EnfInspectReport {
  platformId: string;
  date: string;
  summary: string;
  newCases: number;
  statusChanges: number;
  newDocuments: number;
  alerts: { type: string; caseNo: string; party: string; message: string }[];
  casesActive: number;
  casesClosed: number;
}

/**
 * 连接执法办案平台。
 * @param mode - "chrome" | "session" | "login"
 */
export async function enforceConnect(params: {
  mode?: 'chrome' | 'session' | 'login';
  chromePort?: number;
  jsessionid?: string;
  username?: string;
  password?: string;
}): Promise<{ ok: boolean; sessionToken?: string; message?: string; error?: string }> {
  if (USE_MOCK) {
    await delay(800);
    return { ok: true, sessionToken: 'mock-token', message: 'Mock 模式：已模拟连接' };
  }
  return postJSON('/api/enforcement/connect', params);
}

/**
 * 扫描平台模块，生成 Manifest。
 */
export async function enforceScan(
  sessionToken: string,
): Promise<{ ok: boolean; manifest?: EnfManifest; error?: string }> {
  if (USE_MOCK) {
    await delay(600);
    return {
      ok: true,
      manifest: {
        platformName: '湖南生态环境智慧执法办案系统',
        platformType: 'boanda-queryservice',
        baseUrl: 'https://pwq.sthjt.hunan.gov.cn:8507/zfyth',
        scannedAt: new Date().toISOString(),
        modules: [
          { name: '案卷台账', type: 'case_ledger', totalRecords: 69 },
          { name: '文书管理', type: 'document_repo', totalRecords: 74 },
          { name: '一源一档', type: 'enterprise_registry', totalRecords: 496 },
        ],
        totalCases: 69,
        totalDocuments: 74,
        totalEnterprises: 496,
      },
    };
  }
  return postJSON('/api/enforcement/scan', { sessionToken });
}

/**
 * 全量同步数据。
 */
export async function enforceSync(params: {
  sessionToken: string;
  outputDir?: string;
}): Promise<{ ok: boolean; outputDir?: string; modules?: Record<string, unknown>; error?: string }> {
  if (USE_MOCK) {
    await delay(1500);
    return { ok: true, outputDir: '/tmp/eco-aegis-sync', modules: {} };
  }
  return postJSON('/api/enforcement/sync', params);
}

/**
 * 获取案卷列表（分页）。
 */
export async function enforceGetCases(params: {
  token: string;
  page?: number;
  rows?: number;
}): Promise<EnfCasesResponse> {
  if (USE_MOCK) {
    await delay(400);
    return {
      ok: true,
      total: 69,
      page: params.page || 1,
      rows: 0,
      cases: [],
    };
  }
  const qs = `token=${params.token}&page=${params.page || 1}&rows=${params.rows || 20}`;
  const res = await fetch(`${API_BASE}/api/enforcement/cases?${qs}`);
  return res.json();
}

/**
 * 获取案卷详情。
 */
export async function enforceGetCaseDetail(params: {
  token: string;
  xh: string;
  lcdybh: string;
}): Promise<{ ok: boolean; xh: string; lcdybh: string; html?: string; url?: string }> {
  if (USE_MOCK) {
    await delay(300);
    return { ok: true, xh: params.xh, lcdybh: params.lcdybh, html: '' };
  }
  const qs = `token=${params.token}&xh=${params.xh}&lcdybh=${params.lcdybh}`;
  const res = await fetch(`${API_BASE}/api/enforcement/case-detail?${qs}`);
  return res.json();
}

/**
 * 获取文书列表。
 */
export async function enforceGetDocuments(params: {
  token: string;
  page?: number;
  rows?: number;
}): Promise<EnfDocumentsResponse> {
  if (USE_MOCK) {
    await delay(400);
    return { ok: true, total: 74, page: params.page || 1, documents: [] };
  }
  const qs = `token=${params.token}&page=${params.page || 1}&rows=${params.rows || 20}`;
  const res = await fetch(`${API_BASE}/api/enforcement/documents?${qs}`);
  return res.json();
}

/**
 * 下载单份文书。
 */
export async function enforceDownloadDocument(params: {
  token: string;
  fileId: string;
  saveDir?: string;
}): Promise<{ ok: boolean; fileId: string; path?: string; error?: string }> {
  if (USE_MOCK) {
    await delay(500);
    return { ok: true, fileId: params.fileId, path: `/tmp/mock.doc` };
  }
  const qs = `token=${params.token}&fileId=${params.fileId}&saveDir=${params.saveDir || '/tmp/eco-aegis-docs'}`;
  const res = await fetch(`${API_BASE}/api/enforcement/document-download?${qs}`);
  return res.json();
}

/**
 * 日常巡检。
 */
export async function enforceInspect(params: {
  sessionToken: string;
  lastSyncPath?: string;
}): Promise<{ ok: boolean; report?: EnfInspectReport; error?: string }> {
  if (USE_MOCK) {
    await delay(600);
    return {
      ok: true,
      report: {
        platformId: 'hn-zfyth',
        date: new Date().toISOString().slice(0, 10),
        summary: '巡检正常（Mock）',
        newCases: 0,
        statusChanges: 0,
        newDocuments: 0,
        alerts: [],
        casesActive: 69,
        casesClosed: 8,
      },
    };
  }
  return postJSON('/api/enforcement/inspect', params);
}

/**
 * 导出 Excel。
 */
export async function enforceExport(params: {
  sessionToken: string;
  module?: string;
  savePath?: string;
}): Promise<{ ok: boolean; file?: string; module?: string; error?: string }> {
  if (USE_MOCK) {
    await delay(800);
    return { ok: true, file: '/tmp/mock.xlsx', module: params.module || 'case_ledger' };
  }
  return postJSON('/api/enforcement/export', params);
}
