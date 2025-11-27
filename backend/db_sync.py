"""
数据库同步模块
SQLite (主) -> MySQL + SQL Server (从)
包含冲突检测和解决机制
"""
import os
from sqlalchemy import create_engine, event, MetaData, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from models import db, Admin, Patient, Doctor, Department, Registration, Title
from multi_db_conflict_handler import MultiDBConflictHandler, ConflictResolutionScheduler
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSync:
    def __init__(self, app):
        self.app = app
        self.sqlite_engine = None
        self.mysql_engine = None
        self.sqlserver_engine = None
        self.mysql_session = None
        self.sqlserver_session = None
        self.conflict_handler = None
        self.conflict_scheduler = None
        
    def setup_connections(self):
        """设置数据库连接"""
        # SQLite (主数据库) - 已在app中配置
        self.sqlite_engine = db.engine
        
        # MySQL配置
        mysql_config = self.app.config.get('MYSQL_URI')
        if mysql_config:
            try:
                # 尝试连接MySQL数据库
                self.mysql_engine = create_engine(
                    mysql_config,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30,
                    pool_recycle=3600,
                    pool_pre_ping=True,
                    echo=False
                )
                Session = sessionmaker(bind=self.mysql_engine)
                self.mysql_session = Session()
                logger.info("MySQL连接成功")
            except Exception as e:
                logger.warning(f"MySQL数据库连接失败: {e}")
                # 尝试自动创建数据库
                if self._auto_create_mysql_database(mysql_config):
                    try:
                        # 重新连接
                        self.mysql_engine = create_engine(
                            mysql_config,
                            pool_size=5,
                            max_overflow=10,
                            pool_timeout=30,
                            pool_recycle=3600,
                            pool_pre_ping=True,
                            echo=False
                        )
                        Session = sessionmaker(bind=self.mysql_engine)
                        self.mysql_session = Session()
                        logger.info("MySQL数据库创建并连接成功")
                    except Exception as retry_e:
                        logger.error(f"MySQL重新连接失败: {retry_e}")
                else:
                    logger.error(f"MySQL数据库自动创建失败")
        
        # SQL Server配置
        sqlserver_config = self.app.config.get('SQLSERVER_URI')
        if sqlserver_config:
            try:
                self.sqlserver_engine = create_engine(
                    sqlserver_config,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30,
                    pool_recycle=3600,
                    pool_pre_ping=True,
                    echo=False
                )
                Session = sessionmaker(bind=self.sqlserver_engine)
                self.sqlserver_session = Session()
                logger.info("SQL Server连接成功")
            except Exception as e:
                logger.warning(f"SQL Server数据库连接失败: {e}")
                # 尝试自动创建数据库
                if self._auto_create_sqlserver_database(sqlserver_config):
                    try:
                        # 重新连接
                        self.sqlserver_engine = create_engine(
                            sqlserver_config,
                            pool_size=5,
                            max_overflow=10,
                            pool_timeout=30,
                            pool_recycle=3600,
                            pool_pre_ping=True,
                            echo=False
                        )
                        Session = sessionmaker(bind=self.sqlserver_engine)
                        self.sqlserver_session = Session()
                        logger.info("SQL Server数据库创建并连接成功")
                    except Exception as retry_e:
                        logger.error(f"SQL Server重新连接失败: {retry_e}")
                else:
                    logger.error(f"SQL Server数据库自动创建失败")
    
    def create_tables(self):
        """在从数据库中创建表结构"""
        with self.app.app_context():
            # 在MySQL中创建表
            if self.mysql_engine:
                try:
                    db.metadata.create_all(self.mysql_engine)
                    logger.info("MySQL表结构创建成功")
                except Exception as e:
                    logger.error(f"MySQL表结构创建失败: {e}")
                    # 检查是否是数据库不存在的错误
                    error_msg = str(e).lower()
                    if "unknown database" in error_msg or "1049" in str(e):
                        logger.info("检测到MySQL数据库不存在，尝试自动创建...")
                        mysql_config = self.app.config.get('MYSQL_URI')
                        if mysql_config and self._auto_create_mysql_database(mysql_config):
                            try:
                                # 重新创建MySQL引擎和会话
                                self.mysql_engine = create_engine(
                                    mysql_config,
                                    pool_size=5,
                                    max_overflow=10,
                                    pool_timeout=30,
                                    pool_recycle=3600,
                                    pool_pre_ping=True,
                                    echo=False
                                )
                                Session = sessionmaker(bind=self.mysql_engine)
                                self.mysql_session = Session()
                                # 重新尝试创建表
                                db.metadata.create_all(self.mysql_engine)
                                logger.info("MySQL数据库创建成功，表结构创建完成")
                            except Exception as retry_e:
                                logger.error(f"MySQL数据库创建后表结构创建仍失败: {retry_e}")
                        else:
                            logger.error("MySQL数据库自动创建失败")
            
            # 在SQL Server中创建表
            if self.sqlserver_engine:
                try:
                    db.metadata.create_all(self.sqlserver_engine)
                    logger.info("SQL Server表结构创建成功")
                except Exception as e:
                    logger.error(f"SQL Server表结构创建失败: {e}")
                    # 检查是否是数据库不存在的错误
                    error_msg = str(e).lower()
                    if ("cannot open database" in error_msg or 
                        "无法打开登录所请求的数据库" in error_msg or
                        "4060" in str(e) or
                        ("database" in error_msg and "does not exist" in error_msg)):
                        logger.info("检测到SQL Server数据库不存在，尝试自动创建...")
                        sqlserver_config = self.app.config.get('SQLSERVER_URI')
                        if sqlserver_config and self._auto_create_sqlserver_database(sqlserver_config):
                            try:
                                # 重新创建SQL Server引擎和会话
                                self.sqlserver_engine = create_engine(
                                    sqlserver_config,
                                    pool_size=5,
                                    max_overflow=10,
                                    pool_timeout=30,
                                    pool_recycle=3600,
                                    pool_pre_ping=True,
                                    echo=False
                                )
                                Session = sessionmaker(bind=self.sqlserver_engine)
                                self.sqlserver_session = Session()
                                # 重新尝试创建表
                                db.metadata.create_all(self.sqlserver_engine)
                                logger.info("SQL Server数据库创建成功，表结构创建完成")
                            except Exception as retry_e:
                                logger.error(f"SQL Server数据库创建后表结构创建仍失败: {retry_e}")
                        else:
                            logger.error("SQL Server数据库自动创建失败")
            
            # 初始化冲突处理器
            self._setup_conflict_handler(self.app)
    
    def sync_insert(self, mapper, connection, target):
        """同步插入操作"""
        self._sync_operation('insert', target)
    
    def sync_update(self, mapper, connection, target):
        """同步更新操作"""
        self._sync_operation('update', target)
    
    def sync_delete(self, mapper, connection, target):
        """同步删除操作"""
        self._sync_operation('delete', target)
    
    def _sync_operation(self, operation, target):
        """执行同步操作 - 支持多方向同步"""
        table_name = target.__tablename__
        
        # 确定当前操作来源的数据库
        source_db = self._detect_source_database(target)
        
        # 使用线程池进行并行同步到其他数据库
        import threading
        
        def sync_to_sqlite():
            if source_db != 'sqlite' and self.sqlite_engine:
                self._sync_to_primary_db(operation, target, 'SQLite')
        
        def sync_to_mysql():
            if source_db != 'mysql' and self.mysql_session:
                self._sync_to_db(self.mysql_session, operation, target, 'MySQL')
        
        def sync_to_sqlserver():
            if source_db != 'sqlserver' and self.sqlserver_session:
                self._sync_to_db(self.sqlserver_session, operation, target, 'SQL Server')
        
        try:
            # 并行执行同步，减少总时间
            threads = []
            
            if self.mysql_session:
                mysql_thread = threading.Thread(target=sync_to_mysql)
                mysql_thread.daemon = True
                threads.append(mysql_thread)
                mysql_thread.start()
            
            if self.sqlserver_session:
                sqlserver_thread = threading.Thread(target=sync_to_sqlserver)
                sqlserver_thread.daemon = True
                threads.append(sqlserver_thread)
                sqlserver_thread.start()
            
            # 不等待同步完成，让同步在后台进行，像SQLite一样即时响应
            # 同步操作异步进行，不阻塞主操作
                
        except Exception as e:
            logger.error(f"同步操作失败 [{operation}] {table_name}: {e}")
    
    def _sync_to_db(self, session, operation, target, db_name):
        """同步到指定数据库"""
        # 创建新的会话来避免冲突
        new_session = None
        try:
            target_class = target.__class__
            primary_key = target.__mapper__.primary_key[0].name
            pk_value = getattr(target, primary_key)
            
            # 使用新的会话
            Session = sessionmaker(bind=session.bind)
            new_session = Session()
            
            if operation == 'insert':
                # 创建新对象
                new_obj = target_class()
                for column in target.__table__.columns:
                    value = getattr(target, column.name)
                    setattr(new_obj, column.name, value)
                new_session.add(new_obj)
                
            elif operation == 'update':
                # 查找并更新对象
                existing = new_session.query(target_class).filter(
                    getattr(target_class, primary_key) == pk_value
                ).first()
                
                if existing:
                    for column in target.__table__.columns:
                        value = getattr(target, column.name)
                        setattr(existing, column.name, value)
                else:
                    # 如果不存在，则插入
                    new_obj = target_class()
                    for column in target.__table__.columns:
                        value = getattr(target, column.name)
                        setattr(new_obj, column.name, value)
                    new_session.add(new_obj)
                    
            elif operation == 'delete':
                # 删除对象
                existing = new_session.query(target_class).filter(
                    getattr(target_class, primary_key) == pk_value
                ).first()
                
                if existing:
                    new_session.delete(existing)
            
            new_session.commit()
            
            # 立即刷新连接以确保数据可见性
            new_session.flush()
            
            # 强制刷新连接池确保实时可见
            try:
                if hasattr(new_session.bind, 'pool') and hasattr(new_session.bind.pool, 'invalidate'):
                    new_session.bind.pool.invalidate()
            except Exception:
                pass  # 忽略连接池刷新错误
            
            logger.info(f"{db_name} 实时同步成功: {operation} {target.__tablename__}")
            
        except Exception as e:
            if new_session:
                new_session.rollback()
            logger.error(f"{db_name} 同步失败: {e}")
        finally:
            if new_session:
                new_session.close()
    
    def register_listeners(self):
        """注册SQLAlchemy事件监听器"""
        # 为所有模型注册监听器
        models = [Admin, Patient, Doctor, Department, Registration, Title]
        
        for model in models:
            event.listen(model, 'after_insert', self.sync_insert)
            event.listen(model, 'after_update', self.sync_update)
            event.listen(model, 'after_delete', self.sync_delete)
        
        logger.info("数据库同步监听器已注册")
    
    def full_sync(self):
        """全量同步：将SQLite中的所有数据同步到从数据库"""
        with self.app.app_context():
            models = [
                (Department, 'dept_id'),
                (Title, 'title_id'),
                (Admin, 'admin_id'),
                (Doctor, 'doctor_id'),
                (Patient, 'patient_id'),
                (Registration, 'reg_id')
            ]
            
            for model, pk_field in models:
                try:
                    # 从SQLite读取所有数据
                    records = model.query.all()
                    logger.info(f"开始同步 {model.__tablename__}: {len(records)} 条记录")
                    
                    for record in records:
                        # 同步到MySQL
                        if self.mysql_session:
                            self._sync_record_to_db(self.mysql_session, model, record, pk_field, 'MySQL')
                        
                        # 同步到SQL Server
                        if self.sqlserver_session:
                            self._sync_record_to_db(self.sqlserver_session, model, record, pk_field, 'SQL Server')
                    
                    logger.info(f"{model.__tablename__} 同步完成")
                    
                except Exception as e:
                    logger.error(f"{model.__tablename__} 全量同步失败: {e}")
    
    def _sync_record_to_db(self, session, model, record, pk_field, db_name):
        """同步单条记录到指定数据库"""
        try:
            pk_value = getattr(record, pk_field)
            
            # 检查记录是否已存在
            existing = session.query(model).filter(
                getattr(model, pk_field) == pk_value
            ).first()
            
            if existing:
                # 更新现有记录
                for column in record.__table__.columns:
                    setattr(existing, column.name, getattr(record, column.name))
            else:
                # 插入新记录
                new_obj = model()
                for column in record.__table__.columns:
                    setattr(new_obj, column.name, getattr(record, column.name))
                session.add(new_obj)
            
            session.commit()
            
        except Exception as e:
            session.rollback()
            logger.error(f"{db_name} 记录同步失败 [{model.__tablename__}]: {e}")
    
    def _auto_create_mysql_database(self, mysql_uri):
        """自动创建MySQL数据库"""
        try:
            # 解析数据库URI获取数据库名
            import re
            match = re.search(r'/([^/?]+)(?:\?|$)', mysql_uri)
            if not match:
                logger.error("无法从URI中解析数据库名")
                return False
            
            db_name = match.group(1)
            
            # 创建不包含数据库名的连接URI
            base_uri = mysql_uri.replace(f'/{db_name}', '/mysql')
            
            logger.info(f"尝试创建MySQL数据库: {db_name}")
            
            # 连接到MySQL服务器（使用mysql系统数据库）
            temp_engine = create_engine(base_uri, echo=False)
            
            with temp_engine.connect() as conn:
                # 创建数据库
                from sqlalchemy import text
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                conn.commit()
                logger.info(f"MySQL数据库 '{db_name}' 创建成功")
            
            temp_engine.dispose()
            return True
            
        except Exception as e:
            logger.error(f"创建MySQL数据库失败: {e}")
            return False
    
    def _auto_create_sqlserver_database(self, sqlserver_uri):
        """自动创建SQL Server数据库"""
        try:
            # 解析数据库URI获取数据库名
            import re
            match = re.search(r'/([^/?]+)(?:\?|$)', sqlserver_uri)
            if not match:
                logger.error("无法从URI中解析数据库名")
                return False
            
            db_name = match.group(1)
            
            logger.info(f"尝试创建SQL Server数据库: {db_name}")
            
            # 使用pyodbc直接连接，避免SQLAlchemy的事务问题
            import pyodbc
            import urllib.parse
            
            # 解析连接字符串
            parsed = urllib.parse.urlparse(sqlserver_uri)
            server = parsed.hostname
            if parsed.port:
                server += f",{parsed.port}"
            elif '\\' in parsed.hostname:
                server = parsed.hostname
            
            username = parsed.username
            password = parsed.password
            
            # 构建连接字符串连接到master数据库
            conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE=master;UID={username};PWD={password}"
            
            conn = pyodbc.connect(conn_str, autocommit=True)
            try:
                cursor = conn.cursor()
                
                # 检查数据库是否存在
                cursor.execute(f"SELECT database_id FROM sys.databases WHERE name = '{db_name}'")
                if not cursor.fetchone():
                    # 创建数据库
                    cursor.execute(f"CREATE DATABASE [{db_name}]")
                    logger.info(f"SQL Server数据库 '{db_name}' 创建成功")
                else:
                    logger.info(f"SQL Server数据库 '{db_name}' 已存在")
                
                cursor.close()
            finally:
                conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"创建SQL Server数据库失败: {e}")
            return False

    def close_connections(self):
        """关闭数据库连接"""
        if self.mysql_session:
            self.mysql_session.close()
        if self.sqlserver_session:
            self.sqlserver_session.close()
        logger.info("数据库连接已关闭")
    
    def _detect_source_database(self, target):
        """检测操作来源的数据库"""
        # 这里可以通过连接上下文或其他方式检测
        # 暂时返回sqlite作为默认值，实际应用中需要更精确的检测
        return 'sqlite'
    
    def _sync_to_primary_db(self, operation, target, db_name):
        """同步到主数据库(SQLite)"""
        try:
            table_name = target.__tablename__
            
            if operation == 'insert':
                # 插入到SQLite
                with self.sqlite_engine.connect() as conn:
                    # 构建插入语句
                    columns = [col.name for col in target.__table__.columns]
                    values = {col: getattr(target, col) for col in columns}
                    
                    placeholders = ', '.join([f":{col}" for col in columns])
                    columns_str = ', '.join(columns)
                    
                    query = f"INSERT OR REPLACE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                    conn.execute(query, values)
                    conn.commit()
                    
            elif operation == 'update':
                # 更新SQLite
                with self.sqlite_engine.connect() as conn:
                    pk_col = target.__table__.primary_key.columns.keys()[0]
                    pk_value = getattr(target, pk_col)
                    
                    columns = [col.name for col in target.__table__.columns if col.name != pk_col]
                    values = {col: getattr(target, col) for col in columns}
                    values[pk_col] = pk_value
                    
                    set_clause = ', '.join([f"{col} = :{col}" for col in columns])
                    query = f"UPDATE {table_name} SET {set_clause} WHERE {pk_col} = :{pk_col}"
                    conn.execute(query, values)
                    conn.commit()
                    
            elif operation == 'delete':
                # 从SQLite删除
                with self.sqlite_engine.connect() as conn:
                    pk_col = target.__table__.primary_key.columns.keys()[0]
                    pk_value = getattr(target, pk_col)
                    
                    query = f"DELETE FROM {table_name} WHERE {pk_col} = :{pk_col}"
                    conn.execute(query, {pk_col: pk_value})
                    conn.commit()
                    
            logger.info(f"{db_name} {operation} 同步成功: {table_name}")
            
        except Exception as e:
            logger.error(f"{db_name} {operation} 同步失败: {e}")
    
    def _setup_conflict_handler(self, app):
        """设置冲突处理器"""
        try:
            # 准备从数据库引擎字典
            secondary_engines = {}
            if self.mysql_engine:
                secondary_engines['mysql'] = self.mysql_engine
            if self.sqlserver_engine:
                secondary_engines['sqlserver'] = self.sqlserver_engine
            
            if secondary_engines:
                # 初始化冲突处理器
                self.conflict_handler = MultiDBConflictHandler(
                    self.sqlite_engine, 
                    secondary_engines
                )
                
                # 初始化冲突调度器（每10分钟检查一次）
                self.conflict_scheduler = ConflictResolutionScheduler(
                    self.conflict_handler, 
                    check_interval=600,
                    app=app  # 传入Flask应用实例
                )
                
                # 启动自动冲突解决
                self.conflict_scheduler.start()
                
                logger.info("冲突处理器已初始化并启动")
            else:
                logger.warning("没有从数据库连接，跳过冲突处理器初始化")
                
        except Exception as e:
            logger.error(f"冲突处理器初始化失败: {e}")
    
    def check_and_resolve_conflicts(self, table_name=None, record_id=None):
        """手动检查和解决冲突"""
        if not self.conflict_handler:
            return {'error': '冲突处理器未初始化'}
        
        try:
            if table_name and record_id:
                # 检查特定记录的冲突
                conflict_info = self.conflict_handler.detect_conflicts(table_name, record_id)
                if conflict_info['has_conflict']:
                    resolution = self.conflict_handler.resolve_conflicts(
                        table_name, record_id, 'timestamp_priority'
                    )
                    return {
                        'conflicts_found': True,
                        'resolution': resolution
                    }
                else:
                    return {'conflicts_found': False}
            else:
                # 批量检查所有表
                batch_results = self.conflict_handler.batch_conflict_check()
                
                # 自动解决发现的冲突
                resolution_results = {}
                for table, result in batch_results.items():
                    if 'conflicts' in result and result['conflicts']:
                        table_resolutions = []
                        for conflict in result['conflicts']:
                            resolution = self.conflict_handler.resolve_conflicts(
                                table, conflict['record_id'], 'timestamp_priority'
                            )
                            table_resolutions.append(resolution)
                        resolution_results[table] = table_resolutions
                
                return {
                    'batch_check': batch_results,
                    'resolutions': resolution_results
                }
                
        except Exception as e:
            logger.error(f"冲突检查和解决失败: {e}")
            return {'error': str(e)}
    
    def get_conflict_statistics(self):
        """获取冲突统计信息"""
        if not self.conflict_handler:
            return {'error': '冲突处理器未初始化'}
        
        return self.conflict_handler.get_conflict_statistics()

# 全局同步实例
sync_manager = None

def init_sync(app):
    """初始化数据库同步"""
    global sync_manager
    sync_manager = DatabaseSync(app)
    sync_manager.setup_connections()
    sync_manager.create_tables()
    sync_manager.register_listeners()
    return sync_manager
