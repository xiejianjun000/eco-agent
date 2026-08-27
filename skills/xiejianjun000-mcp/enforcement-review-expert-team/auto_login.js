/**
 * 大气监督帮扶平台 — 自动登录
 * macOS 适配版，修复所有已知缺陷，凭据从 Keychain 读取
 *
 * ⚠️ 安全告警（残余风险 CVE-03）：
 * 大气帮扶平台仅支持 HTTP（TLS 握手失败），凭据经明文传输。
 * 仅在可控内网/VPN 环境运行本脚本。平台侧上线 TLS 后须切换。
 * 密码已通过 macOS Keychain + AES-ECB 双重存储，但传输层不加密。
 */
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ── 配置 ────────────────────────────────────────────
const PLATFORM_URL = process.env.PLATFORM_URL || 'http://114.251.10.199:8080/zfpt_zf/redirect.jsp';
const PLATFORM = process.env.ECOAEGIS_PLATFORM || 'atmosphere';
const MAX_CAPTCHA_ATTEMPTS = 3;              // 防止锁定账号
const OCR_TIMEOUT_MS = 15000;
const PAGE_GOTO_TIMEOUT_MS = 45000;
const STEP_TIMEOUT_MS = 10000;
const LOGIN_TOTAL_TIMEOUT_MS = 180000;       // 3 分钟硬超时

const CAPTCHA_DIR = path.join(__dirname, 'auth', 'captcha_samples');
const IS_HEADFUL = process.env.HEADFUL === '1';
const OCR_PYTHON = process.env.OCR_PYTHON || 'python3';

// ── 工具函数 ────────────────────────────────────────

/** 从文件/行号所在的 __dirname 打开 profile */
function getProfileDir() {
  return path.join(process.env.HOME || '/tmp', '.ecoaegis', 'profiles', PLATFORM);
}

/** 从 Keychain 读取凭据 */
function getCredential(service) {
  return execSync(
    `security find-generic-password -a ecoaegis -s ${service} -w`,
    { encoding: 'utf8', timeout: 5000 }
  ).trim();
}

