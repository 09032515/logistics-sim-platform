# -*- coding: utf-8 -*-
"""
visualization.py —— 功能2：可视化图表中心
=========================================
把所有图表制作函数集中在一个模块，供全部功能复用：
  1. 周转周期分布直方图        fig_cycle_distribution
  2. 周转周期趋势图            fig_cycle_timeline
  3. 周期构成分解（等待+作业）  fig_stage_decomposition
  4. 资源利用率柱状图          fig_utilization_bar
  5. 队列长度时序图            fig_queue_timeseries
  6. 每小时吞吐量图            fig_throughput_timeline
  7. 资源利用率仪表盘          fig_utilization_gauges
  8. 多方案对比柱状图          fig_scenario_groupbar
  9. 多方案雷达图              fig_scenario_radar
  10. 敏感性分析曲线           fig_sensitivity_line
  11. 敏感性龙卷风图           fig_tornado

所有函数输入为 DataFrame / dict，不依赖网页环境，可独立测试。
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

RES_COLORS = {"picker": "#1f77b4", "amr": "#ff7f0e", "pack_station": "#2ca02c"}
RES_NAMES = {"picker": "拣选人员", "amr": "AMR机器人", "pack_station": "打包工作台"}
STAGE_CN = {"picker": "拣选", "amr": "AMR搬运", "pack_station": "打包"}


def _empty_fig(msg: str = "暂无数据，请先运行仿真") -> go.Figure:
    """空数据兜底图"""
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font={"size": 16})
    fig.update_layout(height=320)
    return fig


# ==================== 1. 周转周期分布 ====================
def fig_cycle_distribution(df_order: pd.DataFrame) -> go.Figure:
    if df_order is None or len(df_order) == 0:
        return _empty_fig()
    fig = px.histogram(df_order, x="cycle_time", nbins=20,
                       title="订单周转周期分布（分钟）",
                       labels={"cycle_time": "周转周期（分钟）", "count": "订单数"})
    fig.update_traces(marker_color="#1f77b4", opacity=0.8)
    fig.update_layout(height=360, template="plotly_white")
    return fig


# ==================== 2. 周转周期趋势 ====================
def fig_cycle_timeline(df_order: pd.DataFrame) -> go.Figure:
    if df_order is None or len(df_order) == 0:
        return _empty_fig()
    d = df_order.copy()
    d["完成时刻"] = d["arrive_time"] + d["cycle_time"]
    d = d.sort_values("完成时刻").reset_index(drop=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["完成时刻"], y=d["cycle_time"], mode="lines+markers",
                             name="周转周期", line={"color": "#1f77b4", "width": 2},
                             marker={"size": 4}))
    fig.add_hline(y=d["cycle_time"].mean(), line_dash="dash", line_color="red",
                  annotation_text=f"均值 {d['cycle_time'].mean():.1f} 分钟")
    fig.update_layout(title="周转周期随时间变化趋势（按完成时刻）",
                      xaxis_title="完成时刻（分钟）", yaxis_title="周转周期（分钟）",
                      height=360, template="plotly_white")
    return fig


# ==================== 3. 周期构成分解 ====================
def fig_stage_decomposition(df_order: pd.DataFrame) -> go.Figure:
    """平均周转周期的构成：各环节等待时间 + 作业时间（堆叠条形图）"""
    if df_order is None or len(df_order) == 0:
        return _empty_fig()
    parts = [
        ("拣选等待", "pick_wait", "#d62728"),
        ("拣选作业", "pick_time", "#1f77b4"),
        ("AMR等待", "amr_wait", "#ff9896"),
        ("AMR作业", "amr_time", "#ff7f0e"),
        ("打包等待", "pack_wait", "#c5b0d5"),
        ("打包作业", "pack_time", "#2ca02c"),
    ]
    fig = go.Figure()
    for name, col, color in parts:
        fig.add_trace(go.Bar(name=name, x=["平均周转周期"],
                             y=[df_order[col].mean()], marker_color=color,
                             text=[f"{df_order[col].mean():.2f}"], textposition="inside"))
    fig.update_layout(barmode="stack", height=380,
                      title="平均周转周期构成分解（分钟）：等待 vs 作业",
                      template="plotly_white", showlegend=True)
    return fig


# ==================== 4. 资源利用率柱状图 ====================
def fig_utilization_bar(kpi: dict) -> go.Figure:
    if not kpi:
        return _empty_fig()
    names, values, colors = [], [], []
    for res in ("picker", "amr", "pack_station"):
        names.append(RES_NAMES[res])
        values.append(kpi.get(f"utilization_{res}", 0.0))
        colors.append(RES_COLORS[res])
    fig = go.Figure(go.Bar(x=names, y=values, marker_color=colors,
                           text=[f"{v*100:.1f}%" for v in values],
                           textposition="outside"))
    fig.add_hline(y=0.85, line_dash="dash", line_color="red",
                  annotation_text="85% 警戒线")
    fig.update_layout(title="资源利用率", yaxis_title="利用率",
                      yaxis={"tickformat": ".0%", "range": [0, 1.15]},
                      height=360, template="plotly_white")
    return fig


# ==================== 5. 队列长度时序图 ====================
def fig_queue_timeseries(df_queue: pd.DataFrame) -> go.Figure:
    if df_queue is None or len(df_queue) == 0:
        return _empty_fig()
    fig = go.Figure()
    for res in ("picker", "amr", "pack_station"):
        part = df_queue[df_queue["resource"] == res]
        if len(part) == 0:
            continue
        fig.add_trace(go.Scatter(x=part["time"], y=part["queue_length"],
                                 mode="lines", name=RES_NAMES[res],
                                 line={"color": RES_COLORS[res], "width": 2}))
    fig.update_layout(title="各环节队列长度随时间变化",
                      xaxis_title="仿真时间（分钟）", yaxis_title="排队订单数",
                      height=380, template="plotly_white")
    return fig


# ==================== 6. 每小时吞吐量 ====================
def fig_throughput_timeline(df_order: pd.DataFrame, interval_min: float = 60) -> go.Figure:
    if df_order is None or len(df_order) == 0:
        return _empty_fig()
    d = df_order.copy()
    d["完成时刻"] = d["arrive_time"] + d["cycle_time"]
    d["时段"] = np.floor(d["完成时刻"] / interval_min) * interval_min
    counts = d.groupby("时段").size().reset_index(name="完成量")
    fig = px.bar(counts, x="时段", y="完成量",
                 labels={"时段": "仿真时间（分钟）", "完成量": "完成订单数"},
                 title=f"吞吐量时间线（每{int(interval_min)}分钟完成订单数）")
    fig.update_traces(marker_color="#2ca02c", opacity=0.85)
    fig.update_layout(height=360, template="plotly_white")
    return fig


# ==================== 7. 资源利用率仪表盘 ====================
def fig_utilization_gauges(kpi: dict) -> go.Figure:
    if not kpi:
        return _empty_fig()
    fig = go.Figure()
    for i, res in enumerate(("picker", "amr", "pack_station")):
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=kpi.get(f"utilization_{res}", 0.0) * 100,
            title={"text": RES_NAMES[res]},
            number={"suffix": "%"},
            domain={"row": 0, "column": i},
            gauge={"axis": {"range": [0, 100]},
                   "bar": {"color": RES_COLORS[res]},
                   "steps": [{"range": [0, 85], "color": "#e8f4e8"},
                             {"range": [85, 100], "color": "#fdeaea"}],
                   "threshold": {"line": {"color": "red", "width": 3},
                                 "thickness": 0.8, "value": 85}},
        ))
    fig.update_layout(grid={"rows": 1, "columns": 3, "pattern": "independent"},
                      height=300, title="资源利用率仪表盘（85% 为警戒线）")
    return fig


# ==================== 8. 多方案对比柱状图 ====================
def fig_scenario_groupbar(compare_df: pd.DataFrame,
                          metrics=("avg_cycle_time", "p95_cycle_time",
                                   "throughput_per_hour")) -> go.Figure:
    """compare_df: 行=方案名，列=KPI均值（来源于批量仿真汇总）"""
    if compare_df is None or len(compare_df) == 0:
        return _empty_fig()
    fig = go.Figure()
    for m in metrics:
        if m not in compare_df.columns:
            continue
        fig.add_trace(go.Bar(name=m, x=compare_df.index, y=compare_df[m]))
    fig.update_layout(barmode="group", height=380,
                      title="多方案 KPI 对比", template="plotly_white")
    return fig


# ==================== 9. 多方案雷达图 ====================
def fig_scenario_radar(compare_df: pd.DataFrame,
                       higher_better=("throughput_per_hour",),
                       lower_better=("avg_cycle_time", "p95_cycle_time",
                                     "avg_pick_wait", "avg_amr_wait", "avg_pack_wait")) -> go.Figure:
    if compare_df is None or len(compare_df) < 1:
        return _empty_fig()
    cols = [c for c in higher_better + lower_better if c in compare_df.columns]
    if not cols:
        return _empty_fig("缺少可绘制的指标")
    norm = pd.DataFrame(index=compare_df.index)
    for c in cols:
        v = pd.to_numeric(compare_df[c], errors="coerce")
        vmin, vmax = v.min(), v.max()
        if vmax - vmin < 1e-9:
            norm[c] = 0.5
            continue
        if c in higher_better:
            norm[c] = (v - vmin) / (vmax - vmin)
        else:
            norm[c] = (vmax - v) / (vmax - vmin)
    fig = go.Figure()
    for scenario in norm.index:
        fig.add_trace(go.Scatterpolar(
            r=norm.loc[scenario].tolist(),
            theta=cols,
            fill="toself",
            name=str(scenario),
        ))
    fig.update_layout(height=420, title="多方案综合能力雷达图（归一化，越大越好）",
                      template="plotly_white")
    return fig


# ==================== 9.5 批量仿真置信区间 ====================
def fig_batch_ci(df_summary: pd.DataFrame, metric: str) -> go.Figure:
    """批量仿真汇总表中单个指标：均值 ± 95%CI 柱状图"""
    if df_summary is None or len(df_summary) == 0:
        return _empty_fig()
    row = df_summary[df_summary["指标"] == metric]
    if row.empty:
        return _empty_fig(f"汇总表中没有指标 {metric}")
    r = row.iloc[0]
    fig = go.Figure(go.Bar(
        x=[metric],
        y=[r["均值"]],
        error_y=dict(
            type="data",
            symmetric=False,
            array=[float(r["95%CI上限"]) - float(r["均值"])],
            arrayminus=[float(r["均值"]) - float(r["95%CI下限"])],
            thickness=1.5, width=0.15,
        ),
        marker_color="#1f77b4",
        text=[f"{r['均值']:.2f}"],
        textposition="outside",
    ))
    fig.update_layout(title=f"{metric}：均值与95%置信区间",
                      yaxis_title=metric, height=320, template="plotly_white")
    return fig


# ==================== 10. 敏感性分析曲线 ====================
def fig_sensitivity_line(sens_df: pd.DataFrame, kpi_col: str,
                         param_name: str = "资源数量") -> go.Figure:
    """sens_df: 列为 value(参数值) + 各KPI"""
    if sens_df is None or len(sens_df) == 0 or kpi_col not in sens_df.columns:
        return _empty_fig()
    fig = go.Figure(go.Scatter(x=sens_df["value"], y=sens_df[kpi_col],
                               mode="lines+markers",
                               line={"color": "#1f77b4", "width": 3},
                               marker={"size": 9}))
    fig.update_layout(title=f"{kpi_col} 随 {param_name} 变化",
                      xaxis_title=param_name, yaxis_title=kpi_col,
                      height=360, template="plotly_white")
    return fig


# ==================== 11. 敏感性龙卷风图 ====================
def fig_tornado(tornado_df: pd.DataFrame, kpi_col: str) -> go.Figure:
    """
    tornado_df: 行=资源环节，列 = 参数减1时KPI / 参数加1时KPI / 基准KPI
    （模拟一次性增减一个资源，看对 kpi_col 的影响）
    """
    if tornado_df is None or len(tornado_df) == 0:
        return _empty_fig()
    d = tornado_df.copy()
    d = d.sort_values("影响幅度", ascending=True)
    fig = go.Figure()
    for _, row in d.iterrows():
        base = row.get("基准", 0.0)
        lo = row.get("减1", base)
        hi = row.get("加1", base)
        fig.add_trace(go.Bar(
            y=[row["资源"]], x=[hi - lo], base=[lo],
            orientation="h", marker_color=RES_COLORS.get(row["资源"], "#888"),
            name=RES_NAMES.get(row["资源"], row["资源"]),
            text=[f"{row['影响幅度']*100:.1f}%"], textposition="outside",
        ))
    fig.update_layout(title=f"参数敏感性龙卷风图：{kpi_col}（增减1个资源的变动幅度）",
                      xaxis_title=f"{kpi_col} 变化区间", yaxis_title="资源环节",
                      height=300, template="plotly_white", barmode="overlay")
    return fig


# ==================== 本地测试 ====================
if __name__ == "__main__":
    from sim_core import run_one_simulation, simulation_to_dfs, compute_kpis

    cfg = {"picker_num": 2, "pack_station_num": 1, "amr_num": 3,
           "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
           "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500}
    sim = run_one_simulation(cfg, seed=7)
    df_o, df_e, df_q = simulation_to_dfs(sim)
    kpi = compute_kpis(sim)

    funcs = [
        fig_cycle_distribution(df_o),
        fig_cycle_timeline(df_o),
        fig_stage_decomposition(df_o),
        fig_utilization_bar(kpi),
        fig_queue_timeseries(df_q),
        fig_throughput_timeline(df_o),
        fig_utilization_gauges(kpi),
    ]
    for i, f in enumerate(funcs, 1):
        assert f is not None and len(f.data) >= 0, f"图{i}生成失败"
    print(f"✅ visualization.py 测试通过，共生成 {len(funcs)} 张图")
