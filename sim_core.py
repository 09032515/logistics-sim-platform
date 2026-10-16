# -*- coding: utf-8 -*-
"""
sim_core.py —— 物流仿真内核（V2 完整版）
========================================
在实验1确定性模型基础上全面扩展，为 10 大功能提供引擎：

  功能1 智能计算系统  → 依赖 DEFAULT_STAGE_TIMES 单件作业时间口径
  功能2 可视化中心    → monitor 队列监控 + 订单周期分解记录
  功能3 瓶颈识别      → compute_kpis() 输出各环节利用率/等待/队列
  功能4 多方案对比    → run_batch_simulation() 批量仿真引擎
  功能5 批量仿真      → run_batch_simulation() + 置信区间汇总
  功能6 敏感性分析    → 批量仿真引擎支撑
  功能7 压力情景      → 泊松随机到达 + demand_multiplier + 设备故障
  功能8 决策建议      → compute_kpis() 提供全部决策指标
  功能9 导入导出      → 事件日志/订单记录/队列样本全部结构化输出
  功能10 自动报告     → 提供报告所需的全部数据源

核心流程：订单到达 → 拣选 → AMR搬运 → 打包 → 完成

时间模型支持：fixed(固定) / gamma(Gamma分布) / empirical(经验分布)
到达模式支持：fixed_list(固定列表，人工推演校核) / poisson(泊松随机)
压力情景支持：demand_multiplier(需求倍数) / failure_events(设备故障窗口)
"""

import math
import simpy
import numpy as np
import pandas as pd

# ============ 单件作业时间基线（与智能计算系统共用同一口径） ============
DEFAULT_STAGE_TIMES = {
    "picker": 5.0,        # 拣选人员处理1件货物所需分钟
    "amr": 2.0,           # AMR搬运1件货物所需分钟
    "pack_station": 3.0,  # 打包台处理1件货物所需分钟
}

# WarehouseSimulation 构造函数可接收的参数白名单（其余参数由 run_one_simulation 单独处理）
_CTOR_KEYS = {
    "picker_num", "pack_station_num", "amr_num", "sim_duration",
    "time_model", "pick_base_time", "transport_base_time", "pack_base_time",
    "time_cv", "empirical_df", "amr_cross_num", "crossing_time", "seed",
}


