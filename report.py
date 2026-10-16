# -*- coding: utf-8 -*-
"""
report.py —— 功能10：一键自动仿真报告
=======================================
把一次仿真（或批量仿真）的全部结果组装成一份自包含的 HTML 报告：
  - KPI 总览卡片
  - 全部图表（Plotly 交互图，嵌入报告）
  - 订单结果/事件日志/队列监控 数据表
  - 决策建议表
  - 实验信息（参数、时间模型、到达模式、随机种子）

报告无需联网即可打开（Plotly 使用 CDN，若离线可改为本地引入）。
返回 HTML 字符串，网页端提供下载按钮即可。
"""

import html as html_lib
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go

# KPI 中文名对照
KPI_CN = {
    "completed_orders": "完成订单数",
    "avg_cycle_time": "平均周转周期(分钟)",
    "std_cycle_time": "周期标准差(分钟)",
    "p50_cycle_time": "P50周转周期(分钟)",
    "p95_cycle_time": "P95周转周期(分钟)",
    "max_cycle_time": "最大周转周期(分钟)",
    "throughput_per_hour": "吞吐量(件/小时)",
    "avg_pick_wait": "拣选平均等待(分钟)",
    "avg_amr_wait": "AMR平均等待(分钟)",
    "avg_pack_wait": "打包平均等待(分钟)",
    "utilization_picker": "拣选利用率",
    "utilization_amr": "AMR利用率",
    "utilization_pack_station": "打包利用率",
    "avg_queue_picker": "拣选平均队列",
    "avg_queue_amr": "AMR平均队列",
    "avg_queue_pack_station": "打包平均队列",
    "max_queue_picker": "拣选最大队列",
    "max_queue_amr": "AMR最大队列",
    "max_queue_pack_station": "打包最大队列",
}

_CSS = """
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 24px;
         color: #222; background: #fafafa; }
  h1 { color: #1f4e79; border-bottom: 3px solid #1f4e79; padding-bottom: 8px; }
  h2 { color: #1f4e79; margin-top: 32px; }
  .meta { color: #666; font-size: 13px; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
  .card { background: #fff; border: 1px solid #ddd; border-radius: 8px;
          padding: 12px 16px; min-width: 150px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .card .v { font-size: 22px; font-weight: 700; color: #1f4e79; }
  .card .k { font-size: 12px; color: #888; }
  table { border-collapse: collapse; width: 100%; background: #fff; font-size: 13px; }
  th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
  th { background: #eef3f8; }
  .warn { background: #fff3cd; border: 1px solid #ffe69c; border-radius: 6px;
          padding: 10px 14px; margin: 12px 0; }
  .advice-high { background: #fdecea; }
  .advice-mid { background: #fff7e6; }
</style>
"""


def _fmt_kpi(kpi: dict) -> list:
    """把 KPI 字典转成报告卡片数据（利用率转百分比）"""
    cards = []
    order = ["completed_orders", "throughput_per_hour", "avg_cycle_time",
             "p95_cycle_time", "max_cycle_time"]
    for key in order:
        if key in kpi:
            v = kpi[key]
            if key.startswith("utilization_"):
                v = f"{v*100:.1f}%"
            cards.append((KPI_CN.get(key, key), v))
    return cards


def _figs_to_html(figs: dict) -> str:
    """把 {名称: plotly Figure} 渲染成嵌入 HTML 的 <div> 序列"""
    chunks = []
    for i, (name, fig) in enumerate(figs.items()):
        if fig is None:
            continue
        kwargs = {"full_html": False, "include_plotlyjs": "cdn" if i == 0 else False}
        try:
            chunks.append(f"<h2>{html_lib.escape(name)}</h2>")
            chunks.append(fig.to_html(**kwargs))
        except Exception:
            continue
    return "\n".join(chunks)


def _table_to_html(df: pd.DataFrame, max_rows: int = 200) -> str:
    """DataFrame → HTML 表格（超长截断）"""
    if df is None or len(df) == 0:
        return "<p>无数据</p>"
    d = df.head(max_rows)
    head = "".join(f"<th>{html_lib.escape(str(c))}</th>" for c in d.columns)
    body = ""
    for _, row in d.iterrows():
        body += "<tr>" + "".join(
            f"<td>{html_lib.escape(str(v))}</td>" for v in row) + "</tr>"
    note = f"<p class='meta'>共 {len(df)} 行，仅显示前 {min(max_rows, len(df))} 行</p>" \
        if len(df) > max_rows else ""
    return f"<table><tr>{head}</tr>{body}</table>{note}"


