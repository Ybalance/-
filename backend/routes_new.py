from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from extensions import db
from models import Admin, Patient, Doctor, Department, Registration, Title
from auth import role_required, get_current_user
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, and_

api_bp = Blueprint('api', __name__)

# Helper function to auto-update expired registrations
def auto_update_expired_registrations():
    """
    自动将超过预约时间2小时且状态为'registered'的挂号记录更新为'cancelled'（已过号）
    """
    try:
        # 计算2小时前的时间
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        
        # 查找所有超时且状态为'registered'的挂号记录
        expired_registrations = Registration.query.filter(
            and_(
                Registration.status == 'registered',
                Registration.reg_time < two_hours_ago
            )
        ).all()
        
        # 更新状态为'cancelled'
        if expired_registrations:
            for reg in expired_registrations:
                reg.status = 'cancelled'
                reg.updated_at = datetime.utcnow()
            
            db.session.commit()
            print(f"Auto-updated {len(expired_registrations)} expired registrations to 'cancelled'")
        
        return len(expired_registrations)
    
    except Exception as e:
        db.session.rollback()
        print(f"Error auto-updating expired registrations: {str(e)}")
        return 0

# Authentication Routes
@api_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    
    if not username or not password or not role:
        return jsonify({'error': 'Missing credentials'}), 400
    
    user = None
    user_id = None
    
    if role == 'admin':
        user = Admin.query.filter_by(username=username).first()
        user_id = user.admin_id if user else None
    elif role == 'patient':
        user = Patient.query.filter_by(username=username).first()
        user_id = user.patient_id if user else None
    elif role == 'doctor':
        user = Doctor.query.filter_by(username=username).first()
        user_id = user.doctor_id if user else None
    else:
        return jsonify({'error': 'Invalid role'}), 400
    
    if user and user.check_password(password):
        access_token = create_access_token(
            identity=str(user_id),  # Convert to string
            additional_claims={'role': role, 'user_id': user_id}
        )
        return jsonify({
            'access_token': access_token,
            'role': role,
            'user_id': user_id,
            'username': username
        })
    
    return jsonify({'error': 'Invalid credentials'}), 401

@api_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    name = data.get('name')
    
    if not username or not password or not role or not name:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if username already exists
    existing_user = None
    if role == 'patient':
        existing_user = Patient.query.filter_by(username=username).first()
    elif role == 'doctor':
        existing_user = Doctor.query.filter_by(username=username).first()
    elif role == 'admin':
        return jsonify({'error': 'Admin registration not allowed'}), 403
    
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 400
    
    try:
        if role == 'patient':
            user = Patient(
                username=username,
                name=name,
                phone=data.get('phone'),
                gender=data.get('gender'),
                birthday=datetime.strptime(data.get('birthday'), '%Y-%m-%d').date() if data.get('birthday') else None
            )
        elif role == 'doctor':
            dept_id = data.get('dept_id')
            title_id = data.get('title_id')
            
            if not dept_id:
                return jsonify({'error': 'Department ID required for doctor'}), 400
            
            if not title_id:
                return jsonify({'error': 'Title ID required for doctor'}), 400
            
            user = Doctor(
                username=username,
                name=name,
                title_id=title_id,
                dept_id=dept_id
            )
        
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'User created successfully'}), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Public Routes
@api_bp.route('/departments', methods=['GET'])
def get_departments():
    departments = Department.query.all()
    return jsonify([dept.to_dict() for dept in departments])

@api_bp.route('/doctors', methods=['GET'])
def get_doctors():
    dept_id = request.args.get('dept_id')
    date_str = request.args.get('date')  # Format: YYYY-MM-DD
    time_str = request.args.get('time')  # Format: HH:MM
    
    if dept_id:
        doctors = Doctor.query.filter_by(dept_id=dept_id).all()
    else:
        doctors = Doctor.query.all()
    
    # Filter by schedule if date and time provided
    if date_str and time_str:
        try:
            from datetime import datetime
            date_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            weekday = date_time.weekday()
            hour = date_time.hour
            period = 'am' if hour < 12 else 'pm'
            
            # Filter doctors by availability
            available_doctors = []
            for doctor in doctors:
                if doctor.is_available(weekday, period):
                    available_doctors.append(doctor)
            doctors = available_doctors
        except:
            pass  # If parsing fails, return all doctors
    
    return jsonify([doctor.to_dict() for doctor in doctors])

