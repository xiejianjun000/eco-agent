// wechat-bridge fetch MCP server — minimal, dependency-light, MIT-only.
// Spawned by @deepseek-ai/dsh-mcp-client over stdio.
//
// Safety design (per the WeChat-bridge safety rules):
//  - GET-only web fetch of http/https public URLs.
//  - SSRF guard: localhost, *.local / *.internal, private IPv4, loopback and
//    unique-local IPv6 literals are rejected.
//  - Hard caps: 20 s timeout, 3 MB download limit, maxChars <= 100000.
//  - No JavaScript execution, no link auto-following: the agent only calls
//    this tool when the user explicitly asks for web content.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024;
const TIMEOUT_MS = 20000;

function isPrivateHost(hostname) {
  const h = String(hostname).toLowerCase().replace(/^\[|\]$/g, "");
  if (h === "localhost" || h.endsWith(".localhost")) return true;
  if (h.endsWith(".local") || h.endsWith(".internal")) return true;
  if (h === "0.0.0.0") return true;

  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    const first = a * 256 + b;
    if (a === 10) return true;
    if (a === 127) return true;
    if (a === 169 && b === 254) return true;
    if (first === 172 * 256 + 16 || first >= 172 * 256 + 16 && first <= 172 * 256 + 31) return true;
    if (a === 192 && b === 168) return true;
    if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT 100.64/10
    if (a === 198 && (b === 18 || b === 19)) return true; // benchmarks
    if (a === 233) return true; // multicast docs range (233.252.0.0/24)
    return false;
  }

  // IPv6 loopback / unique-local / link-local prefixes, plus bare "::" forms.
  if (h.includes(":")) {
    const norm = h.toLowerCase();
    if (norm === "::" || norm === "::1") return true;
    if (norm.startsWith("fc") || norm.startsWith("fd")) return true;
    if (norm.startsWith("fe8") || norm.startsWith("fe9") || norm.startsWith("fea") || norm.startsWith("feb")) return true;
    if (norm.startsWith("ff")) return true; // multicast
  }
  return false;
}

function htmlToText(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|tr|h[1-6]|section|article|blockquote|pre)>/gi, "\n")
    .replace(/<li[^>]*>/gi, "\n- ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#0*39;|&apos;/g, "'")
    .replace(/[ \t]+/g, " ")
    .replace(/[ \t]*\n[ \t]*/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function readBody(res) {
  if (!res.body) return "";
  const reader = res.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_DOWNLOAD_BYTES) {
      await reader.cancel();
      throw new Error(`response exceeds ${MAX_DOWNLOAD_BYTES} byte download cap`);
    }
    chunks.push(value);
  }
  const buf = Buffer.concat(chunks);
  return new TextDecoder("utf-8", { fatal: false }).decode(buf);
}

/** 剥离终端 ANSI 转义序列（部分接口如 wttr.in 会返回带颜色的文本）。 */
function stripAnsi(text) {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1b\[[0-9;]*m/g, '')
}

async function fetchUrl(url, format, maxChars, startIndex) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("invalid URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("only http/https URLs are allowed");
  }
  if (isPrivateHost(parsed.hostname)) {
    throw new Error("private/internal network addresses are not allowed");
  }

  let res
  try {
    res = await fetch(parsed.href, {
      redirect: "follow",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { "user-agent": "wechat-bridge-fetch/1.0", accept: "text/html,application/json,text/plain;q=0.9,*/*;q=0.5" },
    })
  } catch (error) {
    // 把黑盒的 "fetch failed" 换成带原因的诊断信息（超时/连接重置/DNS 失败等）
    let reason = error?.cause?.code ?? ''
    if (error?.name === 'TimeoutError' || error?.name === 'AbortError') reason = 'timeout'
    if (error?.cause?.code === 'ENOTFOUND' || error?.cause?.code === 'EAI_AGAIN') reason = 'DNS lookup failed'
    const detail = reason ? ` (${reason})` : ''
    throw new Error(`network fetch failed${detail} for ${parsed.hostname}`)
  }
  const contentType = (res.headers.get("content-type") || "").toLowerCase();
  let text = await readBody(res); // read the body exactly once
  let outFormat = format;

  if (outFormat === "json" || (outFormat === "text" && contentType.includes("json"))) {
    try {
      JSON.parse(text);
      outFormat = "json";
    } catch {
      outFormat = "text";
    }
  }

  if (outFormat !== "html" && outFormat !== "json") {
    if (contentType.includes("html") || text.slice(0, 1000).match(/<\s*(html|body|div|p|meta)[\s>]/i)) {
      text = htmlToText(text)
    } else {
      text = stripAnsi(text)
    }
  }

  const cap = Math.min(Math.max(maxChars, 500), 100000);
  const sliced = text.slice(startIndex, startIndex + cap);
  const meta = `[status ${res.status}] url=${parsed.href} totalChars=${text.length} startIndex=${startIndex} returnedChars=${sliced.length}`;
  return meta + "\n\n" + sliced;
}

const server = new McpServer({ name: "fetch", version: "1.0.0" });

server.registerTool(
  "fetch",
  {
    description:
      "获取一个公开 http/https URL 的网页内容（微信桥接专用）。返回纯文本、HTML 或 JSON 之一，支持分页与长度截断。" +
      "安全限制：仅公网地址（拒绝内网/localhost/私网 IP）、20 秒超时、3 MB 下载上限、单次最多返回 100000 字符。" +
      "对长网页可先用小 maxChars 取开头，再增大 startIndex 分页继续读取。",
    inputSchema: {
      url: z.string().describe("要抓取的完整 URL（http 或 https）"),
      format: z.enum(["text", "html", "json"]).default("text").describe("text=去掉标签的正文（默认）, html=原始 HTML, json=按 JSON 处理"),
      maxChars: z.number().int().min(500).max(100000).default(20000).describe("本次最多返回的字符数"),
      startIndex: z.number().int().min(0).default(0).describe("从内容第几个字符开始返回（用于分页续读）"),
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  async ({ url, format, maxChars, startIndex }) => {
    const text = await fetchUrl(url, format, maxChars, startIndex);
    return { content: [{ type: "text", text }] };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
process.stderr.write("[wechat-bridge fetch MCP] ready\n");

// DSH closes stdin when the client shuts down → exit instead of hanging.
process.stdin.on("end", () => {
  setTimeout(() => process.exit(0), 300);
});
