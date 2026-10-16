"""
warehouse_viz.py
完全兼容版本，不读取df_o、df_q里面任何自定义字段
仓库布局完整保留，2D平面 +3D立体可视化，外行清晰易懂
"""
import plotly.graph_objects as go
import pandas as pd

def create_warehouse_2d(df_order: pd.DataFrame, df_queue: pd.DataFrame):
    fig = go.Figure()
    # 仓库尺寸 单位米
    W = 120
    H = 70
    # 仓库外框
    fig.add_shape(type="rect", x0=0, y0=0, x1=W, y1=H, line=dict(color="#222222", width=3))

    # ========= 区域定义（带文字标注，外行看懂） =========
    # 入库区 红色
    fig.add_shape(type="rect", x0=0, y0=25, x1=12, y1=45, fillcolor="#ff4444", opacity=0.6)
    fig.add_annotation(x=6, y=50, text="📥入库区", showarrow=False, font=dict(size=14,color="red"))

    # 4排货架区 灰色（存储区）
    shelf_list = [
        {"y0":8, "y1":18},
        {"y0":22, "y1":32},
        {"y0":36, "y1":46},
        {"y0":50, "y1":60},
    ]
    for shelf in shelf_list:
        fig.add_shape(type="rect", x0=15, y0=shelf["y0"], x1=55, y1=shelf["y1"], fillcolor="#aaaaaa", opacity=0.7)
    fig.add_annotation(x=35, y=65, text="📦货架存储区", showarrow=False, font=dict(size=14,color="#555555"))

    # AMR主通道（白色空白通道）
    fig.add_annotation(x=62, y=35, text="🚚AMR通行通道", showarrow=False, font=dict(size=13,color="#3377dd"))

    # 拣选工作站 蓝色
    fig.add_shape(type="rect", x0=65, y0=45, x1=85, y1=60, fillcolor="#4488ff", opacity=0.6)
    fig.add_annotation(x=75, y=63, text="👷拣选工作站", showarrow=False, font=dict(size=14,color="#2266cc"))

    # 打包工作站 绿色
    fig.add_shape(type="rect", x0=65, y0=10, x1=85, y1=25, fillcolor="#33bb55", opacity=0.6)
    fig.add_annotation(x=75, y=7, text="📦打包工作站", showarrow=False, font=dict(size=14,color="#229944"))

    # 出库区 橙色
    fig.add_shape(type="rect", x0=95, y0=25, x1=115, y1=45, fillcolor="#ff9933", opacity=0.6)
    fig.add_annotation(x=105, y=50, text="📤出库区", showarrow=False, font=dict(size=14,color="#dd7711"))

    # ========= 订单点位（只展示订单索引ID，不读取任何额外字段） =========
    df_plot = df_order.copy()
    df_plot["plot_x"] = 20 + (df_plot.index % 5) * 7
    df_plot["plot_y"] = 12 + (df_plot.index // 5) * 11

    if len(df_plot) > 0:
        hover_text = df_plot.apply(lambda r: f"订单编号:{r.name}", axis=1)
        fig.add_trace(go.Scatter(
            x=df_plot["plot_x"], y=df_plot["plot_y"],
            mode="markers", marker=dict(symbol="circle", size=11, color="#4488ff"),
            hovertext=hover_text, name="订单"
        ))

    # ========= AMR小车：不再读取df_q的任何列，只固定文字 =========
    if not df_queue.empty:
        amr_x = 60
        amr_y_list = [15, 30, 48]
        for idx in range(min(3, len(df_queue))):
            fig.add_trace(go.Scatter(
                x=[amr_x], y=[amr_y_list[idx % 3]],
                mode="markers", marker=dict(symbol="diamond", size=14, color="#ff2222"),
                hovertext=f"AMR自动导引小车{idx+1}",
                name=f"AMR小车{idx+1}"
            ))

    fig.update_layout(
        title="🏭仓库2D平面仿真图（俯视）",
        xaxis=dict(title="X方向 米", range=[-5, W+5], showgrid=True),
        yaxis=dict(title="Y方向 米", range=[-5, H+5], showgrid=True),
        width=1000, height=620,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=20, r=20, t=80, b=20)
    )
    return fig


