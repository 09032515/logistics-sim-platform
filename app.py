from warehouse_viz import create_warehouse_2d, create_warehouse_3d

# -*- coding: utf-8 -*-
"""
app.py —— 物流系统智能仿真决策平台（V2 · 10大功能完整版）
===========================================================
江苏科技大学《物流系统仿真》课程实验4 · 网页交互主程序

功能导航：
  tab1  🧮 智能计算系统       输入目标处理量 → 自动算出人车配置
  tab2  ▶️ 单次仿真与可视化   运行仿真 + 周期/效率/利用率图表
  tab3  🔍 瓶颈识别           自动定位瓶颈环节
  tab4  ⚖️ 多方案对比          预置方案横向对比选优
  tab5  📊 批量仿真            多次仿真 + 置信区间（正式实验）
  tab6  🎚️ 敏感性分析          参数扫描找边际收益拐点 + 龙卷风图
  tab7  🌪️ 压力情景测试        需求暴涨 / 设备故障抗压检验
  tab8  💡 决策建议            SLA/预算/瓶颈 → 带失效边界的中文建议
  tab9  📦 数据导入导出        结果Excel/配置JSON/历史CSV
  tab10 📄 一键自动报告        生成自包含HTML仿真报告
  tab11 🏬11-仓库2D/3D可视化

启动方式：终端执行  streamlit run app.py
"""

import streamlit as st
import pandas as pd

from sim_core import (
    run_one_simulation, run_batch_simulation, simulation_to_dfs,
    compute_kpis, DEFAULT_STAGE_TIMES,
)
import calculator
import visualization as viz
import bottleneck_detect as bottleneck
import scenario as scenario_mod
import sensitivity as sens
import stress as stress_mod
import advisor
import data_io
import report as report_mod

