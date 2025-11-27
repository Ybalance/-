from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

def role_required(required_role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role')
            
            if user_role != required_role:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """Get current user ID and role from JWT token"""
    claims = get_jwt()
    user_id = claims.get('user_id')
    role = claims.get('role')
    return user_id, role
