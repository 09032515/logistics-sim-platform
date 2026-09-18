import streamlit as st
import simpy
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ----------------------仿真内核----------------------
class 订单履约系统:
    def __init__(self, env, 拣选员数量=2, 打包台数量=1, 缓冲区容量=2, 搬运耗时=2):
        self.env = env
        self.拣选员 = simpy.Resource(env, capacity=拣选员数量)
        self.打包台 = simpy.Resource(env, capacity=打包台数量)
        self.待打包缓冲区 = simpy.Store(env, capacity=缓冲区容量)
        self.搬运耗时 = 搬运耗时
        self.订单结果集 = []
        self.事件日志 = []
        self.拣选总忙碌 = 0
        self.打包总忙碌 = 0

    def 处理单个订单(self, 订单编号, 到达时刻, 拣选工时, 打包工时, 承诺完工时刻):
        yield self.env.timeout(到达时刻)
        实际到达时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"订单到达","发生时间":实际到达时间})

        拣选请求 = self.拣选员.request()
        yield 拣选请求
        拣选开始时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"拣选开始","发生时间":拣选开始时间})

        yield self.env.timeout(拣选工时)
        self.拣选总忙碌 += 拣选工时
        拣选结束时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"拣选完成","发生时间":拣选结束时间})

        yield self.待打包缓冲区.put(订单编号)
        self.拣选员.release(拣选请求)
        self.事件日志.append({"订单编号":订单编号,"事件类型":"进入缓冲区","发生时间":self.env.now})

        yield self.env.timeout(self.搬运耗时)
        搬运完成时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"搬运完成","发生时间":搬运完成时间})

        打包请求 = self.打包台.request()
        yield 打包请求
        _ = yield self.待打包缓冲区.get()
        打包开始时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"打包开始","发生时间":打包开始时间})

        yield self.env.timeout(打包工时)
        self.打包总忙碌 += 打包工时
        打包结束时间 = self.env.now
        self.事件日志.append({"订单编号":订单编号,"事件类型":"打包完成","发生时间":打包结束时间})
        self.打包台.release(打包请求)

        # 全部转浮点数，避免timedelta类型
        拣选等待时长 = float(拣选开始时间 - 实际到达时间)
        打包等待时长 = float(打包开始时间 - 搬运完成时间)
        订单总周期 = float(打包结束时间 - 实际到达时间)
        self.订单结果集.append({
            "订单编号":订单编号,
            "到达时刻":float(实际到达时间),
            "拣选开始":float(拣选开始时间),
            "拣选结束":float(拣选结束时间),
            "搬运完成":float(搬运完成时间),
            "打包开始":float(打包开始时间),
            "打包结束":float(打包结束时间),
            "拣选等待时长":拣选等待时长,
            "打包等待时长":打包等待时长,
            "拣选作业时长":float(拣选工时),
            "搬运时长":float(self.搬运耗时),
            "打包作业时长":float(打包工时),
            "订单总周期":订单总周期,
            "承诺完工时刻":float(承诺完工时刻)
        })

def 运行仿真(订单列表,拣选员数量=2,打包台数量=1,缓冲区容量=2,搬运耗时=2):
    env = simpy.Environment()
    系统实例 = 订单履约系统(env,拣选员数量,打包台数量,缓冲区容量,搬运耗时)
    for 单条订单 in 订单列表:
        env.process(系统实例.处理单个订单(*单条订单))
    env.run()
    df订单输出 = pd.DataFrame(系统实例.订单结果集)
    df事件输出 = pd.DataFrame(系统实例.事件日志)
    仿真总时长 = float(env.now)
    # 计算资源利用率
    拣选利用率 = (系统实例.拣选总忙碌 / (拣选员数量 * 仿真总时长)) *100
    打包利用率 = (系统实例.打包总忙碌 / (打包台数量 * 仿真总时长)) *100
    return df订单输出, df事件输出, 拣选利用率, 打包利用率, 仿真总时长

# 订单数据校验函数
def 校验订单数据(df):
    err_msg = ""
    if (df["到达时刻"] < 0).any():
        err_msg += "到达时刻不能为负数；"
    if (df["拣选工时"] <= 0).any():
        err_msg += "拣选工时必须大于0；"
    if (df["打包工时"] <= 0).any():
        err_msg += "打包工时必须大于0；"
    if (df["承诺完工时刻"] <0).any():
        err_msg += "承诺完工时刻不能为负数；"
    return err_msg

