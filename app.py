from flask import Flask, send_from_directory
from flask_jwt_extended import JWTManager
from config import Config
from models.database import db
import os

jwt = JWTManager()

def create_app(config_class=Config):
    app = Flask(__name__, static_folder='frontend')
    app.config.from_object(config_class)

    # Initialize extensions with app
    db.init_app(app)
    jwt.init_app(app)

    # Import and register blueprints
    from routes.auth import auth_bp, create_admin_if_not_exists
    from routes.bahan import bahan_bp
    from routes.menu import menu_bp
    from routes.penjualan import penjualan_bp
    from routes.stock import stock_bp
    from routes.reports import reports_bp
    from routes.forecast import forecast_bp

    # Register API routes
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(bahan_bp, url_prefix='/api/bahan')
    app.register_blueprint(menu_bp, url_prefix='/api/menu')
    app.register_blueprint(penjualan_bp, url_prefix='/api/penjualan')
    app.register_blueprint(stock_bp, url_prefix='/api/stock')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(forecast_bp, url_prefix='/api/forecast')

    # Serve frontend files
    @app.route('/')
    def index():
        return send_from_directory('frontend', 'login.html')

    @app.route('/<path:path>')
    def serve_frontend(path):
        if os.path.exists(os.path.join('frontend', path)):
            return send_from_directory('frontend', path)
        return send_from_directory('frontend', 'login.html')

    # Create database tables and initial admin user
    with app.app_context():
        db.create_all()
        create_admin_if_not_exists()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=8000)
