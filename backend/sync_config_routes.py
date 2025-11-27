# -*- coding: utf-8 -*-
"""
数据库同步配置管理路由
"""

from flask import Blueprint, jsonify, request
from functools import wraps
import logging
from email_config import email_notifier, EMAIL_CONFIG
from auth import role_required

logger = logging.getLogger(__name__)

sync_config_bp = Blueprint('sync_config', __name__)

# 全局变量存储同步管理器引用
sync_manager = None

def init_sync_config_routes(app, db_sync_manager):
    """初始化同步配置路由"""
    global sync_manager
    sync_manager = db_sync_manager
    app.register_blueprint(sync_config_bp, url_prefix='/api')
    logger.info("同步配置路由已注册")

@sync_config_bp.route('/admin/sync-config/get', methods=['GET'])
@role_required('admin')
def get_sync_config():
    """获取当前同步配置"""
    try:
        if not sync_manager or not sync_manager.conflict_scheduler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        # 获取默认策略
        default_strategy = getattr(sync_manager.conflict_handler, 'default_strategy', 'timestamp_priority')
        
        config = {
            'check_interval': sync_manager.conflict_scheduler.check_interval,
            'check_interval_minutes': sync_manager.conflict_scheduler.check_interval / 60,
            'is_running': sync_manager.conflict_scheduler.running,
            'default_strategy': default_strategy,
            'available_strategies': [
                {
                    'value': 'timestamp_priority',
                    'label': '时间戳优先',
                    'description': '自动选择最新的数据（根据updated_at字段）'
                },
                {
                    'value': 'primary_priority',
                    'label': 'SQLite优先',
                    'description': '始终使用SQLite数据库的数据'
                },
                {
                    'value': 'mysql_priority',
                    'label': 'MySQL优先',
                    'description': '始终使用MySQL数据库的数据'
                },
                {
                    'value': 'sqlserver_priority',
                    'label': 'SQL Server优先',
                    'description': '始终使用SQL Server数据库的数据'
                }
            ]
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        logger.error(f"获取同步配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/update', methods=['POST'])
@role_required('admin')
def update_sync_config():
    """更新同步配置"""
    try:
        if not sync_manager or not sync_manager.conflict_scheduler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '缺少请求数据'
            }), 400
        
        # 获取配置参数
        check_interval_minutes = data.get('check_interval_minutes')
        default_strategy = data.get('default_strategy')
        
        updated_config = {}
        messages = []
        
        # 更新检查间隔
        if check_interval_minutes is not None:
            # 验证时间间隔
            if not isinstance(check_interval_minutes, (int, float)) or check_interval_minutes < 0.17:
                return jsonify({
                    'success': False,
                    'error': '检查间隔必须大于等于10秒（0.17分钟）'
                }), 400
            
            if check_interval_minutes > 1440:  # 24小时
                return jsonify({
                    'success': False,
                    'error': '检查间隔不能超过1440分钟（24小时）'
                }), 400
            
            # 转换为秒
            new_interval = int(check_interval_minutes * 60)
            
            # 更新配置
            old_interval = sync_manager.conflict_scheduler.check_interval
            was_running = sync_manager.conflict_scheduler.running
            
            # 如果调度器正在运行，需要重启以应用新间隔
            if was_running:
                logger.info("停止调度器以应用新间隔...")
                sync_manager.conflict_scheduler.stop()
            
            # 更新间隔
            sync_manager.conflict_scheduler.check_interval = new_interval
            
            # 重新启动调度器
            if was_running:
                logger.info("使用新间隔重启调度器...")
                sync_manager.conflict_scheduler.start()
            
            updated_config['check_interval'] = new_interval
            updated_config['check_interval_minutes'] = check_interval_minutes
            messages.append(f'检查间隔已更新为 {check_interval_minutes} 分钟，调度器已重启')
            
            logger.info(f"同步检查间隔已更新: {old_interval}秒 -> {new_interval}秒 ({check_interval_minutes}分钟)")
        
        # 更新默认策略
        if default_strategy is not None:
            valid_strategies = ['timestamp_priority', 'primary_priority', 'mysql_priority', 'sqlserver_priority']
            
            if default_strategy not in valid_strategies:
                return jsonify({
                    'success': False,
                    'error': f'无效的同步策略，支持的策略: {", ".join(valid_strategies)}'
                }), 400
            
            # 保存默认策略到冲突处理器
            if hasattr(sync_manager.conflict_handler, 'default_strategy'):
                sync_manager.conflict_handler.default_strategy = default_strategy
            else:
                # 如果没有这个属性，添加它
                sync_manager.conflict_handler.default_strategy = default_strategy
            
            updated_config['default_strategy'] = default_strategy
            messages.append(f'默认同步策略已更新为 {default_strategy}')
            
            logger.info(f"默认同步策略已更新为: {default_strategy}")
        
        if not updated_config:
            return jsonify({
                'success': False,
                'error': '未提供有效的配置参数'
            }), 400
        
        return jsonify({
            'success': True,
            'message': '，'.join(messages),
            'config': updated_config
        })
        
    except Exception as e:
        logger.error(f"更新同步配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/scheduler/start', methods=['POST'])
@role_required('admin')
def start_scheduler():
    """启动自动冲突检测调度器"""
    try:
        if not sync_manager or not sync_manager.conflict_scheduler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        if sync_manager.conflict_scheduler.running:
            return jsonify({
                'success': False,
                'error': '调度器已在运行中'
            }), 400
        
        sync_manager.conflict_scheduler.start()
        
        return jsonify({
            'success': True,
            'message': '自动冲突检测调度器已启动'
        })
        
    except Exception as e:
        logger.error(f"启动调度器失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/scheduler/stop', methods=['POST'])
@role_required('admin')
def stop_scheduler():
    """停止自动冲突检测调度器"""
    try:
        if not sync_manager or not sync_manager.conflict_scheduler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        if not sync_manager.conflict_scheduler.running:
            return jsonify({
                'success': False,
                'error': '调度器未在运行'
            }), 400
        
        sync_manager.conflict_scheduler.stop()
        
        return jsonify({
            'success': True,
            'message': '自动冲突检测调度器已停止'
        })
        
    except Exception as e:
        logger.error(f"停止调度器失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/scheduler/status', methods=['GET'])
@role_required('admin')
def get_scheduler_status():
    """获取调度器状态"""
    try:
        if not sync_manager or not sync_manager.conflict_scheduler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        status = {
            'running': sync_manager.conflict_scheduler.running,
            'check_interval': sync_manager.conflict_scheduler.check_interval,
            'check_interval_minutes': sync_manager.conflict_scheduler.check_interval / 60
        }
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"获取调度器状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/manual-sync', methods=['POST'])
@role_required('admin')
def manual_sync():
    """手动触发一次冲突检测和同步"""
    try:
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'success': False,
                'error': '同步管理器未初始化'
            }), 500
        
        data = request.get_json()
        # 使用指定的策略，如果没有指定则使用保存的默认策略
        default_strategy = getattr(sync_manager.conflict_handler, 'default_strategy', 'timestamp_priority')
        strategy = data.get('strategy', default_strategy) if data else default_strategy
        
        # 验证策略
        valid_strategies = ['timestamp_priority', 'primary_priority', 'mysql_priority', 'sqlserver_priority']
        if strategy not in valid_strategies:
            return jsonify({
                'success': False,
                'error': f'无效的同步策略: {strategy}'
            }), 400
        
        # 批量检查冲突
        batch_results = sync_manager.conflict_handler.batch_conflict_check()
        
        # 解决冲突
        resolution_results = {}
        total_conflicts = 0
        resolved_conflicts = 0
        
        for table_name, table_result in batch_results.items():
            if 'conflicts' in table_result and table_result['conflicts']:
                table_resolutions = []
                for conflict_info in table_result['conflicts']:
                    total_conflicts += 1
                    record_id = conflict_info['record_id']
                    
                    # 使用指定策略解决
                    resolution = sync_manager.conflict_handler.resolve_conflicts(
                        table_name, record_id, strategy
                    )
                    
                    if resolution.get('resolved'):
                        resolved_conflicts += 1
                    
                    table_resolutions.append(resolution)
                
                resolution_results[table_name] = table_resolutions
        
        # 发送手动同步邮件通知（无论是否有冲突都发送）
        try:
            if total_conflicts > 0:
                # 有冲突时发送冲突通知
                sync_manager.conflict_handler.send_batch_conflict_notification(
                    batch_results, strategy, sync_type='manual',
                    resolved_count=resolved_conflicts
                )
                logger.info(f"手动同步邮件通知已发送: {total_conflicts}个冲突")
            else:
                # 没有冲突时发送无冲突通知
                from email_config import email_notifier
                subject = "【数据库同步通知】手动同步完成 - 无冲突"
                content = f"""
📊 手动同步完成

同步时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
同步策略: {strategy}
检查结果: 未发现数据冲突
状态: ✅ 所有数据库数据一致

系统已完成手动同步检查，所有数据库之间的数据保持一致。
"""
                email_notifier.send_email(subject, content)
                logger.info("手动同步无冲突通知邮件已发送")
        except Exception as e:
            logger.error(f"发送手动同步邮件通知失败: {e}")
        
        return jsonify({
            'success': True,
            'message': f'手动同步完成，共发现 {total_conflicts} 个冲突，成功解决 {resolved_conflicts} 个',
            'total_conflicts': total_conflicts,
            'resolved_conflicts': resolved_conflicts,
            'strategy': strategy,
            'results': resolution_results
        })
        
    except Exception as e:
        logger.error(f"手动同步失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/email/status', methods=['GET'])
@role_required('admin')
def get_email_status():
    """获取邮件通知配置状态"""
    try:
        return jsonify({
            'success': True,
            'config': {
                'enabled': EMAIL_CONFIG.get('enabled', True),
                'to_email': EMAIL_CONFIG.get('to_email', ''),
                'from_email': EMAIL_CONFIG.get('from_email', '')
            }
        })
    except Exception as e:
        logger.error(f"获取邮件配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@sync_config_bp.route('/admin/sync-config/email/toggle', methods=['POST'])
@role_required('admin')
def toggle_email_notification():
    """启用/禁用邮件通知"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        EMAIL_CONFIG['enabled'] = enabled
        email_notifier.enabled = enabled
        
        status_text = '启用' if enabled else '禁用'
        logger.info(f"邮件通知已{status_text}")
        
        return jsonify({
            'success': True,
            'message': f'邮件通知已{status_text}',
            'enabled': enabled
        })
    except Exception as e:
        logger.error(f"切换邮件通知失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