# ----------------------网页UI----------------------
st.set_page_config(page_title="物流订单履约仿真平台",layout="wide")
st.title("📦 物流订单履行系统仿真平台")

# ==========侧边栏【参数+订单来源选择】==========
with st.sidebar:
    st.header("⚙ 参数配置")
    # 数字输入，最小=1，无上限，自由输入
    exp3_拣选员数量 = st.number_input("拣选员数量", min_value=1, value=2, step=1, key="exp3_pick")
    exp3_打包台数量 = st.number_input("打包台数量", min_value=1, value=1, step=1, key="exp3_pack")
    exp3_缓冲区容量 = st.number_input("待打包缓冲区容量", min_value=1, value=2, step=1, key="exp3_buf")
    exp3_搬运耗时 = st.number_input("搬运耗时（分钟）", min_value=1, value=2, step=1, key="exp3_move")

    st.divider()
    st.header("📥订单数据源")
    data_source = st.radio("选择订单来源",["在线录入订单","默认示例订单","上传CSV文件"], key="source3")

# 示例订单
default_df = pd.DataFrame([
    {"订单编号":"O01","到达时刻":0,"拣选工时":6,"打包工时":4,"承诺完工时刻":15},
    {"订单编号":"O02","到达时刻":2,"拣选工时":7,"打包工时":4,"承诺完工时刻":16},
    {"订单编号":"O03","到达时刻":5,"拣选工时":5,"打包工时":4,"承诺完工时刻":17},
    {"订单编号":"O04","到达时刻":7,"拣选工时":8,"打包工时":5,"承诺完工时刻":22},
])

tab1, tab2 = st.tabs(["⚙单次仿真","📊多方案对比"])

