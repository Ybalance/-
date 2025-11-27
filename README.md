# 医院挂号管理系统

一个基于 Flask + HTML/CSS/JavaScript 的现代化医院挂号管理系统，支持多数据库实时同步、冲突自动解决和响应式设计。

## 🏥 系统概述

本系统为医院提供完整的挂号管理解决方案，包括患者管理、医生管理、科室管理、挂号预约等功能，并支持多数据库环境下的数据同步。

## ✨ 主要特性

### 🎯 核心功能
- **患者管理**: 患者注册、信息管理、挂号历史查询
- **医生管理**: 医生信息维护、排班管理、照片上传
- **科室管理**: 科室信息、位置管理
- **挂号系统**: 在线预约、费用计算、状态管理
- **管理员后台**: 用户管理、数据统计、系统配置

### 🔄 数据同步
- **多数据库支持**: SQLite (主) + MySQL + SQL Server
- **实时同步**: 数据变更自动同步到所有数据库
- **冲突解决**: 智能冲突检测和自动解决
- **邮件通知**: 同步状态和冲突报告邮件提醒

### 📱 用户体验
- **响应式设计**: 支持桌面端和移动端
- **卡片式布局**: 现代化的用户界面
- **实时搜索**: 快速查找患者、医生、挂号记录
- **状态管理**: 挂号状态实时更新

## 🏗️ 技术架构

### 后端技术栈
- **框架**: Flask 2.x
- **数据库**: SQLAlchemy ORM
- **认证**: JWT Token
- **同步**: 自定义多数据库同步引擎
- **邮件**: SMTP 邮件通知
- **文件上传**: 医生照片管理

### 前端技术栈
- **基础**: HTML5 + CSS3 + JavaScript (ES6+)
- **样式**: 自定义 CSS + 响应式设计
- **交互**: 原生 JavaScript + Fetch API
- **布局**: CSS Grid + Flexbox

### 数据库支持
- **SQLite**: 主数据库，本地存储
- **MySQL**: 从数据库，支持远程访问
- **SQL Server**: 从数据库，企业级支持

## 📁 项目结构

```
data3/
├── backend/                    # 后端代码
│   ├── app.py                 # Flask 应用入口
│   ├── config_db.py           # 数据库连接配置
│   ├── models.py              # 数据模型定义
│   ├── routes_new.py          # API 路由
│   ├── db_sync.py             # 数据库同步引擎
│   ├── multi_db_conflict_handler.py  # 冲突处理器
│   ├── email_config.py        # 邮件配置
│   ├── extensions.py          # Flask 扩展
│   ├── auth.py                # 认证装饰器
│   ├── sync_config_routes.py  # 同步配置路由
│   ├── conflict_management_routes.py  # 冲突管理路由
│   ├── database_management_routes.py  # 数据库管理路由
│   ├── instance/              # 数据库文件
│   │   └── data.db           # SQLite 数据库
│   └── uploads/               # 上传文件存储
├── frontend/                   # 前端代码
│   ├── index.html             # 登录页面
│   ├── patient.html           # 患者页面
│   ├── doctor.html            # 医生页面
│   ├── admin.html             # 管理员页面
│   ├── styles.css             # 全局样式
│   ├── patient.css            # 患者页面样式
│   ├── doctor.css             # 医生页面样式
│   └── admin.css              # 管理员页面样式
├── start_system.bat           # 系统启动脚本
├── start_backend.bat          # 后端启动脚本
├── init_databases.py          # 数据库初始化脚本
└── README.md                  # 项目文档
```

## 🚀 快速开始

### 环境要求
- Python 3.8+
- MySQL 5.7+ (可选)
- SQL Server 2017+ (可选)

### 安装依赖
```bash
pip install flask flask-sqlalchemy flask-jwt-extended flask-cors
pip install pymysql pyodbc  # MySQL 和 SQL Server 驱动
```

### 配置数据库
编辑 `backend/config_db.py`:

```python
# MySQL 配置
MYSQL_URI = 'mysql+pymysql://用户名:密码@localhost:3306/hospital_db?charset=utf8mb4'

# SQL Server 配置  
SQLSERVER_URI = 'mssql+pyodbc://sa:密码@localhost\\实例名/hospital_db?driver=ODBC+Driver+17+for+SQL+Server'

# 启用同步
ENABLE_SYNC = True
```

