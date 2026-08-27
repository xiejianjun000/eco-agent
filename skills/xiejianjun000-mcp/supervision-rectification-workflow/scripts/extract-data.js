// 用途：提取EasyUI datagrid表格数据（处理虚拟渲染和分页）
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 说明：提取当前页面datagrid的所有行数据，包括分页信息
// 版本：v2.0.0 (2026-05-25 改进：添加调试日志和错误处理)

(function() {
  var result = { rows: [], total: 0, page: 1, pageSize: 0, error: null, debug: [], method: 'unknown' };
  
  // 调试：输出当前URL
  result.debug.push('当前URL: ' + (window.location ? window.location.href : 'unknown'));
  // 获取最内层iframe文档（改进：添加调试日志）
  function getInnerFrame(doc, maxDepth) {
    maxDepth = maxDepth || 3;
    if (maxDepth <= 0) {
      result.debug.push('getInnerFrame: 达到最大深度');
      return null;
    }
    
    result.debug.push('getInnerFrame: depth=' + maxDepth + ', doc=' + (doc ? 'exists' : 'null'));
    
    var iframes = doc.querySelectorAll('iframe');
    result.debug.push('找到 ' + iframes.length + ' 个iframe');
    
    for (var i = 0; i < iframes.length; i++) {
      try {
        var iframe = iframes[i];
        var innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        var innerWin = iframe.contentWindow;
        
        if (innerDoc && innerDoc.body) {
          result.debug.push('  iframe[' + i + '] 可访问, body子元素: ' + innerDoc.body.children.length);
          
          // 优先查找包含datagrid的iframe
          if (innerDoc.querySelector('.datagrid-btable, .datagrid')) {
            result.debug.push('  ✅ 找到包含datagrid的iframe');
            return { doc: innerDoc, win: innerWin };
          }
          
          var deeper = getInnerFrame(innerDoc, maxDepth - 1);
          if (deeper) {
            result.debug.push('  ✅ 递归找到目标');
            return deeper;
          }
        }
      } catch (e) {
        result.debug.push('  iframe[' + i + '] 跨域无法访问: ' + e.message);
      }
    }
    
    result.debug.push('getInnerFrame: 未找到目标iframe');
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
    result.error = '无法找到包含datagrid的iframe';
    return JSON.stringify(result);
  }

  var doc = ctx.doc;
  var win = ctx.win;

  // 方法1:通过EasyUI API获取数据(最可靠)
  try {
    var datagridEl = doc.querySelector('.datagrid');
    if (datagridEl) {
      var dgId = datagridEl.id;
      if (dgId && win.$ && win.$.fn && win.$.fn.datagrid) {
        var rows = win.$('#' + dgId, doc).datagrid('getRows');
        if (rows && rows.length > 0) {
          result.rows = rows;
          result.total = rows.length;
          // 尝试获取分页信息
          try {
            var pager = win.$('#' + dgId, doc).datagrid('getPager');
            if (pager && pager.pagination) {
              var opts = pager.pagination('options');
              result.page = opts.pageNumber || 1;
              result.pageSize = opts.pageSize || rows.length;
              result.total = opts.total || rows.length;
            }
          } catch (e) {}
          return JSON.stringify(result);
        }
      }
    }
  } catch (e) {
    // API方式失败,降级到DOM方式
  }

  // 方法2:DOM遍历提取datagrid-btable
  try {
    var btable = doc.querySelector('.datagrid-btable');
    if (btable) {
      var trs = btable.querySelectorAll('tr');
      // 获取列标题
      var htable = doc.querySelector('.datagrid-htable');
      var headers = [];
      if (htable) {
        var headerCells = htable.querySelectorAll('td .datagrid-cell');
        for (var h = 0; h < headerCells.length; h++) {
          headers.push(headerCells[h].textContent.trim());
        }
      }

      for (var i = 0; i < trs.length; i++) {
        var tds = trs[i].querySelectorAll('td');
        var row = {};
        for (var j = 0; j < tds.length; j++) {
          var cell = tds[j].querySelector('.datagrid-cell');
          var text = cell ? cell.textContent.trim() : tds[j].textContent.trim();
          var key = headers[j] || ('col_' + j);
          row[key] = text;

          // 提取链接中的onclick函数调用(如"查看检查")
          var links = tds[j].querySelectorAll('a[onclick]');
          if (links.length > 0) {
            row['_links'] = row['_links'] || [];
            for (var l = 0; l < links.length; l++) {
              row['_links'].push({
                text: links[l].textContent.trim(),
                onclick: links[l].getAttribute('onclick')
              });
            }
          }
        }
        if (Object.keys(row).length > 0) {
          result.rows.push(row);
        }
      }
      result.total = result.rows.length;
    }
  } catch (e) {
    result.error = 'DOM提取失败: ' + e.message;
  }

  // 方法3:尝试从分页信息获取总记录数
  try {
    var pagination = doc.querySelector('.pagination-info');
    if (pagination) {
      var infoText = pagination.textContent;
      var totalMatch = infoText.match(/共\s*(\d+)\s*条/);
      if (totalMatch) result.total = parseInt(totalMatch[1]);
    }
  } catch (e) {}

  // 获取分页信息
  try {
    var pageList = doc.querySelector('.pagination .pagination-num');
    if (pageList) result.page = parseInt(pageList.value) || 1;
    var pageSizeSelect = doc.querySelector('.pagination .pagination-page-list');
    if (pageSizeSelect) result.pageSize = parseInt(pageSizeSelect.value) || 0;
  } catch (e) {}

  return JSON.stringify(result);
})()
