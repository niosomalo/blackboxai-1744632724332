from datetime import datetime
from app import db
from sqlalchemy import event

class LogPemakaian(db.Model):
    __tablename__ = 'log_pemakaian'

    id = db.Column(db.Integer, primary_key=True)
    id_penjualan = db.Column(db.Integer, db.ForeignKey('penjualan.id_penjualan'), nullable=False)
    id_bahan = db.Column(db.Integer, db.ForeignKey('bahan_baku.id_bahan'), nullable=False)
    jumlah_terpakai = db.Column(db.Float, nullable=False)  # Amount used in grams
    waste_amount = db.Column(db.Float, nullable=False, default=0)  # Waste amount in grams
    cost = db.Column(db.Float, nullable=False)  # Total cost including waste
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships using back_populates instead of backref
    penjualan = db.relationship('Penjualan', back_populates='usage_logs')
    bahan_baku = db.relationship('BahanBaku', back_populates='usage_logs')

    def __init__(self, id_penjualan, id_bahan, jumlah_terpakai, waste_amount=0):
        self.id_penjualan = id_penjualan
        self.id_bahan = id_bahan
        self.jumlah_terpakai = jumlah_terpakai
        self.waste_amount = waste_amount
        
        # Calculate cost based on ingredient price
        bahan = db.session.get(BahanBaku, id_bahan)  # Fixed reference to BahanBaku
        total_amount = jumlah_terpakai + waste_amount
        self.cost = total_amount * bahan.harga_per_gram if bahan else 0

    @property
    def waste_percentage(self):
        """Calculate waste percentage"""
        if self.jumlah_terpakai > 0:
            return (self.waste_amount / (self.jumlah_terpakai + self.waste_amount)) * 100
        return 0

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id': self.id,
            'id_penjualan': self.id_penjualan,
            'id_bahan': self.id_bahan,
            'nama_bahan': self.bahan_baku.nama_bahan if self.bahan_baku else None,
            'jumlah_terpakai': self.jumlah_terpakai,
            'waste_amount': self.waste_amount,
            'waste_percentage': self.waste_percentage,
            'cost': self.cost,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def get_usage_summary(cls, start_date=None, end_date=None, id_bahan=None):
        """Get usage summary for a period"""
        query = cls.query

        if start_date:
            query = query.filter(cls.created_at >= start_date)
        if end_date:
            query = query.filter(cls.created_at <= end_date)
        if id_bahan:
            query = query.filter_by(id_bahan=id_bahan)

        result = query.with_entities(
            db.func.sum(cls.jumlah_terpakai).label('total_used'),
            db.func.sum(cls.waste_amount).label('total_waste'),
            db.func.sum(cls.cost).label('total_cost')
        ).first()

        total_used = float(result.total_used or 0)
        total_waste = float(result.total_waste or 0)
        total_cost = float(result.total_cost or 0)

        return {
            'total_used': total_used,
            'total_waste': total_waste,
            'total_cost': total_cost,
            'waste_percentage': (
                (total_waste / (total_used + total_waste)) * 100
                if total_used > 0
                else 0
            )
        }

    def __repr__(self):
        return f'<LogPemakaian {self.id_bahan} Amount:{self.jumlah_terpakai}g>'

@event.listens_for(LogPemakaian, 'before_insert')
def validate_log(mapper, connection, target):
    """Validate log data before save"""
    if target.jumlah_terpakai < 0:
        raise ValueError("Jumlah terpakai tidak boleh negatif")
    if target.waste_amount < 0:
        raise ValueError("Waste amount tidak boleh negatif")
