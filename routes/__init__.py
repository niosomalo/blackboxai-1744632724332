from flask import Blueprint

# Import all blueprints
from .auth import auth_bp
from .bahan import bahan_bp
from .menu import menu_bp
from .penjualan import penjualan_bp
from .stock import stock_bp
from .reports import reports_bp
from .forecast import forecast_bp

# List of all blueprints for easy import
all_blueprints = [
    auth_bp,
    bahan_bp,
    menu_bp,
    penjualan_bp,
    stock_bp,
    reports_bp,
    forecast_bp
]

def init_routes(app):
    """Register all blueprints with the app"""
    for blueprint in all_blueprints:
        app.register_blueprint(blueprint)