# ==================== 页面全局设置 ====================
st.set_page_config(
    page_title="物流系统智能仿真决策平台 V2",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📦 物流系统智能仿真决策平台（V2）")
st.caption("课程实验4｜SimPy离散事件仿真｜10大功能：智能计算 · 可视化 · 瓶颈 · 方案对比 · 批量统计 · 敏感性 · 压力测试 · 决策建议 · 导入导出 · 自动报告")

# ==================== 侧边栏：全局仿真参数 ====================
RES_NAME_CN = {"picker": "拣选人员", "amr": "AMR机器人", "pack_station": "打包工作台"}

with st.sidebar:
    st.header("🔧 仿真全局参数")
    st.subheader("资源配置")
    picker_num = st.number_input("拣选人员数量", min_value=1, max_value=6, value=2, step=1)
    pack_station_num = st.number_input("打包工作台数量", min_value=1, max_value=4, value=1, step=1)
    amr_num = st.number_input("AMR搬运机器人数量", min_value=1, max_value=10, value=3, step=1)
    sim_duration = st.number_input("仿真总时长(分钟)", min_value=100, max_value=1440, value=480, step=10)

    st.subheader("作业时间模型")
    time_model = st.selectbox(
        "时间模型",
        ["fixed", "gamma", "empirical"],
        format_func=lambda x: {"fixed": "固定时间", "gamma": "Gamma分布", "empirical": "经验分布"}[x],
    )
    pick_base = st.number_input("拣选单件时间(分钟)", 1.0, 20.0, 5.0, 0.5)
    transport_base = st.number_input("AMR搬运单件时间(分钟)", 0.5, 10.0, 2.0, 0.5)
    pack_base = st.number_input("打包单件时间(分钟)", 1.0, 10.0, 3.0, 0.5)
    time_cv = st.slider("Gamma变异系数CV", 0.05, 1.0, 0.30, 0.05)
    amr_cross_num = st.number_input("AMR交叉口数量(0=关闭拥堵)", 0, 5, 0, 1)

    st.subheader("订单到达")
    arrival_mode = st.selectbox(
        "到达模式",
        ["fixed_list", "poisson"],
        format_func=lambda x: {"fixed_list": "固定时刻(人工校核)", "poisson": "泊松随机(实验2)"}[x],
    )
    order_input_text = st.text_area(
        "固定到达时刻(英文逗号分隔)",
        value="0,2,5,8,12,15,20,22,28,33",
        help="例：0,2,5,8,12 → 第0/2/5/8/12分钟各来1单",
    )
    arrival_rate = st.number_input("泊松到达速率(件/分钟)", 0.1, 5.0, 0.8, 0.1)
    demand_multiplier = st.number_input("需求倍数(压力测试用)", 1.0, 3.0, 1.0, 0.1)
    max_orders = st.number_input("最大订单数上限", 100, 20000, 5000, 100)
    seed_input = st.number_input("随机种子", 0, 99999, 42, 1)
    empirical_file = st.file_uploader("经验分布历史CSV(可选)", type=["csv"],
                                      help="需含 pick_time / transport_time / pack_time 列")

# 解析固定订单列表（提前校验，避免运行时才报错）
try:
    order_arrival_list = data_io.parse_order_list(order_input_text)
except ValueError as e:
    st.sidebar.error(f"订单时间解析失败：{e}")
    order_arrival_list = []


# ==================== 工具函数 ====================
def build_settings(overrides: dict = None) -> dict:
    """把侧边栏参数组装成仿真设置字典（可被各功能覆盖部分参数）"""
    s = {
        "picker_num": int(picker_num),
        "pack_station_num": int(pack_station_num),
        "amr_num": int(amr_num),
        "sim_duration": float(sim_duration),
        "time_model": time_model,
        "pick_base_time": float(pick_base),
        "transport_base_time": float(transport_base),
        "pack_base_time": float(pack_base),
        "time_cv": float(time_cv),
        "amr_cross_num": int(amr_cross_num),
        "arrival_mode": arrival_mode,
        "arrival_rate": float(arrival_rate),
        "demand_multiplier": float(demand_multiplier),
        "max_orders": int(max_orders),
    }
    if empirical_file is not None:
        try:
            s["empirical_df"] = data_io.read_empirical_csv(empirical_file)
        except ValueError as e:
            st.sidebar.warning(f"经验分布CSV读取失败：{e}")
    if overrides:
        s.update(overrides)
    return s


def show_kpi_row(kpi: dict):
    """顶部 KPI 指标卡一行"""
    bn_cn = RES_NAME_CN.get(kpi.get("bottleneck", ""), kpi.get("bottleneck", ""))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("完成订单数", kpi["completed_orders"])
    c2.metric("平均周转周期", f"{kpi['avg_cycle_time']:.1f} 分钟")
    c3.metric("P95周转周期", f"{kpi['p95_cycle_time']:.1f} 分钟")
    c4.metric("吞吐量", f"{kpi['throughput_per_hour']:.1f} 件/时")
    c5.metric("瓶颈环节", bn_cn)


def has_result() -> bool:
    return "last_kpi" in st.session_state


# ==================== 10 个功能标签页 ====================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10,tab11 = st.tabs([
    "1️⃣ 智能计算", "2️⃣ 仿真与可视化", "3️⃣ 瓶颈识别", "4️⃣ 多方案对比",
    "5️⃣ 批量仿真", "6️⃣ 敏感性分析", "7️⃣ 压力情景", "8️⃣ 决策建议",
    "9️⃣ 导入导出", "🔟 自动报告", "2d/3d演示"
])

