#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_core/chart_gen.py — 确定性图表生成器（chart_render 工具内核）
====================================================================
生成完全离线、零依赖的 SVG 交互图表 HTML（内嵌极简 JS tooltip）。
不依赖 CDN/ECharts：政务内网、断网环境同样可渲染。

支持类型：
  line        折线图（单/多系列）
  bar         柱状图（单/多系列，分组柱）
  stacked_bar 堆叠柱状图
  pie         环形饼图（单系列 data 为 [{"name","value"}, ...]）
"""

from __future__ import annotations

import html as _html
import json
import math

PALETTE = ["#0F766E", "#4176E6", "#F59E0B", "#EF4444", "#8A7A9B", "#22C55E",
           "#0EA5E9", "#D946EF"]

_TMPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin:0; font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         background:#fff; color:#0F1115; }}
  .wrap {{ padding: 16px 18px 10px; }}
  .title {{ font-size: 15px; font-weight: 700; margin: 0 0 4px; }}
  .sub {{ font-size: 11px; color:#818588; margin: 0 0 12px; }}
  svg {{ display:block; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:6px 14px; margin: 6px 0 0; }}
  .legend span {{ display:inline-flex; align-items:center; gap:5px; font-size:11.5px; color:#353638; }}
  .legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
  .tip {{ position:fixed; display:none; background:rgba(15,17,21,.92); color:#fff; font-size:11.5px;
          padding:4px 8px; border-radius:6px; pointer-events:none; white-space:nowrap; z-index:9; }}
  .foot {{ font-size:10.5px; color:#ADB2B8; margin-top:8px; }}
</style></head><body>
<div class="wrap">
  <div class="title">{title}</div>
  <div class="sub">{sub}</div>
  {body}
  <div class="legend">{legend}</div>
  <div class="foot">eco Agent · 离线矢量图表（chart_render 生成，可缩放无损）</div>
</div>
<div class="tip" id="tip"></div>
<script>
(function () {{
  var tip = document.getElementById('tip');
  var marks = document.querySelectorAll('[data-tip]');
  var show = function (e) {{
    var el = e.currentTarget; tip.textContent = el.getAttribute('data-tip');
    tip.style.display = 'block';
    var r = el.getBoundingClientRect();
    tip.style.left = Math.min(r.left + 12, innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = Math.max(4, r.top - tip.offsetHeight - 8) + 'px';
  }};
  marks.forEach(function (m) {{
    m.addEventListener('mouseenter', show);
    m.addEventListener('mouseleave', function () {{ tip.style.display = 'none'; }});
  }});
}})();
</script>
</body></html>"""


def _f(x) -> float | None:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _fmt(v: float) -> str:
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v:,.0f}"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    step = span / max(1, n)
    mag = 10 ** math.floor(math.log10(step))
    for m in (1, 2, 2.5, 5, 10):
        if step <= m * mag:
            step = m * mag
            break
    start = math.floor(lo / step) * step
    out = []
    v = start
    while v <= hi + step * 1e-6:
        out.append(round(v, 6))
        v += step
    return out


def _svg_head(w: int, h: int) -> str:
    return f'<svg width="100%" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img">'


def _axis(rect, ticks, fmt=_fmt, xlabel="", ylabel="") -> str:
    x, y, w, h = rect
    parts = [f'<line x1="{x}" y1="{y + h}" x2="{x + w}" y2="{y + h}" stroke="#E1E5EE" stroke-width="1"/>',
             f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + h}" stroke="#E1E5EE" stroke-width="1"/>']
    for t in ticks:
        ty = y + h - (t - ticks[0]) / (ticks[-1] - ticks[0]) * h
        parts.append(f'<line x1="{x}" y1="{ty:.1f}" x2="{x + w}" y2="{ty:.1f}" stroke="#F1F3F5" stroke-width="1"/>')
        parts.append(f'<text x="{x - 6}" y="{ty + 4:.1f}" text-anchor="end" font-size="10.5" fill="#818588">{fmt(t)}</text>')
    if ylabel:
        parts.append(f'<text x="{x - 40}" y="{y + h / 2}" text-anchor="middle" font-size="11" fill="#616567" '
                     f'transform="rotate(-90 {x - 40} {y + h / 2})">{_html.escape(ylabel)}</text>')
    if xlabel:
        parts.append(f'<text x="{x + w / 2}" y="{y + h + 24}" text-anchor="middle" font-size="11" fill="#616567">{_html.escape(xlabel)}</text>')
    return "".join(parts)


def _legend_html(names: list[tuple[str, str]]) -> str:
    return "".join(f'<span><i style="background:{c}"></i>{_html.escape(n)}</span>' for n, c in names)


