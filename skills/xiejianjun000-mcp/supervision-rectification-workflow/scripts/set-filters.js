// 用途：设置筛选条件并触发查询
// 浏览器工具调用方式：browser action=act, kind=evaluate, targetId=<动态获取>, fn="脚本内容"
// 参数：可通过修改config对象来改变筛选条件
// 版本：v2.0.0 (2026-05-25 改进：添加调试日志和错误处理)

(function() {
  var config = {
    SSSF: '430000',   // 湖南省
    SSDS: '431300',   // 娄底市
    SSQX: '431381',   // 冷水江市
    KSSJ: '2026-01-01', // 开始时间
    JSSJ: '2026-05-31'  // 结束时间
  };

  var result = { steps: [], success: false, error: null, config: config, debug: [] };
  
  // 调试：输出配置
  result.debug.push('配置: ' + JSON.stringify(config));
  // 获取最内层iframe文档和窗口（改进：添加更多调试信息）
  function getInnerFrame(doc, maxDepth) {
    maxDepth = maxDepth || 3;
    if (maxDepth <= 0) return null;
    
    result.debug.push('getInnerFrame: depth=' + maxDepth + ', doc=' + (doc ? 'exists' : 'null'));
    
    var iframes = doc.querySelectorAll('iframe');
    result.debug.push('找到 ' + iframes.length + ' 个iframe');
    
    var innerResult = null;
    for (var i = 0; i < iframes.length; i++) {
      try {
        var iframe = iframes[i];
        var innerDoc = iframe.contentDocument || iframe.contentWindow.document;
        var innerWin = iframe.contentWindow;
        
        if (innerDoc && innerDoc.body) {
          result.debug.push('iframe[' + i + '] 可访问, body子元素: ' + innerDoc.body.children.length);
          
          // 检查是否有表单元素（说明是目标iframe）
          var hasForm = innerDoc.querySelector('select, input, button');
          if (hasForm) {
            result.debug.push('  包含表单元素，可能是目标iframe');
            innerResult = { doc: innerDoc, win: innerWin };
          }
          
          // 递归查找更内层
          var deeper = getInnerFrame(innerDoc, maxDepth - 1);
          if (deeper && deeper.doc.querySelector('select[name="SSQX"], input[name="KSSJ"]')) {
            result.debug.push('  递归找到包含筛选表单的iframe');
            return deeper;
          }
          if (deeper) {
            result.debug.push('  递归找到iframe（但未必是目标）');
            innerResult = deeper;
          }
        }
      } catch (e) {
        result.debug.push('iframe[' + i + '] 跨域无法访问: ' + e.message);
      }
    }
    return innerResult;
  }

  // 获取iframe上下文
  var ifrCenter = document.getElementById('ifr_center');
  var ctx = null;
  if (ifrCenter) {
    try {
      var centerDoc = ifrCenter.contentDocument;
      if (centerDoc) ctx = getInnerFrame(centerDoc, 2);
    } catch (e) {}
  }
  if (!ctx) {
    ctx = getInnerFrame(document, 3);
  }

  if (!ctx) {
    result.error = '无法找到包含筛选表单的iframe';
    return JSON.stringify(result);
  }

  var doc = ctx.doc;
  var win = ctx.win;
  result.steps.push('找到目标iframe');

  // 设置省份 SSSF
  try {
    var sssf = doc.querySelector('select[name="SSSF"], #SSSF');
    if (sssf) {
      sssf.value = config.SSSF;
      // 触发change事件(三级联动需要)
      var event = new Event('change', { bubbles: true });
      sssf.dispatchEvent(event);
      result.steps.push('设置省份: ' + config.SSSF);
    }
  } catch (e) {
    result.steps.push('设置省份失败: ' + e.message);
  }

  // 设置地市 SSDS
  try {
    var ssds = doc.querySelector('select[name="SSDS"], #SSDS');
    if (ssds) {
      // 等待联动加载完成(同步设置可能不生效,尝试直接设置value)
      ssds.value = config.SSDS;
      var event = new Event('change', { bubbles: true });
      ssds.dispatchEvent(event);
      result.steps.push('设置地市: ' + config.SSDS);
    }
  } catch (e) {
    result.steps.push('设置地市失败: ' + e.message);
  }

  // 设置区县 SSQX
  try {
    var ssqx = doc.querySelector('select[name="SSQX"], #SSQX');
    if (ssqx) {
      ssqx.value = config.SSQX;
      var event = new Event('change', { bubbles: true });
      ssqx.dispatchEvent(event);
      result.steps.push('设置区县: ' + config.SSQX);
    }
  } catch (e) {
    result.steps.push('设置区县失败: ' + e.message);
  }

  // 设置开始时间 KSSJ
  try {
    var kssj = doc.querySelector('input[name="KSSJ"], #KSSJ');
    if (kssj) {
      // 移除readonly限制
      kssj.removeAttribute('readonly');
      kssj.value = config.KSSJ;
      var event = new Event('change', { bubbles: true });
      kssj.dispatchEvent(event);
      result.steps.push('设置开始时间: ' + config.KSSJ);
    }
  } catch (e) {
    result.steps.push('设置开始时间失败: ' + e.message);
  }

  // 设置结束时间 JSSJ
  try {
    var jssj = doc.querySelector('input[name="JSSJ"], #JSSJ');
    if (jssj) {
      jssj.removeAttribute('readonly');
      jssj.value = config.JSSJ;
      var event = new Event('change', { bubbles: true });
      jssj.dispatchEvent(event);
      result.steps.push('设置结束时间: ' + config.JSSJ);
    }
  } catch (e) {
    result.steps.push('设置结束时间失败: ' + e.message);
  }

  // 触发查询
  try {
    if (typeof win.searchQhdcRecord === 'function') {
      win.searchQhdcRecord();
      result.steps.push('调用searchQhdcRecord()查询');
    } else if (typeof win.query === 'function') {
      win.query();
      result.steps.push('调用query()查询');
    } else {
      // 尝试点击查询按钮
      var searchBtn = doc.querySelector('button[onclick*="search"], a[onclick*="search"], .search-btn');
      if (searchBtn) {
        searchBtn.click();
        result.steps.push('点击查询按钮');
      } else {
        result.steps.push('未找到查询函数或按钮');
      }
    }
  } catch (e) {
    result.steps.push('查询失败: ' + e.message);
  }

  result.success = true;
  return JSON.stringify(result);
})()
