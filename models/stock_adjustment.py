from datetime import datetime
from app import db
from sqlalchemy import event

class StockAdjustment(db.Model):
    __tablename__ = 'stock_adjustment'

    id = db.Column(db.Integer, primary_key=True)
    id_bahan = db.Column(db.Integer, db.ForeignKey('bahan_baku.id_bahan'), nullable=False)
    stok_sistem = db.Column(db.Float, nullable=False)  # System stock before adjustment
    stok_real = db.Column(db.Float, nullable=False)    # Actual physical stock
    selisih = db.Column(db.Float, nullable=False)      # Difference (can be positive or negative)
    keterangan = db.Column(db.Text, nullable=True)     # Reason for adjustment
    tanggal = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Who made the adjustment

    # Relationships
    bahan_baku = db.relationship('BahanBaku', back_populates='stock_adjustments')
    user = db.relationship('User', back_populates='stock_adjustments')

    def __init__(self, id_bahan, stok_sistem, stok_real, keterangan=None, created_by=None):
        self.id_bahan = id_bahan
        self.stok_sistem = stok_sistem
        self.stok_real = stok_real
        self.selisih = stok_real - stok_sistem
        self.keterangan = keterangan
        self.created_by = created_by

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id': self.id,
            'id_bahan': self.id_bahan,
            'nama_bahan': self.bahan.nama_bahan,  # Include ingredient name for convenience
            'stok_sistem': self.stok_sistem,
            'stok_real': self.stok_real,
            'selisih': self.selisih,
            'keterangan': self.keterangan,
            'tanggal': self.tanggal.isoformat(),
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by
        }

    @classmethod
    def get_adjustments_by_date(cls, start_date=None, end_date=None, id_bahan=None):
        """Get adjustments for a specific period and/or ingredient"""
        query = cls.query

        if start_date:
            query = query.filter(cls.tanggal >= start_date)
        if end_date:
            query = query.filter(cls.tanggal <= end_date)
        if id_bahan:
            query = query.filter_by(id_bahan=id_bahan)

        return query.order_by(cls.tanggal.desc()).all()

    def __repr__(self):
        return f'<StockAdjustment Bahan:{self.id_bahan} Selisih:{self.selisih}>'

@event.listens_for(StockAdjustment, 'before_insert')
@event.listens_for(StockAdjustment, 'before_update')
def validate_adjustment(mapper, connection, target):
    """Validate adjustment data before save"""
    if target.stok_real < 0:
        raise ValueError("Stok real tidak boleh negatif")
    if not target.keterangan and target.selisih != 0:
        raise ValueError("Keterangan wajib diisi untuk penyesuaian stok")