def _line_chart(title: str, x_labels: list[str], series: list[dict], unit: str) -> str:
    w, h, mx, my, tx, ty = 820, 400, 56, 36, 16, 14
    pw, ph = w - mx - tx, h - my - ty
    data = [[_f(v) for v in s.get("data", [])] for s in series]
    vals = [v for d in data for v in d if v is not None]
    lo, hi = (min(vals), max(vals)) if vals else (0, 1)
    pad = (hi - lo) * 0.08 or max(1.0, abs(hi) * 0.08)
    lo, hi = lo - pad, hi + pad
    ticks = _nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    n = max(len(x_labels), *(len(d) for d in data))
    step_x = pw / max(1, n - 1)
    parts = [_svg_head(w, h + 30), _axis((mx, my, pw, ph), ticks)]
    for si, s in enumerate(series):
        color = PALETTE[si % len(PALETTE)]
        pts = []
        for i, v in enumerate(data[si]):
            px = mx + i * step_x
            py = my + ph - (0 if v is None else (v - lo) / (hi - lo) * ph)
            if v is not None:
                pts.append(f"{px:.1f},{py:.1f}")
        if len(pts) >= 2:
            parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in enumerate(data[si]):
            if v is None:
                continue
            px, py = mx + i * step_x, my + ph - (v - lo) / (hi - lo) * ph
            lab = _fmt(v) + (unit or "")
            tip = f"{_html.escape(s.get('name', ''))} · {_html.escape(x_labels[i] if i < len(x_labels) else str(i + 1))}：{_html.escape(lab)}"
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.4" fill="#fff" stroke="{color}" stroke-width="2" data-tip="{tip}"/>')
    for i, lab in enumerate(x_labels[:n]):
        px = mx + i * step_x
        parts.append(f'<text x="{px:.1f}" y="{my + ph + 18}" text-anchor="middle" font-size="10.5" fill="#616567">{_html.escape(str(lab))}</text>')
    parts.append("</svg>")
    legend = _legend_html([(s.get("name", f"系列{si + 1}"), PALETTE[si % len(PALETTE)]) for si, s in enumerate(series)])
    sub = f"{n} 个时点 · {len(series)} 系列" + (f" · 单位 {_html.escape(unit)}" if unit else "")
    return _TMPL.format(title=_html.escape(title), sub=sub, body="".join(parts), legend=legend)


def _bar_chart(title: str, x_labels: list[str], series: list[dict], unit: str, stacked: bool) -> str:
    w, h, mx, my, tx, ty = 820, 400, 56, 36, 16, 14
    pw, ph = w - mx - tx, h - my - ty
    data = [[_f(v) for v in s.get("data", [])] for s in series]
    n = max(len(x_labels), *(len(d) for d in data))
    if stacked:
        cum = []
        for i in range(n):
            vals_i = [(data[si][i] or 0) if i < len(data[si]) else 0 for si in range(len(series))]
            cum.append([sum(vals_i[:k + 1]) for k in range(len(series))])
        vals = [c[-1] for c in cum]
    else:
        vals = [v for d in data for v in d if v is not None]
    lo, hi = (0, max(vals) * 1.08) if vals and max(vals) > 0 else (0, 1)
    ticks = _nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    parts = [_svg_head(w, h + 30), _axis((mx, my, pw, ph), ticks)]
    slot = pw / n
    group_w = slot * 0.72
    k = len(series)
    bar_w = group_w / k if k else 0
    for si, s in enumerate(series):
        color = PALETTE[si % len(PALETTE)]
        for i in range(n):
            v = data[si][i] if i < len(data[si]) else None
            if v is None:
                continue
            cx = mx + i * slot + (slot - group_w) / 2 + si * bar_w
            base = 0 if not stacked else (cum[i][si - 1] if si > 0 else 0)
            y0 = my + ph - (base - lo) / (hi - lo) * ph
            y1 = my + ph - (base + v - lo) / (hi - lo) * ph
            lab = _fmt(v) + (unit or "")
            tip = f"{_html.escape(s.get('name', ''))} · {_html.escape(x_labels[i] if i < len(x_labels) else str(i + 1))}：{_html.escape(lab)}"
            parts.append(f'<rect x="{cx:.1f}" y="{min(y0, y1):.1f}" width="{max(2.0, bar_w - 2):.1f}" height="{abs(y1 - y0):.1f}" rx="2" fill="{color}" data-tip="{tip}"/>')
    for i, lab in enumerate(x_labels[:n]):
        cx = mx + i * slot + slot / 2
        parts.append(f'<text x="{cx:.1f}" y="{my + ph + 18}" text-anchor="middle" font-size="10.5" fill="#616567">{_html.escape(str(lab))}</text>')
    parts.append("</svg>")
    legend = _legend_html([(s.get("name", f"系列{si + 1}"), PALETTE[si % len(PALETTE)]) for si, s in enumerate(series)])
    sub = f"{n} 个分组 · {len(series)} 系列" + (" · 堆叠" if stacked else "") + (f" · 单位 {_html.escape(unit)}" if unit else "")
    return _TMPL.format(title=_html.escape(title), sub=sub, body="".join(parts), legend=legend)