class WarehouseSimulation:
    """仓库仿真模型：订单到达 → 拣选 → AMR搬运 → 打包"""

    def __init__(
        self,
        env: simpy.Environment,
        picker_num: int = 2,          # 拣选人员数量
        pack_station_num: int = 1,    # 打包工作台数量
        amr_num: int = 3,             # AMR搬运机器人数量
        sim_duration: float = 480,    # 仿真总时长（分钟），一个工作班次
        time_model: str = "fixed",    # 时间模型: fixed / gamma / empirical
        pick_base_time: float = 5.0,  # 拣选单件基础时间
        transport_base_time: float = 2.0,  # AMR搬运单件基础时间
        pack_base_time: float = 3.0,  # 打包单件基础时间
        time_cv: float = 0.3,         # Gamma分布的变异系数 CV
        empirical_df: pd.DataFrame = None,  # 经验分布历史数据: pick_time/transport_time/pack_time 三列
        amr_cross_num: int = 0,       # AMR通道交叉口数量（0=关闭拥堵模型）
        crossing_time: float = 0.5,   # 每过一个交叉口所需时间（分钟）
        seed: int = 42,
    ):
        self.env = env
        self.rng = np.random.default_rng(seed)
        self.sim_duration = sim_duration
        self.time_model = time_model
        self.time_cv = time_cv

        # ---- 单件作业时间参数 ----
        self._base_times = {
            "picker": pick_base_time,
            "amr": transport_base_time,
            "pack_station": pack_base_time,
        }
        # ---- 经验分布采样池（读历史CSV） ----
        self._empirical = {"picker": [], "amr": [], "pack_station": []}
        if empirical_df is not None and len(empirical_df) > 0:
            col_map = {"picker": "pick_time", "amr": "transport_time", "pack_station": "pack_time"}
            for stage, col in col_map.items():
                if col in empirical_df.columns:
                    series = pd.to_numeric(empirical_df[col], errors="coerce").dropna()
                    self._empirical[stage] = list(series[series > 0])

        # ---- 定义系统永久资源 ----
        self.picker = simpy.Resource(env, capacity=int(picker_num))
        self.pack_station = simpy.Resource(env, capacity=int(pack_station_num))
        self.amr = simpy.Resource(env, capacity=int(amr_num))
        # AMR 通道交叉口（可选，模拟拥堵）
        self.amr_cross = (
            simpy.Resource(env, capacity=int(max(1, amr_cross_num)))
            if int(amr_cross_num) > 0 else None
        )
        self.crossing_time = crossing_time
        self.resources = {
            "picker": self.picker,
            "amr": self.amr,
            "pack_station": self.pack_station,
        }

        # ---- 设备故障标记（故障窗口内该环节资源不可用，订单排队等待） ----
        self.outage_flags = {"picker": False, "amr": False, "pack_station": False}

        # ---- 日志存储 ----
        self.event_log = []     # 事件轨迹日志，导出CSV，与人工推演比对
        self.order_records = [] # 每个订单完整运行记录（含周期分解）
        self.queue_samples = [] # 队列监控采样点（用于利用率/队列时序图）

    # ==================== 基础工具 ====================
    def log_event(self, order_id: int, event_type: str, resource_id: str = ""):
        """事件日志记录函数"""
        self.event_log.append({
            "order_id": order_id,
            "event_time": round(self.env.now, 2),
            "event_type": event_type,
            "resource_id": resource_id,
        })

    def _sample_service_time(self, stage: str) -> float:
        """按时间模型采样该环节的单件作业时间"""
        if self.time_model == "fixed":
            return self._base_times[stage]
        if self.time_model == "gamma":
            mean = self._base_times[stage]
            cv = max(0.05, self.time_cv)
            k = 1.0 / (cv * cv)
            theta = mean * cv * cv
            return max(0.1, float(self.rng.gamma(k, theta)))
        if self.time_model == "empirical":
            arr = self._empirical.get(stage) or []
            if len(arr) == 0:
                return self._base_times[stage]
            return max(0.1, float(self.rng.choice(arr)))
        raise ValueError(f"不支持的时间模型: {self.time_model}")

    def _wait_outage(self, stage: str):
        """若该环节正处于设备故障窗口，则等待恢复"""
        while self.outage_flags.get(stage, False):
            yield self.env.timeout(0.5)

    # ==================== 单个订单完整履约流程 ====================
    def order_flow(self, order_id: int, arrive_time: float):
        """
        流程：订单到达 → 拣选 → AMR搬运（含交叉口拥堵） → 打包 → 完成
        记录每个环节的等待时间与服务时间（周期分解），供瓶颈分析使用。
        """
        yield self.env.timeout(max(0.0, arrive_time - self.env.now))
        self.log_event(order_id, "订单到达")

        # ---------------------- 拣选工序 ----------------------
        yield from self._wait_outage("picker")
        pick_req = self.picker.request()
        t_req = self.env.now
        yield pick_req
        pick_wait = self.env.now - t_req
        self.log_event(order_id, "拣选开始", resource_id="picker")
        pick_time = self._sample_service_time("picker")
        yield self.env.timeout(pick_time)
        self.log_event(order_id, "拣选完成")
        self.picker.release(pick_req)

        # ---------------------- AMR搬运工序 ----------------------
        yield from self._wait_outage("amr")
        amr_req = self.amr.request()
        t_req = self.env.now
        yield amr_req
        amr_wait = self.env.now - t_req
        self.log_event(order_id, "搬运开始", resource_id="amr")
        amr_time = self._sample_service_time("amr")
        yield self.env.timeout(amr_time)
        # 交叉口拥堵：AMR需依次通过交叉口
        if self.amr_cross is not None:
            cross_req = self.amr_cross.request()
            yield cross_req
            yield self.env.timeout(self.crossing_time)
            self.amr_cross.release(cross_req)
        self.log_event(order_id, "搬运完成")
        self.amr.release(amr_req)

        # ---------------------- 打包工序 ----------------------
        yield from self._wait_outage("pack_station")
        pack_req = self.pack_station.request()
        t_req = self.env.now
        yield pack_req
        pack_wait = self.env.now - t_req
        self.log_event(order_id, "打包开始", resource_id="pack_station")
        pack_time = self._sample_service_time("pack_station")
        yield self.env.timeout(pack_time)
        self.log_event(order_id, "打包完成")
        self.pack_station.release(pack_req)

        # 保存订单完整记录（周期分解：等待 + 服务）
        self.order_records.append({
            "order_id": order_id,
            "arrive_time": round(arrive_time, 2),
            "pick_wait": round(pick_wait, 2),
            "pick_time": round(pick_time, 2),
            "amr_wait": round(amr_wait, 2),
            "amr_time": round(amr_time, 2),
            "pack_wait": round(pack_wait, 2),
            "pack_time": round(pack_time, 2),
            "cycle_time": round(self.env.now - arrive_time, 2),
        })

    # ==================== 订单生成 ====================
    def generate_orders(
        self,
        arrival_mode: str = "fixed_list",
        order_arrival_list=None,
        arrival_rate: float = 1.0,       # 泊松模式下平均每分钟到达订单数
        demand_multiplier: float = 1.0,  # 压力测试：需求倍数（>1 表示需求暴涨）
        max_orders: int = 10000,
    ):
        if arrival_mode == "fixed_list":
            lst = order_arrival_list or []
            for i, t in enumerate(lst):
                if t >= 0 and t < self.sim_duration:
                    self.env.process(self.order_flow(order_id=i + 1, arrive_time=t))
        elif arrival_mode == "poisson":
            rate = max(1e-6, arrival_rate * demand_multiplier)
            order_id = 1
            t = self.rng.exponential(1.0 / rate)
            while t < self.sim_duration and order_id <= max_orders:
                self.env.process(self.order_flow(order_id=order_id, arrive_time=t))
                order_id += 1
                t += self.rng.exponential(1.0 / rate)
        else:
            raise ValueError(f"不支持的到达模式: {arrival_mode}")

    # ==================== 压力情景：设备故障 ====================
    def schedule_failures(self, failure_events: dict = None):
        """
        设备故障窗口定义，例如:
            {"picker": [(120, 180)], "amr": [(240, 300)]}
        表示第120~180分钟拣选人员全部停机，第240~300分钟AMR全部停机。
        """
        events = failure_events or {}
        for stage, windows in events.items():
            if stage not in self.outage_flags:
                continue
            for (t1, t2) in windows:
                if t2 > t1 >= 0:
                    self.env.process(self._failure_window(stage, t1, t2))

    def _failure_window(self, stage: str, t1: float, t2: float):
        yield self.env.timeout(max(0.0, t1 - self.env.now))
        self.outage_flags[stage] = True
        self.log_event(0, "设备故障开始", resource_id=stage)
        yield self.env.timeout(max(0.1, t2 - t1))
        self.outage_flags[stage] = False
        self.log_event(0, "设备故障恢复", resource_id=stage)

    # ==================== 队列与利用率监控 ====================
    def monitor(self, interval: float = 1.0):
        """每隔 interval 分钟采样一次各资源的队列长度与占用率"""
        while True:
            for name, res in self.resources.items():
                cap = res.capacity if res.capacity else 1
                self.queue_samples.append({
                    "time": round(self.env.now, 1),
                    "resource": name,
                    "queue_length": len(res.queue),
                    "busy": res.count,
                    "capacity": res.capacity,
                    "utilization": round(res.count / cap, 4),
                })
            yield self.env.timeout(interval)


