/**
 * 大气监督帮扶平台 - 登录与数据采集 v2
 * 使用Playwright完整分析登录表单并尝试自动登录
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PLATFORM_URL = 'http://114.251.10.199:8080/zfpt_zf/redirect.jsp';
const OUTPUT_DIR = path.join(__dirname, 'patrol_data');
const TODAY = '20260805';

// 凭据从环境变量或 Keychain 读取
const { execSync } = require('child_process');
function getCred(service) {
  return (process.env.ECO_PASS || execSync(`security find-generic-password -a ecoaegis -s ${service} -w`, { encoding: 'utf8' })).trim();
}
const CREDENTIALS = [
  { user: process.env.ECOAEGIS_ATMOSPHERE_USER || '430000', pass: () => getCred('atmosphere-pass') },  // 省级账号
  { user: '431300', pass: () => getCred('atmosphere-pass') },  // 娄底市
  { user: '431381', pass: () => getCred('atmosphere-pass') },  // 冷水江市
];

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function analyzeLoginForm(page) {
  console.log('\n=== 分析登录表单 ===');
  
  const formInfo = await page.evaluate(() => {
    const result = { 
      forms: [], 
      inputs: [], 
      buttons: [],
      images: [],
      scripts: []
    };
    
    // 收集所有表单
    document.querySelectorAll('form').forEach((form, fi) => {
      const formData = { index: fi, action: form.action, method: form.method, id: form.id, inputs: [] };
      form.querySelectorAll('input, select, textarea').forEach((input, ii) => {
        formData.inputs.push({
          index: ii,
          type: input.type,
          name: input.name,
          id: input.id,
          placeholder: input.placeholder,
          value: input.value ? input.value.substring(0, 20) : '',
          className: input.className,
          required: input.required
        });
      });
      result.forms.push(formData);
    });
    
    // 收集所有输入框
    document.querySelectorAll('input').forEach((input, i) => {
      result.inputs.push({
        index: i,
        type: input.type || 'text',
        name: input.name || '',
        id: input.id || '',
        placeholder: input.placeholder || '',
        className: input.className || '',
        value: input.value ? input.value.substring(0, 30) : ''
      });
    });
    
    // 收集所有按钮
    document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn, [onclick*="login"], [onclick*="Login"]').forEach((btn, i) => {
      result.buttons.push({
        index: i,
        tag: btn.tagName,
        text: btn.textContent.trim() || btn.value || '',
        id: btn.id || '',
        className: btn.className || '',
        onclick: btn.getAttribute('onclick') || ''
      });
    });
    
    // 收集所有图片（验证码）
    document.querySelectorAll('img').forEach((img, i) => {
      if (img.src) {
        result.images.push({
          index: i,
          src: img.src,
          alt: img.alt || '',
          id: img.id || '',
          className: img.className || '',
          width: img.width,
          height: img.height
        });
      }
    });
    
    return result;
  });
  
  console.log(`表单数量: ${formInfo.forms.length}`);
  formInfo.forms.forEach(f => {
    console.log(`  表单[${f.index}]: action="${f.action}" method="${f.method}" id="${f.id}"`);
    f.inputs.forEach(i => {
      console.log(`    输入: type="${i.type}" name="${i.name}" id="${i.id}" placeholder="${i.placeholder}"`);
    });
  });
  
  console.log(`\n所有输入框: ${formInfo.inputs.length}`);
  formInfo.inputs.forEach(i => {
    console.log(`  [${i.index}] type="${i.type}" name="${i.name}" id="${i.id}" placeholder="${i.placeholder}" class="${i.className}"`);
  });
  
  console.log(`\n按钮: ${formInfo.buttons.length}`);
  formInfo.buttons.forEach(b => {
    console.log(`  [${b.index}] <${b.tag}> "${b.text}" id="${b.id}" onclick="${b.onclick}"`);
  });
  
  console.log(`\n图片: ${formInfo.images.length}`);
  formInfo.images.forEach(img => {
    console.log(`  [${img.index}] src="${img.src}" id="${img.id}" alt="${img.alt}" ${img.width}x${img.height}`);
  });
  
  return formInfo;
}

async function tryLogin(page, cred) {
  console.log(`\n尝试登录: 用户名="${cred.user}"`);
  
  // 清空并填写用户名
  const userInputs = await page.$$('input[type="text"], input:not([type])');
  for (const input of userInputs) {
    const name = await input.getAttribute('name');
    const id = await input.getAttribute('id');
    if (name && (name.includes('user') || name.includes('account') || name.includes('name') || name.includes('login'))) {
      await input.fill(cred.user);
      console.log(`  填写用户名到: name="${name}"`);
      break;
    }
    if (id && (id.includes('user') || id.includes('account') || id.includes('name') || id.includes('login'))) {
      await input.fill(cred.user);
      console.log(`  填写用户名到: id="${id}"`);
      break;
    }
  }
  
  // 填写密码
  const pwdInputs = await page.$$('input[type="password"]');
  for (const input of pwdInputs) {
    await input.fill(cred.pass);
    console.log(`  填写密码`);
    break;
  }
  
  // 检查验证码
  const captchaImg = await page.$('img[src*="captcha"], img[src*="kaptcha"], img[src*="code"], img[src*="yzm"], img[id*="captcha"], img[id*="yzm"], img[id*="code"]');
  if (captchaImg) {
    console.log('  发现验证码图片，尝试识别...');
    
    // 截图验证码并尝试用ddddocr识别
    const captchaBytes = await captchaImg.screenshot();
    const captchaPath = path.join(OUTPUT_DIR, 'captcha.png');
    fs.writeFileSync(captchaPath, captchaBytes);
    
    // 尝试填写验证码
    const captchaInputs = await page.$$('input[name*="captcha"], input[name*="yzm"], input[name*="code"], input[id*="captcha"], input[id*="yzm"], input[id*="code"], input[placeholder*="验证码"]');
    if (captchaInputs.length > 0) {
      console.log('  请手动输入验证码（自动化任务无法识别验证码）');
      // 在自动化任务中，我们无法输入验证码，需要手动处理
      return { success: false, reason: '需要验证码', needCaptcha: true };
    }
  }
  
  // 点击登录按钮
  const loginBtns = await page.$$('button, input[type="submit"], input[type="button"], a.btn');
  let clicked = false;
  for (const btn of loginBtns) {
    const text = await btn.textContent();
    const value = await btn.getAttribute('value');
    const onclick = await btn.getAttribute('onclick');
    
    if ((text && (text.includes('登录') || text.includes('Login') || text.includes('登 录'))) ||
        (value && (value.includes('登录') || value.includes('Login'))) ||
        (onclick && (onclick.includes('login') || onclick.includes('Login')))) {
      await btn.click();
      console.log(`  点击登录按钮: "${text || value}"`);
      clicked = true;
      break;
    }
  }
  
  if (!clicked) {
    // 尝试按Enter提交
    console.log('  未找到登录按钮，尝试按Enter...');
    await page.keyboard.press('Enter');
  }
  
  await sleep(3000);
  
  // 检查是否登录成功
  const currentUrl = page.url();
  const title = await page.title();
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
  
  console.log(`  登录后URL: ${currentUrl}`);
  console.log(`  页面标题: ${title}`);
  
  if (bodyText.includes('密码错误') || bodyText.includes('账号错误') || bodyText.includes('用户名或密码')) {
    console.log('  登录失败: 凭据错误');
    return { success: false, reason: '凭据错误' };
  }
  
  if (bodyText.includes('验证码') && (bodyText.includes('错误') || bodyText.includes('有误'))) {
    console.log('  登录失败: 验证码错误');
    return { success: false, reason: '验证码错误' };
  }
  
  if (!currentUrl.includes('redirect.jsp') && !bodyText.includes('登录')) {
    console.log('  登录成功！');
    return { success: true };
  }
  
  return { success: false, reason: '未知原因' };
}

async function extractTaskData(page) {
  console.log('\n=== 提取任务数据 ===');
  
  // 截图记录
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'screenshot_logged_in.png'), fullPage: false });
  
  // 获取所有frame
  const allFrames = page.frames();
  console.log(`共 ${allFrames.length} 个frame`);
  
  const allData = { frames: [], tables: [], bodyText: '' };
  
  // 提取主页面文本
  allData.bodyText = await page.evaluate(() => document.body.innerText.substring(0, 10000));
  
  // 遍历所有frame提取数据
  for (let fi = 0; fi < allFrames.length; fi++) {
    try {
      const frame = allFrames[fi];
      const frameData = {
        index: fi,
        url: frame.url(),
        text: '',
        tables: [],
        links: []
      };
      
      // 提取frame内文本
      frameData.text = await frame.evaluate(() => {
        return document.body ? document.body.innerText.substring(0, 5000) : '';
      });
      
      // 提取表格
      const tables = await frame.evaluate(() => {
        const result = [];
        document.querySelectorAll('table.datagrid-btable, table.datagrid, .datagrid-view table, table[class*="table"]').forEach((table, ti) => {
          const headers = [];
          const rows = [];
          const ths = table.querySelectorAll('th, .datagrid-header-row td');
          ths.forEach(th => {
            const text = th.textContent.trim();
            if (text) headers.push(text);
          });
          
          const trs = table.querySelectorAll('tr.datagrid-row, tbody tr');
          trs.forEach(tr => {
            const cells = tr.querySelectorAll('td');
            const row = [];
            cells.forEach(td => row.push(td.textContent.trim()));
            if (row.length > 0 && row.some(c => c.length > 0)) rows.push(row);
          });
          
          if (rows.length > 0) {
            result.push({ tableIndex: ti, headers, rowCount: rows.length, rows: rows.slice(0, 100) });
          }
        });
        return result;
      });
      frameData.tables = tables;
      
      // 提取链接
      frameData.links = await frame.evaluate(() => {
        return Array.from(document.querySelectorAll('a')).map(a => ({
          text: a.textContent.trim().substring(0, 80),
          href: a.href || '',
          onclick: a.getAttribute('onclick') || ''
        })).filter(l => l.text || l.href);
      });
      
      allData.frames.push(frameData);
      
      if (tables.length > 0) {
        console.log(`Frame[${fi}] 发现 ${tables.length} 个表格:`);
        tables.forEach(t => {
          console.log(`  表头: ${JSON.stringify(t.headers)}`);
          console.log(`  数据行: ${t.rowCount}`);
          t.rows.slice(0, 5).forEach((r, ri) => {
            console.log(`    [${ri}] ${JSON.stringify(r)}`);
          });
        });
      }
    } catch (e) {
      console.log(`Frame[${fi}] 错误: ${e.message}`);
    }
  }
  
  return allData;
}

async function navigateToTaskList(page) {
  console.log('\n=== 导航到任务列表 ===');
  
  // 尝试通过各种方式找到任务菜单
  const allFrames = page.frames();
  
  for (const frame of allFrames) {
    try {
      // 查找菜单链接
      const menuLinks = await frame.evaluate(() => {
        const links = [];
        const allElements = document.querySelectorAll('a, div[class*="menu"], li[class*="menu"], span[class*="menu"], .tree-node, .nav-item');
        allElements.forEach(el => {
          const text = el.textContent.trim();
          if (text && text.length < 30) {
            links.push({
              text: text,
              tag: el.tagName,
              id: el.id || '',
              className: el.className || '',
              onclick: el.getAttribute('onclick') || '',
              href: el.href || ''
            });
          }
        });
        return links;
      });
      
      const keywords = ['任务台账', '待办', '交办', '督办整改', '督查信息', '整改', '问题', '台账'];
      const matched = menuLinks.filter(l => keywords.some(k => l.text.includes(k)));
      
      if (matched.length > 0) {
        console.log(`Frame中匹配的菜单项:`);
        matched.forEach(m => {
          console.log(`  <${m.tag}> "${m.text}" id="${m.id}" class="${m.className}" onclick="${m.onclick}"`);
        });
        
        // 尝试点击第一个匹配项
        for (const m of matched) {
          try {
            if (m.id) {
              await frame.click(`#${m.id}`);
              console.log(`  点击了: #${m.id}`);
              await sleep(3000);
              return true;
            } else if (m.onclick) {
              await frame.evaluate(m.onclick);
              console.log(`  执行了: ${m.onclick}`);
              await sleep(3000);
              return true;
            }
          } catch (e) {
            console.log(`  点击失败: ${e.message}`);
          }
        }
      }
    } catch (e) {
      // 忽略不可访问的frame
    }
  }
  
  console.log('  未找到可点击的任务菜单');
  return false;
}

async function main() {
  console.log('=== 大气监督帮扶平台 - 登录与数据采集 v2 ===');
  console.log(`时间: ${new Date().toLocaleString('zh-CN')}`);
  
  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });
  
  const page = await context.newPage();
  
  try {
    // 打开平台
    console.log('\n打开平台...');
    await page.goto(PLATFORM_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(2000);
    
    // 分析登录表单
    const formInfo = await analyzeLoginForm(page);
    
    // 保存表单信息
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'login_form_analysis.json'),
      JSON.stringify(formInfo, null, 2),
      'utf8'
    );
    
    // 尝试登录
    let loggedIn = false;
    for (const cred of CREDENTIALS) {
      const result = await tryLogin(page, cred);
      if (result.success) {
        loggedIn = true;
        break;
      }
      if (result.needCaptcha) {
        console.log('\n验证码无法自动识别，请手动完成登录');
        // 等待手动登录
        console.log('等待90秒供手动登录...');
        for (let i = 0; i < 18; i++) {
          await sleep(5000);
          const url = page.url();
          if (!url.includes('redirect.jsp')) {
            console.log(`登录成功！当前URL: ${url}`);
            loggedIn = true;
            break;
          }
        }
        break;
      }
      console.log(`  凭据 ${cred.user} 失败: ${result.reason}`);
    }
    
    if (!loggedIn) {
      console.log('\n所有自动登录尝试失败，等待手动登录...');
      console.log('等待120秒...');
      for (let i = 0; i < 24; i++) {
        await sleep(5000);
        const url = page.url();
        if (!url.includes('redirect.jsp')) {
          console.log(`登录成功！当前URL: ${url}`);
          loggedIn = true;
          break;
        }
      }
    }
    
    if (!loggedIn) {
      console.log('\n登录超时，无法继续');
      return;
    }
    
    await sleep(3000);
    
    // 导航到任务台账
    await navigateToTaskList(page);
    
    // 提取任务数据
    const taskData = await extractTaskData(page);
    
    // 保存完整数据
    const outputPath = path.join(OUTPUT_DIR, `full_data_${TODAY}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(taskData, null, 2), 'utf8');
    console.log(`\n数据已保存到: ${outputPath}`);
    
    // 保存body文本供分析
    fs.writeFileSync(
      path.join(OUTPUT_DIR, `body_text_${TODAY}.txt`),
      taskData.bodyText,
      'utf8'
    );
    
    console.log('\n=== 采集完成 ===');
    
  } catch (error) {
    console.error(`\n错误: ${error.message}`);
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'error_final.png') });
  } finally {
    console.log('\n保持浏览器打开30秒...');
    await sleep(30000);
    await browser.close();
    console.log('浏览器已关闭');
  }
}

main().catch(console.error);
