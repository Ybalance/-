from flask import Flask, make_response, request, jsonify
from flask_cors import CORS
from extensions import db, jwt
from routes_new import api_bp
from config_db import config as db_config
import os

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
    app.config['JWT_SECRET_KEY'] = 'jwt-secret-string-change-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_timeout': 60,
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'pool_size': 10,
        'max_overflow': 20,
        'connect_args': {
            'timeout': 60,
            'check_same_thread': False,
            'isolation_level': None
        }
    }
    
    # 文件上传配置
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 限制2MB
    app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
    
    # 数据库同步配置
    app.config['MYSQL_URI'] = db_config.MYSQL_URI
    app.config['SQLSERVER_URI'] = db_config.SQLSERVER_URI
    app.config['ENABLE_SYNC'] = db_config.ENABLE_SYNC
    
    # Initialize extensions
    db.init_app(app)
    jwt.init_app(app)
    
    # CORS configuration - Allow all origins and methods
    CORS(app, 
         resources={r"/*": {
             "origins": "*",
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization"],
             "expose_headers": ["Content-Type", "Authorization"],
             "supports_credentials": True
         }})
    
    # Handle OPTIONS requests explicitly
    @app.before_request
    def handle_options():
        if request.method == 'OPTIONS':
            response = make_response()
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Max-Age'] = '3600'
            return response
    
    # Handle errors
    @app.errorhandler(Exception)
    def handle_error(e):
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Register conflict management blueprint
    from conflict_management_routes import conflict_bp
    app.register_blueprint(conflict_bp, url_prefix='/api')
    
    # Register database management blueprint
    from database_management_routes import db_management_bp
    app.register_blueprint(db_management_bp, url_prefix='/api')
    
    # 初始化同步配置路由（稍后在同步管理器初始化后注册）
    sync_config_routes_registered = False
    
    # 静态文件路由 - 提供uploads文件夹访问
    from flask import send_from_directory
    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
    # Create tables
    with app.app_context():
        db.create_all()
        print("数据库表已创建或已存在")
        
        # 初始化数据库同步
        if app.config['ENABLE_SYNC']:
            from db_sync import init_sync
            sync_manager = init_sync(app)
            
            # 注册同步配置路由
            from sync_config_routes import init_sync_config_routes
            init_sync_config_routes(app, sync_manager)
            
            print("数据库实时同步已启用")
            print(f"MySQL: {'已配置' if app.config['MYSQL_URI'] else '未配置'}")
            print(f"SQL Server: {'已配置' if app.config['SQLSERVER_URI'] else '未配置'}")
        else:
            print("数据库同步未启用")
    
    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 50002))
    app.run(host='0.0.0.0', port=port, debug=True)
