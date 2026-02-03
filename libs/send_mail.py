#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
try:
    import configparser as ConfigParser  # Python 3
except ImportError:
    import ConfigParser  # Python 2
import base64
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import parseaddr, formataddr

# 解决Windows下编码问题
if sys.platform == 'win32':
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'Chinese_China.UTF-8')
        except:
            pass

    # 确保stdout使用UTF-8编码
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass


class SendMail:
    def __init__(self, sfile="conf/mail.ini", param="gmail"):
        """
        初始化ini配置文件信息
        :param sfile: ini配置文件路径
        :param param: ini配置文件的paramater
        """
        self.__sfile = sfile
        self.__param = param

    def is_mail_configured(self):
        """
        检查邮件配置是否有效（非示例配置）
        :return: True表示配置有效，False表示配置无效
        """
        if not os.path.exists(self.__sfile):
            return False

        try:
            conf = ConfigParser.ConfigParser()
            conf.read(self.__sfile)

            # 检查必要配置项是否存在且不为示例值
            mail_host = conf.get(self.__param, "host")
            mail_user = conf.get(self.__param, "user")
            mail_passwd_base64 = conf.get(self.__param, "passwd")
            sender_name = conf.get(self.__param, "name")
            sender_addr = conf.get(self.__param, "sender")

            # 检查是否为示例配置
            if (mail_host == "smtp.gmail.com" and
                mail_user == "sample@gmail.com" and
                mail_passwd_base64 == "baes64_of_password" and
                sender_name == "发件人名称" and
                sender_addr == "sample@gmail.com"):
                return False

            # 尝试解码密码以验证格式
            try:
                base64.decodestring(mail_passwd_base64)
            except:
                return False

            return True
        except:
            return False

    def __get_mail_conf(self):
        """
        通过配置文件获取邮件相关信息
        :return: SMTP服务器地址、登录账号、登录密码、发件人名称、发件人地址
        """
        if not os.path.exists(self.__sfile):
            print("Error: %s doesn't exist" % self.__sfile)
            sys.exit(-1)
        conf = ConfigParser.ConfigParser()
        conf.read(self.__sfile)
        try:
            mail_host = conf.get(self.__param, "host")
            mail_user = conf.get(self.__param, "user")
            mail_passwd_base64 = conf.get(self.__param, "passwd")
            mail_passwd = base64.decodestring(mail_passwd_base64)
            sender_name = conf.get(self.__param, "name")
            sender_addr = conf.get(self.__param, "sender")
        except Exception as e:
            print("Error:", e)
            sys.exit(-2)
        return mail_host, mail_user, mail_passwd, sender_name, sender_addr

    @staticmethod
    def __format_addr(raw_addr):
        """
        格式化邮件地址
        :param raw_addr: 原始格式地址，可以为仅邮箱地址或"名称<邮箱地址>"
        :return: 格式化后的邮件地址
        """
        name, addr = parseaddr(raw_addr)
        return formataddr((Header(name, "utf-8").encode(),
                           addr.encode("utf-8") if isinstance(addr, unicode) else addr))

    def send_mail(self, rcpt_list, subject, content, att_list=None, cc_list=None, mail_type="html"):
        """
        发送邮件
        :param rcpt_list: 收件人列表
        :param subject: 标题
        :param content: 内容
        :param att_list: 附件列表，默认为空
        :param cc_list: 抄送人列表，默认为空
        :param mail_type: 邮件类型，"html"或"plain"，默认为"html"
        :return: 是否发送成功，True或False
        """
        if cc_list is None:
            cc_list = []
        if att_list is None:
            att_list = []
        # 通过配置文件获取邮箱服务器、登录账号、登录密码、发件人名称和发件人地址
        mail_host, mail_user, mail_passwd, sender_name, sender_addr = self.__get_mail_conf()
        # 格式化邮箱地址
        mail_from = self.__format_addr("%s <%s>" % (sender_name, sender_addr))
        rcpt_list = [self.__format_addr(rcpt_addr) for rcpt_addr in rcpt_list]
        cc_list = [self.__format_addr(cc_addr) for cc_addr in cc_list]
        # 配置邮件标题、发件人、收件人、抄送人和内容
        msg = MIMEMultipart()
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = mail_from
        msg["To"] = ";".join(rcpt_list)
        msg["Cc"] = ";".join(cc_list)
        text_msg = MIMEText(content, _subtype=mail_type, _charset="utf-8")
        msg.attach(text_msg)
        # 配置附件
        for att_path in att_list:
            att_name = os.path.basename(att_path)
            with open(att_path, "rb") as fp:
                part = MIMEApplication(fp.read())
                part.add_header("Content-Disposition", "attachment", filename=att_name)
                msg.attach(part)
        # 发送邮件
        try:
            server = smtplib.SMTP_SSL()
            server.connect(mail_host)
            server.login(mail_user, mail_passwd)
            server.sendmail(mail_from, rcpt_list+cc_list, msg.as_string())
            server.close()
            return True, None
        except Exception as e:
            print("Error:", e)
            return False, str(e)

    def save_test_report_to_log(self, prj_info, device, package, anr_cnt, crash_cnt, att_list):
        """
        当邮件配置无效时，将测试结果保存到日志文件中
        :param prj_info: 项目信息
        :param device: 设备信息
        :param package: 包信息
        :param anr_cnt: ANR数量
        :param crash_cnt: 崩溃数量
        :param att_list: 附件列表
        """
        import datetime
        import logging

        # 创建日志目录
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 生成报告文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"test_report_{device.sn}_{timestamp}.txt"
        report_path = os.path.join(log_dir, report_filename)

        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("车载端侧应用稳定性测试报告\n")
                f.write("=" * 60 + "\n\n")

                f.write("测试时间: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                f.write("项目名称: {}\n".format(prj_info.get("name", "Unknown")))
                f.write("\n")

                f.write("设备信息:\n")
                f.write("- 设备型号: {}\n".format(device.model))
                f.write("- 设备序列号: {}\n".format(device.sn))
                f.write("- 系统版本: {}\n".format(device.os))
                f.write("- 分辨率: {}\n".format(device.screen))
                f.write("\n")

                f.write("应用信息:\n")
                f.write("- 安装包文件名: {}\n".format(package.filename))
                f.write("- 安装包包名: {}\n".format(package.name))
                f.write("\n")

                f.write("测试结果:\n")
                f.write("- 发现CRASH次数: {}\n".format(crash_cnt))
                f.write("- 发现ANR次数: {}\n".format(anr_cnt))
                f.write("\n")

                # 添加详细的错误信息
                if crash_cnt > 0 or anr_cnt > 0:
                    f.write("错误详情:\n")
                    if crash_cnt > 0:
                        f.write("- 发现 {} 次应用崩溃\n".format(crash_cnt))
                    if anr_cnt > 0:
                        f.write("- 发现 {} 次应用无响应\n".format(anr_cnt))
                    f.write("\n")

                    f.write("相关日志文件:\n")
                    for att_path in att_list:
                        f.write("- {}\n".format(os.path.basename(att_path)))
                else:
                    f.write("测试结果正常，未发现崩溃或ANR。\n")

                f.write("\n")
                f.write("-" * 60 + "\n")
                f.write("报告生成时间: {}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                f.write("报告文件位置: {}\n".format(os.path.abspath(report_path)))

            logging.info("测试报告已保存到: {}".format(report_path))
            return True

        except Exception as e:
            logging.error("保存测试报告失败: {}".format(str(e)))
            return False
