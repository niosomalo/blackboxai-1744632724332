from datetime import datetime
from app import db
from sqlalchemy import event
from .log_pemakaian import LogPemakaian

class Penjualan(db.Model):
    __tablename__ = 'penjualan'

    id_penjualan = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.Date, nullable=False, index=True)
    id_menu = db.Column(db.Integer, db.ForeignKey('menu.id_menu'), nullable=False)
    jumlah_terjual = db.Column(db.Integer, nullable=False)
    total_cogs = db.Column(db.Float, nullable=False)  # Total cost of goods sold
    total_sales = db.Column(db.Float, nullable=False)  # Total sales amount
    profit = db.Column(db.Float, nullable=False)  # Profit from this sale
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    menu = db.relationship('Menu', back_populates='penjualan')
    usage_logs = db.relationship('LogPemakaian', back_populates='penjualan', lazy=True,
                               cascade='all, delete-orphan')

    def __init__(self, tanggal, id_menu, jumlah_terjual):
        self.tanggal = tanggal
        self.id_menu = id_menu
        self.jumlah_terjual = jumlah_terjual
        # These will be calculated before insert
        self.total_cogs = 0
        self.total_sales = 0
        self.profit = 0

    def process_sale(self):
        """
        Process the sale: calculate costs, update inventory, and create usage logs
        Returns tuple (success, message)
        """
        try:
            # Check stock availability first
            available, shortages = self.menu.check_stock_availability(self.jumlah_terjual)
            if not available:
                shortage_details = ", ".join([
                    f"{bahan}: kurang {details['shortage']:.2f} {details['available']}"
                    for bahan, details in shortages.items()
                ])
                return False, f"Stok tidak mencukupi: {shortage_details}"

            # Calculate total sales amount
            self.total_sales = self.menu.harga_jual * self.jumlah_terjual
            
            # Process each ingredient in the recipe
            total_cogs = 0
            usage_logs = []

            for resep_item in self.menu.resep:
                # Calculate usage including waste
                base_usage = resep_item.jumlah * self.jumlah_terjual
                waste_amount = base_usage * (resep_item.waste_percent / 100)
                total_usage = base_usage + waste_amount

                # Calculate cost for this ingredient
                ingredient_cost = total_usage * resep_item.bahan.harga_per_gram
                total_cogs += ingredient_cost

                # Create usage log
                log = LogPemakaian(
                    id_penjualan=self.id_penjualan,
                    id_bahan=resep_item.id_bahan,
                    jumlah_terpakai=base_usage,
                    waste_amount=waste_amount
                )
                self.usage_logs.append(log)

                # Update stock
                resep_item.bahan.update_stok(total_usage)

            # Update sale totals
            self.total_cogs = total_cogs
            self.profit = self.total_sales - total_cogs

            # Add usage logs to session
            for log in usage_logs:
                db.session.add(log)

            return True, "Penjualan berhasil diproses"

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def to_dict(self, include_details=False):
        """Convert object to dictionary"""
        sale_dict = {
            'id_penjualan': self.id_penjualan,
            'tanggal': self.tanggal.isoformat(),
            'id_menu': self.id_menu,
            'nama_menu': self.menu.nama_menu,
            'jumlah_terjual': self.jumlah_terjual,
            'total_cogs': self.total_cogs,
            'total_sales': self.total_sales,
            'profit': self.profit,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

        if include_details:
            sale_dict['usage_details'] = [log.to_dict() for log in self.usage_logs]

        return sale_dict

    def __repr__(self):
        return f'<Penjualan {self.id_penjualan} Menu:{self.id_menu} Qty:{self.jumlah_terjual}>'

@event.listens_for(Penjualan, 'before_insert')
def validate_penjualan(mapper, connection, target):
    """Validate sales data before save"""
    if target.jumlah_terjual <= 0:
        raise ValueError("Jumlah terjual harus lebih dari 0")
    if target.tanggal > datetime.now().date():
        raise ValueError("Tanggal penjualan tidak boleh di masa depan")