# ---------------- tab1 智能计算系统 ----------------
with tab1:
    st.header("🧮 智能计算系统：输入目标 → 自动算出人车配置")
    st.markdown(
        "输入**预计处理货物量**与**可用作业时间**，系统按各环节单件作业时间"
        "（与仿真内核同一口径）自动计算需要的拣选人员 / AMR / 打包台数量。"
    )
    c1, c2, c3, c4 = st.columns(4)
    goods_count = c1.number_input("预计处理货物量(件)", 100, 100000, 1000, 100)
    work_time = c2.number_input("可用作业时间(分钟)", 60, 1440, 480, 60)
    target_util = c3.slider("目标资源利用率", 0.50, 0.95, 0.85, 0.05)
    safety = c4.number_input("安全系数(应对波动)", 1.0, 1.5, 1.0, 0.05)

    if st.button("⚡ 自动计算人车配置", type="primary", key="calc_btn"):
        df_req = calculator.calculate_resources(goods_count, work_time, target_util,
                                                safety_factor=safety)
        rec = {row["资源名称"]: int(row["建议配置"]) for _, row in df_req.iterrows()}
        st.success(f"✅ 建议配置：拣选 {rec['picker']} 人 ｜ AMR {rec['amr']} 台 ｜ "
                   f"打包台 {rec['pack_station']} 个")
        st.dataframe(df_req, width="stretch")

        df_cap, sys_cap = calculator.estimate_capacity(rec, work_time, target_util)
        st.subheader("按建议配置反算的班次产能（木桶效应验证）")
        st.dataframe(df_cap, width="stretch")
        st.info(f"🏭 系统产能（最短板的环节决定）= **{sys_cap:.0f} 件/班次**"
                f"（目标 {goods_count:.0f} 件 → {'✅ 可完成' if sys_cap >= goods_count else '⚠️ 不足，需增配'}）")
        cost = calculator.estimate_cost(rec)
        st.caption(f"按示例单价估算班次成本：约 {cost:.0f} 元（拣选200/人·AMR500/台·打包台300/台，可在 advisor.py 修改）")
        st.session_state["calc_rec"] = rec

# ---------------- tab2 单次仿真与可视化 ----------------
with tab2:
    st.header("▶️ 单次仿真运行与可视化")
    run_btn = st.button("🚀 运行单次仿真", type="primary", key="run_once_btn",
                        help="使用侧边栏全部参数，运行一次完整仿真")
    if run_btn:
        if arrival_mode == "fixed_list" and len(order_arrival_list) == 0:
            st.error("固定到达模式必须填写订单到达时刻！")
        else:
            with st.spinner("⏳ 仿真计算中……"):
                sim = run_one_simulation(
                    build_settings(),
                    order_arrival_list=order_arrival_list,
                    seed=int(seed_input),
                )
                df_o, df_e, df_q = simulation_to_dfs(sim)
                kpi = compute_kpis(sim)
                st.session_state["last_sim"] = sim
                st.session_state["last_order"] = df_o
                st.session_state["last_event"] = df_e
                st.session_state["last_queue"] = df_q
                st.session_state["last_kpi"] = kpi
                st.session_state["sim_result"] = {"order_df":df_o, "queue_df":df_q}
            st.success(f"✅ 仿真完成，共完成 {kpi['completed_orders']} 单")

    if has_result():
        kpi = st.session_state["last_kpi"]
        df_o = st.session_state["last_order"]
        df_q = st.session_state["last_queue"]
        st.divider()
        show_kpi_row(kpi)

        left, right = st.columns(2)
        with left:
            st.plotly_chart(viz.fig_cycle_distribution(df_o), width="stretch", key="chart_cycle_hist")
            st.plotly_chart(viz.fig_stage_decomposition(df_o), width="stretch", key="chart_stage_tab2")
            st.plotly_chart(viz.fig_utilization_bar(kpi), width="stretch", key="chart_util_bar")
        with right:
            st.plotly_chart(viz.fig_cycle_timeline(df_o), width="stretch", key="chart_cycle_timeline")
            st.plotly_chart(viz.fig_queue_timeseries(df_q), width="stretch", key="chart_queue_ts")
            st.plotly_chart(viz.fig_throughput_timeline(df_o), width="stretch", key="chart_throughput")
    else:
        st.info("👈 点击上方按钮运行第一次仿真，随后这里会展示全部可视化图表。")

# ---------------- tab3 瓶颈识别 ----------------
with tab3:
    st.header("🔍 瓶颈环节自动识别")
    if not has_result():
        st.info("请先在「2️⃣ 仿真与可视化」运行一次仿真。")
    else:
        kpi = st.session_state["last_kpi"]
        df_o = st.session_state["last_order"]
        st.markdown(bottleneck.explain_bottleneck(kpi))
        st.dataframe(bottleneck.bottleneck_scores(kpi), width="stretch")
        st.plotly_chart(viz.fig_utilization_gauges(kpi), width="stretch", key="chart_gauges")
        st.plotly_chart(viz.fig_stage_decomposition(df_o), width="stretch", key="chart_stage_tab3")
        st.caption("瓶颈判定维度：利用率(50%) + 平均等待(30%) + 最大队列(20%)")

