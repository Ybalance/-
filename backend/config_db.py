"""
数据库配置文件
配置SQLite、MySQL、SQL Server连接信息
"""

class DatabaseConfig:
    # SQLite配置（主数据库）
    SQLITE_URI = 'sqlite:///data.db'
    
    # MySQL配置（从数据库）
    # 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名
    MYSQL_URI = 'mysql+pymysql://root:yzh2766232123@localhost:3306/hospital_db?charset=utf8mb4'  # 示例: 'mysql+pymysql://root:password@localhost:3306/hospital_db'
    
    # SQL Server配置（从数据库）
    # 格式: mssql+pyodbc://用户名:密码@主机:端口/数据库名?driver=ODBC+Driver+17+for+SQL+Server
    SQLSERVER_URI = None  # 示例: 'mssql+pyodbc://sa:password@localhost:1433/hospital_db?driver=ODBC+Driver+17+for+SQL+Server'
    
    # 是否启用数据库同步
    ENABLE_SYNC = False  # 设置为True启用同步

# 开发环境配置
class DevelopmentConfig(DatabaseConfig):
    DEBUG = True
    ENABLE_SYNC = False  # 开发环境默认不启用同步

# 生产环境配置
class ProductionConfig(DatabaseConfig):
    DEBUG = False
    ENABLE_SYNC = True  # ✅ 启用实时同步
    
    # MySQL配置
    MYSQL_URI = 'mysql+pymysql://root:yzh2766232123@localhost:3306/hospital_db?charset=utf8mb4'
    
    # SQL Server配置
    # 实例名: YBALANCE, 混合验证, 密码: yzh2766232123
    SQLSERVER_URI = 'mssql+pyodbc://sa:yzh2766232123@localhost\\YBALANCE/hospital_db?driver=ODBC+Driver+17+for+SQL+Server'

# 当前使用的配置
config = ProductionConfig  # 使用生产配置，启用MySQL实时同步
