from datetime import datetime
from passlib.hash import pbkdf2_sha256
from app import db

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' or 'user'
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    stock_adjustments = db.relationship('StockAdjustment', back_populates='user')

    def __init__(self, username, password, role='user'):
        self.username = username
        self.set_password(password)
        self.role = role

    def set_password(self, password):
        """Hash the password before storing."""
        self.password_hash = pbkdf2_sha256.hash(password)

    def check_password(self, password):
        """Verify the password."""
        return pbkdf2_sha256.verify(password, self.password_hash)

    def to_dict(self):
        """Convert user object to dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    def __repr__(self):
        return f'<User {self.username}>'
