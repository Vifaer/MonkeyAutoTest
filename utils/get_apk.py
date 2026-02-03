#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import socket
import subprocess
import shutil
import logging
import json
import requests
from urllib.parse import urlparse, urljoin
import ftplib
import time
from datetime import datetime

# 设置连接最大时长
socket.setdefaulttimeout(30)


def get_apk_from_url(url, prj_ver):
    """
    从URL下载APK包

    Args:
        url: APK下载地址
        prj_ver: 项目版本，用于创建保存目录

    Returns:
        str: 下载成功的APK文件路径，失败返回None
    """
    # 如果路径不存在，先创建路径
    saved_path = "apks/" + prj_ver
    if not os.path.isdir(saved_path):
        os.makedirs(saved_path)

    # 解析URL获取文件名
    parsed_url = urlparse(url)
    apk_name = os.path.basename(parsed_url.path)
    if not apk_name:
        apk_name = f"app_{prj_ver}_{int(time.time())}.apk"

    file_path = os.path.join(saved_path, apk_name)

    # 使用requests下载（比wget更可靠）
    try:
        logging.info(f"开始下载APK: {url}")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        # 获取文件大小用于进度显示
        total_size = int(response.headers.get('content-length', 0))

        with open(file_path, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = int(100 * downloaded / total_size)
                        logging.debug(f"下载进度: {progress}%")

        logging.info(f"APK下载完成: {file_path}")
        return file_path

    except requests.RequestException as e:
        logging.error(f"APK下载失败: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return None
    except Exception as e:
        logging.error(f"APK下载过程中发生错误: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return None


def get_latest_apk():
    """
    自动获取最新APK包

    从project.json配置中读取APK源信息，自动下载最新的APK包

    Returns:
        str: APK文件路径，获取失败返回None
    """
    try:
        # 读取项目配置
        with open("conf/project.json", 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 获取当前工作目录中的项目版本（可以通过环境变量或其他方式确定）
        # 这里简化处理，查找auto_get_apk为true的版本
        target_version = None
        apk_source = None

        for version, settings in config.items():
            if isinstance(settings, dict) and settings.get('auto_get_apk', False):
                target_version = version
                apk_source = settings.get('apk_source')
                break

        if not target_version or not apk_source:
            logging.warning("未找到启用auto_get_apk的版本配置")
            return None

        logging.info(f"开始自动获取APK，版本: {target_version}")

        source_type = apk_source.get('type', 'http')

        if source_type == 'http' or source_type == 'https':
            return _get_apk_from_http(apk_source, target_version)
        elif source_type == 'jenkins':
            return _get_apk_from_jenkins(apk_source, target_version)
        elif source_type == 'ftp':
            return _get_apk_from_ftp(apk_source, target_version)
        elif source_type == 'local':
            return _get_apk_from_local(apk_source, target_version)
        else:
            logging.error(f"不支持的APK源类型: {source_type}")
            return None

    except Exception as e:
        logging.error(f"自动获取APK失败: {str(e)}")
        return None


def _get_apk_from_http(apk_source, version):
    """从HTTP/HTTPS源获取APK"""
    url = apk_source.get('url')
    if not url:
        logging.error("HTTP源配置中缺少url字段")
        return None

    # 检查是否需要认证
    auth = apk_source.get('auth')
    if auth:
        # 如果需要认证，可以在这里处理
        logging.info("检测到认证配置，但HTTP基本认证暂未实现")

    return get_apk_from_url(url, version)


def _get_apk_from_jenkins(apk_source, version):
    """从Jenkins获取最新构建产物"""
    url = apk_source.get('url')
    if not url:
        logging.error("Jenkins源配置中缺少url字段")
        return None

    try:
        # Jenkins API认证
        auth = apk_source.get('auth')
        if auth:
            username = auth.get('username')
            password = auth.get('password')
            if username and password:
                # 使用基本认证
                response = requests.get(url, auth=(username, password), timeout=30)
            else:
                response = requests.get(url, timeout=30)
        else:
            response = requests.get(url, timeout=30)

        response.raise_for_status()

        # 保存APK文件
        saved_path = f"apks/{version}"
        if not os.path.isdir(saved_path):
            os.makedirs(saved_path)

        # 从URL中提取文件名，或使用时间戳命名
        parsed_url = urlparse(url)
        apk_name = os.path.basename(parsed_url.path)
        if not apk_name or apk_name == 'artifact':
            apk_name = f"jenkins_build_{int(time.time())}.apk"

        file_path = os.path.join(saved_path, apk_name)

        with open(file_path, 'wb') as f:
            f.write(response.content)

        logging.info(f"Jenkins APK获取成功: {file_path}")
        return file_path

    except requests.RequestException as e:
        logging.error(f"Jenkins APK获取失败: {str(e)}")
        return None


def _get_apk_from_ftp(apk_source, version):
    """从FTP服务器获取APK"""
    host = apk_source.get('host')
    port = apk_source.get('port', 21)
    path = apk_source.get('path')
    filename = apk_source.get('filename')

    if not all([host, path, filename]):
        logging.error("FTP源配置不完整，需要host、path和filename字段")
        return None

    try:
        # 创建保存目录
        saved_path = f"apks/{version}"
        if not os.path.isdir(saved_path):
            os.makedirs(saved_path)

        file_path = os.path.join(saved_path, filename)

        # FTP下载
        ftp = ftplib.FTP()
        ftp.connect(host, port)
        ftp.login(apk_source.get('username', 'anonymous'),
                 apk_source.get('password', ''))

        with open(file_path, 'wb') as f:
            ftp.retrbinary(f"RETR {path}/{filename}", f.write)

        ftp.quit()

        logging.info(f"FTP APK获取成功: {file_path}")
        return file_path

    except ftplib.all_errors as e:
        logging.error(f"FTP APK获取失败: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)
        return None


def _get_apk_from_local(apk_source, version):
    """从本地文件系统获取APK"""
    local_path = apk_source.get('path')
    if not local_path:
        logging.error("本地源配置中缺少path字段")
        return None

    if not os.path.exists(local_path):
        logging.error(f"本地APK文件不存在: {local_path}")
        return None

    try:
        # 复制到项目APK目录
        saved_path = f"apks/{version}"
        if not os.path.isdir(saved_path):
            os.makedirs(saved_path)

        filename = os.path.basename(local_path)
        target_path = os.path.join(saved_path, filename)

        shutil.copy2(local_path, target_path)

        logging.info(f"本地APK复制成功: {target_path}")
        return target_path

    except Exception as e:
        logging.error(f"本地APK复制失败: {str(e)}")
        return None


def get_apk_from_url_old(url, prj_ver):
    """
    旧版本的URL下载函数，保留兼容性
    已废弃，请使用get_apk_from_url
    """
    return get_apk_from_url(url, prj_ver)
