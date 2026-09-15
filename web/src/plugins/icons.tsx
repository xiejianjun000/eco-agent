import React from 'react';

/**
 * 前端 SVG 图标库 —— 替代 emoji 功能图标（专家团 P0-1 规则：禁止 emoji 功能图标）。
 * 全部使用 currentColor + stroke，跟随主题；尺寸由调用处控制。
 */

type IconProps = { size?: number };

function svgProps(size: number): React.SVGProps<SVGSVGElement> {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  } as React.SVGProps<SVGSVGElement>;
}

/** 生态助手 / 对话 —— 叶 */
export const IconLeaf = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M5 21c0-9 5-14 14-14 0 9-5 14-14 14Z" />
    <path d="M5 21c2-6 6-10 12-12" />
  </svg>
);

/** 生态空间 / 记忆 —— 地图 */
export const IconMap = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" />
    <path d="M9 4v14M15 6v14" />
  </svg>
);

/** 生态技能 —— 扳手 */
export const IconTool = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M21 4a5 5 0 0 1-6.5 6.5L5 20l-1-1 9.5-9.5A5 5 0 0 1 20 3l1 1Z" />
    <path d="M16 9l-2-2" />
  </svg>
);

/** 生态助手目录 —— 机器人 */
export const IconRobot = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <rect x="5" y="8" width="14" height="11" rx="2" />
    <path d="M12 8V4M9.5 4h5" />
    <circle cx="9.5" cy="13" r="1" />
    <circle cx="14.5" cy="13" r="1" />
  </svg>
);

/** 生态目标 —— 靶心 */
export const IconTarget = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="12" cy="12" r="1" />
  </svg>
);

/** 生态编排 —— 闪电 */
export const IconBolt = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
  </svg>
);

/** 生态插件 —— 插头 */
export const IconPlug = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M9 3v5M15 3v5" />
    <path d="M6 8h12v3a6 6 0 0 1-12 0V8Z" />
    <path d="M12 17v4" />
  </svg>
);

/** 旅行地图 —— 地球 */
export const IconGlobe = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" />
  </svg>
);

/** 系统 —— 齿轮 */
export const IconGear = ({ size = 18 }: IconProps) => (
  <svg {...svgProps(size)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" />
  </svg>
);

/** 主题切换 —— 太阳 */
export const IconSun = ({ size = 15 }: IconProps) => (
  <svg {...svgProps(size)}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" />
  </svg>
);

/** 主题切换 —— 月亮 */
export const IconMoon = ({ size = 15 }: IconProps) => (
  <svg {...svgProps(size)}>
    <path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10Z" />
  </svg>
);

/** 折叠/展开 —— 右箭头（收起面板 / 右栏轨道按钮） */
export const IconChevronRight = ({ size = 16 }: IconProps) => (
  <svg {...svgProps(size)} strokeWidth={2}>
    <path d="M9 5l7 7-7 7" />
  </svg>
);

/** 折叠/展开 —— 左箭头（展开面板） */
export const IconChevronLeft = ({ size = 16 }: IconProps) => (
  <svg {...svgProps(size)} strokeWidth={2}>
    <path d="M15 5l-7 7 7 7" />
  </svg>
);

/** 卡片添加 —— 加号（对标 WorkBuddy 配置卡片右上角 PlusIcon 20×20） */
export const IconPlus = ({ size = 16 }: IconProps) => (
  <svg {...svgProps(size)} strokeWidth={2}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