# ==========单次仿真页面==========
with tab1:
    st.header("订单履行系统仿真")
    orders_df = None
    if data_source == "在线录入订单":
        st.subheader("✏在线录入订单")
        orders_df = st.data_editor(default_df, num_rows="dynamic", use_container_width=True)
        # 校验
        error = 校验订单数据(orders_df)
        if error:
            st.error(f"❌订单数据错误：{error}")
        else:
            st.success("✅订单数据校验通过")
        exp3_orders = [tuple(row) for _,row in orders_df.iterrows()]
    elif data_source == "默认示例订单":
        orders_df = default_df
        exp3_orders = [tuple(row) for _,row in orders_df.iterrows()]
        st.info("ℹ使用内置测试订单")
    elif data_source == "上传CSV文件":
        exp3_upload = st.file_uploader("上传订单CSV文件", type=["csv"], key="exp3_file")
        st.markdown("CSV表头：`订单编号,到达时刻,拣选工时,打包工时,承诺完工时刻`")
        if exp3_upload is not None:
            orders_df = pd.read_csv(exp3_upload, encoding="utf-8-sig")
            exp3_orders = [tuple(row) for _,row in orders_df.iterrows()]
            st.info(f"✅已读取上传订单，共 {len(exp3_orders)} 条")
        else:
            exp3_orders = [tuple(row) for _,row in default_df.iterrows()]
            st.warning("尚未上传文件，临时使用示例订单")

    run_exp3 = st.button("▶ 启动仿真运行", type="primary", key="run_exp3")
    if run_exp3:
        # 运行前再校验
        err = 校验订单数据(pd.DataFrame(exp3_orders,columns=["订单编号","到达时刻","拣选工时","打包工时","承诺完工时刻"]))
        if err:
            st.error("仿真终止！订单数据非法："+err)
        else:
            with st.spinner("仿真计算进行中，请稍候..."):
                df_res, df_log, pick_use, pack_use, sim_time = 运行仿真(exp3_orders,exp3_拣选员数量,exp3_打包台数量,exp3_缓冲区容量,exp3_搬运耗时)
            st.success("✅仿真执行完成！")
            # 指标卡片
            col1,col2,col3,col4 = st.columns(4)
            avg_cycle = df_res['订单总周期'].mean()
            avg_wait_pick = df_res['拣选等待时长'].mean()
            with col1:
                st.metric("平均订单总周期",f"{avg_cycle:.2f} 分钟")
            with col2:
                st.metric("平均拣选等待时长",f"{avg_wait_pick:.2f} 分钟")
            with col3:
                st.metric("拣选员利用率",f"{pick_use:.1f} %")
            with col4:
                st.metric("打包台利用率",f"{pack_use:.1f} %")
            # 拥堵提示
            if pick_use>95 or pack_use>95:
                st.warning("⚠警告：资源利用率接近100%，系统处于拥堵状态，订单排队严重")

            t1, t2, t3, t4 = st.tabs(["📊订单绩效结果","📜仿真事件日志","📈周期分解图","📉资源&甘特图"])
            with t1:
                st.dataframe(df_res, use_container_width=True)
                csv1 = df_res.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("💾下载【订单绩效结果.csv】", data=csv1, file_name="订单绩效结果.csv",mime="text/csv", key="d1")
            with t2:
                st.dataframe(df_log, use_container_width=True)
                csv2 = df_log.to_csv(index=False, encoding="utf-8-sig")
                st.download_button("💾下载【仿真事件日志.csv】", data=csv2, file_name="仿真事件日志.csv",mime="text/csv", key="d2")
            with t3:
                # 订单周期堆叠柱状图
                fig_stack = go.Figure()
                fig_stack.add_trace(go.Bar(x=df_res["订单编号"],y=df_res["拣选等待时长"],name="拣选等待",marker_color="#ff7373"))
                fig_stack.add_trace(go.Bar(x=df_res["订单编号"],y=df_res["拣选作业时长"],name="拣选作业",marker_color="#73b8ff"))
                fig_stack.add_trace(go.Bar(x=df_res["订单编号"],y=df_res["搬运时长"],name="搬运",marker_color="#89e894"))
                fig_stack.add_trace(go.Bar(x=df_res["订单编号"],y=df_res["打包等待时长"],name="打包等待",marker_color="#ffd273"))
                fig_stack.add_trace(go.Bar(x=df_res["订单编号"],y=df_res["打包作业时长"],name="打包作业",marker_color="#c292ff"))
                fig_stack.update_layout(barmode="stack",title="各订单周期构成分解图",xaxis_title="订单编号",yaxis_title="时间(分钟)")
                st.plotly_chart(fig_stack,use_container_width=True)
            with t4:
                c_a,c_b = st.columns(2)
                with c_a:
                    # 资源利用率柱状
                    df_util = pd.DataFrame({"资源":["拣选员","打包台"],"利用率":[pick_use,pack_use]})
                    fig_util = px.bar(df_util,x="资源",y="利用率",range_y=[0,100],title="资源利用率(%)",text="利用率")
                    st.plotly_chart(fig_util,use_container_width=True)
                with c_b:
                    # 甘特图（全部是数值，不会出现timedelta）
                    fig_gantt = go.Figure()
                    y_ticks = []
                    y_labels = []
                    for idx, row in df_res.iterrows():
                        y_pos = idx
                        y_ticks.append(y_pos)
                        y_labels.append(row["订单编号"])
                        #拣选矩形
                        fig_gantt.add_trace(go.Bar(
                            y=[y_pos],
                            x=[row["拣选结束"] - row["拣选开始"]],
                            base=[row["拣选开始"]],
                            orientation='h',
                            name="拣选",
                            marker_color="#73b8ff",
                            showlegend=(idx==0)
                        ))
                        #打包矩形
                        fig_gantt.add_trace(go.Bar(
                            y=[y_pos],
                            x=[row["打包结束"] - row["打包开始"]],
                            base=[row["打包开始"]],
                            orientation='h',
                            name="打包",
                            marker_color="#ff7373",
                            showlegend=(idx==0)
                        ))
                    fig_gantt.update_layout(
                        title="订单处理甘特图",
                        xaxis_title="仿真时间（分钟）",
                        yaxis = dict(tickvals=y_ticks, ticktext=y_labels),
                        barmode="overlay",
                        height=300
                    )
                    st.plotly_chart(fig_gantt,use_container_width=True)

