import React from 'react';
import {
  registerNav, registerSideCard, type AppCtx, type SideCardContribution,
} from './registry';
import {
  IconLeaf, IconMap, IconTool, IconRobot, IconTarget,
  IconBolt, IconPlug, IconGlobe, IconGear,
  IconPlus,
} from './icons';
import ChatView from '../views/ChatView';
import MemoryView from '../views/MemoryView';
import SkillsView from '../views/SkillsView';
import AgentsView from '../views/AgentsView';
import GoalsView from '../views/GoalsView';
import WorkflowView from '../views/WorkflowView';
import PluginsView from '../views/PluginsView';
import SystemView from '../views/SystemView';

/**
 * 内置前端插件注册 —— 把既有 9 个页面与右侧 ContextPanel 的 6 类领域配置卡片登记进插件注册表。
 * 这是「前端一切皆插件」的第一批贡献者；未来新增领域面板只需在此（或独立插件文件）登记。
 */

const StarMapFrame = () => (
  <div className="starmap-frame">
    <iframe
      src="http://127.0.0.1:5175/"
      title="StarMap 旅行足迹地图"
      style={{ width: '100%', height: '100%', border: 0 }}
      allow="geolocation; clipboard-write"
    />
  </div>
);

/** 专家团卡片的已配置态内容（filled）：列出已注册领域团队 */
const ExpertTeams = () => (
  <div className="sc-chip-row">
    {['大气溯源', '执法', '信访', 'EIA审查'].map((t) => (
      <span className="sc-chip" key={t}>{t}</span>
    ))}
  </div>
);

/** 右侧 ContextPanel 的 6 类领域配置卡片（对标 WorkBuddy 的 wb-config-card） */
const SIDE_CARDS: SideCardContribution[] = [
  {
    id: 'instruction', title: '指令', order: 0, icon: <IconLeaf />,
    desc: '领域系统提示与生态法典要点',
    onOpen: () => {},
  },
  {
    id: 'connector', title: '连接', order: 1, icon: <IconPlug />,
    desc: 'govMCP 四源 / CNEMC 实时 / 国家水环境·监督帮扶平台',
    onOpen: () => {},
  },
  {
    id: 'expert', title: '专家团', order: 2, icon: <IconRobot />,
    desc: '大气溯源10-Agent / 执法 / 信访 / EIA 审查团队',
    body: <ExpertTeams />,
    onOpen: () => {},
  },
  {
    id: 'skill', title: '技能', order: 3, icon: <IconTool />,
    desc: '生态法典库 / GB·HJ 标准库 / 案卷评查门禁',
    onOpen: () => {},
  },
  {
    id: 'automation', title: '自动化', order: 4, icon: <IconBolt />,
    desc: '双平台巡检 / 定时舆情与数据巡检任务',
    onOpen: () => {},
  },
  {
    id: 'repo', title: '仓库', order: 5, icon: <IconGear />,
    desc: '生态代码仓 / 法规知识库（可选挂载）',
    onOpen: () => {},
  },
];

let registered = false;

/** 注册全部内置插件（幂等） */
export function registerBuiltinPlugins(): void {
  if (registered) return;
  registered = true;

  registerNav(
    {
      id: 'chat', label: '生态助手', desc: '与 eco Agent 对话', order: 0, icon: <IconLeaf />,
      mount: (ctx: AppCtx) => (
        <ChatView key={`${ctx.sessionId}:${ctx.chatNonce}`} sessionId={ctx.sessionId} onActivity={ctx.onActivity} rightPanelOpen={ctx.rightPanelOpen} />
      ),
    },
    { id: 'memory', label: '生态空间', desc: '生态环境空间数据与长期记忆检索', order: 1, icon: <IconMap />, mount: () => <MemoryView /> },
    { id: 'skills', label: '生态技能', desc: '生态环境技能库与智能体孵化', order: 2, icon: <IconTool />, mount: () => <SkillsView /> },
    { id: 'agents', label: '生态助手目录', desc: '后台生态助手与任务输出', order: 3, icon: <IconRobot />, mount: () => <AgentsView /> },
    { id: 'goals', label: '生态目标', desc: '跨轮生态目标与自动推进', order: 4, icon: <IconTarget />, mount: () => <GoalsView /> },
    { id: 'workflow', label: '生态编排', desc: '生态环境工作流编排与计划', order: 5, icon: <IconBolt />, mount: () => <WorkflowView /> },
    { id: 'plugins', label: '生态插件', desc: '生态环境插件清单与 MCP 连接器', order: 6, icon: <IconPlug />, mount: () => <PluginsView /> },
    { id: 'starmap', label: '旅行地图', desc: 'StarMap 3D 旅行足迹地图（独立应用内嵌）', order: 7, icon: <IconGlobe />, mount: () => <StarMapFrame /> },
    { id: 'system', label: '系统', desc: '组件状态与生态指标', order: 8, icon: <IconGear />, mount: () => <SystemView /> },
  );

  registerSideCard(...SIDE_CARDS);
}