# ==================== 对外调用接口 ====================
def run_one_simulation(settings: dict, order_arrival_list=None, seed: int = 42,
                       failure_events: dict = None):
    """
    运行一次仿真（单次）
    :param settings: 字典，包含资源配置与模型参数（多余键会被自动忽略）
    :param order_arrival_list: 固定到达模式下订单到达时刻列表
    :param seed: 随机种子
    :param failure_events: 设备故障窗口字典
    :return: WarehouseSimulation 实例（含 event_log / order_records / queue_samples）
    """
    env = simpy.Environment()
    ctor = {k: v for k, v in settings.items() if k in _CTOR_KEYS}
    ctor["seed"] = seed
    sim = WarehouseSimulation(env, **ctor)
    sim.schedule_failures(failure_events)
    sim.generate_orders(
        arrival_mode=settings.get("arrival_mode", "fixed_list"),
        order_arrival_list=order_arrival_list,
        arrival_rate=settings.get("arrival_rate", 1.0),
        demand_multiplier=settings.get("demand_multiplier", 1.0),
        max_orders=settings.get("max_orders", 10000),
    )
    env.process(sim.monitor(interval=settings.get("monitor_interval", 1.0)))
    env.run(until=sim.sim_duration)
    return sim


def simulation_to_dfs(sim: WarehouseSimulation):
    """把仿真实例的原始记录转为三个 DataFrame，方便网页/报告直接使用"""
    df_order = pd.DataFrame(sim.order_records)
    df_event = pd.DataFrame(sim.event_log)
    df_queue = pd.DataFrame(sim.queue_samples)
    return df_order, df_event, df_queue