def create_warehouse_3d(df_order: pd.DataFrame, df_queue: pd.DataFrame):
    fig = go.Figure()
    W = 120
    H = 70
    h_shelf = 10    #货架高度
    h_work = 3      #工作站高度

    # 入库区
    fig.add_trace(go.Mesh3d(
        x=[0,12,12,0,0,12,12,0], y=[25,25,45,45,25,25,45,45], z=[0,0,0,0,h_work,h_work,h_work,h_work],
        color="#ff4444", opacity=0.7, name="📥入库区"
    ))
    # 4组货架
    shelf_list = [{"y0":8, "y1":18},{"y0":22, "y1":32},{"y0":36, "y1":46},{"y0":50, "y1":60}]
    for shelf in shelf_list:
        fig.add_trace(go.Mesh3d(
            x=[15,55,55,15,15,55,55,15], y=[shelf["y0"],shelf["y0"],shelf["y1"],shelf["y1"],shelf["y0"],shelf["y0"],shelf["y1"],shelf["y1"]],
            z=[0,0,0,0,h_shelf,h_shelf,h_shelf,h_shelf],
            color="#aaaaaa", opacity=0.7, name="📦货架存储区"
        ))
    #拣选工作站
    fig.add_trace(go.Mesh3d(
        x=[65,85,85,65,65,85,85,65], y=[45,45,60,60,45,45,60,60],
        z=[0,0,0,0,h_work,h_work,h_work,h_work], color="#4488ff", opacity=0.7, name="👷拣选工作站"
    ))
    #打包工作站
    fig.add_trace(go.Mesh3d(
        x=[65,85,85,65,65,85,85,65], y=[10,10,25,25,10,10,25,25],
        z=[0,0,0,0,h_work,h_work,h_work,h_work], color="#33bb55", opacity=0.7, name="📦打包工作站"
    ))
    #出库区
    fig.add_trace(go.Mesh3d(
        x=[95,115,115,95,95,115,115,95], y=[25,25,45,45,25,25,45,45],
        z=[0,0,0,0,h_work,h_work,h_work,h_work], color="#ff9933", opacity=0.7, name="📤出库区"
    ))

    #订单货物点云
    df_plot = df_order.copy()
    df_plot["plot_x"] = 20 + (df_plot.index % 5) *7
    df_plot["plot_y"] =12 + (df_plot.index //5)*11
    df_plot["plot_z"] = 1.2

    if len(df_plot) > 0:
        fig.add_trace(go.Scatter3d(
            x=df_plot["plot_x"],y=df_plot["plot_y"],z=df_plot["plot_z"],
            mode="markers", marker=dict(size=6,color="#4488ff"),
            name="订单"
        ))
    #AMR小车，不读取df_q字段
    if not df_queue.empty:
        amr_x =60
        amr_y_list = [15,30,48]
        for idx in range(min(3, len(df_queue))):
            fig.add_trace(go.Scatter3d(
                x=[amr_x], y=[amr_y_list[idx%3]], z=[1.5],
                mode="markers", marker=dict(size=9,color="#ff2222"),
                hovertext=f"AMR自动导引小车{idx+1}",
                name=f"AMR小车{idx+1}"
            ))

    fig.update_layout(
        title="🏢仓库3D立体仿真视图（可拖拽旋转缩放）",
        scene=dict(xaxis_title="X(m)", yaxis_title="Y(m)", zaxis_title="高度(m)"),
        width=1000, height=650,
        legend=dict(orientation="h", yanchor="bottom",y=1.0,x=0.5)
    )
    return fig
