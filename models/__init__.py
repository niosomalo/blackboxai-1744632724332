from .database import db

# Import models in order of dependency
from .user import User
from .bahan import BahanBaku
from .menu import Menu
from .resep import Resep
from .log_pemakaian import LogPemakaian
from .penjualan import Penjualan
from .stock_adjustment import StockAdjustment
from .forecast import ForecastSettings, StockForecast

# Make models available at package level
__all__ = [
    'db',
    'User',
    'BahanBaku',
    'Menu',
    'Resep',
    'LogPemakaian',
    'Penjualan',
    'StockAdjustment',
    'ForecastSettings',
    'StockForecast'
]