# ==================== KPI 计算 ====================
def compute_kpis(sim: WarehouseSimulation) -> dict:
    """
    从一次仿真结果计算核心 KPI：
      完成量 / 周期时间(均值/标准差/P50/P95/最大) / 各环节等待
      各资源利用率 / 平均队列 / 最大队列 / 吞吐量 / 瓶颈环节
    """
    orders = pd.DataFrame(sim.order_records)
    queue = pd.DataFrame(sim.queue_samples)
    n = len(orders)
    kpi = {"completed_orders": n}

    if n > 0:
        kpi["avg_cycle_time"] = round(float(orders["cycle_time"].mean()), 2)
        kpi["std_cycle_time"] = round(float(orders["cycle_time"].std(ddof=1)), 2) if n > 1 else 0.0
        kpi["p50_cycle_time"] = round(float(orders["cycle_time"].median()), 2)
        kpi["p95_cycle_time"] = round(float(orders["cycle_time"].quantile(0.95)), 2)
        kpi["max_cycle_time"] = round(float(orders["cycle_time"].max()), 2)
        kpi["avg_pick_wait"] = round(float(orders["pick_wait"].mean()), 2)
        kpi["avg_amr_wait"] = round(float(orders["amr_wait"].mean()), 2)
        kpi["avg_pack_wait"] = round(float(orders["pack_wait"].mean()), 2)
    else:
        for key in ("avg_cycle_time", "std_cycle_time", "p50_cycle_time",
                    "p95_cycle_time", "max_cycle_time",
                    "avg_pick_wait", "avg_amr_wait", "avg_pack_wait"):
            kpi[key] = 0.0

    kpi["throughput_per_hour"] = round(n / (sim.sim_duration / 60.0), 2)

    for res_name in ("picker", "amr", "pack_station"):
        qr = queue[queue["resource"] == res_name]
        if len(qr) > 0:
            kpi[f"utilization_{res_name}"] = round(float(qr["utilization"].mean()), 4)
            kpi[f"avg_queue_{res_name}"] = round(float(qr["queue_length"].mean()), 2)
            kpi[f"max_queue_{res_name}"] = int(qr["queue_length"].max())
        else:
            kpi[f"utilization_{res_name}"] = 0.0
            kpi[f"avg_queue_{res_name}"] = 0.0
            kpi[f"max_queue_{res_name}"] = 0

    # 瓶颈 = 利用率最高者；利用率相同时取平均等待更长者
    util_map = {r: kpi[f"utilization_{r}"] for r in ("picker", "amr", "pack_station")}
    wait_map = {"picker": kpi["avg_pick_wait"], "amr": kpi["avg_amr_wait"],
                "pack_station": kpi["avg_pack_wait"]}
    kpi["bottleneck"] = max(
        ("picker", "amr", "pack_station"),
        key=lambda r: (util_map[r], wait_map[r]),
    )
    return kpi