def _pie_chart(title: str, items: list[dict], unit: str) -> str:
    w, h = 820, 420
    cx, cy, r = 250, 220, 150
    values = [_f(it.get("value")) for it in items]
    total = sum(v for v in values if v is not None) or 1
    parts = [_svg_head(w, h)]
    ang = -math.pi / 2
    for i, it in enumerate(items):
        v = values[i] or 0
        frac = v / total
        if frac <= 0:
            continue
        a0, a1 = ang, ang + frac * 2 * math.pi
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        large = 1 if (a1 - a0) > math.pi else 0
        color = PALETTE[i % len(PALETTE)]
        pct = f"{frac * 100:.1f}%"
        lab = _fmt(v) + (unit or "")
        tip = f"{_html.escape(str(it.get('name', f'项{i + 1}')))}：{_html.escape(lab)}（{pct}）"
        parts.append(f'<path d="M {cx} {cy} L {x0:.1f} {y0:.1f} A {r} {r} 0 {large} 1 {x1:.1f} {y1:.1f} Z" fill="{color}" stroke="#fff" stroke-width="1.5" data-tip="{tip}"/>')
        ang = a1
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r * 0.58}" fill="#fff"/>')
    parts.append(f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="13" fill="#616567">合计</text>')
    parts.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="20" font-weight="700" fill="#0F1115">{_fmt(total)}{_html.escape(unit or "")}</text>')
    lx = 480
    for i, it in enumerate(items):
        v = values[i] or 0
        color = PALETTE[i % len(PALETTE)]
        frac = v / total
        parts.append(f'<rect x="{lx}" y="{56 + i * 30}" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{lx + 20}" y="{56 + i * 30 + 10}" font-size="12.5" fill="#0F1115">{_html.escape(str(it.get("name", f"项{i + 1}"))[:14])}</text>')
        parts.append(f'<text x="{lx + 200}" y="{56 + i * 30 + 10}" text-anchor="end" font-size="12.5" fill="#353638">{_fmt(v)}{_html.escape(unit or "")} · {frac * 100:.1f}%</text>')
    parts.append("</svg>")
    legend = ""
    sub = f"{len(items)} 项 · 合计 {_fmt(total)}{_html.escape(unit or '')}"
    return _TMPL.format(title=_html.escape(title), sub=sub, body="".join(parts), legend=legend)


def render_chart(
    type: str = "line",
    title: str = "图表",
    x_labels: list | None = None,
    series: list | None = None,
    unit: str = "",
    pie_data: list | None = None,
) -> str:
    """生成完整离线 SVG 图表 HTML。参数非法时返回带错误说明的 HTML（不抛异常）。"""
    t = (type or "line").lower()
    try:
        if t in ("line", "multi_line"):
            xl = list(x_labels or [])
            ss = list(series or [])
            if not ss:
                raise ValueError("series 为空")
            return _line_chart(title or "趋势图", xl, ss, unit)
        if t == "bar":
            xl = list(x_labels or [])
            ss = list(series or [])
            if not ss:
                raise ValueError("series 为空")
            return _bar_chart(title or "柱状图", xl, ss, unit, stacked=False)
        if t in ("stacked_bar", "stack"):
            xl = list(x_labels or [])
            ss = list(series or [])
            if not ss:
                raise ValueError("series 为空")
            return _bar_chart(title or "堆叠柱状图", xl, ss, unit, stacked=True)
        if t == "pie":
            items = list(pie_data or [])
            if not items:
                # 兼容 series 单系列 data=[{name,value}]
                if series and series[0].get("data"):
                    items = [{"name": str(i), "value": v} for i, v in enumerate(series[0]["data"])]
            if not items:
                raise ValueError("pie 需要 pie_data=[{'name','value'},...]")
            return _pie_chart(title or "占比图", items, unit)
        raise ValueError(f"不支持的图表类型: {type}（支持 line/bar/stacked_bar/pie）")
    except Exception as e:  # noqa: BLE001 — 图表失败也要给可读反馈
        msg = _html.escape(str(e))
        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"></head>
<body style="margin:0;font:14px -apple-system,'PingFang SC',sans-serif;background:#fff;color:#EF4444;
padding:24px;">图表生成失败：{msg}<br><pre style="font-size:11px;color:#616567;">args={_html.escape(json.dumps(
    {"type": type, "title": title, "x_labels": x_labels, "series": series, "unit": unit, "pie_data": pie_data},
    ensure_ascii=False, default=str)[:600])}</pre></body></html>"""
