# -*- coding: utf-8 -*-
"""
data_io.py —— 功能9：数据导入导出
===================================
  1. 导出：订单结果 CSV / 事件日志 CSV / 队列监控 CSV / 配置 JSON
            / 综合结果 Excel（多工作表，一个文件打包全部结果）
  2. 导入：从 JSON 恢复仿真配置；从 CSV 读取历史作业时间（经验分布）
            / 订单到达时刻列表
所有函数返回字符串或 BytesIO，方便网页下载按钮直接使用。
"""

import io
import json

import pandas as pd

# ==================== 导出 ====================
def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """DataFrame → CSV bytes（utf-8-sig 解决 Excel 中文乱码）"""
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def config_to_json(resources: dict, model: dict) -> str:
    """资源配置 + 模型参数 → JSON 字符串（用于保存/恢复配置）"""
    payload = {"resources": resources, "model": model}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_excel_bytes(
    df_order: pd.DataFrame,
    df_event: pd.DataFrame,
    df_queue: pd.DataFrame,
    kpi: dict = None,
    advice: pd.DataFrame = None,
) -> bytes:
    """把全部仿真结果打包成一个 Excel（多工作表）"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_order.to_excel(writer, sheet_name="订单结果", index=False)
        df_event.to_excel(writer, sheet_name="事件日志", index=False)
        df_queue.to_excel(writer, sheet_name="队列监控", index=False)
        if kpi:
            pd.DataFrame([kpi]).to_excel(writer, sheet_name="KPI指标", index=False)
        if advice is not None and len(advice) > 0:
            advice.to_excel(writer, sheet_name="决策建议", index=False)
    return buf.getvalue()


# ==================== 导入 ====================
def parse_order_list(text: str):
    """解析网页文本框里的订单到达时刻字符串，如 '0,2,5,8' → [0.0,2.0,...]"""
    if text is None or str(text).strip() == "":
        return []
    parts = [p.strip() for p in str(text).split(",") if p.strip() != ""]
    result = []
    for p in parts:
        try:
            v = float(p)
        except ValueError:
            raise ValueError(f"无法解析订单时间: {p}")
        if v < 0:
            raise ValueError(f"订单到达时刻不能为负数: {p}")
        result.append(v)
    return result


def json_to_config(json_text: str) -> dict:
    """JSON 字符串 → 配置字典 {resources: {...}, model: {...}}"""
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}")


def read_empirical_csv(uploaded_file) -> pd.DataFrame:
    """
    读取历史作业时间 CSV（经验分布数据源），
    要求包含三列之一或多列：pick_time / transport_time / pack_time
    """
    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
    expected = {"pick_time", "transport_time", "pack_time"}
    have = expected.intersection(df.columns)
    if not have:
        raise ValueError(
            "CSV 至少需要包含 pick_time / transport_time / pack_time 中的一列，"
            "当前列: " + ", ".join(df.columns)
        )
    return df


def read_arrival_csv(uploaded_file) -> list:
    """读取订单到达时刻 CSV（单列数字，或含 arrive_time 列）"""
    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")
    col = None
    for c in ("arrive_time", "arrival_time", "time"):
        if c in df.columns:
            col = c
            break
    if col is None:
        col = df.columns[0]
    values = pd.to_numeric(df[col], errors="coerce").dropna().tolist()
    if not values:
        raise ValueError("CSV 中没有有效的订单到达时刻数据")
    return values


# ==================== 本地测试 ====================
if __name__ == "__main__":
    from sim_core import run_one_simulation, simulation_to_dfs, compute_kpis
    from advisor import generate_advice, advice_to_dataframe

    cfg = {"picker_num": 2, "pack_station_num": 1, "amr_num": 3,
           "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
           "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 300}
    sim = run_one_simulation(cfg, seed=8)
    df_o, df_e, df_q = simulation_to_dfs(sim)
    kpi = compute_kpis(sim)
    adv = advice_to_dataframe(generate_advice(kpi, resources={"picker_num": 2,
                                                              "pack_station_num": 1,
                                                              "amr_num": 3}))

    excel_bytes = build_excel_bytes(df_o, df_e, df_q, kpi, adv)
    print(f"Excel 打包成功，大小 {len(excel_bytes)} 字节")
    cfg_json = config_to_json({"picker_num": 2}, {"time_model": "gamma"})
    back = json_to_config(cfg_json)
    print("配置 JSON 往返解析成功:", back)
    lst = parse_order_list("0,2,5,8,12")
    print("订单列表解析成功:", lst)
    print("✅ data_io.py 测试通过！")
