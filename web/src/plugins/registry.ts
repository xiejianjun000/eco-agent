import type { ReactElement, ComponentType } from 'react';

/**
 * 前端插件注册表 —— 对标 DSH（deepseek-harness）的「一切皆插件 / Slot UI」哲学。
 *
 * DSH 用 Cordis patch 把前端模块注入 Web UI；eco-Agent 前端以本注册表为等价机制：
 * 每个前端插件向「左侧导航栏」贡献页面、向「右侧 ContextPanel」贡献配置卡片，外壳
 * （App / SidePanel）只负责组合，不持有任何特权的硬编码页面。新增一个领域面板 =
 * 注册一个插件，无需改外壳。
 *
 * 右侧栏严格对标 WorkBuddy 的 ContextPanel：header（标题 + 折叠键）+ 垂直配置卡片栈，
 * 每张卡片 = 一个领域实体（指令 / 连接 / 专家团 / 技能 / 自动化 / 仓库）。
 */

/** 外壳传给插件视图的上下文（会话态由外壳持有，插件按需取用） */
export interface AppCtx {
  sessionId: string;
  /** 强制作 ChatView 重挂载的 nonce（删除当前会话等场景） */
  chatNonce: number;
  /** 通知外壳刷新会话列表 */
  onActivity: () => void;
  /** WorkBuddy 式 ContextPanel（右侧生态上下文）是否展开；展开时 ChatView 内联输出面板让位，避免双右栏 */
  rightPanelOpen: boolean;
}

/** 左侧导航栏贡献项 */
export interface NavContribution {
  id: string;
  label: string;
  desc?: string;
  order?: number;
  /** SVG 图标（禁止 emoji），见 icons.tsx */
  icon: ReactElement;
  /** 渲染该导航对应的中栏视图；可基于 ctx 注入会话态 */
  mount: (ctx: AppCtx) => ReactElement | null;
}

/** 右侧 ContextPanel 配置卡片贡献项（对标 WorkBuddy 的 wb-config-card） */
export interface SideCardContribution {
  id: string;
  /** 卡片标题（如「专家团」），对标 WorkBuddy 卡片标题 13px/Medium */
  title: string;
  /** 未配置态描述文案（12px/tertiary），对标 WorkBuddy ConfigCardEmpty */
  desc?: string;
  order?: number;
  /** SVG 图标（禁止 emoji） */
  icon: ReactElement;
  /** 已配置态：自定义卡片内容（头像列 / 任务列表等）；缺省走 empty 态 */
  body?: ReactElement;
  /** 点击卡片 / 右上角 PlusIcon 的回调（打开对应配置面板） */
  onOpen?: () => void;
}

const navItems: NavContribution[] = [];
const sideCards: SideCardContribution[] = [];

/** 注册左侧导航插件（同名 id 覆盖，便于热重载/测试） */
export function registerNav(...items: NavContribution[]): void {
  for (const it of items) {
    const i = navItems.findIndex((x) => x.id === it.id);
    if (i >= 0) navItems[i] = it;
    else navItems.push(it);
  }
}

/** 注册右侧 ContextPanel 配置卡片（同名 id 覆盖） */
export function registerSideCard(...cards: SideCardContribution[]): void {
  for (const c of cards) {
    const i = sideCards.findIndex((x) => x.id === c.id);
    if (i >= 0) sideCards[i] = c;
    else sideCards.push(c);
  }
}

/** 取全部导航项（按 order 升序） */
export function getNavItems(): NavContribution[] {
  return [...navItems].sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
}

/** 按 id 取导航项 */
export function getNavById(id: string): NavContribution | undefined {
  return navItems.find((x) => x.id === id);
}

/** 取全部右侧配置卡片（按 order 升序） */
export function getSideCards(): SideCardContribution[] {
  return [...sideCards].sort((a, b) => (a.order ?? 99) - (b.order ?? 99));
}
