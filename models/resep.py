from datetime import datetime
from app import db
from sqlalchemy import event

class Resep(db.Model):
    __tablename__ = 'resep'

    id = db.Column(db.Integer, primary_key=True)
    id_menu = db.Column(db.Integer, db.ForeignKey('menu.id_menu', ondelete='CASCADE'), nullable=False)
    id_bahan = db.Column(db.Integer, db.ForeignKey('bahan_baku.id_bahan'), nullable=False)
    jumlah = db.Column(db.Float, nullable=False)  # Amount in grams
    waste_percent = db.Column(db.Float, nullable=False, default=0)  # Waste percentage
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    menu = db.relationship('Menu', back_populates='resep')
    bahan_baku = db.relationship('BahanBaku', back_populates='resep')

    def __init__(self, id_menu, id_bahan, jumlah, waste_percent=0):
        self.id_menu = id_menu
        self.id_bahan = id_bahan
        self.jumlah = jumlah
        self.waste_percent = waste_percent

    def calculate_total_usage(self, quantity=1):
        """
        Calculate total ingredient usage including waste
        quantity: number of menu items to be prepared
        """
        base_usage = self.jumlah * quantity
        waste_amount = base_usage * (self.waste_percent / 100)
        return base_usage + waste_amount

    def calculate_cost(self, quantity=1):
        """
        Calculate total cost for this ingredient including waste
        quantity: number of menu items to be prepared
        """
        total_usage = self.calculate_total_usage(quantity)
        return total_usage * self.bahan.harga_per_gram

    def check_stock_availability(self, quantity=1):
        """
        Check if enough stock is available for the specified quantity
        Returns tuple (bool, float) where float is the shortage amount if any
        """
        required = self.calculate_total_usage(quantity)
        available = self.bahan.stok_real
        if available < required:
            return False, required - available
        return True, 0

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id': self.id,
            'id_menu': self.id_menu,
            'id_bahan': self.id_bahan,
            'nama_bahan': self.bahan.nama_bahan,  # Include ingredient name for convenience
            'jumlah': self.jumlah,
            'satuan': self.bahan.satuan,  # Include unit for convenience
            'waste_percent': self.waste_percent,
            'cost_per_unit': self.bahan.harga_per_gram,
            'total_cost': self.calculate_cost(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    def __repr__(self):
        return f'<Resep Menu:{self.id_menu} Bahan:{self.id_bahan}>'

@event.listens_for(Resep, 'before_insert')
@event.listens_for(Resep, 'before_update')
def validate_resep(mapper, connection, target):
    """Validate recipe data before save"""
    if target.jumlah <= 0:
        raise ValueError("Jumlah bahan harus lebih dari 0")
    if target.waste_percent < 0:
        raise ValueError("Persentase waste tidak boleh negatif")
    if target.waste_percent > 100:
        raise ValueError("Persentase waste tidak boleh lebih dari 100%")

# Add unique constraint to prevent duplicate ingredients in a recipe
db.Index('uix_menu_bahan', Resep.id_menu, Resep.id_bahan, unique=True)