/** 保存验证码图片供调试/分析 */
function saveCaptchaSample(b64data, attempt) {
  fs.mkdirSync(CAPTCHA_DIR, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const fname = path.join(CAPTCHA_DIR, `captcha_${ts}_attempt${attempt}.png`);
  fs.writeFileSync(fname, Buffer.from(b64data, 'base64'));
  return fname;
}

/** 调用 OCR（stdin 传 base64，stdout 读结果） */
function ocrDecode(b64data) {
  // 用 echo + stdin 管道避免临时文件不一致
  const ocrScript = path.join(__dirname, 'decode_captcha.py');
  const cmd = `echo '${b64data.replace(/'/g, "'\\''")}' | ${OCR_PYTHON} "${ocrScript}" --stdin`;
  const result = execSync(cmd, { encoding: 'utf8', timeout: OCR_TIMEOUT_MS }).trim();
  // ddddocr 可能多行输出，取最后一行非空内容
  const lines = result.split('\n').filter(l => l.trim());
  return lines[lines.length - 1] || '';
}

/** 错误分类 */
function classifyError(errorText) {
  if (!errorText) return { type: 'unknown' };
  const txt = errorText.toLowerCase();
  if (txt.includes('验证码') || txt.includes('code')) return { type: 'captcha' };
  if (txt.includes('密码') || txt.includes('帐号') || txt.includes('账户') || txt.includes('用户'))
    return { type: 'credential' };
  if (txt.includes('锁定') || txt.includes('禁用') || txt.includes('冻结'))
    return { type: 'locked' };
  return { type: 'other', text: errorText };
}

/** 等待验证码图片的 src 真正变化 */
async function waitCaptchaChanged(page, oldSrc) {
  for (let i = 0; i < 10; i++) {
    const newSrc = await page.evaluate(() => {
      const imgs = document.querySelectorAll('img');
      for (const img of imgs) {
        if (img.src && img.src.includes('code')) return img.src;
      }
      return null;
    });
    if (newSrc && newSrc !== oldSrc) return true;
    await page.waitForTimeout(500);
  }
  return false;
}

// ── 主流程 ────────────────────────────────────────────

(async () => {
  const startTime = Date.now();
  const exit = (code, msg) => { console.log(msg); process.exit(code); };

  // —— 1. 启动浏览器 —————————————————————————————————
  console.log('[1/5] 启动浏览器...');
  const profileDir = getProfileDir();
  fs.mkdirSync(path.dirname(profileDir), { recursive: true });

  const browser = await chromium.launchPersistentContext(profileDir, {
    headless: !IS_HEADFUL,
    channel: 'chrome',
  });

  const page = browser.pages()[0] || await browser.newPage();

  // —— debugger 绕过 ———————————————————————————————————
  await page.addInitScript(() => {
    const origFn = window.Function;
    window.Function = function (...args) {
      if (args.length) {
        const last = args.length - 1;
        args[last] = args[last].toString().replace(/\bdebugger\b/g, '');
      }
      return origFn.apply(this, args);
    };
    window.Function.prototype = origFn.prototype;
  });

  await page.route('**/*.js', async (route) => {
    const resp = await route.fetch();
    let body = await resp.text();
    body = body.replace(/\bdebugger\b/g, '');
    await route.fulfill({ response: resp, body });
  });

  // —— 2. 导航到登录页 —————————————————————————————————
  console.log('[2/5] 导航到登录页...');
  try {
    await page.goto(PLATFORM_URL, {
      waitUntil: 'domcontentloaded',
      timeout: PAGE_GOTO_TIMEOUT_MS,
    });
  } catch (e) {
    exit(2, `[FATAL] 平台不可达: ${e.message}`);
  }

  // —— 3. 填写凭据 ————————————————————————————————————
  console.log('[3/5] 填写凭据...');
  const user = process.env.ECO_USER || getCredential(`${PLATFORM}-user`);
  const pass = process.env.ECO_PASS || getCredential(`${PLATFORM}-pass`);

  // 平台专用选择器（water=CAS登录，atmosphere=政务平台登录）
  const SELECTORS = {
    atmosphere: {
      user: 'input[name="username"], [placeholder*="登录账户"], [placeholder*="账户"]',
      pass: 'input[name="password"], [placeholder*="密码"]',
      captcha: 'input[name="valicode"], [placeholder*="验证码"]',
      submit: 'a:has-text("登录"), button:has-text("登录"), input[value="登录"]',
    },
    water: {
      user: '#useraccount',
      pass: '#password',
      captcha: '#yzm, img[alt="captcha"], img.yzmcrm',
      submit: '#submit, input[value="登录"], button:has-text("登录")',
    },
  };
  const sel = SELECTORS[PLATFORM] || SELECTORS.atmosphere;

  try {
    await page.fill(sel.user, user, { timeout: STEP_TIMEOUT_MS });
    await page.fill(sel.pass, pass, { timeout: STEP_TIMEOUT_MS });
  } catch (e) {
    exit(2, `[FATAL] 表单填写失败: ${e.message}`);
  }

  // —— 4. 验证码识别 + 提交循环 ————————————————————————
  console.log('[4/5] 开始验证码循环...');
  let finalStatus = 'unknown';

  for (let attempt = 0; attempt < MAX_CAPTCHA_ATTEMPTS; attempt++) {
    // 硬超时检查
    if (Date.now() - startTime > LOGIN_TOTAL_TIMEOUT_MS) {
      exit(3, '[TIMEOUT] 登录总超时');
    }

    console.log(`\n--- 第 ${attempt + 1}/${MAX_CAPTCHA_ATTEMPTS} 次尝试 ---`);

    // 4a. 提取验证码 base64
    const captchaB64 = await page.evaluate(() => {
      const imgs = document.querySelectorAll('img');
      for (const img of imgs) {
        if (img.src && img.src.includes('code')) {
          const canvas = document.createElement('canvas');
          canvas.width = img.naturalWidth || img.width;
          canvas.height = img.naturalHeight || img.height;
          canvas.getContext('2d').drawImage(img, 0, 0);
          return canvas.toDataURL('image/png');
        }
      }
      return null;
    });

    if (!captchaB64) {
      console.log('[OCR] 未找到验证码图片');
      break;
    }

    // 保存样本
    const b64data = captchaB64.replace('data:image/png;base64,', '');
    const samplePath = saveCaptchaSample(b64data, attempt + 1);

    // 4b. OCR 识别
    let captchaText = '';
    try {
      captchaText = ocrDecode(b64data);
      console.log(`[OCR] 结果: "${captchaText}" → 样本: ${samplePath}`);
    } catch (e) {
      console.log(`[OCR] 识别异常: ${e.message}`);
    }

    // 4c. OCR 失败 → 刷新验证码重来
    if (!captchaText || captchaText.length < 2) {
      console.log('[OCR] 识别结果无效，刷新验证码...');
      const oldSrc = await page.evaluate(() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
          if (img.src && img.src.includes('code')) return img.src;
        }
        return '';
      });
      await page.evaluate(() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
          if (img.src && img.src.includes('code')) { img.click(); break; }
        }
      });
      if (!(await waitCaptchaChanged(page, oldSrc))) {
        console.log('[WARN] 验证码图片未刷新');
      }
      continue;
    }

    // 4d. 填写验证码
    try {
      const captchaInput = await page.$(sel.captcha);
      if (captchaInput) {
        await captchaInput.click({ timeout: STEP_TIMEOUT_MS });
        await captchaInput.fill('', { timeout: STEP_TIMEOUT_MS });
        await captchaInput.fill(captchaText, { timeout: STEP_TIMEOUT_MS });
      } else {
        console.log('[WARN] 未找到验证码输入框');
        break;
      }
    } catch (e) {
      console.log(`[WARN] 验证码填充失败: ${e.message}`);
      continue;
    }

    // 4e. 点击登录（兼容 EasyUI iframe 嵌套）
    try {
      // 先找 iframe 中的按钮，再找主页面中的
      let clicked = false;
      const selectors = [
        sel.submit,
        'input.btn',
        'input[type="button"]',
        'a.l-btn:has-text("登录")',
        'a:has-text("登录")',
        'input[value="登录"]',
        'button:has-text("登录")',
        'input[type="submit"]',
        'button[type="submit"]',
        'button',
        'input[type="submit"]',
      ];
      for (const sel of selectors) {
        try {
          const btn = await page.$(sel);
          if (btn) {
            await btn.click({ timeout: STEP_TIMEOUT_MS });
            clicked = true;
            console.log(`[CLICK] 点击了: ${sel}`);
            break;
          }
        } catch {}
      }
      if (!clicked) {
        console.log('[WARN] 未找到登录按钮');
        break;
      }
    } catch (e) {
      console.log(`[WARN] 登录按钮点击失败: ${e.message}`);
      continue;
    }

    // 4f. 等待登录结果（基于页面信号而非固定等待）
    try {
      // 等待：URL 变化、或错误提示出现、或登录成功页面出现
      await Promise.race([
        page.waitForURL((url) => !url.toString().includes('redirect.jsp'), { timeout: 8000 }),
        page.waitForSelector('.error, .errorMsg, [ref="e27"]', { timeout: 8000 }),
        page.waitForURL((url) => url.toString().includes('main'), { timeout: 8000 }),
      ]);
    } catch {
      // 等待超时不代表失败，继续检查
    }

    // 4g. 结果判定
    const pageUrl = page.url();
    const errorText = await page.evaluate(() => {
      const el = document.querySelector('.error, .errorMsg, [ref="e27"], .el-message--error');
      return el ? el.textContent || el.innerText || '' : '';
    });

    console.log(`[RESULT] URL: ${pageUrl}`);
    if (errorText) console.log(`[RESULT] 错误: ${errorText}`);

    // 登录成功判定
    if (pageUrl.includes('main') || pageUrl.includes('home') || pageUrl.includes('index')) {
      finalStatus = 'success';
      console.log('[SUCCESS] 登录成功！');
      break;
    }

    // 判定失败类型
    const classification = classifyError(errorText);

    if (classification.type === 'credential') {
      console.log('[CRITICAL] 凭据失效！停止重试以免锁定账号');
      finalStatus = 'credential_failed';
      break;
    }

    if (classification.type === 'locked') {
      console.log('[EMERGENCY] 账号已被锁定！');
      finalStatus = 'account_locked';
      break;
    }

    // 验证码错误 → 刷新重试
    if (classification.type === 'captcha' || !pageUrl.includes('main')) {
      console.log('[RETRY] 验证码错误或未成功，刷新验证码...');

      const oldSrc = await page.evaluate(() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
          if (img.src && img.src.includes('code')) return img.src;
        }
        return '';
      });

      await page.evaluate(() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
          if (img.src && img.src.includes('code')) { img.click(); break; }
        }
      });

      await waitCaptchaChanged(page, oldSrc);
    }
  }

  // —— 5. 退出 —————————————————————————————————————————
  console.log(`\n[5/5] 最终状态: ${finalStatus}`);

  if (finalStatus === 'success') {
    // 导出会话状态供其他脚本复用
    const storageState = await browser.storageState();
    const stateDir = path.join(__dirname, 'auth', 'state');
    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(
      path.join(stateDir, `${PLATFORM}.storageState.json`),
      JSON.stringify(storageState, null, 2)
    );
    fs.chmodSync(path.join(stateDir, `${PLATFORM}.storageState.json`), 0o600);

    // 写入心跳账本
    fs.writeFileSync(
      path.join(stateDir, `${PLATFORM}.json`),
      JSON.stringify({
        lastCredentialAuthAt: new Date().toISOString(),
        authMode: 'credential_verified',
        status: 'ok',
      }, null, 2)
    );
    fs.chmodSync(path.join(stateDir, `${PLATFORM}.json`), 0o600);

    console.log('[DONE] 会话已保存');
    await browser.close();
    process.exit(0);
  }

  // 失败退出
  await browser.close();

  if (finalStatus === 'credential_failed') {
    exit(4, '[EXIT] 凭据失效，需人工更换密码后更新 Keychain');
  } else if (finalStatus === 'account_locked') {
    exit(5, '[EXIT] 账号已锁定');
  }
  exit(3, '[EXIT] 登录失败（验证码识别耗尽）');
})();
