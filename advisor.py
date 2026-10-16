# -*- coding: utf-8 -*-
"""
advisor.py —— 功能8：智能决策建议引擎
======================================
基于仿真 KPI，输出带"失效边界条件"的中文决策建议。

规则体系（按优先级输出）：
  R1  SLA(服务水平)校验    —— P95周转周期是否超过 SLA 目标
  R2  预算校验             —— 资源配置总成本是否超出预算
  R3  瓶颈增配建议         —— 利用率>85% 或等待过长的环节建议增配
  R4  资源冗余建议         —— 利用率<40% 的环节建议减配
  R5  配置均衡建议         —— 各环节利用率差距过大时提示"木桶效应"
  R6  压力测试预警         —— 若吞吐量已接近产能上限，预警扩容

每条建议都附带：
  - 风险等级（高/中/低）
  - 现状描述（基于KPI的定量事实）
  - 建议动作
  - 失效边界条件（什么情况下这条建议不再成立）
"""

import pandas as pd

from calculator import DEFAULT_COSTS, estimate_cost

STAGE_NAMES = {"picker": "拣选", "amr": "AMR搬运", "pack_station": "打包"}
RESOURCE_KEYS = {"picker": "picker_num", "amr": "amr_num", "pack_station": "pack_station_num"}


def generate_advice(
    kpi: dict,
    resources: dict = None,          # 当前资源配置 {"picker_num":2,...}
    sla_target: float = 30.0,        # SLA目标：P95周转周期 <= 30 分钟
    budget: float = None,            # 班次预算（元），None 表示不校验
    costs: dict = None,              # 各资源单价
) -> list:
    """返回建议列表，每条为 dict: {level, title, finding, action, boundary}"""
    advice = []
    costs = costs or dict(DEFAULT_COSTS)
    resources = resources or {}

    # ---------- R1 SLA 校验 ----------
    p95 = kpi.get("p95_cycle_time", 0.0)
    if sla_target is not None:
        if p95 > sla_target:
            advice.append({
                "level": "高",
                "title": "SLA 服务水平不达标",
                "finding": f"P95 周转周期 {p95:.1f} 分钟，超过 SLA 目标 {sla_target:.0f} 分钟。",
                "action": "优先处理瓶颈环节（见 R3），或提高 SLA 目标的承诺口径；"
                          "若为业务刚需，必须增加瓶颈资源。",
                "boundary": "当订单到达速率下降（需求回落）或 SLA 目标上调时，本结论可能不再成立。",
            })
        else:
            advice.append({
                "level": "低",
                "title": "SLA 服务水平达标",
                "finding": f"P95 周转周期 {p95:.1f} 分钟 ≤ SLA 目标 {sla_target:.0f} 分钟。",
                "action": "维持现状即可，无需增配。",
                "boundary": "若未来订单量继续增长，P95 会上升，需重新评估。",
            })

    # ---------- R2 预算校验 ----------
    if budget is not None and resources:
        cost = estimate_cost(resources, costs)
        if cost > budget:
            advice.append({
                "level": "高",
                "title": "配置成本超预算",
                "finding": f"当前配置一个班次成本约 {cost:.0f} 元，超过预算 {budget:.0f} 元。",
                "action": "优先削减利用率最低环节的资源（见 R4），或与预算方协商上调。",
                "boundary": "若单价口径（DEFAULT_COSTS）与实际报价不符，需先修正单价再决策。",
            })

    # ---------- R3 瓶颈增配建议 ----------
    for res in ("picker", "amr", "pack_station"):
        util = kpi.get(f"utilization_{res}", 0.0)
        wait = kpi.get({"picker": "avg_pick_wait", "amr": "avg_amr_wait",
                        "pack_station": "avg_pack_wait"}[res], 0.0)
        q = kpi.get(f"max_queue_{res}", 0)
        if util >= 0.85 or wait >= 3.0 or q >= 8:
            advice.append({
                "level": "中" if util < 0.95 else "高",
                "title": f"{STAGE_NAMES[res]}环节成为瓶颈",
                "finding": (f"利用率 {util*100:.1f}%，平均等待 {wait:.1f} 分钟，"
                            f"最大队列 {q} 件。"),
                "action": (f"建议 {STAGE_NAMES[res]}环节增配 1 个单位，"
                           f"并通过「多方案对比/敏感性分析」验证改善幅度。"),
                "boundary": "若增配后该环节利用率仍 >85%，说明是上游来料不均或需求本身超产能，"
                            "单纯增配无效，需调整到达模式或工作班次。",
            })

    # ---------- R4 资源冗余建议 ----------
    for res in ("picker", "amr", "pack_station"):
        util = kpi.get(f"utilization_{res}", 0.0)
        if 0.0 < util < 0.40:
            advice.append({
                "level": "低",
                "title": f"{STAGE_NAMES[res]}环节资源冗余",
                "finding": f"利用率仅 {util*100:.1f}%，低于 40%。",
                "action": f"可考虑把{STAGE_NAMES[res]}环节减少 1 个单位以节省成本。",
                "boundary": "若需求存在明显波峰（如月底集中发货），低谷期低利用率不代表冗余，"
                            "需结合压力情景测试判断。",
            })

    # ---------- R5 配置均衡建议 ----------
    utils = [kpi.get(f"utilization_{r}", 0.0) for r in ("picker", "amr", "pack_station")]
    if utils:
        spread = max(utils) - min(utils)
        if spread >= 0.35 and max(utils) >= 0.75:
            max_res = max(("picker", "amr", "pack_station"),
                          key=lambda r: kpi.get(f"utilization_{r}", 0.0))
            advice.append({
                "level": "中",
                "title": "资源配置不均衡（木桶效应）",
                "finding": (f"各环节利用率差距达 {spread*100:.0f} 个百分点，"
                            f"{STAGE_NAMES[max_res]}环节最忙。"),
                "action": "把冗余环节（利用率<40%）的资源向瓶颈环节转移，而非整体增配。",
                "boundary": "若各环节作业时间口径（单件时间）发生改变，均衡点会移动，需重新分析。",
            })

    # ---------- R6 吞吐量压力预警 ----------
    tp = kpi.get("throughput_per_hour", 0.0)
    completed = kpi.get("completed_orders", 0)
    if completed > 0 and tp > 0:
        # 粗估：吞吐量接近理论产能上限（利用率均>85%时）
        if all(kpi.get(f"utilization_{r}", 0.0) > 0.85 for r in ("picker", "amr", "pack_station")):
            advice.append({
                "level": "高",
                "title": "系统接近满载，扩容预警",
                "finding": f"吞吐量 {tp:.1f} 件/小时，各环节利用率均超 85%。",
                "action": "任何订单量增长都会直接拉长周期，建议提前扩容或启用弹性班次。",
                "boundary": "若仿真未包含高峰期（如双11）情景，需先运行压力情景测试再下结论。",
            })

    if not advice:
        advice.append({
            "level": "低",
            "title": "系统运行健康",
            "finding": "各项指标均在合理区间。",
            "action": "保持当前配置，定期运行批量仿真监控指标漂移。",
            "boundary": "指标随时间或需求变化后需重新评估。",
        })
    return advice


def advice_to_dataframe(advice: list) -> pd.DataFrame:
    """把建议列表转成表格，方便网页展示/导出"""
    return pd.DataFrame(advice, columns=["level", "title", "finding", "action", "boundary"])


# ==================== 本地测试 ====================
if __name__ == "__main__":
    from sim_core import run_one_simulation, compute_kpis

    cfg = {"picker_num": 1, "pack_station_num": 1, "amr_num": 1,
           "sim_duration": 480, "time_model": "fixed",
           "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500}
    sim = run_one_simulation(cfg, seed=3)
    kpi = compute_kpis(sim)
    adv = generate_advice(kpi, resources={"picker_num": 1, "pack_station_num": 1, "amr_num": 1},
                          sla_target=30, budget=2000)
    print(advice_to_dataframe(adv).to_string(index=False))
    print("✅ advisor.py 测试通过！")
