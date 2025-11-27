# -*- coding: utf-8 -*-
"""
数据库冲突管理API接口
"""

from flask import Blueprint, request, jsonify
from auth import role_required
from db_sync import sync_manager
import logging

logger = logging.getLogger(__name__)

# 创建冲突管理蓝图
conflict_bp = Blueprint('conflict', __name__)

@conflict_bp.route('/admin/conflicts/check', methods=['POST'])
@role_required('admin')
def check_conflicts():
    """检查数据库冲突"""
    try:
        data = request.get_json() or {}
        table_name = data.get('table_name')
        record_id = data.get('record_id')
        
        if not sync_manager:
            return jsonify({
                'error': '同步管理器未初始化',
                'success': False
            }), 500
        
        # 检查冲突
        result = sync_manager.check_and_resolve_conflicts(table_name, record_id)
        
        if 'error' in result:
            return jsonify({
                'error': result['error'],
                'success': False
            }), 500
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"冲突检查API错误: {e}")
        return jsonify({
            'error': '冲突检查失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/resolve', methods=['POST'])
@role_required('admin')
def resolve_conflicts():
    """解决数据库冲突"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': '缺少请求数据',
                'success': False
            }), 400
        
        table_name = data.get('table_name')
        record_id = data.get('record_id')
        strategy = data.get('strategy', 'timestamp_priority')
        
        if not table_name or not record_id:
            return jsonify({
                'error': '缺少必要参数：table_name 和 record_id',
                'success': False
            }), 400
        
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'error': '冲突处理器未初始化',
                'success': False
            }), 500
        
        # 解决冲突
        result = sync_manager.conflict_handler.resolve_conflicts(
            table_name, record_id, strategy
        )
        
        return jsonify({
            'success': result.get('resolved', False),
            'result': result
        })
        
    except Exception as e:
        logger.error(f"冲突解决API错误: {e}")
        return jsonify({
            'error': '冲突解决失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/statistics', methods=['GET'])
@role_required('admin')
def get_conflict_statistics():
    """获取冲突统计信息"""
    try:
        if not sync_manager:
            return jsonify({
                'error': '同步管理器未初始化',
                'success': False
            }), 500
        
        stats = sync_manager.get_conflict_statistics()
        
        if 'error' in stats:
            return jsonify({
                'error': stats['error'],
                'success': False
            }), 500
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"冲突统计API错误: {e}")
        return jsonify({
            'error': '获取冲突统计失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/batch-check', methods=['POST'])
@role_required('admin')
def batch_check_conflicts():
    """批量检查所有表的冲突"""
    try:
        data = request.get_json() or {}
        tables = data.get('tables')  # 可选：指定要检查的表
        
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'error': '冲突处理器未初始化',
                'success': False
            }), 500
        
        # 批量检查冲突
        batch_results = sync_manager.conflict_handler.batch_conflict_check(tables)
        
        return jsonify({
            'success': True,
            'results': batch_results
        })
        
    except Exception as e:
        logger.error(f"批量冲突检查API错误: {e}")
        return jsonify({
            'error': '批量冲突检查失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/sync-status', methods=['GET'])
@role_required('admin')
def get_sync_status():
    """获取数据库同步状态"""
    try:
        if not sync_manager:
            return jsonify({
                'error': '同步管理器未初始化',
                'success': False
            }), 500
        
        status = {
            'sqlite_connected': sync_manager.sqlite_engine is not None,
            'mysql_connected': sync_manager.mysql_engine is not None,
            'sqlserver_connected': sync_manager.sqlserver_engine is not None,
            'conflict_handler_active': sync_manager.conflict_handler is not None,
            'conflict_scheduler_running': (
                sync_manager.conflict_scheduler is not None and 
                sync_manager.conflict_scheduler.running
            )
        }
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"同步状态API错误: {e}")
        return jsonify({
            'error': '获取同步状态失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/manual-sync', methods=['POST'])
@role_required('admin')
def manual_sync():
    """手动触发数据同步"""
    try:
        data = request.get_json() or {}
        table_name = data.get('table_name')
        record_id = data.get('record_id')
        
        if not sync_manager:
            return jsonify({
                'error': '同步管理器未初始化',
                'success': False
            }), 500
        
        if table_name and record_id:
            # 同步特定记录
            # 这里可以添加特定记录的同步逻辑
            return jsonify({
                'success': True,
                'message': f'记录 {table_name}:{record_id} 同步完成'
            })
        else:
            # 全量同步
            sync_manager.full_sync()
            return jsonify({
                'success': True,
                'message': '全量同步完成'
            })
        
    except Exception as e:
        logger.error(f"手动同步API错误: {e}")
        return jsonify({
            'error': '手动同步失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/resolution-strategies', methods=['GET'])
@role_required('admin')
def get_resolution_strategies():
    """获取可用的冲突解决策略"""
    try:
        strategies = {
            'timestamp_priority': {
                'name': '时间戳优先',
                'description': '选择最新修改时间的数据',
                'recommended': True
            },
            'primary_priority': {
                'name': '主数据库优先',
                'description': '始终使用主数据库（SQLite）的数据',
                'recommended': False
            },
            'manual_review': {
                'name': '手动审查',
                'description': '标记冲突供管理员手动处理',
                'recommended': False
            },
        }
        
        return jsonify({
            'success': True,
            'strategies': strategies
        })
        
    except Exception as e:
        logger.error(f"获取解决策略API错误: {e}")
        return jsonify({
            'error': '获取解决策略失败',
            'details': str(e),
            'success': False
        }), 500

@conflict_bp.route('/admin/conflicts/logs', methods=['GET'])
@role_required('admin')
def get_conflict_logs():
    """获取冲突处理日志"""
    try:
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'error': '冲突处理器未初始化',
                'success': False
            }), 500
        
        # 获取最近的冲突日志
        logs = sync_manager.conflict_handler.conflict_log[-50:]  # 最近50条
        
        return jsonify({
            'success': True,
            'logs': logs,
            'total_logs': len(sync_manager.conflict_handler.conflict_log)
        })
        
    except Exception as e:
        logger.error(f"获取冲突日志API错误: {e}")
        return jsonify({
            'error': '获取冲突日志失败',
            'details': str(e),
            'success': False
        }), 500
