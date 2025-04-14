from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, 
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from datetime import datetime, timezone
from models import db, User
from werkzeug.security import generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint
    Expects JSON: {
        "username": "string",
        "password": "string"
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                'error': 'Missing username or password'
            }), 400

        user = User.query.filter_by(username=data['username']).first()
        
        if not user or not user.check_password(data['password']):
            return jsonify({
                'error': 'Invalid username or password'
            }), 401

        # Create tokens
        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        return jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@auth_bp.route('/register', methods=['POST'])
@jwt_required()  # Only authenticated users can create new users
def register():
    """
    Register new user endpoint
    Expects JSON: {
        "username": "string",
        "password": "string",
        "role": "string" (optional, defaults to "user")
    }
    """
    try:
        # Check if requester is admin
        current_user = User.query.get(get_jwt_identity())
        if not current_user or current_user.role != 'admin':
            return jsonify({
                'error': 'Unauthorized. Only admins can create new users.'
            }), 403

        data = request.get_json()
        
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({
                'error': 'Missing required fields'
            }), 400

        # Check if username already exists
        if User.query.filter_by(username=data['username']).first():
            return jsonify({
                'error': 'Username already exists'
            }), 409

        # Create new user
        new_user = User(
            username=data['username'],
            password=data['password'],
            role=data.get('role', 'user')
        )
        
        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            'message': 'User created successfully',
            'user': new_user.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': str(e)
        }), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    try:
        current_user_id = get_jwt_identity()
        new_access_token = create_access_token(identity=current_user_id)
        
        return jsonify({
            'access_token': new_access_token
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout endpoint"""
    try:
        jti = get_jwt()['jti']
        # Here you might want to add the token to a blocklist
        # This is just a basic implementation
        return jsonify({
            'message': 'Successfully logged out'
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user information"""
    try:
        current_user = User.query.get(get_jwt_identity())
        if not current_user:
            return jsonify({
                'error': 'User not found'
            }), 404

        return jsonify(current_user.to_dict()), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

# Create initial admin user if none exists
def create_admin_if_not_exists():
    try:
        if not User.query.filter_by(role='admin').first():
            admin = User(
                username='admin',
                password='admin123',  # Change this in production!
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created successfully')
    except Exception as e:
        print(f'Error creating admin user: {str(e)}')
        db.session.rollback()
