import streamlit as st
import pandas as pd
from sim_core import run_one_simulation

# ----------------网页全局基础设置----------------
st.set_page_config(
    page_title="物流系统智能仿真决策平台｜实验4",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦物流系统智能仿真决策平台")
st.subheader("课程实验4｜基于SimPy离散事件仿真｜实验1确定性基准版本")
st.markdown("> 说明：当前版本为实验1确定性模型；输出事件日志可下载，用于人工推演校核。")
st.divider()

# ----------------侧边栏：全部参数配置区域----------------
with st.sidebar:
    st.header("🔧仿真情景参数配置")
    st.subheader("资源参数")
    picker_num = st.number_input(label="拣选人员数量", min_value=1, max_value=6, value=2, step=1)
    pack_station_num = st.number_input(label="打包工作台数量", min_value=1, max_value=4, value=1, step=1)
    amr_num = st.number_input(label="AMR搬运机器人数量", min_value=1, max_value=10, value=3, step=1)
    sim_duration = st.number_input(label="仿真总时长（单位：分钟）", min_value=100, max_value=1000, value=480, step=10)

    st.divider()
    st.subheader("实验1‑固定订单输入（人工推演对照）")
    st.markdown("多个订单到达时刻，英文逗号隔开，例：0,2,5,8")
    order_input_text = st.text_area("订单到达时刻列表", value="0,2,5,8,12,15,20,22,28,33")
    seed_input = st.number_input("随机种子(预留给实验2随机输入)", value=42)

# 解析文本框输入的订单时间字符串，转为数字列表
try:
    order_arrival_list = [float(x.strip()) for x in order_input_text.split(",") if x.strip() != ""]
except Exception as parse_err:
    st.error(f"订单时间解析失败：{parse_err}")
    order_arrival_list = []

# 主页面运行按钮
run_sim_button = st.button("▶️运行单次仿真（实验1确定性模型）", type="primary")

if run_sim_button:
    if len(order_arrival_list) <= 0:
        st.warning("⚠️请填写订单到达时刻！")
    else:
        with st.spinner("⏳仿真正在运行计算，请稍候……"):
            sim_settings_dict = {
                "picker_num": picker_num,
                "pack_station_num": pack_station_num,
                "amr_num": amr_num,
                "sim_duration": sim_duration
            }
            # 调用sim_core的仿真函数
            sim_res = run_one_simulation(
                settings=sim_settings_dict,
                order_arrival_list=order_arrival_list,
                seed=int(seed_input)
            )
        st.success("✅仿真运行完毕！")

        # 拿到仿真输出数据
        df_order = pd.DataFrame(sim_res.order_records)
        df_event_log = pd.DataFrame(sim_res.event_log)

        tab_order, tab_event, tab_stat = st.tabs(["📋订单完整结果表", "📜事件校核日志", "📊基础统计指标"])

        with tab_order:
            st.dataframe(df_order, use_container_width=True)
            csv_download_1 = df_order.to_csv(index=False, encoding="utf‑8‑sig")
            st.download_button(
                label="📥下载订单结果CSV文件",
                data=csv_download_1,
                file_name="web_sim_order_result.csv",
                mime="text/csv"
            )

        with tab_event:
            st.dataframe(df_event_log, use_container_width=True)
            csv_download_2 = df_event_log.to_csv(index=False, encoding="utf‑8‑sig")
            st.download_button(
                label="📥下载事件日志CSV（用于模型校核）",
                data=csv_download_2,
                file_name="web_sim_event_log.csv",
                mime="text/csv"
            )

        with tab_stat:
            if len(df_order) > 0:
                avg_cycle = df_order["cycle_time"].mean()
                max_cycle = df_order["cycle_time"].max()
                min_cycle = df_order["cycle_time"].min()
                completed_count = len(df_order)
                st.markdown(f"""
                - 完成订单总数量：**{completed_count}**
                - 订单平均周期：**{avg_cycle:.2f} 分钟**
                - 最大订单周期：**{max_cycle:.2f} 分钟**
                - 最小订单周期：**{min_cycle:.2f} 分钟**
                """)

st.divider()
st.info("💡迭代提示：下一阶段开发实验2随机输入、实验3批量仿真、压力情景、方案对比图表。")