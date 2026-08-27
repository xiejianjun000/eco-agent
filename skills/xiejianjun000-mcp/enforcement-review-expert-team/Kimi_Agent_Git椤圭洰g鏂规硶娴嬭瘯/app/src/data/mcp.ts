export type McpStatus = 'connected' | 'off' | 'error';

export interface McpConn {
  id: string;
  name: string;
  desc: string;
  status: McpStatus;
  callsToday?: number;
  lastCall?: string;
  errorMsg?: string;
  endpoint: string;
  auth: string;
  quota: string;
}

export const connections: McpConn[] = [
  {
    id: 'map', name: '地图服务', desc: '为辖区地图与 AI 圈选提供底图',
    status: 'connected', callsToday: 46, lastCall: '08-08 07:02',
    endpoint: 'https://geo.internal/v1', auth: 'Bearer 令牌', quota: '5000 次/日',
  },
  {
    id: 'doc', name: '文档处理服务', desc: '读写 docx/xlsx/pdf，支撑文书协同',
    status: 'connected', callsToday: 132, lastCall: '08-08 07:11',
    endpoint: 'https://doc.internal/v2', auth: 'API Key', quota: '2000 次/日',
  },
  {
    id: 'notify', name: '消息通知服务', desc: '向承办人发送临期提醒',
    status: 'connected', lastCall: '08-08 06:50',
    endpoint: 'https://msg.internal/v1', auth: 'App Secret', quota: '1000 条/日',
  },
  {
    id: 'print', name: '打印服务', desc: '文书直接送打印',
    status: 'off',
    endpoint: '—', auth: '—', quota: '—',
  },
  {
    id: 'backup', name: '数据备份服务', desc: '每日卷宗自动备份',
    status: 'error', errorMsg: '昨晚备份失败，已自动重试 2 次', lastCall: '08-07 23:00',
    endpoint: 'https://bk.internal/v1', auth: 'AK/SK', quota: '无限制',
  },
];

export interface McpLog {
  time: string;
  expert: string;
  tool: string;
  action: string;
  ok: boolean;
}

export const logs: McpLog[] = [
  { time: '07:11', expert: '卷查清', tool: '文档处理服务', action: '读取了决定书草稿.docx 并写入批注', ok: true },
  { time: '07:02', expert: '巡检员', tool: '地图服务', action: '圈选金竹山矿业周边 1km 企业', ok: true },
  { time: '06:50', expert: '督察精', tool: '消息通知服务', action: '向 3 名承办人推送临期提醒', ok: true },
  { time: '06:32', expert: '数据芯', tool: '文档处理服务', action: '导出本月处罚台账.xlsx', ok: true },
  { time: '23:00', expert: '系统', tool: '数据备份服务', action: '执行每日卷宗备份', ok: false },
];

export const statusMeta: Record<McpStatus, { label: string; cls: string }> = {
  connected: { label: '已接通', cls: 'ok' },
  off: { label: '未接通', cls: 'off' },
  error: { label: '异常', cls: 'err' },
};
