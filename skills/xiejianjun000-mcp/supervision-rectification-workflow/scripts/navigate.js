// 用途：导航到督办整改页面
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 说明：处理三层iframe嵌套，找到并点击"督办整改"菜单项，等待页面加载
// 版本：v2.0.0 (2026-05-25 改进：添加更好的错误处理和日志)

(function() {
  var result = { steps: [], success: false, error: null, debug: [] };

  // 递归查找iframe中的文档
  function findInnerDoc(doc, maxDepth) {
    maxDepth = maxDepth || 3;
    if (maxDepth <= 0) return null;
    
    result.debug.push('查找iframe，深度: ' + maxDepth + ', doc URL: ' + (doc.location ? doc.location.href : 'unknown'));
    
    var iframes = doc.querySelectorAll('iframe');
    result.debug.push('找到 ' + iframes.length + ' 个iframe');
    
    for (var i = 0; i < iframes.length; i++) {
      try {
        var iframe = iframes[i];
        var innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        var innerWin = iframe.contentWindow;
        
        if (innerDoc && innerDoc.body && innerDoc.body.children.length > 0) {
          result.debug.push('iframe[' + i + '] 可访问，body子元素: ' + innerDoc.body.children.length);
          
          // 尝试查找目标元素
          var menuItems = innerDoc.querySelectorAll('a, span, div, li, .tree-title, .tree-node');
          result.debug.push('  找到 ' + menuItems.length + ' 个可能的菜单项');
          
          for (var j = 0; j < menuItems.length; j++) {
            var el = menuItems[j];
            var text = el.textContent ? el.textContent.trim() : '';
            if (text === '督办整改' || text.indexOf('督办整改') >= 0) {
              result.debug.push('  找到督办整改菜单项！');
              return { doc: innerDoc, win: innerWin, element: el };
            }
          }
          
          // 递归深入
          var deeper = findInnerDoc(innerDoc, maxDepth - 1);
          if (deeper) {
            result.debug.push('  递归找到目标');
            return deeper;
          }
        }
      } catch (e) {
        // 跨域iframe无法访问
        result.debug.push('iframe[' + i + '] 跨域无法访问: ' + e.message);
      }
    }
    return null;
  }

  // 方法1：直接通过ifr_center查找
  try {
    var ifrCenter = document.getElementById('ifr_center');
    if (ifrCenter) {
      result.steps.push('找到ifr_center');
      var centerDoc = ifrCenter.contentDocument || ifrCenter.contentWindow.document;
      if (centerDoc) {
        result.steps.push('访问ifr_center文档成功');
        // 在中心iframe中查找内层iframe
        var innerFound = findInnerDoc(centerDoc, 2);
        if (innerFound) {
          result.steps.push('在iframe中找到督办整改菜单项');
          innerFound.element.click();
          result.success = true;
          result.steps.push('已点击督办整改');
          return JSON.stringify(result);
        }
        // 也尝试在centerDoc直接查找
        var links = centerDoc.querySelectorAll('a');
        for (var k = 0; k < links.length; k++) {
          if (links[k].textContent.trim().indexOf('督办整改') >= 0) {
            links[k].click();
            result.success = true;
            result.steps.push('在ifr_center直接找到并点击督办整改');
            return JSON.stringify(result);
          }
        }
      }
    }
  } catch (e) {
    result.steps.push('ifr_center方式失败: ' + e.message);
  }

  // 方法2：遍历所有iframe递归查找
  try {
    var found = findInnerDoc(document, 3);
    if (found) {
      result.steps.push('递归查找找到督办整改');
      found.element.click();
      result.success = true;
      result.steps.push('已点击督办整改');
      return JSON.stringify(result);
    }
  } catch (e) {
    result.steps.push('递归查找失败: ' + e.message);
  }

  // 方法3：通过菜单路径点击（任务台账 → 督查信息 → 督办整改）
  try {
    var allFrames = document.querySelectorAll('iframe');
    result.steps.push('找到 ' + allFrames.length + ' 个iframe');
    for (var f = 0; f < allFrames.length; f++) {
      try {
        var fDoc = allFrames[f].contentDocument;
        if (!fDoc) continue;
        // 查找菜单树
        var treeNodes = fDoc.querySelectorAll('.tree-title, .tree-node');
        for (var t = 0; t < treeNodes.length; t++) {
          if (treeNodes[t].textContent.trim().indexOf('督办整改') >= 0) {
            treeNodes[t].click();
            result.success = true;
            result.steps.push('通过树菜单找到并点击督办整改');
            return JSON.stringify(result);
          }
        }
      } catch (e) {}
    }
  } catch (e) {
    result.steps.push('菜单树方式失败: ' + e.message);
  }

  result.error = '未能找到督办整改菜单项';
  return JSON.stringify(result);
})()