### 启动系统
```bash
# 方式1: 使用启动脚本 (推荐)
start_system.bat

# 方式2: 手动启动
cd backend
python app.py
```

### 访问系统
- 系统地址: http://localhost:5000
- 默认管理员: admin / admin123

## 👥 用户角色

### 患者 (Patient)
- 注册登录
- 查看个人信息
- 预约挂号
- 查看挂号历史
- 取消预约

### 医生 (Doctor)  
- 查看个人信息
- 管理排班
- 查看预约患者
- 处理挂号记录

### 管理员 (Admin)
- 用户管理 (患者、医生、管理员)
- 科室管理
- 职称管理  
- 挂号记录管理
- 数据库同步配置
- 冲突解决管理
- 系统统计

## 🔧 配置说明

### 数据库配置
在 `backend/config_db.py` 中配置:

```python
class ProductionConfig(DatabaseConfig):
    # MySQL 配置
    MYSQL_URI = 'mysql+pymysql://root:password@localhost:3306/hospital_db?charset=utf8mb4'
    
    # SQL Server 配置
    SQLSERVER_URI = 'mssql+pyodbc://sa:password@localhost\\INSTANCE/hospital_db?driver=ODBC+Driver+17+for+SQL+Server'
    
    # 启用同步
    ENABLE_SYNC = True
```

### 邮件配置
在 `backend/email_config.py` 中配置 SMTP:

```python
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': 'your-email@gmail.com',
    'password': 'your-app-password',
    'from_email': 'your-email@gmail.com',
    'admin_email': 'admin@hospital.com'
}
```

## 🔄 数据同步机制

### 同步策略
- **时间戳优先**: 使用最新的数据 (默认)
- **SQLite优先**: 主数据库优先
- **MySQL优先**: MySQL 数据优先  
- **SQL Server优先**: SQL Server 数据优先

### 冲突解决
- 自动检测数据冲突
- 根据策略自动解决
- 邮件通知同步结果
- 手动冲突解决界面

### 同步监控
- 实时同步状态显示
- 冲突统计和历史
- 同步日志查看
- 邮件通知配置

## 📊 数据模型

### 核心表结构
- **admin**: 管理员信息
- **patient**: 患者信息  
- **doctor**: 医生信息
- **department**: 科室信息
- **title**: 职称信息
- **registration**: 挂号记录

### 字段说明
所有表都包含时间戳字段:
- `created_at`: 创建时间
- `updated_at`: 更新时间

## 🛠️ 开发指南

### 添加新功能
1. 在 `models.py` 中定义数据模型
2. 在 `routes_new.py` 中添加 API 路由
3. 在前端页面中添加界面和交互
4. 测试数据同步功能

### 自定义同步策略
在 `multi_db_conflict_handler.py` 中添加新的解决策略:

```python
def _resolve_by_custom_strategy(self, table_name, record_id, db_name, reference_data, current_data):
    # 自定义冲突解决逻辑
    pass
```

## 🔍 故障排除

### 常见问题

**1. 数据库连接失败**
- 检查 `config_db.py` 中的连接字符串
- 确认数据库服务已启动
- 验证用户名密码正确

**2. 同步冲突**
- 查看管理员页面的冲突管理
- 检查邮件通知
- 手动解决冲突或调整策略

**3. 前端页面异常**
- 检查浏览器控制台错误
- 确认后端 API 正常响应
- 清除浏览器缓存

### 日志查看
- 后端日志: 控制台输出
- 同步日志: 管理员页面查看
- 冲突日志: 邮件通知和管理界面

## 📈 性能优化

### 数据库优化
- 连接池配置
- 索引优化
- 查询优化

### 前端优化  
- 响应式设计
- 懒加载
- 缓存策略

## 🔒 安全特性

- JWT Token 认证
- 角色权限控制
- SQL 注入防护
- XSS 防护
- 文件上传安全

## 📝 更新日志

### v1.0.0 (2025-11-27)
- ✅ 完整的医院挂号管理系统
- ✅ 多数据库实时同步
- ✅ 智能冲突解决
- ✅ 响应式用户界面
- ✅ 邮件通知系统