# ---------------- tab4 多方案对比 ----------------
with tab4:
    st.header("⚖️ 多方案对比分析")
    st.markdown("每个方案独立做批量仿真后横向对比 KPI，选择最优资源配置。")
    selected = st.multiselect(
        "选择参与对比的方案",
        list(scenario_mod.SCENARIOS.keys()),
        default=["基础配置", "增加拣选", "增加AMR"],
    )
    n_runs_scen = st.slider("每个方案重复次数（预览5 / 正式≥20）", 3, 30, 5, key="scen_runs")
    if st.button("🏁 开始方案对比", type="primary", key="scen_btn"):
        if not selected:
            st.warning("请至少勾选一个方案。")
        else:
            progress = st.progress(0.0, text="方案对比仿真中……")

            def cb(a, b, i, n):
                progress.progress((a - 1) / b + (i / n) / b,
                                  text=f"方案 {a}/{b} · 第 {i}/{n} 次运行")

            compare = scenario_mod.run_scenario_comparison(
                selected, build_settings(), n_runs=n_runs_scen,
                seed=int(seed_input), progress_cb=cb,
                order_arrival_list=order_arrival_list,
            )
            st.session_state["last_compare"] = compare
            progress.empty()

    if "last_compare" in st.session_state:
        compare = st.session_state["last_compare"]
        st.markdown(scenario_mod.recommend_scenario(compare))
        st.dataframe(compare.round(3), width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(viz.fig_scenario_groupbar(
                compare, metrics=("avg_cycle_time", "p95_cycle_time", "throughput_per_hour")),
                width="stretch", key="chart_scen_groupbar")
        with c2:
            st.plotly_chart(viz.fig_scenario_radar(compare), width="stretch", key="chart_scen_radar")
        st.download_button("📥 下载对比结果CSV",
                           data=data_io.df_to_csv_bytes(compare.reset_index().rename(
                               columns={"index": "方案"})),
                           file_name="scenario_compare.csv", mime="text/csv")

# ---------------- tab5 批量仿真与置信区间 ----------------
with tab5:
    st.header("📊 批量仿真与置信区间（正式实验统计）")
    st.markdown(
        "重复运行 **N 次独立仿真**（每次换随机种子），对每个 KPI 计算"
        "**均值 / 标准差 / 95%置信区间**。\n\n"
        "> ⚠️ 预览模式（N<20）结果只作方向参考，**不能作为正式实验结论**；"
        "正式实验建议 N≥20。"
    )
    n_runs = st.slider("重复次数 N", 3, 50, 10, key="batch_n")
    if st.button("🎲 运行批量仿真", type="primary", key="batch_btn"):
        progress = st.progress(0.0, text="批量仿真中……")

        def cb(i, n):
            progress.progress(i / n, text=f"第 {i}/{n} 次运行")

        df_runs, df_summary = run_batch_simulation(
            build_settings(), n_runs=n_runs,
            order_arrival_list=order_arrival_list, seed=int(seed_input),
            progress_cb=cb,
        )
        st.session_state["last_batch"] = (df_runs, df_summary)
        progress.empty()

    if "last_batch" in st.session_state:
        df_runs, df_summary = st.session_state["last_batch"]
        st.dataframe(df_summary, width="stretch")
        st.caption("95%CI 表示：重复同样的实验，该指标均值有95%概率落在这个区间。")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(viz.fig_batch_ci(df_summary, "avg_cycle_time"),
                            width="stretch", key="chart_batch_ci_cycle")
        with c2:
            st.plotly_chart(viz.fig_batch_ci(df_summary, "throughput_per_hour"),
                            width="stretch", key="chart_batch_ci_tp")
        st.download_button("📥 下载批量仿真汇总CSV",
                           data=data_io.df_to_csv_bytes(df_summary),
                           file_name="batch_summary.csv", mime="text/csv")

# ---------------- tab6 敏感性分析 ----------------
with tab6:
    st.header("🎚️ 敏感性分析")
    st.markdown(
        "**参数扫描**：只改变一个资源数量，观察关键 KPI 的变化，找出"
        "「边际收益递减拐点」（再加资源改善不明显的位置）。\n\n"
        "**龙卷风图**：把每个资源 +1/-1，比较对平均周期的影响幅度，"
        "找出影响最大的参数。"
    )
    res_key = st.selectbox(
        "扫描哪个资源", ["picker", "amr", "pack_station"],
        format_func=lambda r: RES_NAME_CN[r],
    )
    lo, hi = sens.RESOURCE_RANGES[res_key]
    metric = st.selectbox(
        "观察指标",
        ["avg_cycle_time", "throughput_per_hour", f"utilization_{res_key}"],
        format_func=lambda m: {
            "avg_cycle_time": "平均周转周期(分钟)",
            "throughput_per_hour": "吞吐量(件/小时)",
        }.get(m, "该资源利用率"),
    )
    n_runs_sens = st.slider("每个取值重复次数", 2, 10, 3, key="sens_runs")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📈 运行参数扫描", type="primary", key="sens_btn"):
            progress = st.progress(0.0, text="参数扫描中……")
            sens_df = sens.run_sensitivity_scan(
                res_key, list(range(lo, hi + 1)), build_settings(),
                n_runs=n_runs_sens, seed=int(seed_input),
                order_arrival_list=order_arrival_list,
                progress_cb=lambda i, n: progress.progress(i / n, text=f"取值 {i}/{n}"),
            )
            st.session_state["last_sens"] = (sens_df, res_key)
            progress.empty()
    with c2:
        if st.button("🌪️ 运行龙卷风分析", key="torn_btn"):
            with st.spinner("龙卷风分析中……"):
                tornado_df = sens.run_tornado(
                    build_settings(), kpi_col="avg_cycle_time",
                    n_runs=3, seed=int(seed_input),
                    order_arrival_list=order_arrival_list,
                )
            st.session_state["last_tornado"] = tornado_df

    if "last_sens" in st.session_state:
        sens_df, s_key = st.session_state["last_sens"]
        st.dataframe(sens_df.round(3), width="stretch")
        st.plotly_chart(viz.fig_sensitivity_line(sens_df, metric, param_name=RES_NAME_CN[s_key]),
                        width="stretch", key="chart_sens_line")
        inflection = sens.find_inflection_point(sens_df, "avg_cycle_time")
        st.info(f"💡 边际收益拐点：{RES_NAME_CN[s_key]} 配置 **{inflection}** 个后，"
                f"继续增加对平均周期的改善已低于 5%")

    if "last_tornado" in st.session_state:
        tornado_df = st.session_state["last_tornado"]
        st.plotly_chart(viz.fig_tornado(tornado_df, "avg_cycle_time"),
                        width="stretch", key="chart_tornado")

# ---------------- tab7 压力情景测试 ----------------
with tab7:
    st.header("🌪️ 压力情景测试")
    st.markdown(
        "模拟**需求暴涨**（到达速率×倍数）与**设备故障**（第120~180分钟停机），"
        "检验系统抗压能力，找出最先撑不住的压力点。"
    )
    n_runs_stress = st.slider("每个情景重复次数", 3, 20, 5, key="stress_runs")
    if st.button("🧨 运行压力测试", type="primary", key="stress_btn"):
        progress = st.progress(0.0, text="压力测试中……")
        scen = stress_mod.build_stress_scenarios(build_settings())
        compare = stress_mod.run_stress_comparison(
            scen, n_runs=n_runs_stress, seed=int(seed_input),
            order_arrival_list=order_arrival_list,
            progress_cb=lambda a, b, i, n: progress.progress(
                (a - 1) / b + (i / n) / b, text=f"情景 {a}/{b} · 第 {i}/{n} 次"),
        )
        st.session_state["last_stress"] = compare
        progress.empty()

    if "last_stress" in st.session_state:
        compare = st.session_state["last_stress"]
        st.markdown(stress_mod.stress_verdict(compare))
        st.dataframe(compare.round(2), width="stretch")
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(viz.fig_scenario_groupbar(
                compare, metrics=("avg_cycle_time", "p95_cycle_time")),
                width="stretch", key="chart_stress_cycle")
        with c2:
            st.plotly_chart(viz.fig_scenario_groupbar(
                compare, metrics=("throughput_per_hour", "max_queue_picker",
                                  "max_queue_amr", "max_queue_pack_station")),
                width="stretch", key="chart_stress_tp")

# ---------------- tab8 决策建议 ----------------
with tab8:
    st.header("💡 智能决策建议引擎")
    if not has_result():
        st.info("请先在「2️⃣ 仿真与可视化」运行一次仿真。")
    else:
        kpi = st.session_state["last_kpi"]
        c1, c2 = st.columns(2)
        sla_target = c1.number_input("SLA目标：P95周转周期 ≤ (分钟)", 10.0, 240.0, 30.0, 5.0)
        budget = c2.number_input("班次预算(元)，填0表示不校验", 0, 100000, 0, 500)
        adv_df = advisor.advice_to_dataframe(advisor.generate_advice(
            kpi,
            resources={k: v for k, v in zip(
                ["picker_num", "pack_station_num", "amr_num"],
                [picker_num, pack_station_num, amr_num])},
            sla_target=sla_target,
            budget=budget if budget > 0 else None,
        ))
        st.dataframe(adv_df, width="stretch")
        st.caption("每条建议都附带「失效边界条件」：业务前提变化后该建议可能不再成立。")
        st.download_button("📥 下载建议CSV",
                           data=data_io.df_to_csv_bytes(adv_df),
                           file_name="decision_advice.csv", mime="text/csv")

# ---------------- tab9 数据导入导出 ----------------
with tab9:
    st.header("📦 数据导入导出")
    st.subheader("导出（基于最近一次仿真结果）")
    if has_result():
        df_o = st.session_state["last_order"]
        df_e = st.session_state["last_event"]
        df_q = st.session_state["last_queue"]
        kpi = st.session_state["last_kpi"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.download_button("📋 订单结果CSV", data=data_io.df_to_csv_bytes(df_o),
                           file_name="order_result.csv", mime="text/csv")
        c2.download_button("📜 事件日志CSV", data=data_io.df_to_csv_bytes(df_e),
                           file_name="event_log.csv", mime="text/csv")
        c3.download_button("📊 队列监控CSV", data=data_io.df_to_csv_bytes(df_q),
                           file_name="queue_monitor.csv", mime="text/csv")
        excel_bytes = data_io.build_excel_bytes(
            df_o, df_e, df_q, kpi,
            advisor.advice_to_dataframe(advisor.generate_advice(kpi)) if kpi else None,
        )
        c4.download_button("📦 全部结果打包Excel", data=excel_bytes,
                           file_name="simulation_full_result.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        cfg_json = data_io.config_to_json(
            {"picker_num": picker_num, "pack_station_num": pack_station_num, "amr_num": amr_num},
            {"time_model": time_model, "sim_duration": sim_duration,
             "arrival_mode": arrival_mode, "arrival_rate": arrival_rate,
             "seed": seed_input},
        )
        c5.download_button("⚙️ 配置JSON", data=cfg_json,
                           file_name="sim_config.json", mime="application/json")
    else:
        st.info("请先运行一次仿真，这里会提供全部下载按钮。")

    st.divider()
    st.subheader("导入")
    c1, c2 = st.columns(2)
    with c1:
        cfg_upload = st.file_uploader("上传配置JSON（查看后手动填回侧边栏）", type=["json"])
        if cfg_upload is not None:
            try:
                cfg_back = data_io.json_to_config(cfg_upload.read().decode("utf-8"))
                st.json(cfg_back)
                st.caption("把 JSON 中的数值填到左侧「仿真全局参数」即可恢复该配置。")
            except ValueError as e:
                st.error(str(e))
    with c2:
        arr_upload = st.file_uploader("上传订单到达时刻CSV（单列数字）", type=["csv"])
        if arr_upload is not None:
            try:
                arr_values = data_io.read_arrival_csv(arr_upload)
                st.success(f"解析到 {len(arr_values)} 个到达时刻，"
                           f"前5个：{arr_values[:5]} → 可复制到「固定到达时刻」输入框。")
            except ValueError as e:
                st.error(str(e))

# ---------------- tab10 一键自动报告 ----------------
with tab10:
    st.header("📄 一键自动仿真报告")
    if not has_result():
        st.info("请先在「2️⃣ 仿真与可视化」运行一次仿真。")
    else:
        kpi = st.session_state["last_kpi"]
        df_o = st.session_state["last_order"]
        df_e = st.session_state["last_event"]
        df_q = st.session_state["last_queue"]
        report_title = st.text_input("报告标题", "物流系统仿真实验报告")
        report_author = st.text_input("报告作者/小组（可选）", "")
        if st.button("📄 生成HTML报告", type="primary", key="report_btn"):
            figs = {
                "周转周期分布": viz.fig_cycle_distribution(df_o),
                "周转周期趋势": viz.fig_cycle_timeline(df_o),
                "周期构成分解": viz.fig_stage_decomposition(df_o),
                "资源利用率": viz.fig_utilization_bar(kpi),
                "队列长度时序": viz.fig_queue_timeseries(df_q),
                "每小时吞吐量": viz.fig_throughput_timeline(df_o),
            }
            adv_df = advisor.advice_to_dataframe(advisor.generate_advice(
                kpi,
                resources={"picker_num": picker_num, "pack_station_num": pack_station_num,
                           "amr_num": amr_num},
            ))
            meta = {
                "资源配置": f"拣选{picker_num}人/打包{pack_station_num}台/AMR{amr_num}台",
                "时间模型": time_model,
                "到达模式": arrival_mode,
                "随机种子": seed_input,
                "作者": report_author or "未填写",
            }
            html_str = report_mod.generate_html_report(
                report_title, kpi, df_o, df_e, df_q, figs, adv_df, meta=meta,
            )
            st.session_state["last_report_html"] = html_str

        if "last_report_html" in st.session_state:
            st.download_button(
                "⬇️ 下载HTML报告",
                data=st.session_state["last_report_html"],
                file_name=f"{report_title}.html",
                mime="text/html",
            )
            st.success("报告已生成：包含 KPI 总览、6 张交互图表、数据明细与决策建议。"
                       "用浏览器打开后可直接打印/另存为 PDF 提交。")

# ==================== 页脚 ====================
st.divider()
st.caption("物流系统智能仿真决策平台 V2 ｜ 技术栈：Python + SimPy + Streamlit + Plotly ｜ "
           "部署：GitHub + Streamlit Cloud（share.streamlit.io）")
# ========= Tab11 仓库2D&3D可视化 =========
with tab11:
    st.subheader("🏬 仓储仿真2D平面图 + 3D立体视图")
    st.markdown("""
    > 💡 使用说明：
    > 1. 先切换到【2 仿真与可视化】，点击【运行单次仿真】
    > 2. 仿真跑完，再回到本页面查看仓库仿真图
    > 3. 鼠标悬浮在圆点上，查看订单/AMR详细信息
    > 4. 3D图：按住鼠标拖拽旋转，滚轮缩放
    """)
    df_o = st.session_state.get("last_order")
    df_q = st.session_state.get("last_queue")

    if df_o is not None and df_q is not None and len(df_o)>0:
        view_mode = st.radio("选择视图", ["2D俯视平面图", "3D立体仓库"], horizontal=True)
        if view_mode == "2D俯视平面图":
            fig2d = create_warehouse_2d(df_o, df_q)
            st.plotly_chart(fig2d, use_container_width=True, key="warehouse_2d_enhanced")
        else:
            fig3d = create_warehouse_3d(df_o, df_q)
            st.plotly_chart(fig3d, use_container_width=True, key="warehouse_3d_enhanced")
    else:
        st.warning("⚠️暂无仿真数据，请前往【2 仿真与可视化】运行单次仿真！")