# Test Route
@api_bp.route('/test', methods=['GET'])
def test_route():
    """测试端点"""
    return jsonify({'message': 'API is working', 'status': 'ok'})

# Patient Routes
@api_bp.route('/patient/profile', methods=['GET'])
@role_required('patient')
def get_patient_profile():
    """获取患者个人信息"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_id = claims.get('user_id')
    patient = Patient.query.get(user_id)
    
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    
    return jsonify(patient.to_dict())

@api_bp.route('/patient/profile', methods=['PUT'])
@role_required('patient')
def update_patient_profile():
    """更新患者个人信息"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_id = claims.get('user_id')
    patient = Patient.query.get(user_id)
    
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'name' in data:
            patient.name = data['name']
        if 'phone' in data:
            patient.phone = data['phone']
        if 'password' in data and data['password']:
            patient.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/patient/registrations', methods=['GET'])
@role_required('patient')
def get_patient_registrations():
    # 自动更新过期的挂号记录
    auto_update_expired_registrations()
    
    user_id, _ = get_current_user()
    registrations = Registration.query.filter_by(patient_id=user_id).all()
    return jsonify([reg.to_dict() for reg in registrations])

@api_bp.route('/register', methods=['POST'])
@api_bp.route('/registrations', methods=['POST'])
@role_required('patient')
def create_registration():
    user_id, _ = get_current_user()
    data = request.get_json()
    
    doctor_id = data.get('doctor_id')
    reg_time_str = data.get('reg_time')
    
    if not doctor_id or not reg_time_str:
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        # Parse the input datetime and convert to China timezone (UTC+8)
        try:
            # Try to parse as ISO format first
            if 'T' in reg_time_str:
                reg_time = datetime.fromisoformat(reg_time_str.replace('Z', '+00:00'))
            else:
                reg_time = datetime.strptime(reg_time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return jsonify({'error': 'Invalid datetime format'}), 400
        
        # Convert to China timezone (UTC+8)
        china_tz = timezone(timedelta(hours=8))
        if reg_time.tzinfo is None:
            # 假设输入的是中国时间
            reg_time = reg_time.replace(tzinfo=china_tz)
        else:
            reg_time = reg_time.astimezone(china_tz)
        
        # Convert to timezone-naive for database storage (in China time)
        reg_time = reg_time.replace(tzinfo=None)
        
        # Check if doctor exists
        doctor = Doctor.query.get(doctor_id)
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404
        
        # Check if registration time is valid
        # 根据具体预约时间判断是否可预约
        now = datetime.now()  # 假设服务器时间就是中国时间
        
        print(f"DEBUG: Current time: {now}")
        print(f"DEBUG: Registration time: {reg_time}")
        
        # 如果预约时间已经过去，不允许预约
        if reg_time <= now:
            return jsonify({'error': '预约时间已过，无法预约'}), 400
        
        # Check doctor's schedule availability
        # 注意：前端已经根据排班过滤了医生列表，所以这里不需要再次检查
        # 如果需要双重验证，可以取消下面的注释
        # weekday = reg_time.weekday()  # 0=Monday, 6=Sunday
        # hour = reg_time.hour
        # period = 'am' if hour < 12 else 'pm'
        # if not doctor.is_available(weekday, period):
        #     return jsonify({'error': 'Doctor is not available at this time'}), 400
        
        # Check for existing registration at the same time
        existing_reg = Registration.query.filter_by(
            doctor_id=doctor_id,
            reg_time=reg_time,
            status='registered'
        ).first()
        
        if existing_reg:
            return jsonify({'error': 'This time slot is already booked'}), 400
        
        # Calculate registration fee
        fee = doctor.get_registration_fee()
        
        # Create registration
        registration = Registration(
            patient_id=user_id,
            doctor_id=doctor_id,
            reg_time=reg_time,
            status='registered',
            fee=fee
        )
        
        db.session.add(registration)
        db.session.commit()
        
        return jsonify(registration.to_dict()), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/registrations/<int:reg_id>/cancel', methods=['POST'])
@role_required('patient')
def cancel_registration(reg_id):
    user_id, _ = get_current_user()
    
    registration = Registration.query.filter_by(
        reg_id=reg_id,
        patient_id=user_id,
        status='registered'
    ).first()
    
    if not registration:
        return jsonify({'error': 'Registration not found'}), 404
    
    # Check if cancellation is allowed (at least 1 hour before appointment)
    # Ensure timezone-naive comparison
    reg_time = registration.reg_time
    if reg_time.tzinfo is not None:
        reg_time = reg_time.replace(tzinfo=None)
    
    if reg_time <= datetime.now() + timedelta(hours=1):
        return jsonify({'error': 'Cannot cancel within 1 hour of appointment'}), 400
    
    try:
        db.session.delete(registration)
        db.session.commit()
        return jsonify({'message': 'Registration cancelled successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Doctor Routes
@api_bp.route('/doctor/stats', methods=['GET'])
@role_required('doctor')
def get_doctor_stats():
    """获取医生个人统计数据"""
    user_id, _ = get_current_user()
    
    # 获取该医生的所有挂号记录
    all_registrations = Registration.query.filter_by(doctor_id=user_id).all()
    
    # 统计数据
    total_registrations = len(all_registrations)
    active_registrations = len([r for r in all_registrations if r.status == 'registered'])
    completed_registrations = len([r for r in all_registrations if r.status == 'completed'])
    
    # 统计不同患者数
    patient_ids = set([r.patient_id for r in all_registrations])
    total_patients = len(patient_ids)
    
    return jsonify({
        'total_patients': total_patients,
        'total_registrations': total_registrations,
        'active_registrations': active_registrations,
        'completed_registrations': completed_registrations
    })

@api_bp.route('/doctor/trend', methods=['GET'])
@role_required('doctor')
def get_doctor_trend():
    """获取医生个人挂号趋势"""
    user_id, _ = get_current_user()
    
    # 获取该医生的所有挂号记录
    registrations = Registration.query.filter_by(doctor_id=user_id).all()
    
    # 按日期统计
    date_count = {}
    for reg in registrations:
        if reg.created_at:
            date_key = reg.created_at.date()
            date_count[date_key] = date_count.get(date_key, 0) + 1
    
    # 构建最近30天的数据
    trend_data = {'labels': [], 'data': []}
    today = datetime.utcnow().date()
    
    for i in range(29, -1, -1):
        date = today - timedelta(days=i)
        date_str = date.strftime('%m-%d')
        trend_data['labels'].append(date_str)
        trend_data['data'].append(date_count.get(date, 0))
    
    return jsonify(trend_data)

@api_bp.route('/doctor/profile', methods=['GET'])
@role_required('doctor')
def get_doctor_profile():
    """获取医生个人信息"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_id = claims.get('user_id')
    doctor = Doctor.query.get(user_id)
    
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    dept = Department.query.get(doctor.dept_id) if doctor.dept_id else None
    
    return jsonify({
        'doctor_id': doctor.doctor_id,
        'name': doctor.name,
        'title': doctor.title_info.title_name if doctor.title_info else '未设置',
        'title_id': doctor.title_id,
        'dept_id': doctor.dept_id,
        'dept_name': dept.dept_name if dept else None,
        'photo': doctor.photo  # 添加照片字段
    })

@api_bp.route('/doctor/profile', methods=['PUT'])
@role_required('doctor')
def update_doctor_profile():
    """更新医生个人信息"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_id = claims.get('user_id')
    doctor = Doctor.query.get(user_id)
    
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'name' in data:
            doctor.name = data['name']
        # 职称由管理员管理，医生不能自行修改
        # if 'title_id' in data:
        #     doctor.title_id = data['title_id']
        if 'password' in data and data['password']:
            doctor.set_password(data['password'])
        
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/doctor/photo', methods=['POST'])
@role_required('doctor')
def upload_doctor_photo():
    """医生上传个人照片"""
    from flask_jwt_extended import get_jwt
    from werkzeug.utils import secure_filename
    import os
    from flask import current_app
    
    claims = get_jwt()
    user_id = claims.get('user_id')
    doctor = Doctor.query.get(user_id)
    
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    # 检查是否有文件
    if 'photo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['photo']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # 验证文件类型
    def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif'}), 400
    
    try:
        # 生成安全的文件名
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"doctor_{user_id}.{ext}"
        
        # 保存文件
        upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'doctors')
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # 更新数据库
        doctor.photo = f"doctors/{filename}"
        db.session.commit()
        
        print(f"DEBUG: Photo saved for doctor {user_id}")
        print(f"DEBUG: Photo path in DB: {doctor.photo}")
        print(f"DEBUG: File saved to: {filepath}")
        
        return jsonify({
            'message': 'Photo uploaded successfully',
            'photo': doctor.photo
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/doctor/schedule', methods=['GET'])
@role_required('doctor')
def get_doctor_own_schedule():
    """获取医生自己的排班信息"""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    user_id = claims.get('user_id')
    doctor = Doctor.query.get(user_id)
    
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    import json
    schedule = {}
    if doctor.schedule:
        try:
            schedule = json.loads(doctor.schedule)
        except:
            schedule = {}
    
    return jsonify({
        'doctor_id': doctor.doctor_id,
        'doctor_name': doctor.name,
        'schedule': schedule
    })

@api_bp.route('/doctor/registrations', methods=['GET'])
@role_required('doctor')
def get_doctor_registrations():
    # 自动更新过期的挂号记录
    auto_update_expired_registrations()
    
    user_id, _ = get_current_user()
    registrations = Registration.query.filter_by(doctor_id=user_id).all()
    return jsonify([reg.to_dict() for reg in registrations])

@api_bp.route('/doctor/search', methods=['GET'])
@role_required('doctor')
def search_patients():
    user_id, _ = get_current_user()
    patient_name = request.args.get('patient_name', '')
    phone = request.args.get('phone', '')
    reg_id = request.args.get('reg_id', '')
    
    query = Registration.query.filter_by(doctor_id=user_id)
    
    if patient_name:
        query = query.join(Patient).filter(Patient.name.contains(patient_name))
    
    if phone:
        query = query.join(Patient).filter(Patient.phone.contains(phone))
    
    if reg_id:
        try:
            query = query.filter(Registration.reg_id == int(reg_id))
        except ValueError:
            return jsonify({'error': 'Invalid registration ID'}), 400
    
    registrations = query.all()
    return jsonify([reg.to_dict() for reg in registrations])

@api_bp.route('/registrations/<int:reg_id>/complete', methods=['POST'])
@role_required('doctor')
def complete_registration(reg_id):
    user_id, _ = get_current_user()
    
    registration = Registration.query.filter_by(
        reg_id=reg_id,
        doctor_id=user_id,
        status='registered'
    ).first()
    
    if not registration:
        return jsonify({'error': 'Registration not found'}), 404
    
    try:
        registration.status = 'completed'
        registration.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(registration.to_dict())
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Admin Routes
@api_bp.route('/admin/registrations', methods=['GET'])
@role_required('admin')
def get_all_registrations():
    # 自动更新过期的挂号记录
    auto_update_expired_registrations()
    
    registrations = Registration.query.all()
    return jsonify([reg.to_dict() for reg in registrations])

@api_bp.route('/admin/patients', methods=['GET'])
@role_required('admin')
def get_all_patients():
    patients = Patient.query.all()
    return jsonify([patient.to_dict() for patient in patients])

@api_bp.route('/admin/doctors', methods=['GET'])
@role_required('admin')
def get_all_doctors():
    doctors = Doctor.query.all()
    return jsonify([doctor.to_dict() for doctor in doctors])

@api_bp.route('/admin/doctors/<int:doctor_id>/schedule', methods=['GET'])
@role_required('admin')
def get_doctor_schedule(doctor_id):
    """获取医生排班信息"""
    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    import json
    schedule = {}
    if doctor.schedule:
        try:
            schedule = json.loads(doctor.schedule)
        except:
            schedule = {}
    
    return jsonify({
        'doctor_id': doctor.doctor_id,
        'doctor_name': doctor.name,
        'schedule': schedule
    })

@api_bp.route('/admin/doctors/<int:doctor_id>/schedule', methods=['PUT'])
@role_required('admin')
def update_doctor_schedule(doctor_id):
    """更新医生排班信息"""
    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    data = request.get_json()
    schedule = data.get('schedule', {})
    
    import json
    try:
        doctor.schedule = json.dumps(schedule)
        db.session.commit()
        return jsonify({
            'message': 'Schedule updated successfully',
            'doctor_id': doctor.doctor_id,
            'schedule': schedule
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/department', methods=['POST'])
@role_required('admin')
def create_department():
    data = request.get_json()
    dept_name = data.get('dept_name')
    location = data.get('location')
    
    if not dept_name or not location:
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        department = Department(dept_name=dept_name, location=location)
        db.session.add(department)
        db.session.commit()
        
        return jsonify(department.to_dict()), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/department/<int:dept_id>', methods=['PUT'])
@role_required('admin')
def update_department(dept_id):
    department = Department.query.get(dept_id)
    if not department:
        return jsonify({'error': 'Department not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'dept_name' in data:
            department.dept_name = data['dept_name']
        if 'location' in data:
            department.location = data['location']
        
        db.session.commit()
        return jsonify(department.to_dict())
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/department/<int:dept_id>', methods=['DELETE'])
@role_required('admin')
def delete_department(dept_id):
    department = Department.query.get(dept_id)
    if not department:
        return jsonify({'error': 'Department not found'}), 404
    
    # Check if department has doctors
    if department.doctors:
        return jsonify({'error': 'Cannot delete department with doctors'}), 400
    
    try:
        db.session.delete(department)
        db.session.commit()
        return jsonify({'message': 'Department deleted successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/department-trend', methods=['GET'])
@role_required('admin')
def get_department_trend():
    """获取指定科室的挂号趋势"""
    dept_name = request.args.get('dept_name')
    
    if not dept_name:
        return jsonify({'error': 'Department name is required'}), 400
    
    try:
        # 获取该科室
        dept = Department.query.filter_by(dept_name=dept_name).first()
        if not dept:
            return jsonify({'labels': ['无数据'], 'data': [0]})
        
        # 获取该科室的所有医生
        doctors = Doctor.query.filter_by(dept_id=dept.dept_id).all()
        doctor_ids = [d.doctor_id for d in doctors]
        
        # 获取这些医生的所有挂号记录
        registrations = Registration.query.filter(Registration.doctor_id.in_(doctor_ids)).all()
        
        # 按日期统计
        date_count = {}
        for reg in registrations:
            if reg.created_at:
                date_key = reg.created_at.date()
                date_count[date_key] = date_count.get(date_key, 0) + 1
        
        # 构建最近30天的完整数据
        trend_data = {'labels': [], 'data': []}
        today = datetime.utcnow().date()
        
        for i in range(29, -1, -1):  # 从30天前到今天
            date = today - timedelta(days=i)
            date_str = date.strftime('%m-%d')
            trend_data['labels'].append(date_str)
            trend_data['data'].append(date_count.get(date, 0))  # 没有数据则为0
        
        return jsonify(trend_data)
    
    except Exception as e:
        print(f"Error in get_department_trend: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/chart-data', methods=['GET'])
@role_required('admin')
def get_chart_data():
    """获取图表数据：科室分布和时间趋势"""
    try:
        # 1. 获取所有挂号记录
        all_registrations = Registration.query.all()
        
        # 统计各科室挂号数量
        dept_count = {}
        date_count = {}
        
        for reg in all_registrations:
            # 获取科室信息
            doctor = Doctor.query.get(reg.doctor_id)
            if doctor:
                dept = Department.query.get(doctor.dept_id)
                if dept:
                    dept_name = dept.dept_name
                    dept_count[dept_name] = dept_count.get(dept_name, 0) + 1
            
            # 统计日期
            if reg.created_at:
                date_key = reg.created_at.date()
                date_count[date_key] = date_count.get(date_key, 0) + 1
        
        # 构建科室数据
        if dept_count:
            department_data = {
                'labels': list(dept_count.keys()),
                'data': list(dept_count.values())
            }
        else:
            department_data = {
                'labels': ['暂无数据'],
                'data': [1]
            }
        
        # 构建最近30天的完整数据
        time_data = {'labels': [], 'data': []}
        today = datetime.utcnow().date()
        
        for i in range(29, -1, -1):  # 从30天前到今天
            date = today - timedelta(days=i)
            date_str = date.strftime('%m-%d')
            time_data['labels'].append(date_str)
            time_data['data'].append(date_count.get(date, 0))  # 没有数据则为0
        
        return jsonify({
            'department': department_data,
            'time': time_data
        })
    
    except Exception as e:
        print(f"Error in get_chart_data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/admin/stats', methods=['GET'])
@role_required('admin')
def get_stats():
    from datetime import datetime, timedelta
    
    total_patients = Patient.query.count()
    total_doctors = Doctor.query.count()
    total_departments = Department.query.count()
    total_registrations = Registration.query.count()
    active_registrations = Registration.query.filter_by(status='registered').count()
    completed_registrations = Registration.query.filter_by(status='completed').count()
    
    # 计算累计挂号费用（排除已取消的）
    total_fee_result = db.session.query(db.func.sum(Registration.fee)).filter(
        Registration.status != 'cancelled'
    ).scalar()
    total_fee = total_fee_result if total_fee_result else 0.0
    
    # 计算近30天的挂号费用
    thirty_days_ago = datetime.now() - timedelta(days=30)
    monthly_fee_result = db.session.query(db.func.sum(Registration.fee)).filter(
        Registration.status != 'cancelled',
        Registration.created_at >= thirty_days_ago
    ).scalar()
    monthly_fee = monthly_fee_result if monthly_fee_result else 0.0
    
    return jsonify({
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'total_departments': total_departments,
        'total_registrations': total_registrations,
        'active_registrations': active_registrations,
        'completed_registrations': completed_registrations,
        'total_fee': total_fee,
        'monthly_fee': monthly_fee
    })

# User management routes for admin - removed duplicate function

# Admin creation route
@api_bp.route('/admin/create_admin', methods=['POST'])
@role_required('admin')
def create_admin():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')  # 获取邮箱地址
    
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
    
    # 验证邮箱格式（如果提供了邮箱）
    if email:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({'error': 'Invalid email format'}), 400
    
    # Check if username already exists
    if Admin.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    # Check if email already exists (if provided)
    if email and Admin.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    try:
        admin = Admin(username=username, email=email)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        
        return jsonify({
            'message': 'Admin created successfully',
            'admin': admin.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Get all admins
@api_bp.route('/admin/admins', methods=['GET'])
@role_required('admin')
def get_all_admins():
    admins = Admin.query.all()
    return jsonify([admin.to_dict() for admin in admins])

# Delete user (admin, doctor, or patient) and their associated registrations
@api_bp.route('/admin/users/<string:role>/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(role, user_id):
    try:
        if role == 'admin':
            user = Admin.query.get(user_id)
            if not user:
                return jsonify({'error': 'Admin not found'}), 404
            
            # Prevent deleting the last admin
            if Admin.query.count() <= 1:
                return jsonify({'error': 'Cannot delete the last admin'}), 400
                
        elif role == 'doctor':
            user = Doctor.query.get(user_id)
            if not user:
                return jsonify({'error': 'Doctor not found'}), 404
                
            # Delete all registrations for this doctor
            Registration.query.filter_by(doctor_id=user_id).delete()
                
        elif role == 'patient':
            user = Patient.query.get(user_id)
            if not user:
                return jsonify({'error': 'Patient not found'}), 404
                
            # Delete all registrations for this patient
            Registration.query.filter_by(patient_id=user_id).delete()
        else:
            return jsonify({'error': 'Invalid role'}), 400
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': f'{role.capitalize()} and associated registrations deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Update admin information (email)
@api_bp.route('/admin/admins/<int:admin_id>', methods=['PUT'])
@role_required('admin')
def update_admin(admin_id):
    """
    更新管理员信息（邮箱）
    权限：只能编辑ID小于等于自己的管理员
    """
    from flask import g
    
    # 获取当前登录的管理员ID
    current_admin_id = g.current_user.get('user_id')
    
    # 检查权限：只能编辑ID小于等于自己的管理员
    if admin_id > current_admin_id:
        return jsonify({'error': 'Permission denied: You can only edit admins with ID less than or equal to yours'}), 403
    
    admin = Admin.query.get(admin_id)
    if not admin:
        return jsonify({'error': 'Admin not found'}), 404
    
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')  # 可选：更新密码
    
    try:
        # 更新邮箱
        if email is not None:
            # 验证邮箱格式
            if email:  # 如果邮箱不为空
                import re
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, email):
                    return jsonify({'error': 'Invalid email format'}), 400
                
                # 检查邮箱是否已被其他管理员使用
                existing_admin = Admin.query.filter_by(email=email).first()
                if existing_admin and existing_admin.admin_id != admin_id:
                    return jsonify({'error': 'Email already exists'}), 400
            
            admin.email = email
        
        # 更新密码（如果提供）
        if password:
            admin.set_password(password)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Admin updated successfully',
            'admin': admin.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Update patient information
@api_bp.route('/admin/patients/<int:patient_id>', methods=['PUT'])
@role_required('admin')
def update_patient(patient_id):
    patient = Patient.query.get(patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'name' in data:
            patient.name = data['name']
        if 'phone' in data:
            patient.phone = data['phone']
        if 'gender' in data:
            patient.gender = data['gender']
        if 'birthday' in data and data['birthday']:
            patient.birthday = datetime.strptime(data['birthday'], '%Y-%m-%d').date()
        
        db.session.commit()
        return jsonify(patient.to_dict())
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Update doctor information
@api_bp.route('/admin/doctors/<int:doctor_id>', methods=['PUT'])
@role_required('admin')
def update_doctor(doctor_id):
    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'name' in data:
            doctor.name = data['name']
        if 'title_id' in data:
            doctor.title_id = data['title_id']
        if 'dept_id' in data:
            doctor.dept_id = data['dept_id']
        
        db.session.commit()
        return jsonify(doctor.to_dict())
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Update registration
@api_bp.route('/admin/registrations/<int:reg_id>', methods=['PUT'])
@role_required('admin')
def update_registration(reg_id):
    registration = Registration.query.get(reg_id)
    if not registration:
        return jsonify({'error': 'Registration not found'}), 404
    
    data = request.get_json()
    
    try:
        if 'reg_time' in data:
            # Parse the datetime string
            reg_time_str = data['reg_time']
            if 'T' in reg_time_str:
                registration.reg_time = datetime.fromisoformat(reg_time_str.replace('Z', '+00:00'))
            else:
                registration.reg_time = datetime.strptime(reg_time_str, '%Y-%m-%d %H:%M:%S')
        
        if 'status' in data:
            registration.status = data['status']
        
        registration.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(registration.to_dict())
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Delete registration
@api_bp.route('/admin/registrations/<int:reg_id>', methods=['DELETE'])
@role_required('admin')
def delete_registration(reg_id):
    registration = Registration.query.get(reg_id)
    if not registration:
        return jsonify({'error': 'Registration not found'}), 404
    
    try:
        db.session.delete(registration)
        db.session.commit()
        return jsonify({'message': 'Registration deleted successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== 职称管理API ====================

@api_bp.route('/titles', methods=['GET'])
@role_required('admin')
def get_titles():
    """获取所有职称"""
    try:
        titles = Title.query.all()
        titles_data = []
        
        for title in titles:
            # 统计使用该职称的医生数量
            doctor_count = Doctor.query.filter_by(title_id=title.title_id).count()
            
            title_dict = title.to_dict()
            title_dict['doctor_count'] = doctor_count
            titles_data.append(title_dict)
        
        return jsonify({
            'success': True,
            'titles': titles_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取职称列表失败: {str(e)}'
        }), 500

@api_bp.route('/titles', methods=['POST'])
@role_required('admin')
def add_title():
    """添加新职称"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        if not data.get('title_name'):
            return jsonify({
                'success': False,
                'message': '职称名称不能为空'
            }), 400
        
        if not data.get('registration_fee'):
            return jsonify({
                'success': False,
                'message': '挂号费不能为空'
            }), 400
        
        # 检查职称名称是否已存在
        existing_title = Title.query.filter_by(title_name=data['title_name']).first()
        if existing_title:
            return jsonify({
                'success': False,
                'message': '该职称名称已存在'
            }), 400
        
        # 验证挂号费
        try:
            registration_fee = float(data['registration_fee'])
            if registration_fee < 0:
                return jsonify({
                    'success': False,
                    'message': '挂号费不能为负数'
                }), 400
        except ValueError:
            return jsonify({
                'success': False,
                'message': '挂号费格式不正确'
            }), 400
        
        # 创建新职称
        new_title = Title(
            title_name=data['title_name'].strip(),
            registration_fee=registration_fee
        )
        
        db.session.add(new_title)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '职称添加成功',
            'title': new_title.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'添加职称失败: {str(e)}'
        }), 500

@api_bp.route('/titles/<int:title_id>', methods=['PUT'])
@role_required('admin')
def update_title(title_id):
    """更新职称信息"""
    try:
        title = Title.query.get(title_id)
        if not title:
            return jsonify({
                'success': False,
                'message': '职称不存在'
            }), 404
        
        data = request.get_json()
        
        # 验证职称名称
        if 'title_name' in data:
            if not data['title_name'].strip():
                return jsonify({
                    'success': False,
                    'message': '职称名称不能为空'
                }), 400
            
            # 检查名称是否与其他职称重复
            existing_title = Title.query.filter(
                Title.title_name == data['title_name'].strip(),
                Title.title_id != title_id
            ).first()
            
            if existing_title:
                return jsonify({
                    'success': False,
                    'message': '该职称名称已存在'
                }), 400
            
            title.title_name = data['title_name'].strip()
        
        # 验证挂号费
        if 'registration_fee' in data:
            try:
                registration_fee = float(data['registration_fee'])
                if registration_fee < 0:
                    return jsonify({
                        'success': False,
                        'message': '挂号费不能为负数'
                    }), 400
                title.registration_fee = registration_fee
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': '挂号费格式不正确'
                }), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '职称更新成功',
            'title': title.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'更新职称失败: {str(e)}'
        }), 500

@api_bp.route('/titles/<int:title_id>', methods=['DELETE'])
@role_required('admin')
def delete_title(title_id):
    """删除职称"""
    try:
        title = Title.query.get(title_id)
        if not title:
            return jsonify({
                'success': False,
                'message': '职称不存在'
            }), 404
        
        # 检查是否有医生使用该职称
        doctor_count = Doctor.query.filter_by(title_id=title_id).count()
        if doctor_count > 0:
            return jsonify({
                'success': False,
                'message': f'无法删除该职称，还有 {doctor_count} 名医生使用该职称'
            }), 400
        
        db.session.delete(title)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '职称删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'删除职称失败: {str(e)}'
        }), 500

@api_bp.route('/titles/public', methods=['GET'])
def get_titles_public():
    """获取所有职称（公开接口，用于医生注册等）"""
    try:
        titles = Title.query.all()
        titles_data = [title.to_dict() for title in titles]
        
        return jsonify({
            'success': True,
            'titles': titles_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取职称列表失败: {str(e)}'
        }), 500
