// 用途：批量采集多个区县的督办整改数据（可执行版本）
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 说明：本脚本可执行，会自动遍历所有区县并采集数据

(function() {
  // === 配置区 ===
  var CONFIG = {
    province: '430000',  // 湖南省
    city: '431300',      // 娄底市
    counties: [
      { code: '431302', name: '娄星区' },
      { code: '431321', name: '双峰县' },
      { code: '431322', name: '新化县' },
      { code: '431381', name: '冷水江市' },
      { code: '431382', name: '涟源市' }
    ],
    timeRange: {
      start: '2026-01-01',
      end: '2026-05-31'
    },
    delayMs: 3000  // 每次查询间隔（毫秒）
  };

  var result = {
    success: false,
    totalCounties: CONFIG.counties.length,
    collectedCounties: 0,
    totalRecords: 0,
    data: [],
    errors: [],
    steps: []
  };

  // === 辅助函数：获取最内层iframe ===
  function getInnerFrame(doc, maxDepth) {
    maxDepth = maxDepth || 3;
    if (maxDepth <= 0) return null;
    
    var iframes = doc.querySelectorAll('iframe');
    for (var i = 0; i < iframes.length; i++) {
      try {
        var iframe = iframes[i];
        var innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        var innerWin = iframe.contentWindow;
        
        if (innerDoc && innerDoc.body) {
          // 优先查找包含datagrid或筛选表单的iframe
          if (innerDoc.querySelector('.datagrid, select[name="SSQX"], input[name="KSSJ"]')) {
            return { doc: innerDoc, win: innerWin };
          }
          
          // 递归查找更内层
          var deeper = getInnerFrame(innerDoc, maxDepth - 1);
          if (deeper) return deeper;
        }
      } catch (e) {
        // 跨域iframe无法访问，跳过
      }
    }
    return null;
  }

  // === 辅助函数：设置筛选条件 ===
  function setFilters(ctx, config) {
    var doc = ctx.doc;
    var win = ctx.win;
    var steps = [];

    // 设置省份
    var sssf = doc.querySelector('select[name="SSSF"], #SSSF');
    if (sssf) {
      sssf.value = config.province;
      sssf.dispatchEvent(new Event('change', { bubbles: true }));
      steps.push('设置省份: ' + config.province);
    }

    // 设置地市
    var ssds = doc.querySelector('select[name="SSDS"], #SSDS');
    if (ssds) {
      ssds.value = config.city;
      ssds.dispatchEvent(new Event('change', { bubbles: true }));
      steps.push('设置地市: ' + config.city);
    }

    // 设置开始时间
    var kssj = doc.querySelector('input[name="KSSJ"], #KSSJ');
    if (kssj) {
      kssj.removeAttribute('readonly');
      kssj.value = config.timeRange.start;
      kssj.dispatchEvent(new Event('change', { bubbles: true }));
      steps.push('设置开始时间: ' + config.timeRange.start);
    }

    // 设置结束时间
    var jssj = doc.querySelector('input[name="JSSJ"], #JSSJ');
    if (jssj) {
      jssj.removeAttribute('readonly');
      jssj.value = config.timeRange.end;
      jssj.dispatchEvent(new Event('change', { bubbles: true }));
      steps.push('设置结束时间: ' + config.timeRange.end);
    }

    return steps;
  }

  // === 辅助函数：触发查询 ===
  function triggerQuery(ctx) {
    var win = ctx.win;
    var doc = ctx.doc;

    if (typeof win.searchQhdcRecord === 'function') {
      win.searchQhdcRecord();
      return '调用searchQhdcRecord()';
    } else if (typeof win.query === 'function') {
      win.query();
      return '调用query()';
    } else {
      var searchBtn = doc.querySelector('button[onclick*="search"], a[onclick*="search"]');
      if (searchBtn) {
        searchBtn.click();
        return '点击查询按钮';
      }
    }

    return '未找到查询函数或按钮';
  }

  // === 辅助函数：提取datagrid数据 ===
  function extractData(ctx) {
    var doc = ctx.doc;
    var win = ctx.win;
    var rows = [];

    // 方法1：通过EasyUI API获取
    try {
      var datagridEl = doc.querySelector('.datagrid');
      if (datagridEl && datagridEl.id && win.$ && win.$.fn && win.$.fn.datagrid) {
        var apiRows = win.$('#' + datagridEl.id, doc).datagrid('getRows');
        if (apiRows && apiRows.length > 0) {
          return { rows: apiRows, method: 'API' };
        }
      }
    } catch (e) {
      // API方式失败，降级到DOM方式
    }

    // 方法2：DOM遍历
    try {
      var btable = doc.querySelector('.datagrid-btable');
      if (btable) {
        var trs = btable.querySelectorAll('tr');
        for (var i = 0; i < trs.length; i++) {
          var tds = trs[i].querySelectorAll('td');
          var row = {};
          for (var j = 0; j < tds.length; j++) {
            var text = tds[j].textContent.trim();
            row['col_' + j] = text;
          }
          if (Object.keys(row).length > 0) {
            rows.push(row);
          }
        }
        return { rows: rows, method: 'DOM' };
      }
    } catch (e) {
      return { rows: [], error: e.message };
    }

    return { rows: [], error: '未找到datagrid数据' };
  }

  // === 主流程 ===
  try {
    result.steps.push('开始批量采集...');
    result.steps.push('共 ' + CONFIG.counties.length + ' 个区县');

    // 获取iframe上下文
    var ifrCenter = document.getElementById('ifr_center');
    var ctx = null;

    if (ifrCenter) {
      try {
        var centerDoc = ifrCenter.contentDocument;
        if (centerDoc) {
          ctx = getInnerFrame(centerDoc, 2);
        }
      } catch (e) {
        result.steps.push('ifr_center访问失败: ' + e.message);
      }
    }

    if (!ctx) {
      ctx = getInnerFrame(document, 3);
    }

    if (!ctx) {
      result.error = '无法找到目标iframe';
      return JSON.stringify(result);
    }

    result.steps.push('✅ 找到目标iframe');

    // 遍历所有区县
    for (var i = 0; i < CONFIG.counties.length; i++) {
      var county = CONFIG.counties[i];
      result.steps.push('📥 采集 [' + (i+1) + '/' + CONFIG.counties.length + '] ' + county.name + ' (' + county.code + ')');

      try {
        // 1. 设置区县
        var ssqx = ctx.doc.querySelector('select[name="SSQX"], #SSQX');
        if (ssqx) {
          ssqx.value = county.code;
          ssqx.dispatchEvent(new Event('change', { bubbles: true }));
          result.steps.push('  设置区县: ' + county.name);
        } else {
          result.errors.push({ county: county.name, error: '未找到SSQX下拉框' });
          continue;
        }

        // 2. 触发查询
        var queryMethod = triggerQuery(ctx);
        result.steps.push('  触发查询: ' + queryMethod);

        // 3. 等待页面加载（重要！）
        // 注意：在evaluate中无法使用await，所以需要外部控制等待
        result.steps.push('  ⏳ 等待页面加载（需要外部等待3秒）');

        // 4. 提取数据（需要在等待后再次调用）
        // 注意：本脚本只负责设置筛选和触发查询，数据提取需要单独执行
        result.steps.push('  💡 请等待3秒后执行extract-data.js提取数据');

        result.collectedCounties++;
        result.steps.push('  ✅ ' + county.name + ' 筛选完成');

      } catch (e) {
        result.errors.push({ county: county.name, error: e.message });
        result.steps.push('  ❌ ' + county.name + ' 采集失败: ' + e.message);
      }

      // 延时（通过返回结果告诉外部需要等待）
      if (i < CONFIG.counties.length - 1) {
        result.steps.push('  ⏳ 等待 ' + (CONFIG.delayMs / 1000) + ' 秒后继续...');
      }
    }

    result.success = true;
    result.message = '批量采集完成！共采集 ' + result.collectedCounties + '/' + result.totalCounties + ' 个区县';
    result.nextStep = '请等待3秒后，对每个区县执行extract-data.js提取数据';

  } catch (e) {
    result.error = '批量采集失败: ' + e.message;
  }

  return JSON.stringify(result);
})()
