#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
非Root设备网络模拟演示脚本

展示如何在不需要设备root权限的情况下进行弱网/断网环境模拟
"""

import time
import logging
from utils.network_proxy import NonRootNetworkSimulator

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def demo_pc_proxy_simulation():
    """演示PC端代理网络模拟"""
    print("=== PC端代理网络模拟演示 ===")

    device_sn = "emulator-5554"  # 替换为实际设备序列号
    simulator = NonRootNetworkSimulator(device_sn, method='pc_proxy')

    try:
        print("1. 模拟断网10秒...")
        simulator.simulate_disconnect(10)

        print("2. 模拟弱网环境15秒...")
        weak_net_config = {
            'delay': 1000,    # 1秒延迟
            'loss': 10,       # 10%丢包率
            'bandwidth': 1024 # 1KB/s带宽
        }
        simulator.simulate_weak_network(weak_net_config, 15)

        print("3. 模拟高延迟网络10秒...")
        simulator.simulate_high_latency(2000, 10)

        print("演示完成！")

    except Exception as e:
        print(f"演示失败: {str(e)}")

def demo_wifi_control_simulation():
    """演示WiFi路由器控制网络模拟"""
    print("=== WiFi路由器控制网络模拟演示 ===")

    device_sn = "emulator-5554"  # 替换为实际设备序列号
    simulator = NonRootNetworkSimulator(device_sn, method='wifi_control')

    try:
        print("1. 通过WiFi路由器断开设备连接10秒...")
        simulator.simulate_disconnect(10)

        print("2. 通过WiFi路由器模拟弱网15秒...")
        weak_net_config = {
            'delay': 500,     # 500ms延迟
            'loss': 5,        # 5%丢包率
            'bandwidth': 512  # 512B/s带宽
        }
        simulator.simulate_weak_network(weak_net_config, 15)

        print("演示完成！")

    except Exception as e:
        print(f"演示失败: {str(e)}")
        print("注意：WiFi控制需要路由器支持和管理员权限")

def demo_app_simulation():
    """演示应用内部网络模拟"""
    print("=== 应用内部网络模拟演示 ===")

    device_sn = "emulator-5554"  # 替换为实际设备序列号
    simulator = NonRootNetworkSimulator(device_sn, method='app_simulation')

    try:
        print("1. 发送应用断网广播...")
        simulator.simulate_disconnect(10)

        print("2. 发送应用弱网广播...")
        weak_net_config = {
            'delay': 1000,
            'loss': 0,
            'bandwidth': 0
        }
        simulator.simulate_weak_network(weak_net_config, 15)

        print("演示完成！")
        print("注意：应用内部模拟需要应用实现相应的广播接收器")

    except Exception as e:
        print(f"演示失败: {str(e)}")

def main():
    """主演示函数"""
    print("非Root设备网络模拟功能演示")
    print("=" * 50)

    # 演示PC端代理方法
    demo_pc_proxy_simulation()

    print("\n" + "=" * 50)

    # 演示WiFi控制方法
    demo_wifi_control_simulation()

    print("\n" + "=" * 50)

    # 演示应用内部方法
    demo_app_simulation()

    print("\n" + "=" * 50)
    print("演示结束")
    print("\n使用建议：")
    print("1. pc_proxy方法最通用，推荐首先尝试")
    print("2. wifi_control方法需要路由器支持")
    print("3. app_simulation方法需要应用配合实现")
    print("4. 可以根据实际环境选择最适合的方法")

if __name__ == "__main__":
    main()