from datetime import datetime
from app import db

class Menu(db.Model):
    __tablename__ = 'menu'

    id_menu = db.Column(db.Integer, primary_key=True)
    nama_menu = db.Column(db.String(100), nullable=False, unique=True)
    deskripsi = db.Column(db.Text, nullable=True)
    harga_jual = db.Column(db.Float, nullable=False)  # Selling price
    stok_real = db.Column(db.Float, nullable=False, default=0)  # Actual stock after physical count
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resep = db.relationship('Resep', back_populates='menu', lazy=True, cascade='all, delete-orphan')
    penjualan = db.relationship('Penjualan', back_populates='menu', lazy=True)

    def __init__(self, nama_menu, harga_jual, deskripsi=None, stok_real=0):
        self.nama_menu = nama_menu
        self.harga_jual = harga_jual
        self.deskripsi = deskripsi
        self.stok_real = stok_real

    def calculate_cogs(self):
        """Calculate Cost of Goods Sold for this menu item"""
        total_cost = 0
        for item in self.resep:
            # Cost = amount of ingredient × price per gram
            item_cost = item.jumlah * item.bahan.harga_per_gram
            # Add waste cost
            waste_cost = item_cost * (item.waste_percent / 100)
            total_cost += item_cost + waste_cost
        return total_cost

    def get_profit_margin(self):
        """Calculate profit margin percentage"""
        cogs = self.calculate_cogs()
        if cogs == 0:
            return 0
        return ((self.harga_jual - cogs) / self.harga_jual) * 100

    def check_stock_availability(self, quantity=1):
        """
        Check if enough stock is available for all ingredients
        Returns tuple (bool, dict) where dict contains shortage details if any
        """
        shortages = {}
        for item in self.resep:
            required = item.jumlah * quantity * (1 + item.waste_percent / 100)
            if item.bahan.stok_real < required:
                shortages[item.bahan.nama_bahan] = {
                    'required': required,
                    'available': item.bahan.stok_real,
                    'shortage': required - item.bahan.stok_real
                }
        return (len(shortages) == 0, shortages)

    def to_dict(self, include_resep=False):
        """Convert object to dictionary"""
        menu_dict = {
            'id_menu': self.id_menu,
            'nama_menu': self.nama_menu,
            'deskripsi': self.deskripsi,
            'harga_jual': self.harga_jual,
            'stok_real': self.stok_real,
            'is_active': self.is_active,
            'cogs': self.calculate_cogs(),
            'profit_margin': self.get_profit_margin(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        if include_resep:
            menu_dict['resep'] = [item.to_dict() for item in self.resep]
        
        return menu_dict

    def adjust_stock(self, new_stock, keterangan=""):
        """
        Adjust stock based on physical count
        """
        if new_stock < 0:
            raise ValueError("Stok tidak boleh negatif")
            
        self.stok_real = new_stock
        db.session.commit()
        
    def __repr__(self):
        return f'<Menu {self.nama_menu}>'
