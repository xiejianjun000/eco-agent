/**
 * 大气监督帮扶平台 - 每日跟踪数据采集脚本
 * 使用 Playwright 自动登录并提取待办/交办任务数据
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const PLATFORM_URL = 'http://114.251.10.199:8080/zfpt_zf/redirect.jsp';
const OUTPUT_DIR = path.join(__dirname, 'patrol_data');
const TODAY = new Date().toISOString().slice(0, 10).replace(/-/g, '');
const OUTPUT_FILE = path.join(OUTPUT_DIR, `tasks_${TODAY}.json`);

// 确保输出目录存在
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function main() {
  console.log('[启动] 大气监督帮扶平台数据采集');
  console.log(`[时间] ${new Date().toLocaleString('zh-CN')}`);
  console.log(`[输出] ${OUTPUT_FILE}`);

  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    acceptDownloads: true
  });

  const page = await context.newPage();

  try {
    // ========== 步骤1: 打开平台 ==========
    console.log('\n[步骤1] 正在打开大气监督帮扶平台...');
    await page.goto(PLATFORM_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await sleep(3000);

    // 截图记录
    await page.screenshot({ path: path.join(OUTPUT_DIR, `screenshot_01_initial.png`), fullPage: false });
    console.log('[步骤1] 平台页面已加载，截图已保存');

    // ========== 步骤2: 检查登录状态 ==========
    console.log('\n[步骤2] 检查登录状态...');
    
    // 获取当前URL，判断是否跳转到登录页
    const currentUrl = page.url();
    console.log(`  当前URL: ${currentUrl}`);
    
    // 尝试获取页面标题
    const title = await page.title();
    console.log(`  页面标题: ${title}`);

    // 检查是否存在登录表单
    const loginForm = await page.$('input[type="password"], input[name="password"], #password');
    let needLogin = false;
    
    if (loginForm) {
      console.log('  检测到登录页面，需要登录');
      needLogin = true;
    } else {
      // 检查是否已登录（查找典型的主页面元素）
      const mainElements = await page.$$('frame, iframe, #main, .main, .header');
      console.log(`  检测到 ${mainElements.length} 个主要页面元素`);
      
      if (mainElements.length === 0) {
        // 可能还在登录页
        const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
        console.log(`  页面内容摘要: ${bodyText}`);
        needLogin = bodyText.includes('登录') || bodyText.includes('密码') || bodyText.includes('验证码');
      }
    }

    if (needLogin) {
      console.log('\n[步骤2] ===== 需要手动登录 =====');
      console.log('  请在浏览器窗口中手动输入用户名和密码完成登录');
      console.log('  等待60秒...');
      
      // 等待登录完成（URL变化或页面元素出现）
      for (let i = 0; i < 12; i++) {
        await sleep(5000);
        const url = page.url();
        console.log(`  等待中 (${(i+1)*5}s)... 当前URL: ${url}`);
        
        // 检查是否跳转到主页面
        if (!url.includes('login') && !url.includes('Login')) {
          const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 200));
          if (!bodyText.includes('登录') && !bodyText.includes('密码')) {
            console.log('  登录似乎已完成');
            break;
          }
        }
      }
    } else {
      console.log('  已经登录，跳过登录步骤');
    }

    // 截图登录后状态
    await page.screenshot({ path: path.join(OUTPUT_DIR, `screenshot_02_after_login.png`), fullPage: false });

    // ========== 步骤3: 提取页面结构 ==========
    console.log('\n[步骤3] 分析页面结构...');
    
    // 获取所有iframe
    const frameInfo = await page.evaluate(() => {
      const iframes = document.querySelectorAll('iframe, frame');
      const info = [];
      iframes.forEach((f, i) => {
        info.push({
          index: i,
          id: f.id || '',
          name: f.name || '',
          src: f.src || ''
        });
      });
      return info;
    });
    console.log(`  发现 ${frameInfo.length} 个iframe/frame:`);
    frameInfo.forEach(f => {
      console.log(`    [${f.index}] id="${f.id}" name="${f.name}" src="${f.src}"`);
    });

    // ========== 步骤4: 导航到待办/交办任务页面 ==========
    console.log('\n[步骤4] 查找待办/交办任务入口...');
    
    // 获取主页面的所有链接和可点击元素
    const clickableElements = await page.evaluate(() => {
      const elements = document.querySelectorAll('a, button, [onclick], .menu-item, .nav-item, li, span[class*="menu"]');
      const result = [];
      elements.forEach((el, i) => {
        const text = (el.textContent || '').trim();
        if (text && text.length > 1 && text.length < 50) {
          result.push({
            index: i,
            tag: el.tagName,
            text: text,
            id: el.id || '',
            className: el.className || '',
            onclick: el.getAttribute('onclick') || ''
          });
        }
      });
      return result;
    });

    // 查找关键词："待办"、"交办"、"任务"、"督办"、"台账"
    const keywords = ['待办', '交办', '任务', '督办', '台账', '督查', '整改', '任务台账'];
    const matchedElements = clickableElements.filter(el => 
      keywords.some(kw => el.text.includes(kw))
    );
    
    console.log(`  找到 ${matchedElements.length} 个匹配关键词的元素:`);
    matchedElements.slice(0, 20).forEach(el => {
      console.log(`    [${el.index}] <${el.tag}> "${el.text}" id="${el.id}" class="${el.className}"`);
    });

    // 如果有"任务台账"链接，尝试点击
    const taskMenuEl = matchedElements.find(el => el.text.includes('任务台账'));
    if (taskMenuEl) {
      console.log(`\n  点击"任务台账"入口...`);
      if (taskMenuEl.id) {
        await page.click(`#${taskMenuEl.id}`);
      } else if (taskMenuEl.onclick) {
        await page.evaluate(taskMenuEl.onclick);
      }
      await sleep(3000);
    }

    // ========== 步骤5: 提取所有页面文本内容 ==========
    console.log('\n[步骤5] 提取页面数据...');
    
    // 获取主页面body文本
    const mainBodyText = await page.evaluate(() => document.body.innerText);
    
    // 保存原始文本
    fs.writeFileSync(path.join(OUTPUT_DIR, `raw_text_${TODAY}.txt`), mainBodyText, 'utf8');
    console.log(`  主页面文本已保存 (${mainBodyText.length} 字符)`);

    // 尝试获取所有frame的内容
    const allFrames = page.frames();
    console.log(`  共发现 ${allFrames.length} 个frame`);
    
    for (let i = 0; i < allFrames.length; i++) {
      try {
        const frame = allFrames[i];
        const frameUrl = frame.url();
        const frameContent = await frame.evaluate(() => document.body ? document.body.innerText.substring(0, 3000) : '');
        console.log(`\n  Frame[${i}] URL: ${frameUrl}`);
        console.log(`  Frame[${i}] 内容 (前3000字符):`);
        console.log(frameContent);
        
        // 保存frame内容
        if (frameContent && frameContent.length > 10) {
          fs.writeFileSync(
            path.join(OUTPUT_DIR, `frame_${i}_text.txt`),
            frameContent,
            'utf8'
          );
        }
      } catch (e) {
        console.log(`  Frame[${i}] 无法访问: ${e.message}`);
      }
    }

    // ========== 步骤6: 提取表格数据 ==========
    console.log('\n[步骤6] 尝试提取表格/列表数据...');
    
    // 在所有frame中查找表格
    const tableData = [];
    for (let i = 0; i < allFrames.length; i++) {
      try {
        const frame = allFrames[i];
        const tables = await frame.evaluate(() => {
          const tableEls = document.querySelectorAll('table, .datagrid, .easyui-datagrid, [class*="table"], [class*="grid"]');
          const result = [];
          tableEls.forEach((table, ti) => {
            const rows = table.querySelectorAll('tr');
            if (rows.length > 1) {
              const headers = [];
              const firstRow = rows[0].querySelectorAll('th, td');
              firstRow.forEach(cell => headers.push(cell.textContent.trim()));
              
              const dataRows = [];
              for (let ri = 1; ri < Math.min(rows.length, 50); ri++) {
                const cells = rows[ri].querySelectorAll('td');
                const rowData = [];
                cells.forEach(cell => rowData.push(cell.textContent.trim()));
                if (rowData.length > 0) dataRows.push(rowData);
              }
              
              result.push({
                tableIndex: ti,
                headers: headers,
                rowCount: dataRows.length,
                rows: dataRows.slice(0, 30) // 最多取30行
              });
            }
          });
          return result;
        });
        
        if (tables.length > 0) {
          console.log(`  Frame[${i}] 发现 ${tables.length} 个表格`);
          tables.forEach((t, ti) => {
            console.log(`    表格[${ti}]: 表头=${JSON.stringify(t.headers)}, 数据行=${t.rowCount}`);
          });
          tableData.push({ frameIndex: i, tables: tables });
        }
      } catch (e) {
        // 忽略无法访问的frame
      }
    }

    // ========== 步骤7: 提取EasyUI datagrid数据 ==========
    console.log('\n[步骤7] 尝试提取EasyUI datagrid数据...');
    
    for (let i = 0; i < allFrames.length; i++) {
      try {
        const frame = allFrames[i];
        const datagridData = await frame.evaluate(() => {
          const result = [];
          try {
            // 尝试jQuery datagrid
            if (typeof $ !== 'undefined') {
              $('.datagrid, .easyui-datagrid, table[class*="datagrid"]').each(function() {
                const id = $(this).attr('id');
                if (id && $(this).datagrid) {
                  try {
                    const rows = $(this).datagrid('getRows');
                    const columns = $(this).datagrid('options').columns;
                    result.push({ id: id, type: 'datagrid', rows: rows, columns: columns });
                  } catch (e) {
                    result.push({ id: id, type: 'datagrid', error: e.message });
                  }
                }
              });
            }
          } catch (e) {
            result.push({ error: e.message });
          }
          return result;
        });
        
        if (datagridData && datagridData.length > 0) {
          console.log(`  Frame[${i}] EasyUI datagrid数据:`);
          console.log(JSON.stringify(datagridData, null, 2).substring(0, 5000));
          
          // 保存完整数据
          fs.writeFileSync(
            path.join(OUTPUT_DIR, `datagrid_frame${i}.json`),
            JSON.stringify(datagridData, null, 2),
            'utf8'
          );
        }
      } catch (e) {
        // 忽略
      }
    }

    // ========== 步骤8: 获取所有链接 ==========
    console.log('\n[步骤8] 提取所有页面链接...');
    
    const allLinks = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('a[href]')).map(a => ({
        text: a.textContent.trim(),
        href: a.href
      })).filter(l => l.href && !l.href.startsWith('javascript:'));
    });
    
    console.log(`  找到 ${allLinks.length} 个链接`);
    allLinks.slice(0, 30).forEach(l => {
      console.log(`    "${l.text}" -> ${l.href}`);
    });

    // ========== 步骤9: 保存综合数据 ==========
    const summary = {
      date: new Date().toISOString(),
      platform_url: PLATFORM_URL,
      page_title: title,
      current_url: currentUrl,
      has_login_form: !!loginForm,
      total_frames: allFrames.length,
      frame_info: frameInfo,
      matched_menu_items: matchedElements.slice(0, 30),
      table_data: tableData,
      total_links: allLinks.length,
      body_text_length: mainBodyText.length,
      key_elements_count: clickableElements.length
    };

    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(summary, null, 2), 'utf8');
    console.log(`\n[完成] 数据已保存到 ${OUTPUT_FILE}`);
    console.log(JSON.stringify(summary, null, 2));

  } catch (error) {
    console.error(`\n[错误] ${error.message}`);
    console.error(error.stack);
    
    // 错误截图
    await page.screenshot({ 
      path: path.join(OUTPUT_DIR, `error_${TODAY}.png`),
      fullPage: false 
    });
  } finally {
    // 保持浏览器打开以便调试（自动化任务中关闭）
    console.log('\n[提示] 浏览器保持打开，等待手动操作...');
    await sleep(60000); // 等待60秒后关闭
    await browser.close();
    console.log('[结束] 浏览器已关闭');
  }
}

main().catch(console.error);
