from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class Admin(db.Model):
    __tablename__ = 'admin'
    
    admin_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)  # 管理员邮箱地址
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'admin_id': self.admin_id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Patient(db.Model):
    __tablename__ = 'patient'
    
    patient_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(12), nullable=False)
    phone = db.Column(db.String(11))
    gender = db.Column(db.String(2))
    birthday = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    registrations = db.relationship('Registration', backref='patient', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_total_fee(self):
        """动态计算累计挂号费"""
        total = db.session.query(db.func.sum(Registration.fee)).filter(
            Registration.patient_id == self.patient_id,
            Registration.status != 'cancelled'
        ).scalar()
        return total if total else 0.0
    
    def to_dict(self):
        return {
            'patient_id': self.patient_id,
            'username': self.username,
            'name': self.name,
            'phone': self.phone,
            'gender': self.gender,
            'birthday': self.birthday.isoformat() if self.birthday else None,
            'total_fee': self.get_total_fee()
        }

class Department(db.Model):
    __tablename__ = 'department'
    
    dept_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dept_name = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    doctors = db.relationship('Doctor', backref='department', lazy=True)
    
    def to_dict(self):
        return {
            'dept_id': self.dept_id,
            'dept_name': self.dept_name,
            'location': self.location
        }

# 职称表
class Title(db.Model):
    __tablename__ = 'title'
    
    title_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title_name = db.Column(db.String(50), nullable=False, unique=True)
    registration_fee = db.Column(db.Float, nullable=False, default=15.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    doctors = db.relationship('Doctor', backref='title_info', lazy=True)
    
    def to_dict(self):
        return {
            'title_id': self.title_id,
            'title_name': self.title_name,
            'registration_fee': self.registration_fee
        }

class Doctor(db.Model):
    __tablename__ = 'doctor'
    
    doctor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(12), nullable=False)
    title_id = db.Column(db.Integer, db.ForeignKey('title.title_id'), nullable=True)  # 改为外键
    dept_id = db.Column(db.Integer, db.ForeignKey('department.dept_id'), nullable=False)
    schedule = db.Column(db.Text)  # JSON格式存储排班信息: {"monday_am": true, "monday_pm": false, ...}
    photo = db.Column(db.String(255))  # 医生照片文件名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    registrations = db.relationship('Registration', backref='doctor', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_registration_fee(self):
        """根据职称返回挂号费"""
        if self.title_info:
            return self.title_info.registration_fee
        return 15.0  # 默认15元
    
    def is_available(self, weekday, period):
        """
        检查医生在指定时间是否可预约
        weekday: 0-6 (周一到周日)
        period: 'am' 或 'pm'
        如果没有设置排班，默认全部时间可用
        """
        if not self.schedule:
            return True  # 未设置排班，默认全部可用
        
        import json
        try:
            schedule_dict = json.loads(self.schedule)
            weekday_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            key = f"{weekday_names[weekday]}_{period}"
            return schedule_dict.get(key, True)  # 如果key不存在，默认可用
        except:
            return True  # 解析失败，默认可用
    
    def to_dict(self):
        return {
            'doctor_id': self.doctor_id,
            'username': self.username,
            'name': self.name,
            'title': self.title_info.title_name if self.title_info else '未设置',
            'title_id': self.title_id,
            'dept_id': self.dept_id,
            'dept_name': self.department.dept_name if self.department else None,
            'schedule': self.schedule,
            'registration_fee': self.get_registration_fee(),
            'photo': self.photo  # 返回实际照片路径或None，由前端处理占位图
        }

class Registration(db.Model):
    __tablename__ = 'registration'
    
    reg_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.patient_id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.doctor_id'), nullable=False)
    reg_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='registered')
    fee = db.Column(db.Float, nullable=False, default=0.0)  # 本次挂号费用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'reg_id': self.reg_id,
            'patient_id': self.patient_id,
            'doctor_id': self.doctor_id,
            'reg_time': self.reg_time.isoformat() if self.reg_time else None,
            'status': self.status,
            'fee': self.fee,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'patient_name': self.patient.name if self.patient else None,
            'patient_phone': self.patient.phone if self.patient else None,
            'doctor_name': self.doctor.name if self.doctor else None,
            'doctor_title': self.doctor.title_info.title_name if self.doctor and self.doctor.title_info else None,
            'dept_name': self.doctor.department.dept_name if self.doctor and self.doctor.department else None,
            'dept_location': self.doctor.department.location if self.doctor and self.doctor.department else None
        }