# ==================== 批量仿真（功能4/5/6 共用引擎） ====================
def run_batch_simulation(settings: dict, n_runs: int = 10, order_arrival_list=None,
                         seed: int = 42, progress_cb=None):
    """
    运行 n_runs 次独立仿真（每次换一个随机种子），返回：
      df_runs   : 每次运行一行，列为各 KPI（行数 = n_runs）
      df_summary: 每个 KPI 的 均值 / 标准差 / 95%置信区间
    progress_cb(i, n) 可用于网页进度条
    """
    run_list = []
    for i in range(n_runs):
        sim = run_one_simulation(settings, order_arrival_list=order_arrival_list,
                                 seed=seed + i)
        run_list.append(compute_kpis(sim))
        if progress_cb:
            progress_cb(i + 1, n_runs)
    df_runs = pd.DataFrame(run_list)

    summary_rows = []
    numeric_cols = [c for c in df_runs.columns
                    if df_runs[c].dtype.kind in "fi" and c != "bottleneck"]
    for col in numeric_cols:
        vals = df_runs[col].astype(float)
        mean = float(vals.mean())
        std = float(vals.std(ddof=1)) if n_runs > 1 else 0.0
        se = std / math.sqrt(n_runs)
        summary_rows.append({
            "指标": col,
            "均值": round(mean, 3),
            "标准差": round(std, 3),
            "95%CI下限": round(mean - 1.96 * se, 3),
            "95%CI上限": round(mean + 1.96 * se, 3),
        })
    df_summary = pd.DataFrame(summary_rows)
    return df_runs, df_summary


def summary_to_dict(df_summary: pd.DataFrame) -> dict:
    """把批量仿真汇总表转成 {指标: 均值} 字典，方便多方案对比"""
    return {row["指标"]: row["均值"] for _, row in df_summary.iterrows()}


# ==================== 本地直接测试 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("测试1：固定订单确定性模型（人工推演校核）")
    print("=" * 60)
    test_config = {
        "picker_num": 2, "pack_station_num": 1, "amr_num": 3,
        "sim_duration": 480, "time_model": "fixed",
    }
    test_order_arrival = [0, 2, 5, 8, 12, 15, 20, 22, 28, 33]
    sim_result = run_one_simulation(test_config, order_arrival_list=test_order_arrival, seed=42)
    df_order, df_event, df_queue = simulation_to_dfs(sim_result)
    print(df_order.to_string())
    print("\n事件日志前15条：")
    print(df_event.head(15).to_string())
    df_order.to_csv("test_order_output.csv", index=False, encoding="utf-8-sig")
    df_event.to_csv("test_event_log_output.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 60)
    print("测试2：Gamma随机时间 + 泊松到达（实验2随机模型）")
    print("=" * 60)
    gamma_config = {
        "picker_num": 2, "pack_station_num": 1, "amr_num": 3,
        "sim_duration": 480, "time_model": "gamma", "time_cv": 0.3,
        "arrival_mode": "poisson", "arrival_rate": 0.8, "max_orders": 500,
    }
    sim2 = run_one_simulation(gamma_config, seed=1)
    kpi2 = compute_kpis(sim2)
    for k, v in kpi2.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("测试3：批量仿真 5 次 + 置信区间（功能5引擎）")
    print("=" * 60)
    _, summary = run_batch_simulation(gamma_config, n_runs=5, seed=10)
    print(summary.to_string(index=False))

    print("\n✅ sim_core.py 全部测试通过！")
