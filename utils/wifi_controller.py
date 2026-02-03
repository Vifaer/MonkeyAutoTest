#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
from utils.timeout_command import run as run_cmd


class WiFiController:
    """
    WiFi网络控制器
    通过控制WiFi路由器来模拟网络条件
    支持多种路由器品牌和协议
    """

    def __init__(self, router_ip='192.168.1.1', username='admin', password='admin'):
        """
        Args:
            router_ip: 路由器IP地址
            username: 路由器管理用户名
            password: 路由器管理密码
        """
        self.router_ip = router_ip
        self.username = username
        self.password = password
        self.router_type = self._detect_router_type()

    def disconnect_device(self, device_sn, duration_seconds):
        """
        断开指定设备的WiFi连接

        Args:
            device_sn: 设备序列号
            duration_seconds: 断开持续时间
        """
        logging.info(f"通过WiFi路由器断开设备 {device_sn} 的连接，持续 {duration_seconds} 秒")

        try:
            # 获取设备的MAC地址
            device_mac = self._get_device_mac(device_sn)
            if not device_mac:
                logging.error("无法获取设备MAC地址")
                return

            # 断开设备连接
            self._disconnect_device_by_mac(device_mac)

            # 等待指定时间
            time.sleep(duration_seconds)

            # 重新连接设备
            self._reconnect_device_by_mac(device_mac)

            logging.info("WiFi断开模拟完成")

        except Exception as e:
            logging.error(f"WiFi断开模拟失败: {str(e)}")

    def simulate_weak_network_for_device(self, device_sn, config, duration_seconds):
        """
        为指定设备模拟弱网环境

        Args:
            device_sn: 设备序列号
            config: 弱网配置 {'delay': ms, 'loss': %, 'bandwidth': bps}
            duration_seconds: 模拟持续时间
        """
        logging.info(f"为设备 {device_sn} 模拟弱网环境，持续 {duration_seconds} 秒")

        try:
            # 获取设备的MAC地址
            device_mac = self._get_device_mac(device_sn)
            if not device_mac:
                logging.error("无法获取设备MAC地址")
                return

            # 配置QoS规则模拟弱网
            self._configure_weak_network_for_mac(device_mac, config)

            # 等待指定时间
            time.sleep(duration_seconds)

            # 清理QoS规则
            self._cleanup_weak_network_for_mac(device_mac)

            logging.info("WiFi弱网模拟完成")

        except Exception as e:
            logging.error(f"WiFi弱网模拟失败: {str(e)}")

    def _detect_router_type(self):
        """检测路由器类型"""
        # 这里可以实现路由器类型检测逻辑
        # 暂时返回通用类型
        return 'generic'

    def _get_device_mac(self, device_sn):
        """获取设备的MAC地址"""
        try:
            # 通过ADB获取设备的WiFi MAC地址
            cmd = f"adb -s {device_sn} shell cat /sys/class/net/wlan0/address"
            mac_address = run_cmd(cmd).strip()

            if mac_address and len(mac_address) == 17:  # MAC地址格式验证
                logging.info(f"设备 {device_sn} 的MAC地址: {mac_address}")
                return mac_address.lower()
            else:
                logging.warning("无法通过ADB获取MAC地址，尝试其他方法")

                # 备选方法：通过ip命令获取（Python 解析替代 grep）
                cmd = f"adb -s {device_sn} shell ip link show wlan0"
                result = run_cmd(cmd)
                import re
                if isinstance(result, str):
                    match = re.search(r'link/ether ([0-9a-f:]+)', result)
                    if match:
                        mac_address = match.group(1)
                        logging.info(f"通过ip命令获取MAC地址: {mac_address}")
                        return mac_address.lower()

        except Exception as e:
            logging.error(f"获取设备MAC地址失败: {str(e)}")

        return None

    def _disconnect_device_by_mac(self, mac_address):
        """通过MAC地址断开设备连接"""
        logging.info(f"断开MAC地址为 {mac_address} 的设备")

        if self.router_type == 'tplink':
            self._tplink_disconnect_device(mac_address)
        elif self.router_type == 'dlink':
            self._dlink_disconnect_device(mac_address)
        elif self.router_type == 'netgear':
            self._netgear_disconnect_device(mac_address)
        else:
            self._generic_disconnect_device(mac_address)

    def _reconnect_device_by_mac(self, mac_address):
        """重新连接设备"""
        logging.info(f"重新连接MAC地址为 {mac_address} 的设备")

        # 对于大多数路由器，设备会自动重新连接
        # 如果需要手动重连，可以在这里实现
        pass

    def _configure_weak_network_for_mac(self, mac_address, config):
        """为指定MAC地址配置弱网环境"""
        logging.info(f"为MAC {mac_address} 配置弱网: {config}")

        if self.router_type == 'tplink':
            self._tplink_configure_weak_network(mac_address, config)
        elif self.router_type == 'asus':
            self._asus_configure_weak_network(mac_address, config)
        else:
            self._generic_configure_weak_network(mac_address, config)

    def _cleanup_weak_network_for_mac(self, mac_address):
        """清理弱网配置"""
        logging.info(f"清理MAC {mac_address} 的弱网配置")

        if self.router_type == 'tplink':
            self._tplink_cleanup_weak_network(mac_address)
        elif self.router_type == 'asus':
            self._asus_cleanup_weak_network(mac_address)
        else:
            self._generic_cleanup_weak_network(mac_address)

    # 路由器特定实现方法

    def _tplink_disconnect_device(self, mac_address):
        """TP-Link路由器断开设备"""
        # TP-Link路由器通常支持通过Web界面或API断开设备
        # 这里是示例实现
        logging.info("TP-Link路由器断开设备 - 实际实现需要路由器API")

    def _dlink_disconnect_device(self, mac_address):
        """D-Link路由器断开设备"""
        logging.info("D-Link路由器断开设备 - 实际实现需要路由器API")

    def _netgear_disconnect_device(self, mac_address):
        """Netgear路由器断开设备"""
        logging.info("Netgear路由器断开设备 - 实际实现需要路由器API")

    def _generic_disconnect_device(self, mac_address):
        """通用路由器断开设备"""
        logging.info("通用路由器断开设备 - 尝试通用方法")

        # 通用方法：使用arp命令或其他网络工具
        # 注意：这可能需要PC端的管理员权限
        try:
            import subprocess
            # 这里可以实现一些通用的网络控制方法
            # 例如：修改防火墙规则、ARP欺骗等
            logging.warning("通用断开方法可能需要管理员权限")
        except Exception as e:
            logging.error(f"通用断开方法失败: {str(e)}")

    def _tplink_configure_weak_network(self, mac_address, config):
        """TP-Link路由器配置弱网"""
        # 配置QoS规则限制带宽
        logging.info("TP-Link路由器配置弱网QoS规则")

    def _asus_configure_weak_network(self, mac_address, config):
        """ASUS路由器配置弱网"""
        # ASUS路由器有强大的QoS功能
        logging.info("ASUS路由器配置弱网QoS规则")

    def _generic_configure_weak_network(self, mac_address, config):
        """通用路由器配置弱网"""
        logging.info("通用路由器配置弱网 - 使用系统网络工具")

        try:
            # 使用tc (traffic control) 命令配置网络QoS
            # 这需要在PC端有管理员权限
            self._configure_tc_rules(mac_address, config)
        except Exception as e:
            logging.error(f"配置QoS规则失败: {str(e)}")

    def _configure_tc_rules(self, mac_address, config):
        """配置Linux tc规则模拟弱网"""
        try:
            import subprocess

            # 示例tc命令（需要管理员权限）
            # 添加延迟
            if config.get('delay', 0) > 0:
                delay_ms = config['delay']
                cmd = f"tc qdisc add dev eth0 root netem delay {delay_ms}ms"
                subprocess.run(cmd, shell=True, check=True)

            # 添加丢包
            if config.get('loss', 0) > 0:
                loss_rate = config['loss']
                cmd = f"tc qdisc change dev eth0 root netem loss {loss_rate}%"
                subprocess.run(cmd, shell=True, check=True)

            # 带宽限制
            if config.get('bandwidth', 0) > 0:
                bandwidth_kbps = config['bandwidth'] // 1024
                cmd = f"tc qdisc add dev eth0 root tbf rate {bandwidth_kbps}kbit burst 1600 latency 400ms"
                subprocess.run(cmd, shell=True, check=True)

        except subprocess.CalledProcessError as e:
            logging.error(f"tc命令执行失败: {str(e)}")
            logging.warning("需要管理员权限才能配置网络QoS规则")

    def _tplink_cleanup_weak_network(self, mac_address):
        """清理TP-Link弱网配置"""
        logging.info("清理TP-Link弱网QoS规则")

    def _asus_cleanup_weak_network(self, mac_address):
        """清理ASUS弱网配置"""
        logging.info("清理ASUS弱网QoS规则")

    def _generic_cleanup_weak_network(self, mac_address):
        """清理通用弱网配置"""
        logging.info("清理通用弱网配置")

        try:
            import subprocess
            # 删除tc规则
            cmd = "tc qdisc del dev eth0 root"
            subprocess.run(cmd, shell=True)
        except Exception as e:
            logging.error(f"清理tc规则失败: {str(e)}")