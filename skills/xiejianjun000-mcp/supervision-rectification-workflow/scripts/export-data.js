// 用途：导出数据（触发系统导出功能下载Excel/PDF）
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 版本：v2.0.0 (2026-05-25 改进：添加调试日志和错误处理)

(function() {
  var result = { steps: [], success: false, error: null, debug: [] };
  
  // 调试：输出当前URL
  result.debug.push('当前URL: ' + (window.location ? window.location.href : 'unknown'));
  // 获取最内层iframe文档
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
          if (innerDoc.querySelector('.datagrid, button, a[onclick]')) {
            return { doc: innerDoc, win: innerWin };
          }
          var deeper = getInnerFrame(innerDoc, maxDepth - 1);
          if (deeper) return deeper;
        }
      } catch (e) {}
    }
    return null;
  }

  var ifrCenter = document.getElementById('ifr_center');
  var ctx = null;
  if (ifrCenter) {
    try {
      var centerDoc = ifrCenter.contentDocument;
      if (centerDoc) ctx = getInnerFrame(centerDoc, 2);
    } catch (e) {}
  }
  if (!ctx) ctx = getInnerFrame(document, 3);

  if (!ctx) {
    result.error = '无法找到目标iframe';
    return JSON.stringify(result);
  }

  var doc = ctx.doc;
  var win = ctx.win;

  // 方法1:查找并点击导出按钮
  try {
    var exportBtn = doc.querySelector('button[onclick*="export"], a[onclick*="export"], a[onclick*="导出"], button:contains("导出")');
    // jQuery :contains 扩展
    if (!exportBtn && win.$) {
      exportBtn = win.$('button:contains("导出"), a:contains("导出")', doc)[0];
    }
    if (exportBtn) {
      exportBtn.click();
      result.success = true;
      result.steps.push('点击导出按钮');
      return JSON.stringify(result);
    }
  } catch (e) {
    result.steps.push('点击导出按钮失败: ' + e.message);
  }

  // 方法2:调用导出函数
  try {
    if (typeof win.exportData === 'function') {
      win.exportData();
      result.success = true;
      result.steps.push('调用exportData()');
      return JSON.stringify(result);
    }
    if (typeof win.exportExcel === 'function') {
      win.exportExcel();
      result.success = true;
      result.steps.push('调用exportExcel()');
      return JSON.stringify(result);
    }
    if (typeof win.doExport === 'function') {
      win.doExport();
      result.success = true;
      result.steps.push('调用doExport()');
      return JSON.stringify(result);
    }
  } catch (e) {
    result.steps.push('调用导出函数失败: ' + e.message);
  }

  // 方法3:通过datagrid扩展按钮触发导出
  try {
    if (win.$) {
      var dgEl = doc.querySelector('.datagrid');
      if (dgEl) {
        var toolbar = doc.querySelector('.datagrid-toolbar');
        if (toolbar) {
          var btns = toolbar.querySelectorAll('a, button');
          for (var i = 0; i < btns.length; i++) {
            if (btns[i].textContent.indexOf('导出') >= 0 || btns[i].textContent.indexOf('Export') >= 0) {
              btns[i].click();
              result.success = true;
              result.steps.push('通过toolbar点击导出');
              return JSON.stringify(result);
            }
          }
        }
      }
    }
  } catch (e) {
    result.steps.push('toolbar导出失败: ' + e.message);
  }

  // 方法4:模拟表单提交导出
  try {
    var dgEl = doc.querySelector('.datagrid');
    if (dgEl) {
      var dgId = dgEl.id;
      // 获取datagrid的url
      if (win.$ && dgId) {
        var opts = win.$('#' + dgId, doc).datagrid('options');
        if (opts && opts.url) {
          var exportUrl = opts.url.replace('list', 'export').replace('query', 'export');
          // 创建隐藏iframe触发下载
          var downloadFrame = doc.createElement('iframe');
          downloadFrame.style.display = 'none';
          downloadFrame.src = exportUrl + '?exportType=excel';
          doc.body.appendChild(downloadFrame);
          result.success = true;
          result.steps.push('通过iframe触发导出: ' + exportUrl);
          return JSON.stringify(result);
        }
      }
    }
  } catch (e) {
    result.steps.push('表单提交导出失败: ' + e.message);
  }

  result.error = '未能找到导出功能';
  return JSON.stringify(result);
})()