# ==========多方案对比页面==========
with tab2:
    st.header("仿真决策平台｜多方案对比")
    st.markdown("设置2组方案，对比不同人员/设备配置下订单平均周期，找到较优方案")
    st.subheader("订单数据源")
    data_source4 = st.radio("订单来源",["在线录入订单","默认示例订单","上传CSV文件"], key="source4")
    exp4_orders = []
    if data_source4 == "在线录入订单":
        orders4_df = st.data_editor(default_df, num_rows="dynamic", use_container_width=True, key="editor4")
        error4 = 校验订单数据(orders4_df)
        if error4:
            st.error(f"❌订单数据错误：{error4}")
        else:
            st.success("✅订单数据校验通过")
        exp4_orders = [tuple(row) for _,row in orders4_df.iterrows()]
    elif data_source4 == "默认示例订单":
        exp4_orders = [tuple(row) for _,row in default_df.iterrows()]
        st.info("ℹ对比使用内置测试订单")
    elif data_source4 == "上传CSV文件":
        exp4_upload = st.file_uploader("上传订单CSV", type=["csv"], key="exp4_file")
        st.markdown("CSV表头：`订单编号,到达时刻,拣选工时,打包工时,承诺完工时刻`")
        if exp4_upload is not None:
            df_up4 = pd.read_csv(exp4_upload, encoding="utf-8-sig")
            exp4_orders = [tuple(row) for _,row in df_up4.iterrows()]
            st.info(f"✅读取上传订单，共 {len(exp4_orders)} 条")
        else:
            exp4_orders = [tuple(row) for _,row in default_df.iterrows()]
            st.warning("尚未上传文件，临时使用示例订单")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("方案A")
        A_拣选员 = st.number_input("拣选员数量A", min_value=1,value=2, step=1, key="A1")
        A_打包台 = st.number_input("打包台数量A", min_value=1,value=1, step=1, key="A2")
        A_缓冲区 = st.number_input("缓冲区A", min_value=1,value=2, step=1, key="A3")
        A_搬运 = st.number_input("搬运耗时A", min_value=1,value=2, step=1, key="A4")
    with col_b:
        st.subheader("方案B")
        B_拣选员 = st.number_input("拣选员数量B", min_value=1,value=3, step=1, key="B1")
        B_打包台 = st.number_input("打包台数量B", min_value=1,value=2, step=1, key="B2")
        B_缓冲区 = st.number_input("缓冲区B", min_value=1,value=3, step=1, key="B3")
        B_搬运 = st.number_input("搬运耗时B", min_value=1,value=2, step=1, key="B4")

    run_exp4 = st.button("▶ 同时运行方案A、B仿真", type="primary", key="run_exp4")
    if run_exp4:
        err4 = 校验订单数据(pd.DataFrame(exp4_orders,columns=["订单编号","到达时刻","拣选工时","打包工时","承诺完工时刻"]))
        if err4:
            st.error("仿真终止！订单数据非法："+err4)
        else:
            with st.spinner("多方案仿真计算..."):
                dfA, logA, pickA, packA, _ = 运行仿真(exp4_orders,A_拣选员,A_打包台,A_缓冲区,A_搬运)
                dfB, logB, pickB, packB, _ = 运行仿真(exp4_orders,B_拣选员,B_打包台,B_缓冲区,B_搬运)
            st.success("✅两个方案仿真完成")
            res_compare = pd.DataFrame({
                "方案":["方案A","方案B"],
                "拣选员":[A_拣选员,B_拣选员],
                "打包台":[A_打包台,B_打包台],
                "缓冲区":[A_缓冲区,B_缓冲区],
                "平均订单周期":[dfA["订单总周期"].mean(), dfB["订单总周期"].mean()],
                "平均拣选等待":[dfA["拣选等待时长"].mean(), dfB["拣选等待时长"].mean()],
                "拣选员利用率":[pickA,pickB],
                "打包台利用率":[packA,packB]
            })
            st.subheader("📋方案对比汇总表")
            st.dataframe(res_compare, use_container_width=True)
            # 对比图表
            c1,c2 = st.columns(2)
            with c1:
                fig_cycle = px.bar(res_compare,x="方案",y="平均订单周期",title="平均订单周期对比",text="平均订单周期")
                st.plotly_chart(fig_cycle,use_container_width=True)
            with c2:
                # 利用率对比
                fig_util_comp = go.Figure()
                fig_util_comp.add_trace(go.Bar(x=res_compare["方案"],y=res_compare["拣选员利用率"],name="拣选员利用率"))
                fig_util_comp.add_trace(go.Bar(x=res_compare["方案"],y=res_compare["打包台利用率"],name="打包台利用率"))
                fig_util_comp.update_layout(title="资源利用率对比",barmode="group")
                st.plotly_chart(fig_util_comp,use_container_width=True)
