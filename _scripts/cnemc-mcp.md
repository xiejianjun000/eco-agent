# CNEMC govMCP — 中国环境监测总站空气质量六参数服务

## 简介

将总站"全国城市空气质量实时发布平台"（air.cnemc.cn:18007 公开接口）封装为
**govMCP 服务**（等保加固的 MCP：SM3 不可篡改审计 + 只读语义）。

| 工具 | 能力 |
|------|------|
| `cnemc_air_quality(city)` | 城市实时六参数（PM2.5/PM10/SO2/NO2/CO/O3）+ AQI + 首要污染物 + 等级 |
| `cnemc_city_list()` | 可查询城市列表 |
| `cnemc_aqi_level(aqi)` | AQI 数值 → 等级/类别/健康提示（HJ 633-2012 六档） |

## 接入方式（任意 MCP 客户端）

```json
{
  "mcpServers": {
    "cnemc": {
      "command": "python3",
      "args": ["_scripts/cnemc-mcp.py"],
      "cwd": "/path/to/eco-agent"
    }
  }
}
```

Cursor（.cursor/mcp.json）、Claude Desktop、Cherry Studio 等按各自格式填入即可。

## 等保加固

- 每次调用写 **govmcp SM3 审计链**：`memory-tree/data/audit/cnemc_mcp_audit.jsonl`
  （prev_hash/current_hash 衔接，可整体校验防篡改）
- 数据源只读公开接口，无写操作、无敏感数据
- 失败如实报错（`CNEMCError`），含缓存降级（data_source=cache 标注）

## 自检

```bash
python3 _scripts/cnemc-mcp.py --selftest
```