def _advice_to_html(advice: pd.DataFrame) -> str:
    if advice is None or len(advice) == 0:
        return "<p>无建议</p>"
    rows = ""
    for _, r in advice.iterrows():
        level = str(r.get("level", ""))
        cls = {"高": "advice-high", "中": "advice-mid"}.get(level, "")
        rows += (
            f"<tr class='{cls}'>"
            f"<td>{html_lib.escape(str(r.get('level', '')))}</td>"
            f"<td>{html_lib.escape(str(r.get('title', '')))}</td>"
            f"<td>{html_lib.escape(str(r.get('finding', '')))}</td>"
            f"<td>{html_lib.escape(str(r.get('action', '')))}</td>"
            f"<td>{html_lib.escape(str(r.get('boundary', '')))}</td>"
            f"</tr>")
    return ("<table><tr><th>等级</th><th>结论</th><th>现状</th><th>建议动作</th>"
            f"<th>失效边界</th></tr>{rows}</table>")


def generate_html_report(
    title: str,
    kpi: dict,
    df_order: pd.DataFrame,
    df_event: pd.DataFrame,
    df_queue: pd.DataFrame,
    figs: dict,                 # {图表名: plotly Figure}
    advice: pd.DataFrame = None,
    meta: dict = None,          # 实验参数信息
) -> str:
    """生成完整自包含 HTML 报告字符串"""
    meta = meta or {}
    cards_html = "".join(
        f"<div class='card'><div class='v'>{html_lib.escape(str(v))}</div>"
        f"<div class='k'>{html_lib.escape(k)}</div></div>"
        for k, v in _fmt_kpi(kpi))

    meta_lines = "｜".join(
        f"{html_lib.escape(k)}：{html_lib.escape(str(v))}" for k, v in meta.items())
    bottleneck = kpi.get("bottleneck", "")
    bn_cn = {"picker": "拣选", "amr": "AMR搬运", "pack_station": "打包"}.get(bottleneck, bottleneck)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{html_lib.escape(title)}</title>{_CSS}</head>
<body>
<h1>{html_lib.escape(title)}</h1>
<p class='meta'>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}　{meta_lines}</p>
<h2>一、KPI 总览</h2>
<div class='cards'>{cards_html}</div>
<div class='warn'>系统当前瓶颈环节：<b>{bn_cn}</b>（{bottleneck}）</div>
{_figs_to_html(figs)}
<h2>二、决策建议</h2>
{_advice_to_html(advice)}
<h2>三、订单结果明细</h2>
{_table_to_html(df_order)}
<h2>四、事件日志（模型校核）</h2>
{_table_to_html(df_event)}
<h2>五、队列监控数据</h2>
{_table_to_html(df_queue)}
<p class='meta'>本报告由物流系统智能仿真决策平台自动生成。</p>
</body>
</html>"""


# ==================== 本地测试 ====================
if __name__ == "__main__":
    from sim_core import run_one_simulation, simulation_to_dfs, compute_kpis
    from advisor import generate_advice, advice_to_dataframe
    import visualization as viz

    cfg = {"picker_num": 2, "pack_station_num": 1, "amr_num": 3,
           "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
           "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 300}
    sim = run_one_simulation(cfg, seed=8)
    df_o, df_e, df_q = simulation_to_dfs(sim)
    kpi = compute_kpis(sim)
    adv = advice_to_dataframe(generate_advice(kpi, resources={"picker_num": 2,
                                                              "pack_station_num": 1,
                                                              "amr_num": 3}))

    figs = {
        "周转周期分布": viz.fig_cycle_distribution(df_o),
        "周期构成分解": viz.fig_stage_decomposition(df_o),
        "资源利用率": viz.fig_utilization_bar(kpi),
        "队列长度时序": viz.fig_queue_timeseries(df_q),
    }
    html_str = generate_html_report(
        "物流仿真实验报告", kpi, df_o, df_e, df_q, figs, adv,
        meta={"时间模型": "Gamma", "到达模式": "泊松", "随机种子": 8})
    assert "物流仿真实验报告" in html_str and "KPI 总览" in html_str
    print(f"✅ report.py 测试通过，报告长度 {len(html_str)} 字符")
