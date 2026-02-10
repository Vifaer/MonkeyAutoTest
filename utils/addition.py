#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import json
import logging
from utils import get_apk
from utils import Device
from utils import Package
from utils import DeviceLog
from libs import SendMail


def get_project_json(sfile="conf/project.json"):
    with open(sfile, 'r', encoding='utf-8') as json_file:
        try:
            prj_json = json.load(json_file)
        except Exception as e:
            logging.error(e)
            sys.exit(-1)
    return prj_json


def monkey_test(sn, package, prj_info, need_uninstall, throttle, count, rcpt_list):
    device = Device(sn)
    device_log = DeviceLog(sn)
    # 初始化设备日志
    logging.info(">>> Init log for device")
    device_log.init()
    logging.info(">>> Done")
    # 卸载apk文件
    if need_uninstall:
        logging.info(">>> Uninstall package")
        device.uninstall(package)
        logging.info(">>> Done")
    # 安装apk文件
    logging.info(">>> Install package")
    device.install(package)
    logging.info(">>> Done")
    # 安装Wifi Manager
    logging.info(">>> Install Wifi Manager")
    device.install(Package("apks/wifimanager-debug.apk"))
    logging.info(">>> Done")
    # 启动Wifi Manager
    logging.info(">>> Enable Wifi Manager")
    device.enable_wifi_manager()
    logging.info(">>> Done")
    # 安装simiasque
    logging.info(">>> Install simiasque")
    device.install(Package("apks/simiasque-debug.apk"))
    logging.info(">>> Done")
    # 启动simiasque
    logging.info(">>> Enable simiasque")
    device.enable_simiasque()
    logging.info(">>> Done")
    # 执行monkey测试
    logging.info(">>> Run monkey test")
    device.run_monkey(package, device_log.log_path, throttle, count)
    logging.info(">>> Done")
    # 关闭simiasque
    logging.info(">>> Disable simiasque")
    device.disable_simiasque()
    logging.info(">>> Done")
    # 关闭屏幕
    logging.info(">>> Turn off screen")
    device.turn_off_screen()
    logging.info(">>> Done")
    # 生成dumpsys信息
    logging.info(">>> Dumpsys activities")
    device.dumpsys_activity(device_log.dump_dir)
    logging.info(">>> Done")
    # 分析设备日志
    logging.info(">>> Check logs")
    device_log.check(package)
    logging.info(">>> Done")
    # 获取anr数量、crash数量和附件list
    anr_cnt, crash_cnt, att_list = device_log.get()
    # 使用统一报告生成器生成 HTML/JSON 报告（与稳定性测试等格式一致）
    try:
        from utils.report_generator import StabilityReportGenerator, TEST_TYPE_MONKEY
        raw_results = {
            'device_info': {
                'sn': device.sn,
                'model': device.model,
                'os': device.os,
                'screen': device.screen,
                # 设备显示版本号（ro.build.display.id），用于报告展示与筛选
                'build_display_id': getattr(device, "build_display_id", ""),
            },
            'package_info': {
                'name': package.name,
                'filename': package.filename,
                'path': getattr(package, 'path', ''),
                # 应用版本信息（若可用）
                'version_name': getattr(package, "version_name", ""),
                'app_label': getattr(package, "app_label", ""),
            },
            'crashes': crash_cnt,
            'anrs': anr_cnt,
            'throttle': throttle,
            'count': count,
            'log_path': device_log.log_path,
        }
        report_gen = StabilityReportGenerator()
        report_gen.generate_report(raw_results, test_type=TEST_TYPE_MONKEY)
    except Exception as e:
        logging.debug("统一报告生成跳过: %s", e)
    # 发送邮件
    send_log(prj_info, device, package, rcpt_list, anr_cnt, crash_cnt, att_list)


def send_log(prj_info, device, package, rcpt_list, anr_cnt, crash_cnt, att_list):
    # 检查邮件配置是否有效
    mail_sender = SendMail()
    if not mail_sender.is_mail_configured():
        logging.info("邮件配置无效，将测试结果保存到日志文件")

        # 保存测试结果到日志文件
        if mail_sender.save_test_report_to_log(prj_info, device, package, anr_cnt, crash_cnt, att_list):
            logging.info("测试报告已保存到logs目录")
        else:
            logging.error("保存测试报告失败")

        return

    # 如果没有anr和crash，则不发邮件
    if anr_cnt == 0 and crash_cnt == 0:
        logging.info("No anr or crash, won't send mail")
        return

    prj_name = prj_info["name"]
    subject = u"%s Monkey测试异常提醒" % prj_name
    content = "<table border='1' cellspacing='0' cellpadding='0'>" \
              + "<tr align='center'><th style='width:600px' colspan='2'>{} Monkey测试结果</th></tr>".format(prj_name) \
              + "<tr><td width='30%%'><b>安装包文件名</b></td><td width='70%%'>{}</a></td></tr>".format(package.filename) \
              + "<tr><td width='30%%'><b>安装包包名</b></td><td width='70%%'>{}</td>".format(package.name) \
              + "<tr><td width='30%%'><b>设备型号</b></td><td width='70%%'>{}</td>".format(device.model) \
              + "<tr><td width='30%%'><b>设备序列号</b></td><td width='70%%'>{}</td>".format(device.sn) \
              + "<tr><td width='30%%'><b>系统版本</b></td><td width='70%%'>{}</td>".format(device.os) \
              + "<tr><td width='30%%'><b>分辨率</b></td><td width='70%%'>{}</td>".format(device.screen) \
              + "<tr><td width='30%%'><b>发现ANR次数</b></td><td width='70%%'>{}</td>".format(anr_cnt) \
              + "<tr><td width='30%%'><b>发现CRASH次数</b></td><td width='70%%'>{}</td>".format(crash_cnt) \
              + "</table>" \
              + "<br/><p>具体日志见附件</p>"
    status, reason = mail_sender.send_mail(rcpt_list, subject, content, att_list=att_list)
    if status:
        logging.info("Succeed in sending mails")
    else:
        logging.error("Failed to send mails, reason: %s" % reason)


def get_package(prj_ver, prj_info, apk_url, apk_path):
    # 如果apk_url不为空，优先下载该apk
    if apk_url != "":
        logging.info("[get_package] get apk from url: {}".format(apk_url))
        apk_path = get_apk.get_apk_from_url(apk_url, prj_ver)
    # 如果apk_url为空，apk_path不为空，直接使用该路径的apk
    elif apk_path != "":
        logging.info("[get_package] get apk from local: {}".format(apk_path))
    # 如果apk_url和apk_path均为空，则通过prj_info下载最新包
    else:
        logging.info("[get_package] get latest apk...")
        apk_path = get_apk.get_latest_apk()
    # 如果apk_path为None，则报错，否则返回包
    if apk_path is None:
        logging.error("[get_package] failed to get package")
        sys.exit(-1)
    return Package(apk_path)
