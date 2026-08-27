# 大气监督帮扶督办整改技能 - 实战使用示例 ⚡

> **重要说明**：本文件提供详细的使用示例，展示如何实际调用本技能的浏览器自动化脚本。
> 
> 所有脚本都通过OpenClaw的`browser`工具执行，脚本路径：`scripts/`目录下。

---

## 目录

1. [示例1：导航到督办整改页面](#示例1导航到督办整改页面)
2. [示例2：设置筛选条件并查询](#示例2设置筛选条件并查询)
3. [示例3：提取datagrid数据](#示例3提取datagrid数据)
4. [示例4：查看检查详情](#示例4查看检查详情)
5. [示例5：端到端完整流程](#示例5端到端完整流程)
6. [示例6：批量采集多个区县](#示例6批量采集多个区县)
7. [常见问题排查](#常见问题排查)

---

## 示例1：导航到督办整改页面

### 目标
自动登录并导航到督办整改页面

### 步骤

```javascript
// Step 1: 打开浏览器并登录
var browserResult = await browser({
  action: "open",
  profile: "openclaw",
  targetUrl: "http://114.251.10.199:8080/zfpt_zf/redirect.jsp"
});

// Step 2: 获取当前tab的targetId（重要！不要用硬编码的targetId）
var tabsResult = await browser({ action: "tabs" });
var targetId = tabsResult.tabs[0].id; // 获取第一个tab的ID

// Step 3: 执行导航脚本
var navigateScript = await read({ path: "/Users/mac/.qclaw/skills/supervision-rectification-workflow/scripts/navigate.js" });

var navResult = await browser({
  action: "act",
  kind: "evaluate",
  targetId: targetId,
  fn: navigateScript.content
});

// Step 4: 解析结果
var result = JSON.parse(navResult.result);
if (result.success) {
  console.log("✅ 导航成功：" + result.steps.join(", "));
} else {
  console.error("❌ 导航失败：" + result.error);
}
```

### 预期结果
- 浏览器自动登录系统
- 成功点击"任务台账 → 督查信息 → 督办整改"菜单
- 页面跳转到督办整改列表页面

### 注意事项
- **不要硬编码targetId**！每次会话的targetId都不同，必须用`browser({ action: "tabs" })`获取
- 如果导航失败，检查：
  1. 是否已登录（检查浏览器cookie）
  2. 页面是否有iframe嵌套（脚本已处理三层iframe嵌套）
  3. 菜单项名称是否正确（"督办整改"）

---

## 示例2：设置筛选条件并查询

### 目标
筛选湖南省娄底市冷水江市2026年1-5月的数据

### 步骤

```javascript
// Step 1: 读取并设置筛选脚本（修改配置）
var setFiltersScript = await read({ path: "/Users/mac/.qclaw/skills/supervision-rectification-workflow/scripts/set-filters.js" });

// Step 2: 修改配置（可选，脚本内部有默认值）
var modifiedScript = setFiltersScript.content
  .replace("431381", "431381") // 冷水江市（默认值就是431381，无需修改）
  .replace("2026-01-01", "2026-01-01") // 开始时间
  .replace("2026-05-31", "2026-05-31"); // 结束时间

// Step 3: 执行脚本
var filterResult = await browser({
  action: "act",
  kind: "evaluate",
  targetId: targetId,
  fn: modifiedScript
});

// Step 4: 解析结果
var result = JSON.parse(filterResult.result);
console.log("✅ 筛选步骤：" + result.steps.join("; "));

// Step 5: 等待页面加载（重要！）
await new Promise(resolve => setTimeout(resolve, 3000));
```

### 配置参数说明

```javascript
var config = {
  SSSF: '430000',   // 省份编码（湖南省）
  SSDS: '431300',   // 地市编码（娄底市）
  SSQX: '431381',   // 区县编码（冷水江市）
  KSSJ: '2026-01-01', // 开始时间（格式：YYYY-MM-DD）
  JSSJ: '2026-05-31'  // 结束时间（格式：YYYY-MM-DD）
};
```

### 地区编码参考

| 地区 | 编码 |
|------|------|
| **湖南省** | 430000 |
| 娄底市 | 431300 |
| ├─ 娄星区 | 431302 |
| ├─ 双峰县 | 431321 |
| ├─ 新化县 | 431322 |
| ├─ 冷水江市 | 431381 |
| └─ 涟源市 | 431382 |

### 预期结果
- 省份下拉框自动选择"湖南省"
- 地市下拉框自动选择"娄底市"
- 区县下拉框自动选择"冷水江市"
- 开始时间和结束时间自动填充
- 自动触发查询，页面显示筛选结果

### 注意事项
- **三级联动**：省份→地市→区县是联动的，脚本会自动触发`change`事件
- **等待加载**：设置筛选条件后，必须等待页面加载完成再提取数据
- **时间格式**：必须是`YYYY-MM-DD`格式，否则EasyUI可能无法识别

---

## 示例3：提取datagrid数据

### 目标
提取当前页面的所有记录

### 步骤

```javascript
// Step 1: 读取提取脚本
var extractScript = await read({ path: "/Users/mac/.qclaw/skills/supervision-rectification-workflow/scripts/extract-data.js" });

// Step 2: 执行提取
var extractResult = await browser({
  action: "act",
  kind: "evaluate",
  targetId: targetId,
  fn: extractScript.content
});

// Step 3: 解析结果
var result = JSON.parse(extractResult.result);
console.log("✅ 提取到 " + result.rows.length + " 条记录，总共 " + result.total + " 条");

// Step 4: 处理分页（如果有）
if (result.total > result.rows.length) {
  var totalPages = Math.ceil(result.total / result.pageSize);
  console.log("📄 共 " + totalPages + " 页，开始翻页提取...");
  
  for (var page = 2; page <= totalPages; page++) {
    console.log("  提取第 " + page + "/" + totalPages + " 页...");
    
    // 翻页（调用EasyUI API）
    await browser({
      action: "act",
      kind: "evaluate",
      targetId: targetId,
      fn: "$('#datagridId').datagrid('gotoPage', " + page + ");"
    });
    
    // 等待加载
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // 再次提取
    var pageResult = await browser({
      action: "act",
      kind: "evaluate",
      targetId: targetId,
      fn: extractScript.content
    });
    
    var pageData = JSON.parse(pageResult.result);
    result.rows = result.rows.concat(pageData.rows);
  }
}

console.log("✅ 全部提取完成，共 " + result.rows.length + " 条记录");
```

### 数据字段说明

提取的数据包含以下字段（根据实际datagrid列而定）：

| 字段名 | 说明 | 示例 |
|--------|------|------|
| 企业名称 | 被检查企业名称 | "冷水江三A新材料科技有限公司" |
| 统一社会信用代码 | 企业信用代码 | "91431381187523361L" |
| 问题类别 | 问题分类 | "污染源自动监测类" |
| 问题类型 | 具体问题描述 | "未安装污染源自动监测设备" |
| 检查时间 | 现场检查时间 | "2026-03-20" |
| 轮次 | 监督帮扶轮次 | "2026005" |
| 是否完成整改 | 整改状态 | "是" / "否" |
| 省级审核 | 省级审核状态 | "通过" / "不通过" / "待审核" |
| 部级审核 | 部级审核状态 | "通过" / "不通过" / "待审核" |
| _links | 操作链接（如"查看检查"） | `[{ text: "查看检查", onclick: "jcxx(...)" }]` |

### 预期结果
- 返回当前页的所有记录（JSON格式）
- 如果有多页，自动翻页提取全部数据
- 数据保存为JSON数组，可直接用于分析

### 注意事项
- **虚拟渲染**：EasyUI datagrid默认只渲染可见行，脚本已处理这个问题（优先使用API方式`$('#dg').datagrid('getRows')`）
- **分页处理**：如果`result.total > result.rows.length`，说明有多页，需要翻页
- **性能优化**：每次翻页后等待2-3秒，避免请求过快被封IP

---

## 示例4：查看检查详情

### 目标
查看第一条记录的详细信息

### 步骤

```javascript
// Step 1: 读取查看详情脚本
var viewDetailsScript = await read({ path: "/Users/mac/.qclaw/skills/supervision-rectification-workflow/scripts/view-details.js" });

// Step 2: 修改行索引（可选，默认查看第一行）
var modifiedScript = viewDetailsScript.content.replace("__ROW_INDEX__", "0");

// Step 3: 执行脚本（打开弹窗）
var viewResult = await browser({
  action: "act",
  kind: "evaluate",
  targetId: targetId,
  fn: modifiedScript
});

// Step 4: 等待弹窗加载
await new Promise(resolve => setTimeout(resolve, 2000));

// Step 5: 提取弹窗内容
var extractDetailScript = `
(function() {
  var detail = {};
  var dialog = document.querySelector('.window, .panel-body, .dialog');
  if (dialog) {
    var tables = dialog.querySelectorAll('table');
    for (var t = 0; t < tables.length; t++) {
      var cells = tables[t].querySelectorAll('td, th');
      for (var c = 0; c < cells.length; c++) {
        var text = cells[c].textContent.trim();
        if (text) detail['field_' + c] = text;
      }
    }
  }
  return JSON.stringify(detail);
})()
`;

var detailResult = await browser({
  action: "act",
  kind: "evaluate",
  targetId: targetId,
  fn: extractDetailScript
});

var detail = JSON.parse(detailResult.result);
console.log("✅ 检查详情：", detail);
```

### 检查详情字段说明

| 字段名 | 说明 | 示例 |
|--------|------|------|
| 检查时间 | 现场检查时间 | "2026-03-20 14:30" |
| 检查人员 | 监督帮扶人员 | "张某、李某" |
| 问题描述 | 现场发现的问题 | "未安装污染源自动监测设备" |
| 整改要求 | 整改要求和时间 | "30日内完成安装" |
| 现场照片 | 照片附件链接 | "photo1.jpg, photo2.jpg" |
| 整改方案 | 整改方案附件 | "整改方案.pdf" |

### 预期结果
- 点击"查看检查"链接，打开详情弹窗
- 提取弹窗中的检查详情信息
- 返回JSON格式的检查详情数据

### 注意事项
- **弹窗在iframe内部**：脚本已处理iframe嵌套问题
- **等待加载**：点击后必须等待2秒，让弹窗加载完成
- **关闭弹窗**：查看完后，需要点击弹窗右上角的"×"关闭

---

## 示例5：端到端完整流程

### 目标
自动化完成从登录到生成报告的完整流程

### 步骤

```javascript
// 完整流程封装函数
async function executeFullWorkflow(config) {
  var results = { steps: [], data: null, report: null };
  
  try {
    // Step 1: 登录并导航
    results.steps.push("1. 登录系统");
    var openResult = await browser({
      action: "open",
      profile: "openclaw",
      targetUrl: "http://114.251.10.199:8080/zfpt_zf/redirect.jsp"
    });
    
    var tabsResult = await browser({ action: "tabs" });
    var targetId = tabsResult.tabs[0].id;
    
    results.steps.push("2. 导航到督办整改");
    var navScript = await read({ path: "scripts/navigate.js" });
    await browser({ action: "act", kind: "evaluate", targetId: targetId, fn: navScript.content });
    
    // Step 2: 设置筛选条件
    results.steps.push("3. 设置筛选条件");
    var filterScript = await read({ path: "scripts/set-filters.js" });
    // 修改配置...
    await browser({ action: "act", kind: "evaluate", targetId: targetId, fn: filterScript.content });
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // Step 3: 提取数据
    results.steps.push("4. 提取数据");
    var extractScript = await read({ path: "scripts/extract-data.js" });
    var extractResult = await browser({ action: "act", kind: "evaluate", targetId: targetId, fn: extractScript.content });
    var data = JSON.parse(extractResult.result);
    
    // 处理分页...
    
    // Step 4: 查看详情（可选）
    if (config.viewDetails) {
      results.steps.push("5. 查看检查详情");
      // ...
    }
    
    // Step 5: 生成报告
    results.steps.push("6. 生成分析报告");
    var report = generateReport(data);
    
    results.data = data;
    results.report = report;
    results.success = true;
    
  } catch (error) {
    results.error = error.message;
    results.success = false;
  }
  
  return results;
}

// 调用示例
var workflowResult = await executeFullWorkflow({
  region: { province: "430000", city: "431300", county: "431381" },
  timeRange: { start: "2026-01-01", end: "2026-05-31" },
  viewDetails: true
});

console.log("✅  workflow完成：", workflowResult.steps);
```

### 预期结果
- 自动完成登录 → 导航 → 筛选 → 提取 → 生成报告
- 返回结构化的结果数据和分析报告

---

## 示例6：批量采集多个区县

### 目标
自动采集娄底市下所有区县的督办整改数据

### 步骤

```javascript
// 批量采集配置
var batchConfig = {
  province: "430000",
  city: "431300",
  counties: [
    { code: "431302", name: "娄星区" },
    { code: "431321", name: "双峰县" },
    { code: "431322", name: "新化县" },
    { code: "431381", name: "冷水江市" },
    { code: "431382", name: "涟源市" }
  ],
  timeRange: { start: "2026-01-01", end: "2026-05-31" }
};

// 批量采集函数
async function batchCollect(config) {
  var allData = [];
  
  for (var i = 0; i < config.counties.length; i++) {
    var county = config.counties[i];
    console.log("📥 采集 " + county.name + " (" + county.code + ")...");
    
    // 1. 设置筛选条件（修改set-filters.js中的SSQX）
    var filterScript = await read({ path: "scripts/set-filters.js" });
    var modifiedFilter = filterScript.content.replace(/SSQX:\s*'\d+'/g, "SSQX: '" + county.code + "'");
    
    await browser({ action: "act", kind: "evaluate", targetId: targetId, fn: modifiedFilter });
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // 2. 提取数据
    var extractScript = await read({ path: "scripts/extract-data.js" });
    var extractResult = await browser({ action: "act", kind: "evaluate", targetId: targetId, fn: extractScript.content });
    var data = JSON.parse(extractResult.result);
    
    // 3. 添加区县标识
    data.rows.forEach(row => row["_区县"] = county.name);
    allData = allData.concat(data.rows);
    
    console.log("  ✅ 采集到 " + data.rows.length + " 条记录");
  }
  
  // 保存汇总数据
  await write({ path: "批量采集_" + config.city + "_" + Date.now() + ".json", content: JSON.stringify(allData, null, 2) });
  
  return allData;
}

// 执行批量采集
var batchData = await batchCollect(batchConfig);
console.log("✅ 批量采集完成，共 " + batchData.length + " 条记录");
```

### 预期结果
- 自动遍历所有区县
- 每个区县自动设置筛选条件、提取数据
- 所有数据汇总保存为一个JSON文件

### 注意事项
- **延时**：每次查询后等待3秒，避免被封IP
- **错误处理**：如果某个区县采集失败，记录错误并继续下一个
- **数据去重**：如果区县之间有重叠数据，需要去重

---

## 常见问题排查 🔧

### Q1: 脚本执行后没有效果？

**原因**：
- targetId不正确
- 页面未加载完成
- 脚本内部报错

**解决**：
```javascript
// 1. 使用browser({ action: "tabs" })获取当前tab的targetId
var tabsResult = await browser({ action: "tabs" });
var targetId = tabsResult.tabs[0].id;

// 2. 在执行脚本前添加等待
await new Promise(resolve => setTimeout(resolve, 3000));

// 3. 检查浏览器控制台是否有错误
var consoleResult = await browser({ action: "console", targetId: targetId });
console.log(consoleResult.logs);
```

---

### Q2: 无法找到iframe内部元素？

**原因**：
- 跨域iframe无法访问
- iframe尚未加载完成
- 脚本的递归查找深度不够

**解决**：
```javascript
// 1. 检查iframe是否同源（查看iframe.src）
var iframeSrc = document.querySelector('iframe').src;
console.log(iframeSrc); // 如果是about:blank或不同域名，说明跨域

// 2. 等待iframe加载
await new Promise(resolve => setTimeout(resolve, 2000));

// 3. 增加递归查找深度（修改脚本中的maxDepth参数）
function getInnerFrame(doc, maxDepth) {
  maxDepth = maxDepth || 5; // 从3改为5
  // ...
}
```

---

### Q3: EasyUI datagrid提取数据不全？

**原因**：
- 虚拟渲染导致只渲染可见行
- 分页数据未全部提取

**解决**：
```javascript
// 1. 优先使用API方式
var rows = $('#datagridId').datagrid('getRows'); // 获取全部行（不受虚拟渲染影响）

// 2. 降级到DOM遍历（脚本中已内置）
var btable = document.querySelector('.datagrid-btable');
var trs = btable.querySelectorAll('tr');

// 3. 处理分页
var totalPages = Math.ceil(result.total / result.pageSize);
for (var page = 2; page <= totalPages; page++) {
  $('#datagridId').datagrid('gotoPage', page);
  await new Promise(resolve => setTimeout(resolve, 2000));
  // 提取当前页数据...
}
```

---

### Q4: 导出功能无法触发？

**原因**：
- 导出按钮可能在toolbar或iframe内部
- 浏览器拦截了下载弹窗
- 导出函数不存在

**解决**：
```javascript
// 1. 尝试4种导出方法（脚本中已内置）
// 方法1：点击导出按钮
var exportBtn = innerDoc.querySelector('button:contains("导出")');
if (exportBtn) exportBtn.click();

// 方法2：调用导出函数
if (typeof innerWin.exportData === 'function') innerWin.exportData();

// 方法3：通过toolbar点击导出
var toolbar = innerDoc.querySelector('.datagrid-toolbar');
var btns = toolbar.querySelectorAll('a, button');
for (var i = 0; i < btns.length; i++) {
  if (btns[i].textContent.indexOf('导出') >= 0) btns[i].click();
}

// 方法4：模拟表单提交导出
var exportUrl = opts.url.replace('list', 'export');
var downloadFrame = document.createElement('iframe');
downloadFrame.src = exportUrl + '?exportType=excel';
document.body.appendChild(downloadFrame);

// 2. 检查是否有下载弹窗被浏览器拦截
// 在浏览器设置中允许自动下载

// 3. 使用browser工具的download action管理下载
var downloads = await browser({ action: "download", targetId: targetId });
console.log(downloads.files);
```

---

## 总结

本示例文档展示了如何实际使用`supervision-rectification-workflow`技能的浏览器自动化脚本。

**核心要点**：
1. **不要硬编码targetId** - 每次会话都用`browser({ action: "tabs" })`获取
2. **等待页面加载** - 每次操作后用`await new Promise(resolve => setTimeout(resolve, 3000))`等待
3. **处理分页** - 如果数据有多页，必须翻页提取全部
4. **错误处理** - 所有脚本都有try-catch，但调用时也要加try-catch

**下一步**：
1. 根据实际使用场景，调整脚本配置
2. 测试端到端流程，确保无误
3. 如有问题，参考"常见问题排查"章节

---

**文件版本**：v1.0.0  
**最后更新**：2026-05-25  
**作者**：小虾米
