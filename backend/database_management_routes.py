# -*- coding: utf-8 -*-
"""
数据库管理API接口
"""

from flask import Blueprint, request, jsonify
from auth import role_required
from models import db, Admin, Patient, Doctor, Department, Registration, Title
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 创建数据库管理蓝图
db_management_bp = Blueprint('db_management', __name__)

def _is_same_date_value(value1, value2):
    """判断两个值是否表示同一个日期"""
    if value1 is None or value2 is None:
        return value1 == value2
    
    try:
        from dateutil import parser
        
        # 如果是字符串，尝试解析
        if isinstance(value1, str):
            date1 = parser.parse(value1).date()
        elif hasattr(value1, 'date'):
            date1 = value1.date() if callable(value1.date) else value1
        else:
            date1 = value1
        
        if isinstance(value2, str):
            date2 = parser.parse(value2).date()
        elif hasattr(value2, 'date'):
            date2 = value2.date() if callable(value2.date) else value2
        else:
            date2 = value2
        
        # 比较日期部分
        return date1 == date2
        
    except:
        # 如果解析失败，按字符串比较
        return str(value1) == str(value2)

# 数据库引擎配置
def get_database_engines(app):
    """获取所有数据库引擎"""
    engines = {
        'sqlite': db.engine
    }
    
    # MySQL配置
    mysql_uri = app.config.get('MYSQL_URI')
    if mysql_uri:
        try:
            engines['mysql'] = create_engine(mysql_uri, pool_pre_ping=True)
        except Exception as e:
            logger.error(f"MySQL连接失败: {e}")
    
    # SQL Server配置
    sqlserver_uri = app.config.get('SQLSERVER_URI')
    if sqlserver_uri:
        try:
            engines['sqlserver'] = create_engine(sqlserver_uri, pool_pre_ping=True)
        except Exception as e:
            logger.error(f"SQL Server连接失败: {e}")
    
    return engines

