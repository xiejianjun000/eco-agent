// 辖区地图 mock 数据 —— 锚定 design/map.md

export type PointStatus = 'over' | 'case' | 'normal';

export interface MapPoint {
  id: string;
  name: string;
  x: number; // 百分比坐标
  y: number;
  status: PointStatus;
  label?: string; // 红点脉冲标签
  permitNo: string;
  industry: string;
  over30: number;
  openCases: number;
}

export const mapPoints: MapPoint[] = [
  { id: 'jinzhushan', name: '金竹山矿业有限公司', x: 32, y: 40, status: 'over', label: 'CEMS 24 次超标', permitNo: '91431381MA4LXXXX1A', industry: '采矿 · 煤炭', over30: 24, openCases: 1 },
  { id: 'yinghu', name: '赢湖矿产品加工厂', x: 58, y: 30, status: 'case', permitNo: '91431381MA4LXXXX2B', industry: '建材', over30: 0, openCases: 0 },
  { id: 'heqing', name: '禾青镇页岩砖厂', x: 70, y: 58, status: 'case', permitNo: '91431381MA4LXXXX3C', industry: '建材 · 砖瓦', over30: 0, openCases: 1 },
  { id: 'xinshun', name: '鑫顺建材有限公司', x: 45, y: 66, status: 'case', permitNo: '91431381MA4LXXXX4D', industry: '建材', over30: 0, openCases: 1 },
  { id: 'ruilong', name: '瑞龙木艺厂', x: 24, y: 72, status: 'case', permitNo: '91431381MA4LXXXX5E', industry: '木艺', over30: 0, openCases: 1 },
  { id: 'changhong', name: '冷水江市长宏陶瓷', x: 80, y: 42, status: 'normal', permitNo: '91431381MA4LXXXX6F', industry: '建材', over30: 0, openCases: 0 },
  { id: 'duoshan', name: '铎山金属制品厂', x: 62, y: 74, status: 'over', permitNo: '91431381MA4LXXXX7G', industry: '金属制品', over30: 3, openCases: 1 },
  { id: 'zhonglian', name: '中连乡石料场', x: 38, y: 22, status: 'normal', permitNo: '91431381MA4LXXXX8H', industry: '采矿 · 石料', over30: 0, openCases: 0 },
];

export const stations = [
  { id: 's1', name: '资江断面 A', x: 48, y: 18 },
  { id: 's2', name: '资江断面 B', x: 66, y: 46 },
  { id: 's3', name: '涟溪断面', x: 30, y: 60 },
];

export const pointStatusMeta: Record<PointStatus, { cls: string; label: string }> = {
  over: { cls: 'red', label: '当前超标' },
  case: { cls: 'amber', label: '有未结案件' },
  normal: { cls: 'olive', label: '正常' },
};

export interface MapTask {
  id: string;
  title: string;
  time: string;
  type: string;
  pointId: string;
}
export const mapTasks: MapTask[] = [
  { id: 't1', title: '赢湖矿产品现场复查', time: '10:00', type: '督察复查', pointId: 'yinghu' },
  { id: 't2', title: '禾青镇页岩砖厂 送达核查', time: '14:00', type: '送达节点', pointId: 'heqing' },
  { id: 't3', title: '金竹山矿业 询问调查', time: '16:00', type: '执法检查', pointId: 'jinzhushan' },
];

export interface OverEvent {
  id: string;
  time: string;
  name: string;
  factor: string;
  mult: string;
  seq?: string;
}
export const overEvents: OverEvent[] = [
  { id: 'o1', time: '8/2 22:14', name: '金竹山矿业', factor: '烟尘', mult: '超标 2.1 倍', seq: '（第24次）' },
  { id: 'o2', time: '8/1 03:40', name: '铎山金属制品厂', factor: 'NOx', mult: '超标 1.6 倍' },
  { id: 'o3', time: '7/31 21:05', name: '金竹山矿业', factor: 'SO₂', mult: '超标 1.9 倍', seq: '（第23次）' },
];

export const aiSelectResult = '圈内 8 家企业，2 家近 30 天有超标，建议优先检查金竹山矿业。';
export const heatSuggestion = '禾青镇覆盖率偏低，建议下周安排 2 次巡查。';
