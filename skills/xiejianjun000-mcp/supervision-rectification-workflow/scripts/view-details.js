// 用途：查看记录详情（打开检查详情弹窗并提取内容）
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 参数：rowIndex - 要查看的行索引（从0开始），不传则查看第一行
// 版本：v2.0.0 (2026-05-25 改进：添加调试日志和错误处理)

(function() {
  var rowIndex = typeof __ROW_INDEX__ !== 'undefined' ? __ROW_INDEX__ : 0;
  var result = { detail: null, success: false, error: null, debug: [], steps: [] };
  
  // 调试：输出参数
  result.debug.push('rowIndex=' + rowIndex);
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
          if (innerDoc.querySelector('.datagrid-btable, .datagrid')) {
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

  // 方法1:直接调用jcxx()函数打开弹窗
  try {
    var btable = doc.querySelector('.datagrid-btable');
    if (btable) {
      var trs = btable.querySelectorAll('tr');
      if (rowIndex < trs.length) {
        var targetRow = trs[rowIndex];
        // 查找"查看检查"链接
        var viewLinks = targetRow.querySelectorAll('a[onclick*="jcxx"], a');
        for (var i = 0; i < viewLinks.length; i++) {
          var link = viewLinks[i];
          if (link.textContent.trim().indexOf('查看检查') >= 0 ||
              link.getAttribute('onclick') && link.getAttribute('onclick').indexOf('jcxx') >= 0) {
            link.click();
            result.success = true;
            result.steps = ['点击查看检查链接'];
            break;
          }
        }
        // 如果没找到链接,尝试直接调用jcxx函数
        if (!result.success && typeof win.jcxx === 'function') {
          // 从datagrid获取行数据作为参数
          var dgEl = doc.querySelector('.datagrid');
          if (dgEl && win.$) {
            var rows = win.$('#' + dgEl.id, doc).datagrid('getRows');
            if (rows && rows[rowIndex]) {
              win.jcxx(rows[rowIndex]);
              result.success = true;
              result.steps = ['调用jcxx()函数'];
            }
          }
        }
      }
    }
  } catch (e) {
    result.error = '打开详情失败: ' + e.message;
    return JSON.stringify(result);
  }

  // 等待弹窗加载后提取内容(需分步执行,此脚本仅负责点击打开弹窗)
  // 提取弹窗内容需要单独执行下面的脚本

  // 尝试提取弹窗内容(如果弹窗已存在)
  try {
    var dialog = doc.querySelector('.window, .panel-body, .dialog');
    if (dialog) {
      var detail = {};
      var labels = dialog.querySelectorAll('label, .label, th');
      var values = dialog.querySelectorAll('input, textarea, select, td');
      // 提取所有文本内容
      var tables = dialog.querySelectorAll('table');
      for (var t = 0; t < tables.length; t++) {
        var cells = tables[t].querySelectorAll('td, th');
        for (var c = 0; c < cells.length; c++) {
          var text = cells[c].textContent.trim();
          if (text) detail['field_' + c] = text;
        }
      }
      result.detail = detail;
    }
  } catch (e) {}

  return JSON.stringify(result);
})()
