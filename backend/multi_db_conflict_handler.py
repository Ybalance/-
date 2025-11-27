# -*- coding: utf-8 -*-
"""
多数据库同步冲突处理机制
"""

import logging
import json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import hashlib
import threading
from collections import defaultdict
from email_config import email_notifier

logger = logging.getLogger(__name__)

class MultiDBConflictHandler:
    """多数据库冲突处理器"""
    
    def __init__(self, primary_engine, secondary_engines):
        self.primary_engine = primary_engine
        self.secondary_engines = secondary_engines
        self.conflict_log = []
        self.resolution_strategies = {
            'timestamp_priority': self._resolve_by_timestamp,
            'primary_priority': self._resolve_by_primary,
            'mysql_priority': self._resolve_by_mysql,
            'sqlserver_priority': self._resolve_by_sqlserver,
            'manual_review': self._mark_for_manual_review,
            'delete_all': self._delete_all_records
        }
        self.lock = threading.RLock()
    
    def detect_conflicts(self, table_name, record_id):
        """检测多数据库间的数据冲突"""
        try:
            # 获取所有数据库的记录
            all_records = {}
            
            # 获取主数据库记录
            primary_record = self._get_record(self.primary_engine, table_name, record_id)
            all_records['sqlite'] = primary_record
            
            # 获取从数据库记录
            for db_name, engine in self.secondary_engines.items():
                secondary_record = self._get_record(engine, table_name, record_id)
                all_records[db_name] = secondary_record
            
            # 检查是否所有数据库都没有记录
            existing_records = {db: record for db, record in all_records.items() if record is not None}
            if not existing_records:
                return {'has_conflict': False, 'reason': 'no_records_found_in_any_database'}
            
            conflicts = []
            
            # 找到有记录的数据库作为参考
            reference_db = list(existing_records.keys())[0]
            reference_record = existing_records[reference_db]
            
            # 检查每个数据库
            for db_name in all_records.keys():
                current_record = all_records[db_name]
                
                if current_record is None:
                    # 记录缺失
                    conflicts.append({
                        'type': 'missing_record',
                        'database': db_name,
                        'details': f'{db_name}数据库中缺少该记录',
                        'reference_data': reference_record
                    })
                elif db_name != reference_db:
                    # 比较记录内容
                    conflict_details = self._compare_records(reference_record, current_record)
                    if conflict_details:
                        conflicts.append({
                            'type': 'data_mismatch',
                            'database': db_name,
                            'details': conflict_details,
                            'reference_data': reference_record,
                            'current_data': current_record
                        })
            
            return {
                'has_conflict': len(conflicts) > 0,
                'conflicts': conflicts,
                'all_records': all_records,
                'reference_record': reference_record,
                'reference_database': reference_db
            }
            
        except Exception as e:
            logger.error(f"冲突检测失败 {table_name}:{record_id}: {e}")
            return {'has_conflict': False, 'error': str(e)}
    
    def resolve_conflicts(self, table_name, record_id, strategy='timestamp_priority'):
        """解决数据库间冲突"""
        with self.lock:
            try:
                # 检测冲突
                conflict_info = self.detect_conflicts(table_name, record_id)
                
                if not conflict_info['has_conflict']:
                    return {'resolved': True, 'message': '无冲突需要解决'}
                
                # 选择解决策略
                resolver = self.resolution_strategies.get(strategy, self._resolve_by_primary)
                
                resolution_results = []
                
                # 如果是删除所有记录策略，直接调用删除方法
                if strategy == 'delete_all':
                    result = self._delete_all_records(
                        table_name, record_id, 'all',
                        conflict_info.get('reference_record'), None
                    )
                    resolution_results.append(result)
                else:
                    # 其他策略按冲突类型处理
                    for conflict in conflict_info['conflicts']:
                        if conflict['type'] == 'missing_record':
                            # 处理缺失记录
                            result = self._handle_missing_record(
                                table_name, record_id, conflict['database'], 
                                conflict['reference_data'], strategy
                            )
                            resolution_results.append(result)
                        
                        elif conflict['type'] == 'data_mismatch':
                            # 处理数据不匹配
                            result = resolver(
                                table_name, record_id, conflict['database'],
                                conflict['reference_data'], conflict['current_data']
                            )
                            resolution_results.append(result)
                
                # 记录冲突解决日志
                self._log_conflict_resolution(table_name, record_id, strategy, resolution_results)
                
                # 检查是否所有冲突都成功解决
                all_resolved = True
                failed_results = []
                for result in resolution_results:
                    action = result.get('action', '')
                    if action in ['failed', 'skipped']:
                        all_resolved = False
                        failed_results.append(result)
                
                # 注意：不在这里发送单个冲突邮件，而是在批量同步完成后统一发送汇总邮件
                # 这样可以避免批量同步时发送大量邮件
                
                return {
                    'resolved': all_resolved,
                    'strategy': strategy,
                    'results': resolution_results,
                    'failed_results': failed_results if not all_resolved else []
                }
                
            except Exception as e:
                logger.error(f"冲突解决失败 {table_name}:{record_id}: {e}")
                return {'resolved': False, 'error': str(e)}
    
    def _get_record(self, engine, table_name, record_id):
        """从指定数据库获取记录"""
        try:
            # 确定主键字段名
            pk_field = self._get_primary_key_field(table_name)
            
            with engine.connect() as conn:
                query = text(f"SELECT * FROM {table_name} WHERE {pk_field} = :record_id")
                result = conn.execute(query, {'record_id': record_id})
                row = result.fetchone()
                
                if row:
                    # 转换为字典
                    return dict(row._mapping)
                return None
                
        except Exception as e:
            logger.error(f"获取记录失败 {table_name}:{record_id} from {engine}: {e}")
            return None
    
    def _get_primary_key_field(self, table_name):
        """获取表的主键字段名"""
        pk_mapping = {
            'admin': 'admin_id',
            'patient': 'patient_id', 
            'doctor': 'doctor_id',
            'department': 'dept_id',
            'registration': 'reg_id',
            'title': 'title_id'
        }
        return pk_mapping.get(table_name, 'id')
    
    def _convert_datetime_for_sqlserver(self, data, table_name):
        """为SQL Server转换日期时间格式"""
        from datetime import datetime
        
        # 定义各表的日期时间字段
        datetime_fields = {
            'registration': ['reg_time', 'created_at', 'updated_at'],
            'patient': ['created_at', 'updated_at'],
            'doctor': ['created_at', 'updated_at'],
            'admin': ['created_at', 'updated_at'],
            'department': ['created_at', 'updated_at'],
            'title': ['created_at', 'updated_at']
        }
        
        fields = datetime_fields.get(table_name, [])
        
        for field in fields:
            if field in data and data[field] is not None:
                value = data[field]
                
                # 如果是字符串，尝试解析
                if isinstance(value, str):
                    try:
                        # 尝试解析各种日期时间格式
                        if '.' in value:
                            # 包含微秒的格式
                            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
                        else:
                            # 不包含微秒的格式
                            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                        
                        # 转换为SQL Server兼容的格式（不包含微秒）
                        data[field] = dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                    except ValueError as e:
                        logger.warning(f"日期时间格式转换失败 {field}={value}: {e}")
                        # 如果转换失败，尝试移除微秒部分
                        if '.' in value:
                            data[field] = value.split('.')[0]
                
                # 如果是datetime对象，转换为字符串
                elif isinstance(value, datetime):
                    data[field] = value.strftime('%Y-%m-%d %H:%M:%S')
    
    def _check_and_handle_dependencies(self, table_name, record_data, target_db):
        """检查并处理表的依赖关系"""
        # 定义表的依赖关系
        dependencies = {
            'doctor': ['title', 'department'],  # doctor依赖title和department
            'registration': ['patient', 'doctor']  # registration依赖patient和doctor
        }
        
        if table_name not in dependencies:
            return True  # 没有依赖关系，可以直接插入
        
        # 检查每个依赖表
        for dep_table in dependencies[table_name]:
            if not self._ensure_dependency_exists(dep_table, record_data, target_db):
                return False
        
        return True
    
    def _ensure_dependency_exists(self, dep_table, record_data, target_db):
        """确保依赖记录存在"""
        try:
            # 根据依赖表确定需要检查的字段和值
            dep_field_mapping = {
                'title': ('title_id', 'title_id'),
                'department': ('dept_id', 'dept_id'),
                'patient': ('patient_id', 'patient_id'),
                'doctor': ('doctor_id', 'doctor_id')
            }
            
            if dep_table not in dep_field_mapping:
                return True
            
            record_field, dep_pk = dep_field_mapping[dep_table]
            
            # 检查记录中是否有依赖字段
            if record_field not in record_data or record_data[record_field] is None:
                return True  # 没有依赖字段，跳过检查
            
            dep_id = record_data[record_field]
            
            # 检查目标数据库中是否存在依赖记录
            target_engine = self.secondary_engines.get(target_db) if target_db != 'sqlite' else self.primary_engine
            if not target_engine:
                return False
            
            existing_record = self._get_record(target_engine, dep_table, dep_id)
            if existing_record:
                return True  # 依赖记录已存在
            
            # 依赖记录不存在，尝试从其他数据库获取并插入
            logger.info(f"依赖记录不存在，尝试创建 {dep_table}:{dep_id} 到 {target_db}")
            
            # 从主数据库或其他数据库获取依赖记录
            source_record = None
            
            # 先尝试从主数据库获取
            if target_db != 'sqlite':
                source_record = self._get_record(self.primary_engine, dep_table, dep_id)
            
            # 如果主数据库没有，尝试从其他从数据库获取
            if not source_record:
                for db_name, engine in self.secondary_engines.items():
                    if db_name != target_db:
                        source_record = self._get_record(engine, dep_table, dep_id)
                        if source_record:
                            break
            
            if not source_record:
                logger.error(f"无法找到依赖记录 {dep_table}:{dep_id}")
                return False
            
            # 递归检查依赖记录的依赖关系
            if not self._check_and_handle_dependencies(dep_table, source_record, target_db):
                logger.error(f"依赖记录的依赖关系检查失败 {dep_table}:{dep_id}")
                return False
            
            # 插入依赖记录
            try:
                if target_db == 'sqlite':
                    self._insert_primary_record(dep_table, source_record, preserve_id=True)
                else:
                    self._insert_secondary_record(target_db, dep_table, source_record, preserve_id=True)
                
                logger.info(f"成功创建依赖记录 {dep_table}:{dep_id} 到 {target_db}")
                return True
                
            except Exception as e:
                logger.error(f"插入依赖记录失败 {dep_table}:{dep_id} 到 {target_db}: {e}")
                return False
                
        except Exception as e:
            logger.error(f"依赖关系检查失败 {dep_table}: {e}")
            return False
    
    def _is_same_date(self, value1, value2):
        """判断两个值是否表示同一个日期"""
        if value1 is None or value2 is None:
            return value1 == value2
        
        try:
            # 尝试将两个值都转换为日期对象
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
    
    def _compare_records(self, primary_record, secondary_record):
        """比较两个记录的差异 - 检查所有重要字段"""
        differences = {}
        
        # 忽略这些可能经常变化的字段
        ignore_fields = {
            'created_at', 'updated_at', 
            'password_hash', 'password', 'passwordhash',  # 密码相关字段的各种写法
            'created_time', 'updated_time', 'modify_time'  # 时间戳字段
        }
        
        # 获取所有字段进行比较
        all_fields = set(primary_record.keys()) | set(secondary_record.keys())
        
        for field in all_fields:
            # 忽略指定字段（不区分大小写）
            if field.lower() in {f.lower() for f in ignore_fields}:
                continue
                
            primary_value = primary_record.get(field)
            secondary_value = secondary_record.get(field)
            
            # 处理None值的比较
            if primary_value is None and secondary_value is None:
                continue
            
            # 处理日期时间字段的特殊比较
            if (field in ['reg_time', 'birth_date', 'birthday'] or 
                field.endswith('_time') or field.endswith('_date') or field.endswith('_birthday')):
                if not self._is_same_date(primary_value, secondary_value):
                    differences[field] = {
                        'primary': primary_value,
                        'secondary': secondary_value
                    }
            else:
                # 普通字段比较
                if primary_value != secondary_value:
                    differences[field] = {
                        'primary': primary_value,
                        'secondary': secondary_value
                    }
        
        return differences if differences else None
    
    def _parse_timestamp(self, timestamp_str):
        """解析时间戳字符串为datetime对象"""
        if not timestamp_str:
            return datetime.min
        
        try:
            # 尝试多种时间戳格式
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%fZ'
            ]
            
            timestamp_str = str(timestamp_str).strip()
            
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except ValueError:
                    continue
            
            # 如果所有格式都失败，返回最小时间
            logger.warning(f"无法解析时间戳: {timestamp_str}")
            return datetime.min
            
        except Exception as e:
            logger.warning(f"解析时间戳失败: {timestamp_str}, 错误: {e}")
            return datetime.min
    
    def _resolve_by_timestamp(self, table_name, record_id, db_name, primary_data, secondary_data):
        """基于时间戳解决冲突（选择最新的）- 更新所有数据库"""
        try:
            primary_time = self._parse_timestamp(primary_data.get('updated_at'))
            secondary_time = self._parse_timestamp(secondary_data.get('updated_at'))
            
            updated_databases = []
            
            if primary_time >= secondary_time:
                # 使用主数据库数据更新所有从数据库
                newest_data = primary_data
                source = 'sqlite'
            else:
                # 使用从数据库数据更新所有数据库
                newest_data = secondary_data
                source = db_name
            
            # 更新所有数据库为最新数据
            # 更新SQLite
            if source != 'sqlite':
                try:
                    self._update_primary_record(table_name, record_id, newest_data)
                    updated_databases.append('sqlite')
                except Exception as e:
                    logger.warning(f"更新SQLite失败: {e}")
            
            # 更新MySQL
            if 'mysql' in self.secondary_engines and source != 'mysql':
                try:
                    self._update_secondary_record('mysql', table_name, record_id, newest_data)
                    updated_databases.append('mysql')
                except Exception as e:
                    logger.warning(f"更新MySQL失败: {e}")
            
            # 更新SQL Server
            if 'sqlserver' in self.secondary_engines and source != 'sqlserver':
                try:
                    self._update_secondary_record('sqlserver', table_name, record_id, newest_data)
                    updated_databases.append('sqlserver')
                except Exception as e:
                    logger.warning(f"更新SQL Server失败: {e}")
            
            return {
                'action': 'updated_all_with_newest',
                'reason': 'timestamp_priority',
                'source': source,
                'updated_databases': updated_databases,
                'database': db_name
            }
                
        except Exception as e:
            logger.error(f"时间戳解决冲突失败: {e}")
            return self._resolve_by_primary(table_name, record_id, db_name, primary_data, secondary_data)
    
    def _resolve_by_primary(self, table_name, record_id, db_name, primary_data, secondary_data):
        """优先使用主数据库数据解决冲突 - 更新所有从数据库"""
        try:
            updated_databases = []
            
            # 使用SQLite数据更新所有从数据库
            # 更新MySQL
            if 'mysql' in self.secondary_engines:
                try:
                    self._update_secondary_record('mysql', table_name, record_id, primary_data)
                    updated_databases.append('mysql')
                except Exception as e:
                    logger.warning(f"更新MySQL失败: {e}")
            
            # 更新SQL Server
            if 'sqlserver' in self.secondary_engines:
                try:
                    self._update_secondary_record('sqlserver', table_name, record_id, primary_data)
                    updated_databases.append('sqlserver')
                except Exception as e:
                    logger.warning(f"更新SQL Server失败: {e}")
            
            return {
                'action': 'updated_all_with_primary',
                'reason': 'primary_priority',
                'updated_databases': updated_databases,
                'database': db_name
            }
        except Exception as e:
            logger.error(f"主数据库优先解决冲突失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _merge_field_values(self, table_name, record_id, db_name, primary_data, secondary_data):
        """合并字段值解决冲突"""
        try:
            merged_data = primary_data.copy()
            
            # 合并策略：非空值优先
            for key, secondary_value in secondary_data.items():
                if secondary_value is not None and (key not in merged_data or merged_data[key] is None):
                    merged_data[key] = secondary_value
            
            # 更新两个数据库
            self._update_primary_record(table_name, record_id, merged_data)
            self._update_secondary_record(db_name, table_name, record_id, merged_data)
            
            return {
                'action': 'merged_both',
                'reason': 'field_merge',
                'database': db_name,
                'merged_fields': list(merged_data.keys())
            }
            
        except Exception as e:
            logger.error(f"字段合并解决冲突失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _resolve_by_mysql(self, table_name, record_id, db_name, reference_data, current_data):
        """优先使用MySQL数据解决冲突 - 更新所有其他数据库"""
        try:
            # 获取MySQL数据
            mysql_engine = self.secondary_engines.get('mysql')
            if not mysql_engine:
                return {'action': 'failed', 'error': 'MySQL数据库未配置', 'database': db_name}
            
            mysql_record = self._get_record(mysql_engine, table_name, record_id)
            if not mysql_record:
                return {'action': 'failed', 'error': 'MySQL中未找到记录', 'database': db_name}
            
            # 使用MySQL数据更新所有其他数据库
            updated_databases = []
            
            # 更新SQLite
            try:
                self._update_primary_record(table_name, record_id, mysql_record)
                updated_databases.append('sqlite')
            except Exception as e:
                logger.warning(f"更新SQLite失败: {e}")
            
            # 更新SQL Server
            if 'sqlserver' in self.secondary_engines:
                try:
                    self._update_secondary_record('sqlserver', table_name, record_id, mysql_record)
                    updated_databases.append('sqlserver')
                except Exception as e:
                    logger.warning(f"更新SQL Server失败: {e}")
            
            return {
                'action': 'updated_all_with_mysql',
                'reason': 'mysql_priority',
                'updated_databases': updated_databases,
                'database': db_name
            }
        except Exception as e:
            logger.error(f"MySQL优先解决冲突失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _resolve_by_sqlserver(self, table_name, record_id, db_name, reference_data, current_data):
        """优先使用SQL Server数据解决冲突 - 更新所有其他数据库"""
        try:
            # 获取SQL Server数据
            sqlserver_engine = self.secondary_engines.get('sqlserver')
            if not sqlserver_engine:
                return {'action': 'failed', 'error': 'SQL Server数据库未配置', 'database': db_name}
            
            sqlserver_record = self._get_record(sqlserver_engine, table_name, record_id)
            if not sqlserver_record:
                return {'action': 'failed', 'error': 'SQL Server中未找到记录', 'database': db_name}
            
            # 使用SQL Server数据更新所有其他数据库
            updated_databases = []
            
            # 更新SQLite
            try:
                self._update_primary_record(table_name, record_id, sqlserver_record)
                updated_databases.append('sqlite')
            except Exception as e:
                logger.warning(f"更新SQLite失败: {e}")
            
            # 更新MySQL
            if 'mysql' in self.secondary_engines:
                try:
                    self._update_secondary_record('mysql', table_name, record_id, sqlserver_record)
                    updated_databases.append('mysql')
                except Exception as e:
                    logger.warning(f"更新MySQL失败: {e}")
            
            return {
                'action': 'updated_all_with_sqlserver',
                'reason': 'sqlserver_priority',
                'updated_databases': updated_databases,
                'database': db_name
            }
        except Exception as e:
            logger.error(f"SQL Server优先解决冲突失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _delete_all_records(self, table_name, record_id, db_name, reference_data, current_data):
        """删除所有数据库中的记录"""
        try:
            deleted_databases = []
            failed_databases = []
            
            # 删除主数据库中的记录
            try:
                self._delete_primary_record(table_name, record_id)
                deleted_databases.append('sqlite')
                logger.info(f"已删除SQLite中的记录: {table_name}:{record_id}")
            except Exception as e:
                failed_databases.append(f'sqlite: {str(e)}')
                logger.warning(f"删除SQLite记录失败: {e}")
            
            # 删除从数据库中的记录
            for db_name_target, engine in self.secondary_engines.items():
                try:
                    self._delete_secondary_record(db_name_target, table_name, record_id)
                    deleted_databases.append(db_name_target)
                    logger.info(f"已删除{db_name_target}中的记录: {table_name}:{record_id}")
                except Exception as e:
                    failed_databases.append(f'{db_name_target}: {str(e)}')
                    logger.warning(f"删除{db_name_target}记录失败: {e}")
            
            return {
                'action': 'deleted_all',
                'reason': 'delete_all_strategy',
                'database': db_name,
                'deleted_databases': deleted_databases,
                'failed_databases': failed_databases,
                'success_count': len(deleted_databases),
                'total_count': len(self.secondary_engines) + 1  # +1 for primary
            }
            
        except Exception as e:
            logger.error(f"删除所有记录失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _mark_for_manual_review(self, table_name, record_id, db_name, primary_data, secondary_data):
        """标记为需要手动审查"""
        conflict_record = {
            'timestamp': datetime.now().isoformat(),
            'table_name': table_name,
            'record_id': record_id,
            'database': db_name,
            'primary_data': primary_data,
            'secondary_data': secondary_data,
            'status': 'pending_review'
        }
        
        self.conflict_log.append(conflict_record)
        
        return {
            'action': 'marked_for_review',
            'reason': 'manual_review_required',
            'database': db_name,
            'conflict_id': len(self.conflict_log) - 1
        }
    
    def _handle_missing_record(self, table_name, record_id, db_name, reference_record, strategy='primary_priority'):
        """处理缺失记录"""
        try:
            # 检查并处理依赖关系
            if not self._check_and_handle_dependencies(table_name, reference_record, db_name):
                logger.warning(f"依赖关系处理失败，跳过插入 {table_name}:{record_id} 到 {db_name}")
                return {'action': 'skipped', 'reason': 'dependency_failed', 'database': db_name}
            
            # 根据策略选择数据源
            source_record = None
            
            if strategy == 'mysql_priority':
                mysql_engine = self.secondary_engines.get('mysql')
                if mysql_engine:
                    source_record = self._get_record(mysql_engine, table_name, record_id)
            elif strategy == 'sqlserver_priority':
                sqlserver_engine = self.secondary_engines.get('sqlserver')
                if sqlserver_engine:
                    source_record = self._get_record(sqlserver_engine, table_name, record_id)
            elif strategy == 'timestamp_priority':
                # 找到最新的记录
                source_record = self._get_latest_record(table_name, record_id)
            elif strategy == 'primary_priority':
                # 主数据库优先，但如果主数据库没有记录，使用参考记录
                primary_record = self._get_record(self.primary_engine, table_name, record_id)
                source_record = primary_record if primary_record else reference_record
            
            # 如果策略指定的数据库没有记录，使用参考记录
            if not source_record:
                source_record = reference_record
            
            # 最后的兜底：如果还是没有数据源，尝试从任何有数据的数据库获取
            if not source_record:
                # 尝试从主数据库获取
                source_record = self._get_record(self.primary_engine, table_name, record_id)
                
                # 如果主数据库没有，尝试从从数据库获取
                if not source_record:
                    for db_name_src, engine in self.secondary_engines.items():
                        try:
                            source_record = self._get_record(engine, table_name, record_id)
                            if source_record:
                                logger.info(f"使用{db_name_src}数据库的记录作为数据源")
                                break
                        except Exception as e:
                            logger.warning(f"从{db_name_src}获取记录失败: {e}")
            
            if not source_record:
                return {'action': 'failed', 'error': '没有可用的数据源', 'database': db_name}
            
            # 插入记录到目标数据库
            try:
                # 根据策略决定是否保留原ID
                preserve_id = strategy in ['mysql_priority', 'sqlserver_priority', 'primary_priority', 'timestamp_priority']
                
                if db_name == 'sqlite':
                    # 插入到主数据库
                    self._insert_primary_record(table_name, source_record, preserve_id)
                else:
                    # 插入到从数据库
                    self._insert_secondary_record(db_name, table_name, source_record, preserve_id)
                
                return {
                    'action': 'inserted_missing',
                    'reason': 'record_missing',
                    'database': db_name,
                    'strategy': strategy
                }
            except Exception as insert_error:
                # 如果插入失败（可能是唯一性约束冲突），尝试查找并更新现有记录
                error_msg = str(insert_error).lower()
                if 'unique' in error_msg or 'duplicate' in error_msg or '重复' in error_msg:
                    logger.info(f"检测到唯一性约束冲突，尝试查找并更新现有记录: {db_name}")
                    return self._handle_unique_constraint_conflict(table_name, record_id, db_name, source_record)
                else:
                    # 其他错误，重新抛出
                    raise insert_error
            
        except Exception as e:
            logger.error(f"处理缺失记录失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _handle_unique_constraint_conflict(self, table_name, record_id, db_name, source_record):
        """处理唯一性约束冲突"""
        try:
            # 对于title表，根据title_name查找现有记录
            if table_name == 'title' and 'title_name' in source_record:
                title_name = source_record['title_name']
                
                # 查找具有相同title_name的记录
                if db_name == 'sqlite':
                    engine = self.primary_engine
                else:
                    engine = self.secondary_engines[db_name]
                
                with engine.connect() as conn:
                    query = text(f"SELECT * FROM {table_name} WHERE title_name = :title_name")
                    result = conn.execute(query, {'title_name': title_name})
                    existing_record = result.fetchone()
                    
                    if existing_record:
                        existing_dict = dict(existing_record._mapping)
                        logger.info(f"找到现有记录: {existing_dict}")
                        
                        # 更新现有记录的其他字段（除了title_name和主键）
                        pk_field = self._get_primary_key_field(table_name)
                        existing_id = existing_dict[pk_field]
                        
                        # 准备更新数据（排除主键和唯一字段）
                        update_data = {}
                        for key, value in source_record.items():
                            if key not in [pk_field, 'title_name']:  # 跳过主键和唯一字段
                                update_data[key] = value
                        
                        if update_data:
                            # 更新记录
                            if db_name == 'sqlite':
                                self._update_primary_record(table_name, existing_id, update_data)
                            else:
                                self._update_secondary_record(db_name, table_name, existing_id, update_data)
                        
                        return {
                            'action': 'updated_existing',
                            'reason': 'unique_constraint_conflict',
                            'database': db_name,
                            'existing_id': existing_id,
                            'source_id': record_id
                        }
            
            # 对于其他表或情况，可以添加类似的处理逻辑
            return {
                'action': 'failed',
                'error': f'无法处理{table_name}表的唯一性约束冲突',
                'database': db_name
            }
            
        except Exception as e:
            logger.error(f"处理唯一性约束冲突失败: {e}")
            return {'action': 'failed', 'error': str(e), 'database': db_name}
    
    def _get_latest_record(self, table_name, record_id):
        """获取最新的记录（基于时间戳）"""
        latest_record = None
        latest_timestamp = None
        fallback_record = None  # 兜底记录（如果没有时间戳字段）
        
        # 检查主数据库
        try:
            primary_record = self._get_record(self.primary_engine, table_name, record_id)
            if primary_record:
                if 'updated_at' in primary_record and primary_record['updated_at']:
                    latest_record = primary_record
                    latest_timestamp = primary_record['updated_at']
                elif not fallback_record:
                    fallback_record = primary_record
        except:
            pass
        
        # 检查从数据库
        for db_name, engine in self.secondary_engines.items():
            try:
                secondary_record = self._get_record(engine, table_name, record_id)
                if secondary_record:
                    if 'updated_at' in secondary_record and secondary_record['updated_at']:
                        if not latest_timestamp or secondary_record['updated_at'] > latest_timestamp:
                            latest_record = secondary_record
                            latest_timestamp = secondary_record['updated_at']
                    elif not fallback_record:
                        fallback_record = secondary_record
            except:
                pass
        
        # 如果有基于时间戳的记录，优先返回；否则返回兜底记录
        return latest_record if latest_record else fallback_record
    
    def _insert_primary_record(self, table_name, data, preserve_id=False):
        """向主数据库插入记录"""
        # 处理主数据库的特殊情况（如果需要）
        processed_data = data.copy()
        
        # 过滤掉None值的字段
        processed_data = {k: v for k, v in processed_data.items() if v is not None}
        
        # 根据preserve_id参数决定是否保留原ID
        pk_field = self._get_primary_key_field(table_name)
        if not preserve_id and pk_field in processed_data:
            del processed_data[pk_field]
        
        # 添加必需字段（仅当表中存在该字段时）
        if table_name in ['patient', 'doctor', 'admin'] and 'password_hash' not in processed_data:
            # 检查表是否有password_hash字段
            try:
                with self.primary_engine.connect() as conn:
                    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'password_hash' in columns:
                        processed_data['password_hash'] = 'default_hash'
            except:
                # 如果检查失败，跳过添加password_hash
                pass
        
        if processed_data:
            columns = ', '.join(processed_data.keys())
            placeholders = ', '.join([f":{key}" for key in processed_data.keys()])
            query = text(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})")
            
            with self.primary_engine.connect() as conn:
                with conn.begin():
                    conn.execute(query, processed_data)
    
    def _update_secondary_record(self, db_name, table_name, record_id, data):
        """更新从数据库记录"""
        engine = self.secondary_engines[db_name]
        pk_field = self._get_primary_key_field(table_name)
        
        # 过滤掉None值的字段（避免SQL Server等数据库报错）
        filtered_data = {k: v for k, v in data.items() if v is not None and k != pk_field}
        
        if not filtered_data:
            logger.warning(f"没有有效数据可更新: {table_name}#{record_id}")
            return
        
        # 构建更新语句
        set_clause = ', '.join([f"{key} = :{key}" for key in filtered_data.keys()])
        query = text(f"UPDATE {table_name} SET {set_clause} WHERE {pk_field} = :record_id")
        
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(query, {**filtered_data, 'record_id': record_id})
    
    def _update_primary_record(self, table_name, record_id, data):
        """更新主数据库记录"""
        pk_field = self._get_primary_key_field(table_name)
        
        # 过滤掉None值的字段
        filtered_data = {k: v for k, v in data.items() if v is not None and k != pk_field}
        
        if not filtered_data:
            logger.warning(f"没有有效数据可更新: {table_name}#{record_id}")
            return
        
        set_clause = ', '.join([f"{key} = :{key}" for key in filtered_data.keys()])
        query = text(f"UPDATE {table_name} SET {set_clause} WHERE {pk_field} = :record_id")
        
        with self.primary_engine.connect() as conn:
            with conn.begin():
                conn.execute(query, {**filtered_data, 'record_id': record_id})
    
    def _insert_secondary_record(self, db_name, table_name, data, preserve_id=False):
        """向从数据库插入记录"""
        engine = self.secondary_engines[db_name]
        
        # 处理SQL Server的特殊情况
        processed_data = data.copy()
        
        # 过滤掉None值的字段（避免插入时出错）
        processed_data = {k: v for k, v in processed_data.items() if v is not None}
        
        if db_name == 'sqlserver':
            # 获取主键字段名
            pk_field = self._get_primary_key_field(table_name)
            
            # 根据preserve_id参数决定是否保留原ID
            if not preserve_id and pk_field in processed_data:
                del processed_data[pk_field]
            
            # 处理日期时间字段格式转换
            self._convert_datetime_for_sqlserver(processed_data, table_name)
            
            # 添加必需的默认值
            if table_name in ['patient', 'doctor', 'admin'] and 'password_hash' not in processed_data:
                processed_data['password_hash'] = 'default_hash'
        else:
            # 对于MySQL等其他数据库
            pk_field = self._get_primary_key_field(table_name)
            if not preserve_id and pk_field in processed_data:
                del processed_data[pk_field]
        
        # 确保有数据要插入
        if not processed_data:
            logger.warning(f"没有数据可插入到 {db_name}.{table_name}")
            return
        
        columns = ', '.join(processed_data.keys())
        placeholders = ', '.join([f":{key}" for key in processed_data.keys()])
        query = text(f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})")
        
        with engine.connect() as conn:
            with conn.begin():
                # SQL Server特殊处理：如果保留ID且是自增列，需要设置IDENTITY_INSERT
                if db_name == 'sqlserver' and preserve_id:
                    pk_field = self._get_primary_key_field(table_name)
                    if pk_field in processed_data:
                        # 启用IDENTITY_INSERT
                        conn.execute(text(f"SET IDENTITY_INSERT {table_name} ON"))
                        try:
                            conn.execute(query, processed_data)
                        finally:
                            # 无论成功失败都要关闭IDENTITY_INSERT
                            conn.execute(text(f"SET IDENTITY_INSERT {table_name} OFF"))
                    else:
                        conn.execute(query, processed_data)
                else:
                    conn.execute(query, processed_data)
    
    def _delete_primary_record(self, table_name, record_id):
        """删除主数据库中的记录"""
        pk_field = self._get_primary_key_field(table_name)
        query = text(f"DELETE FROM {table_name} WHERE {pk_field} = :record_id")
        
        with self.primary_engine.connect() as conn:
            with conn.begin():
                result = conn.execute(query, {'record_id': record_id})
                if result.rowcount == 0:
                    raise Exception(f"记录不存在或已被删除: {record_id}")
    
    def _delete_secondary_record(self, db_name, table_name, record_id):
        """删除从数据库中的记录"""
        engine = self.secondary_engines[db_name]
        pk_field = self._get_primary_key_field(table_name)
        query = text(f"DELETE FROM {table_name} WHERE {pk_field} = :record_id")
        
        with engine.connect() as conn:
            with conn.begin():
                result = conn.execute(query, {'record_id': record_id})
                if result.rowcount == 0:
                    raise Exception(f"记录不存在或已被删除: {record_id}")
    
    def _log_conflict_resolution(self, table_name, record_id, strategy, results):
        """记录冲突解决日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'table_name': table_name,
            'record_id': record_id,
            'strategy': strategy,
            'results': results
        }
        
        self.conflict_log.append(log_entry)
        
        # 检查是否有失败的结果
        failed_count = sum(1 for r in results if r.get('action') in ['failed', 'skipped'])
        success_count = len(results) - failed_count
        
        if failed_count > 0:
            logger.warning(f"冲突部分解决: {table_name}#{record_id} - 成功:{success_count}, 失败:{failed_count}, 策略:{strategy}")
        else:
            logger.info(f"冲突完全解决: {table_name}#{record_id} - 策略:{strategy}")
    
    def get_conflict_statistics(self):
        """获取冲突统计信息"""
        if not self.conflict_log:
            return {'total_conflicts': 0}
        
        stats = {
            'total_conflicts': len(self.conflict_log),
            'by_table': defaultdict(int),
            'by_strategy': defaultdict(int),
            'by_action': defaultdict(int),
            'recent_conflicts': []
        }
        
        recent_time = datetime.now() - timedelta(hours=24)
        
        for entry in self.conflict_log:
            # 按表统计
            stats['by_table'][entry.get('table_name', 'unknown')] += 1
            
            # 按策略统计
            stats['by_strategy'][entry.get('strategy', 'unknown')] += 1
            
            # 按操作统计
            for result in entry.get('results', []):
                stats['by_action'][result.get('action', 'unknown')] += 1
            
            # 最近冲突
            try:
                entry_time = datetime.fromisoformat(entry['timestamp'])
                if entry_time > recent_time:
                    stats['recent_conflicts'].append(entry)
            except:
                pass
        
        return dict(stats)
    
    def batch_conflict_check(self, tables=None):
        """批量检查所有表的冲突"""
        if tables is None:
            tables = ['admin', 'patient', 'doctor', 'department', 'registration', 'title']
        
        batch_results = {}
        
        for table_name in tables:
            try:
                # 获取所有数据库中的记录ID
                pk_field = self._get_primary_key_field(table_name)
                all_record_ids = set()
                
                # 从主数据库获取记录ID
                try:
                    with self.primary_engine.connect() as conn:
                        query = text(f"SELECT {pk_field} FROM {table_name}")
                        result = conn.execute(query)
                        primary_ids = [row[0] for row in result]
                        all_record_ids.update(primary_ids)
                except Exception as e:
                    logger.warning(f"从主数据库获取{table_name}记录失败: {e}")
                
                # 从从数据库获取记录ID
                for db_name, engine in self.secondary_engines.items():
                    try:
                        with engine.connect() as conn:
                            query = text(f"SELECT {pk_field} FROM {table_name}")
                            result = conn.execute(query)
                            secondary_ids = [row[0] for row in result]
                            all_record_ids.update(secondary_ids)
                    except Exception as e:
                        logger.warning(f"从{db_name}获取{table_name}记录失败: {e}")
                
                table_conflicts = []
                
                # 检查每个记录ID的冲突
                for record_id in all_record_ids:
                    conflict_info = self.detect_conflicts(table_name, record_id)
                    if conflict_info['has_conflict']:
                        table_conflicts.append({
                            'record_id': record_id,
                            'conflicts': conflict_info['conflicts']
                        })
                
                batch_results[table_name] = {
                    'total_records': len(all_record_ids),
                    'conflicts_found': len(table_conflicts),
                    'conflicts': table_conflicts
                }
                
            except Exception as e:
                logger.error(f"批量检查表 {table_name} 失败: {e}")
                batch_results[table_name] = {'error': str(e)}
        
        return batch_results
    
    def _send_conflict_email_notification(self, table_name, record_id, strategy, 
                                         conflict_databases, resolution_results, sync_type='single'):
        """
        发送冲突邮件通知
        
        Args:
            table_name: 表名
            record_id: 记录ID
            strategy: 解决策略
            conflict_databases: 冲突的数据库列表
            resolution_results: 解决结果列表
            sync_type: 同步类型 ('single', 'auto', 'manual')
        """
        try:
            # 构建冲突信息
            # 检查解决结果：action不是'failed'就认为成功
            is_resolved = all(r.get('action', 'failed') != 'failed' for r in resolution_results)
            
            conflict_info = {
                'total_conflicts': 1,
                'resolved_conflicts': 1 if is_resolved else 0,
                'strategy': strategy,
                'details': {
                    table_name: [{
                        'record_id': record_id,
                        'databases': conflict_databases,
                        'result': 'resolved' if is_resolved else 'failed'
                    }]
                }
            }
            
            # 发送邮件
            email_notifier.send_conflict_notification(conflict_info, sync_type)
            
        except Exception as e:
            logger.error(f"发送邮件通知失败: {e}")
    
    def send_batch_conflict_notification(self, batch_results, strategy, sync_type='auto', resolved_count=None):
        """
        发送批量冲突通知邮件
        
        Args:
            batch_results: 批量冲突检测结果
            strategy: 解决策略
            sync_type: 同步类型 ('auto' 或 'manual')
            resolved_count: 实际解决的冲突数量（如果为None则假设全部解决）
        """
        try:
            total_conflicts = 0
            details = {}
            
            for table_name, table_result in batch_results.items():
                if 'conflicts' in table_result and table_result['conflicts']:
                    table_conflicts = []
                    for conflict_info in table_result['conflicts']:
                        total_conflicts += 1
                        
                        # 获取冲突数据库列表
                        conflict_databases = []
                        for conflict in conflict_info.get('conflicts', []):
                            db_name = conflict.get('database', 'unknown')
                            if db_name not in conflict_databases:
                                conflict_databases.append(db_name)
                        
                        table_conflicts.append({
                            'record_id': conflict_info.get('record_id'),
                            'databases': conflict_databases,
                            'result': 'resolved'  # 标记为已解决
                        })
                    
                    details[table_name] = table_conflicts
            
            # 使用传入的resolved_count，如果没有则假设全部解决
            resolved_conflicts = resolved_count if resolved_count is not None else total_conflicts
            failed_conflicts = total_conflicts - resolved_conflicts
            
            if total_conflicts > 0:
                conflict_info = {
                    'total_conflicts': total_conflicts,
                    'resolved_conflicts': resolved_conflicts,
                    'failed_conflicts': failed_conflicts,
                    'strategy': strategy,
                    'details': details
                }
                
                email_notifier.send_conflict_notification(conflict_info, sync_type)
                if failed_conflicts > 0:
                    logger.warning(f"已发送批量冲突通知邮件: {total_conflicts}个冲突 (成功:{resolved_conflicts}, 失败:{failed_conflicts})")
                else:
                    logger.info(f"已发送批量冲突通知邮件: {total_conflicts}个冲突 (全部成功)")
            
        except Exception as e:
            logger.error(f"发送批量冲突通知失败: {e}")

# 自动冲突解决调度器
class ConflictResolutionScheduler:
    """冲突解决调度器"""
    
    def __init__(self, conflict_handler, check_interval=300, app=None):  # 5分钟检查一次
        self.conflict_handler = conflict_handler
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.app = app  # Flask应用实例，用于应用上下文
    
    def start(self):
        """启动自动冲突检查"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            logger.info("冲突解决调度器已启动")
    
    def stop(self):
        """停止自动冲突检查"""
        self.running = False
        if self.thread and self.thread.is_alive():
            logger.info("等待调度器线程停止...")
            self.thread.join(timeout=5)  # 最多等待5秒
            if self.thread.is_alive():
                logger.warning("调度器线程未能在5秒内停止")
        logger.info("冲突解决调度器已停止")
    
    def _run_scheduler(self):
        """运行调度器"""
        logger.info(f"冲突调度器开始运行，检查间隔: {self.check_interval}秒")
        
        while self.running:
            try:
                # 如果有app实例，在应用上下文中运行
                if self.app:
                    with self.app.app_context():
                        self._check_and_resolve_conflicts()
                else:
                    self._check_and_resolve_conflicts()
                
                # 等待下次检查
                logger.info(f"等待 {self.check_interval} 秒后进行下次检查...")
                import time
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"冲突调度器运行错误: {e}")
                import time
                time.sleep(60)  # 出错时等待1分钟再重试
        
        logger.info("冲突调度器已停止")
    
    def _check_and_resolve_conflicts(self):
        """检查并解决冲突（在应用上下文中执行）"""
        logger.info("执行自动冲突检查...")
        
        # 批量检查冲突
        batch_results = self.conflict_handler.batch_conflict_check()
        
        # 检查是否有冲突需要解决
        has_conflicts = False
        total_conflicts = 0
        for table_result in batch_results.values():
            if 'conflicts' in table_result and table_result['conflicts']:
                has_conflicts = True
                total_conflicts += len(table_result['conflicts'])
        
        if has_conflicts:
            logger.info(f"检测到 {total_conflicts} 个冲突，开始自动解决...")
            
            # 获取默认策略
            default_strategy = getattr(self.conflict_handler, 'default_strategy', 'timestamp_priority')
            logger.info(f"使用策略: {default_strategy}")
            
            # 自动解决冲突
            resolved_count = 0
            failed_count = 0
            for table_name, table_result in batch_results.items():
                if 'conflicts' in table_result:
                    for conflict_info in table_result['conflicts']:
                        record_id = conflict_info['record_id']
                        
                        # 使用默认策略自动解决
                        result = self.conflict_handler.resolve_conflicts(
                            table_name, record_id, default_strategy
                        )
                        
                        if result.get('resolved'):
                            resolved_count += 1
                        else:
                            failed_count += 1
                            # 记录失败详情
                            failed_results = result.get('failed_results', [])
                            if failed_results:
                                for failed in failed_results:
                                    logger.warning(f"冲突解决失败: {table_name}#{record_id} - {failed.get('reason', 'unknown')}")
            
            logger.info(f"自动解决完成: 成功 {resolved_count}/{total_conflicts}, 失败 {failed_count}")
            
            # 发送批量冲突通知邮件
            try:
                self.conflict_handler.send_batch_conflict_notification(
                    batch_results, default_strategy, sync_type='auto', 
                    resolved_count=resolved_count  # 传入实际解决的数量
                )
                logger.info("自动同步邮件通知已发送")
            except Exception as e:
                logger.error(f"发送自动同步邮件通知失败: {e}")
        else:
            logger.info("未检测到冲突")
