import simpy
import numpy as np
import pandas as pd

class WarehouseSimulation:
    def __init__(
        self,
        env: simpy.Environment,
        picker_num: int = 2,      # 拣选人员数量
        pack_station_num: int = 1, # 打包工作台数量
        amr_num: int = 4,          # AMR搬运机器人数量
        sim_duration: float = 480, # 仿真总时长，单位：分钟，一个工作班次
        seed: int = 42
    ):
        self.env = env
        np.random.seed(seed)

        # ========= 定义系统永久资源 =========
        self.picker = simpy.Resource(env, capacity=picker_num)
        self.pack_station = simpy.Resource(env, capacity=pack_station_num)
        self.amr = simpy.Resource(env, capacity=amr_num)

        self.sim_duration = sim_duration

        # ========= 日志存储（任务书硬性要求，用于模型校核） =========
        self.event_log = []       # 事件轨迹日志，导出csv，和人工推演比对
        self.order_records = []   # 每一个订单完整运行记录

    def log_event(self, order_id: int, event_type: str, resource_id: str = ""):
        """
        事件日志记录函数
        :param order_id: 订单编号
        :param event_type: 事件名称，如订单到达、拣选开始、打包完成
        :param resource_id: 占用资源编号
        """
        self.event_log.append({
            "order_id": order_id,
            "event_time": round(self.env.now, 2),
            "event_type": event_type,
            "resource_id": resource_id
        })

    def order_flow(self, order_id: int, arrive_time: float):
        """
        单个订单完整履约流程
        流程：订单到达 → 请求拣选资源 →拣选完成 →请求AMR搬运 →搬运完成 →请求打包台 →打包完成
        :param order_id:订单编号
        :param arrive_time:订单进入系统的时刻
        """
        # 等待，直到订单到达系统时间
        yield self.env.timeout(arrive_time - self.env.now)
        self.log_event(order_id, "订单到达")

        # ----------------------拣选工序----------------------
        pick_request = self.picker.request()
        yield pick_request  # 等待获取拣选人员资源，如果全部忙则进入队列排队
        pick_start_time = self.env.now
        self.log_event(order_id, "拣选开始", resource_id=f"picker_resource")

        pick_fixed_time = 5.0  # 实验1确定性固定拣选作业时间，单位分钟
        yield self.env.timeout(pick_fixed_time)

        pick_end_time = self.env.now
        self.log_event(order_id, "拣选完成")
        self.picker.release(pick_request)  # 释放拣选人员资源

        # ----------------------AMR搬运工序----------------------
        amr_request = self.amr.request()
        yield amr_request
        transport_start_time = self.env.now
        self.log_event(order_id, "搬运开始")

        transport_fixed_time = 2.0 #固定搬运时间
        yield self.env.timeout(transport_fixed_time)

        transport_end_time = self.env.now
        self.log_event(order_id, "搬运完成")
        self.amr.release(amr_request) #释放机器人

        # ----------------------打包工序----------------------
        pack_request = self.pack_station.request()
        yield pack_request
        pack_start_time = self.env.now
        self.log_event(order_id, "打包开始")

        pack_fixed_time = 3.0 #固定打包时间
        yield self.env.timeout(pack_fixed_time)

        pack_end_time = self.env.now
        self.log_event(order_id, "打包完成")
        self.pack_station.release(pack_request)

        # 保存该订单全部指标
        total_cycle_time = pack_end_time - arrive_time
        self.order_records.append({
            "order_id": order_id,
            "arrive_time": arrive_time,
            "pick_start": pick_start_time,
            "pick_end": pick_end_time,
            "transport_end": transport_end_time,
            "pack_end": pack_end_time,
            "cycle_time": round(total_cycle_time, 2)
        })

    def generate_fixed_orders(self, order_arrival_list: list):
        """
        批量生成固定到达时间的订单，用于实验1人工推演校核
        :param order_arrival_list: list，每一个数字代表订单到达时刻
        """
        for order_index, arrive_t in enumerate(order_arrival_list):
            self.env.process(self.order_flow(order_id=order_index+1, arrive_time=arrive_t))

def run_one_simulation(settings: dict, order_arrival_list: list, seed: int = 42):
    """
    对外调用接口：运行一次仿真
    :param settings:字典，存放资源配置参数
    :param order_arrival_list:订单到达时刻列表
    :param seed:随机种子（当前实验1是确定性模型，种子预留，给后续实验2随机输入用）
    :return:WarehouseSimulation实例对象，包含日志、订单结果
    """
    env = simpy.Environment()
    sim_instance = WarehouseSimulation(env, **settings, seed=seed)
    sim_instance.generate_fixed_orders(order_arrival_list)
    env.run(until=settings["sim_duration"])
    return sim_instance

# ==========本地直接测试仿真内核，不需要网页，运行这个文件就可以输出csv日志做人工核对==========
if __name__ == "__main__":
    test_config = {
        "picker_num": 2,
        "pack_station_num": 1,
        "amr_num": 3,
        "sim_duration": 480
    }
    # 测试用10条固定订单到达时间，对应实验1人工推演案例
    test_order_arrival = [0, 2, 5, 8, 12, 15, 20, 22, 28, 33]
    sim_result = run_one_simulation(test_config, test_order_arrival, seed=42)

    df_order_result = pd.DataFrame(sim_result.order_records)
    df_event_log_result = pd.DataFrame(sim_result.event_log)

    print("========订单运行结果表========")
    print(df_order_result.to_string())
    print("\n========事件日志前15条========")
    print(df_event_log_result.head(15).to_string())

    # 导出csv文件，utf‑8‑sig解决excel打开中文乱码
    df_order_result.to_csv("test_order_output.csv", index=False, encoding="utf‑8‑sig")
    df_event_log_result.to_csv("test_event_log_output.csv", index=False, encoding="utf‑8‑sig")
    print("\n✅文件导出完成：test_order_output.csv 、 test_event_log_output.csv")