@db_management_bp.route('/admin/database/tables', methods=['GET'])
@role_required('admin')
def get_all_tables():
    """获取所有表名"""
    try:
        from flask import current_app
        engines = get_database_engines(current_app)
        
        result = {}
        
        for db_name, engine in engines.items():
            try:
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                result[db_name] = tables
            except Exception as e:
                logger.error(f"获取{db_name}表名失败: {e}")
                result[db_name] = []
        
        return jsonify({
            'success': True,
            'tables': result
        })
        
    except Exception as e:
        logger.error(f"获取表名失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/table-data', methods=['POST'])
@role_required('admin')
def get_table_data():
    """获取指定表的数据"""
    try:
        data = request.get_json()
        db_name = data.get('database')  # sqlite, mysql, sqlserver
        table_name = data.get('table')
        page = data.get('page', 1)
        page_size = data.get('page_size', 20)
        
        if not db_name or not table_name:
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        from flask import current_app
        engines = get_database_engines(current_app)
        
        if db_name not in engines:
            return jsonify({
                'success': False,
                'error': f'数据库 {db_name} 不存在'
            }), 400
        
        engine = engines[db_name]
        
        # 获取表结构
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        column_names = [col['name'] for col in columns]
        
        # 获取主键
        pk_constraint = inspector.get_pk_constraint(table_name)
        primary_keys = pk_constraint.get('constrained_columns', [])
        
        # 分页查询数据
        offset = (page - 1) * page_size
        
        with engine.connect() as conn:
            # 获取总数
            count_query = text(f"SELECT COUNT(*) FROM {table_name}")
            total = conn.execute(count_query).scalar()
            
            # 获取数据 - 根据数据库类型使用不同的分页语法
            if db_name == 'sqlserver':
                # SQL Server 使用 OFFSET...FETCH 语法
                # 需要ORDER BY子句，使用主键排序
                pk_field = primary_keys[0] if primary_keys else column_names[0]
                data_query = text(f"""
                    SELECT * FROM {table_name} 
                    ORDER BY {pk_field}
                    OFFSET :offset ROWS 
                    FETCH NEXT :limit ROWS ONLY
                """)
            elif db_name == 'mysql':
                # MySQL 使用 LIMIT...OFFSET 语法
                data_query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
            else:
                # SQLite 使用 LIMIT...OFFSET 语法
                data_query = text(f"SELECT * FROM {table_name} LIMIT :limit OFFSET :offset")
            
            result = conn.execute(data_query, {'limit': page_size, 'offset': offset})
            
            rows = []
            for row in result:
                row_dict = dict(row._mapping)
                # 转换日期时间为字符串
                for key, value in row_dict.items():
                    if isinstance(value, datetime):
                        row_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                rows.append(row_dict)
        
        return jsonify({
            'success': True,
            'data': {
                'columns': column_names,
                'primary_keys': primary_keys,
                'rows': rows,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size
            }
        })
        
    except Exception as e:
        logger.error(f"获取表数据失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/update-record', methods=['POST'])
@role_required('admin')
def update_record():
    """更新记录"""
    try:
        data = request.get_json()
        db_name = data.get('database')
        table_name = data.get('table')
        primary_key = data.get('primary_key')  # {column: value}
        updates = data.get('updates')  # {column: new_value}
        
        if not all([db_name, table_name, primary_key, updates]):
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        from flask import current_app
        engines = get_database_engines(current_app)
        
        if db_name not in engines:
            return jsonify({
                'success': False,
                'error': f'数据库 {db_name} 不存在'
            }), 400
        
        engine = engines[db_name]
        
        with engine.connect() as conn:
            with conn.begin():
                # 首先检查记录是否存在
                where_clause = ' AND '.join([f"{col} = :pk_{col}" for col in primary_key.keys()])
                check_query = text(f"SELECT COUNT(*) as count FROM {table_name} WHERE {where_clause}")
                
                check_params = {}
                for col, val in primary_key.items():
                    check_params[f'pk_{col}'] = val
                
                result = conn.execute(check_query, check_params)
                record_exists = result.fetchone()[0] > 0
                
                if record_exists:
                    # 记录存在，执行更新
                    set_clause = ', '.join([f"{col} = :{col}" for col in updates.keys()])
                    update_query = text(f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}")
                    
                    # 准备更新参数，处理数据类型
                    params = {}
                    for col, val in updates.items():
                        if val == '' or val is None:
                            params[col] = None
                        elif isinstance(val, str) and val.isdigit():
                            params[col] = int(val)
                        else:
                            params[col] = val
                    
                    for col, val in primary_key.items():
                        params[f'pk_{col}'] = val
                    
                    conn.execute(update_query, params)
                    message = '记录更新成功'
                else:
                    # 记录不存在，执行插入
                    all_data = primary_key.copy()
                    all_data.update(updates)
                    
                    # 处理数据类型转换和特殊字段
                    processed_data = {}
                    for col, val in all_data.items():
                        # 跳过自增主键字段
                        if col.endswith('_id') and col in primary_key:
                            # 对于SQL Server，跳过自增ID字段
                            if db_name == 'sqlserver':
                                continue
                        
                        if val == '' or val is None:
                            processed_data[col] = None
                        elif isinstance(val, str) and val.isdigit():
                            processed_data[col] = int(val)
                        else:
                            processed_data[col] = val
                    
                    # 为SQL Server添加必需的默认值
                    if db_name == 'sqlserver':
                        if table_name == 'patient' and 'password_hash' not in processed_data:
                            processed_data['password_hash'] = 'default_hash'
                        elif table_name == 'doctor' and 'password_hash' not in processed_data:
                            processed_data['password_hash'] = 'default_hash'
                        elif table_name == 'admin' and 'password_hash' not in processed_data:
                            processed_data['password_hash'] = 'default_hash'
                    
                    if processed_data:  # 确保有数据要插入
                        columns = ', '.join(processed_data.keys())
                        placeholders = ', '.join([f":{col}" for col in processed_data.keys()])
                        insert_query = text(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})")
                        
                        conn.execute(insert_query, processed_data)
                        message = '记录插入成功（原记录不存在）'
                    else:
                        message = '无法插入记录：没有有效数据'
        
        return jsonify({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"更新记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/delete-record', methods=['POST'])
@role_required('admin')
def delete_record():
    """删除记录"""
    try:
        data = request.get_json()
        db_name = data.get('database')
        table_name = data.get('table')
        primary_key = data.get('primary_key')
        
        if not all([db_name, table_name, primary_key]):
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        from flask import current_app
        engines = get_database_engines(current_app)
        
        if db_name not in engines:
            return jsonify({
                'success': False,
                'error': f'数据库 {db_name} 不存在'
            }), 400
        
        engine = engines[db_name]
        
        # 构建删除语句
        where_clause = ' AND '.join([f"{col} = :{col}" for col in primary_key.keys()])
        query = text(f"DELETE FROM {table_name} WHERE {where_clause}")
        
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(query, primary_key)
        
        return jsonify({
            'success': True,
            'message': '记录删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/compare-records', methods=['POST'])
@role_required('admin')
def compare_records():
    """比较三个数据库中的记录"""
    try:
        data = request.get_json()
        table_name = data.get('table')
        record_id = data.get('record_id')
        
        if not table_name:
            return jsonify({
                'success': False,
                'error': '缺少表名'
            }), 400
        
        from flask import current_app
        engines = get_database_engines(current_app)
        
        # 获取主键字段名
        pk_mapping = {
            'admin': 'admin_id',
            'patient': 'patient_id',
            'doctor': 'doctor_id',
            'department': 'dept_id',
            'registration': 'reg_id',
            'title': 'title_id'
        }
        pk_field = pk_mapping.get(table_name, 'id')
        
        result = {}
        conflicts = []
        
        # 从每个数据库获取数据
        for db_name, engine in engines.items():
            try:
                with engine.connect() as conn:
                    if record_id:
                        # 获取特定记录
                        query = text(f"SELECT * FROM {table_name} WHERE {pk_field} = :id")
                        row = conn.execute(query, {'id': record_id}).fetchone()
                    else:
                        # 获取所有记录
                        query = text(f"SELECT * FROM {table_name}")
                        rows = conn.execute(query).fetchall()
                        result[db_name] = [dict(r._mapping) for r in rows]
                        continue
                    
                    if row:
                        row_dict = dict(row._mapping)
                        # 转换日期时间
                        for key, value in row_dict.items():
                            if isinstance(value, datetime):
                                row_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                        result[db_name] = row_dict
                    else:
                        result[db_name] = None
                        
            except Exception as e:
                logger.error(f"从{db_name}获取数据失败: {e}")
                result[db_name] = {'error': str(e)}
        
        # 检测冲突
        if record_id and len(result) > 1:
            databases = list(result.keys())
            
            # 检查缺失记录
            existing_dbs = []
            missing_dbs = []
            
            for db_name in databases:
                data = result[db_name]
                if data is None:
                    missing_dbs.append(db_name)
                elif isinstance(data, dict) and 'error' not in data:
                    existing_dbs.append(db_name)
            
            # 如果有数据库缺失记录，添加冲突
            if missing_dbs and existing_dbs:
                for missing_db in missing_dbs:
                    conflicts.append({
                        'type': 'missing_record',
                        'database': missing_db,
                        'message': f'记录在 {missing_db} 中缺失',
                        'existing_databases': existing_dbs
                    })
            
            # 比较存在记录的数据库之间的差异
            if len(existing_dbs) > 1:
                for i in range(len(existing_dbs)):
                    for j in range(i + 1, len(existing_dbs)):
                        db1, db2 = existing_dbs[i], existing_dbs[j]
                        data1, data2 = result[db1], result[db2]
                        
                        # 比较字段
                        for key in data1.keys():
                            if key in ['created_at', 'updated_at']:
                                continue
                            if key in data2 and data1[key] != data2[key]:
                                # 特殊处理日期比较
                                if _is_same_date_value(data1[key], data2[key]):
                                    continue
                                    
                                conflicts.append({
                                    'type': 'data_mismatch',
                                    'field': key,
                                    'databases': [db1, db2],
                                    'values': {
                                        db1: data1[key],
                                        db2: data2[key]
                                    }
                                })
        
        return jsonify({
            'success': True,
            'data': result,
            'conflicts': conflicts,
            'has_conflicts': len(conflicts) > 0
        })
        
    except Exception as e:
        logger.error(f"比较记录失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/find-all-conflicts', methods=['POST'])
@role_required('admin')
def find_all_conflicts():
    """查找所有冲突"""
    try:
        data = request.get_json() or {}
        table_name = data.get('table')
        
        from flask import current_app
        from db_sync import sync_manager
        
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'success': False,
                'error': '冲突处理器未初始化'
            }), 500
        
        # 批量检查冲突
        if table_name:
            tables = [table_name]
        else:
            tables = None
        
        batch_results = sync_manager.conflict_handler.batch_conflict_check(tables)
        
        # 整理冲突信息
        all_conflicts = []
        
        for table, result in batch_results.items():
            if 'conflicts' in result:
                for conflict_info in result['conflicts']:
                    all_conflicts.append({
                        'table': table,
                        'record_id': conflict_info['record_id'],
                        'conflicts': conflict_info['conflicts']
                    })
        
        return jsonify({
            'success': True,
            'conflicts': all_conflicts,
            'total': len(all_conflicts)
        })
        
    except Exception as e:
        logger.error(f"查找冲突失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@db_management_bp.route('/admin/database/resolve-conflict', methods=['POST'])
@role_required('admin')
def resolve_conflict():
    """解决冲突"""
    try:
        data = request.get_json()
        table_name = data.get('table')
        record_id = data.get('record_id')
        strategy = data.get('strategy', 'timestamp_priority')
        
        if not table_name or not record_id:
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        from db_sync import sync_manager
        
        if not sync_manager or not sync_manager.conflict_handler:
            return jsonify({
                'success': False,
                'error': '冲突处理器未初始化'
            }), 500
        
        # 解决冲突
        result = sync_manager.conflict_handler.resolve_conflicts(
            table_name, record_id, strategy
        )
        
        # 发送邮件通知
        if result.get('resolved', False):
            try:
                from email_config import email_notifier
                import datetime
                
                subject = "【数据库同步通知】冲突解决完成"
                content = f"""
📊 冲突解决通知

解决时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
表名: {table_name}
记录ID: {record_id}
解决策略: {strategy}
状态: ✅ 冲突已解决

管理员手动解决了数据库冲突，数据已同步完成。
"""
                email_notifier.send_email(subject, content)
                logger.info(f"冲突解决邮件通知已发送: {table_name}#{record_id}")
            except Exception as e:
                logger.error(f"发送冲突解决邮件通知失败: {e}")
        
        return jsonify({
            'success': result.get('resolved', False),
            'result': result
        })
        
    except Exception as e:
        logger.error(f"解决冲突失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
