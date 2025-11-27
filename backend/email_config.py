# -*- coding: utf-8 -*-
"""
邮件配置和发送功能
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from datetime import datetime

logger = logging.getLogger(__name__)

# 邮件配置
EMAIL_CONFIG = {
    'smtp_host': 'smtp.qiye.aliyun.com',
    'smtp_port': 465,
    'username': 'Ybalance@ginwin.xyz',
    'password': 'yzh2766232123',
    'from_email': 'Ybalance@ginwin.xyz',
    'from_name': '数据库同步系统',
    'to_email': '2365416032@qq.com',
    'enabled': True  # 是否启用邮件通知
}


class EmailNotifier:
    """邮件通知器"""
    
    def __init__(self, config=None):
        self.config = config or EMAIL_CONFIG
        self.enabled = self.config.get('enabled', True)
    
    def get_admin_emails(self):
        """
        从数据库获取所有管理员的邮箱地址
        
        Returns:
            list: 管理员邮箱地址列表
        """
        try:
            from models import Admin
            from extensions import db
            from flask import current_app
            
            # 确保在应用上下文中
            if not current_app:
                logger.warning("不在应用上下文中，使用默认邮箱")
                return [self.config.get('to_email')]
            
            # 查询所有有邮箱的管理员
            admins = Admin.query.filter(Admin.email.isnot(None), Admin.email != '').all()
            emails = [admin.email for admin in admins if admin.email]
            
            logger.info(f"获取到 {len(emails)} 个管理员邮箱: {emails}")
            return emails if emails else [self.config.get('to_email')]
        except Exception as e:
            logger.error(f"获取管理员邮箱失败: {e}")
            # 如果数据库查询失败，返回配置文件中的默认邮箱
            return [self.config.get('to_email')]
    
    def send_email(self, subject, content, content_type='plain', to_emails=None):
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            content: 邮件内容
            content_type: 内容类型 ('plain' 或 'html')
            to_emails: 收件人邮箱列表，如果为None则从数据库获取所有管理员邮箱
        
        Returns:
            bool: 是否发送成功
        """
        if not self.enabled:
            logger.info("邮件通知已禁用，跳过发送")
            return False
        
        try:
            # 如果没有指定收件人，从数据库获取所有管理员邮箱
            if to_emails is None:
                to_emails = self.get_admin_emails()
            
            # 确保to_emails是列表
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            
            if not to_emails:
                logger.warning("没有找到收件人邮箱，使用默认配置")
                to_emails = [self.config['to_email']]
            
            # 创建邮件对象
            message = MIMEMultipart()
            
            # 正确设置From头部，符合RFC5322标准
            from_name_encoded = Header(self.config['from_name'], 'utf-8').encode()
            message['From'] = f"{from_name_encoded} <{self.config['from_email']}>"
            
            # 设置To和Subject（显示第一个收件人，实际发送给所有人）
            message['To'] = ', '.join(to_emails)
            message['Subject'] = Header(subject, 'utf-8')
            
            # 添加必要的邮件头部，提高兼容性
            message['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')
            message['Message-ID'] = f"<{datetime.now().timestamp()}@{self.config['smtp_host']}>"
            message['X-Mailer'] = 'Database Sync System v1.0'
            
            # 添加邮件内容
            message.attach(MIMEText(content, content_type, 'utf-8'))
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP_SSL(self.config['smtp_host'], self.config['smtp_port']) as server:
                server.login(self.config['username'], self.config['password'])
                
                server.sendmail(
                    self.config['from_email'],
                    to_emails,
                    message.as_string()
                )
            
            logger.info(f"邮件发送成功: {subject} -> {', '.join(to_emails)}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    def send_conflict_notification(self, conflict_info, sync_type='auto'):
        """
        发送冲突通知邮件
        
        Args:
            conflict_info: 冲突信息字典
            sync_type: 同步类型 ('auto' 或 'manual')
        
        Returns:
            bool: 是否发送成功
        """
        sync_type_text = '自动同步' if sync_type == 'auto' else '手动同步'
        
        # 构建邮件主题
        subject = f"【数据库同步通知】{sync_type_text}检测到数据冲突"
        
        # 构建邮件内容
        content = self._build_conflict_email_content(conflict_info, sync_type_text)
        
        return self.send_email(subject, content, 'html')
    
    def _build_conflict_email_content(self, conflict_info, sync_type_text):
        """构建冲突通知邮件的HTML内容"""
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 提取冲突信息
        total_conflicts = conflict_info.get('total_conflicts', 0)
        resolved_conflicts = conflict_info.get('resolved_conflicts', 0)
        failed_conflicts = conflict_info.get('failed_conflicts', 0)
        strategy = conflict_info.get('strategy', 'unknown')
        details = conflict_info.get('details', {})
        
        # 策略名称映射
        strategy_names = {
            'timestamp_priority': '时间戳优先',
            'primary_priority': 'SQLite优先',
            'mysql_priority': 'MySQL优先',
            'sqlserver_priority': 'SQL Server优先'
        }
        strategy_name = strategy_names.get(strategy, strategy)
        
        # 构建HTML内容
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, 'Microsoft YaHei', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .content {{
            background: #f8f9fa;
            padding: 20px;
            border: 1px solid #dee2e6;
            border-top: none;
        }}
        .info-box {{
            background: white;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #667eea;
            border-radius: 4px;
        }}
        .info-item {{
            margin: 8px 0;
        }}
        .label {{
            font-weight: bold;
            color: #495057;
            display: inline-block;
            width: 120px;
        }}
        .value {{
            color: #212529;
        }}
        .conflict-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            background: white;
        }}
        .conflict-table th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        .conflict-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #dee2e6;
        }}
        .conflict-table tr:hover {{
            background: #f8f9fa;
        }}
        .footer {{
            background: #e9ecef;
            padding: 15px;
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
            border-radius: 0 0 8px 8px;
        }}
        .success {{
            color: #28a745;
            font-weight: bold;
        }}
        .warning {{
            color: #ffc107;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h2>🔄 数据库同步冲突通知</h2>
    </div>
    
    <div class="content">
        <div class="info-box">
            <h3>📊 同步概要</h3>
            <div class="info-item">
                <span class="label">同步时间:</span>
                <span class="value">{current_time}</span>
            </div>
            <div class="info-item">
                <span class="label">同步类型:</span>
                <span class="value">{sync_type_text}</span>
            </div>
            <div class="info-item">
                <span class="label">解决策略:</span>
                <span class="value">{strategy_name}</span>
            </div>
            <div class="info-item">
                <span class="label">检测到冲突:</span>
                <span class="value warning">{total_conflicts} 个</span>
            </div>
            <div class="info-item">
                <span class="label">成功解决:</span>
                <span class="value success">{resolved_conflicts} 个</span>
            </div>
            <div class="info-item">
                <span class="label">解决失败:</span>
                <span class="value" style="color: #dc3545; font-weight: bold;">{failed_conflicts} 个</span>
            </div>
        </div>
        
        <div class="info-box">
            <h3>📝 冲突详情</h3>
"""
        
        # 添加冲突详情表格
        if details:
            for table_name, table_conflicts in details.items():
                if table_conflicts:
                    html_content += f"""
            <h4>表: {table_name}</h4>
            <table class="conflict-table">
                <thead>
                    <tr>
                        <th>记录ID</th>
                        <th>冲突数据库</th>
                        <th>解决结果</th>
                    </tr>
                </thead>
                <tbody>
"""
                    for conflict in table_conflicts:
                        record_id = conflict.get('record_id', 'N/A')
                        databases = conflict.get('databases', [])
                        result = conflict.get('result', 'unknown')
                        
                        result_text = '✅ 已解决' if result == 'resolved' else '❌ 失败'
                        db_list = ', '.join(databases) if databases else 'N/A'
                        
                        html_content += f"""
                    <tr>
                        <td>{record_id}</td>
                        <td>{db_list}</td>
                        <td>{result_text}</td>
                    </tr>
"""
                    html_content += """
                </tbody>
            </table>
"""
        else:
            html_content += """
            <p style="color: #6c757d; font-style: italic;">暂无详细冲突信息</p>
"""
        
        html_content += """
        </div>
    </div>
    
    <div class="footer">
        <p>此邮件由数据库同步系统自动发送，请勿回复</p>
        <p>如需帮助，请联系系统管理员</p>
    </div>
</body>
</html>
"""
        
        return html_content
    
    def send_sync_summary(self, summary_info):
        """
        发送同步摘要邮件
        
        Args:
            summary_info: 同步摘要信息
        
        Returns:
            bool: 是否发送成功
        """
        subject = "【数据库同步】同步任务完成通知"
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, 'Microsoft YaHei', sans-serif;
            padding: 20px;
        }}
        .summary-box {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }}
    </style>
</head>
<body>
    <h2>✅ 数据库同步完成</h2>
    <div class="summary-box">
        <p><strong>同步时间:</strong> {current_time}</p>
        <p><strong>同步状态:</strong> {summary_info.get('status', '完成')}</p>
        <p><strong>处理记录:</strong> {summary_info.get('total_records', 0)} 条</p>
    </div>
</body>
</html>
"""
        
        return self.send_email(subject, html_content, 'html')


# 创建全局邮件通知器实例
email_notifier = EmailNotifier()
