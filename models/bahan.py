from datetime import datetime
from app import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event

class BahanBaku(db.Model):
    __tablename__ = 'bahan_baku'

    id_bahan = db.Column(db.Integer, primary_key=True)
    nama_bahan = db.Column(db.String(100), nullable=False)
    satuan = db.Column(db.String(20), nullable=False)
    stok_awal = db.Column(db.Float, nullable=False)
    stok_real = db.Column(db.Float, nullable=False)  # Actual stock after physical count
    harga_per_gram = db.Column(db.Float, nullable=False)
    min_stok = db.Column(db.Float, nullable=False, default=0)  # Minimum stock level
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    resep = db.relationship('Resep', back_populates='bahan_baku', lazy=True)
    usage_logs = db.relationship('LogPemakaian', back_populates='bahan_baku', lazy=True)
    stock_adjustments = db.relationship('StockAdjustment', back_populates='bahan_baku', lazy=True)

    def __init__(self, nama_bahan, satuan, stok_awal, harga_per_gram, min_stok=0):
        self.nama_bahan = nama_bahan
        self.satuan = satuan
        self.stok_awal = stok_awal
        self.stok_real = stok_awal  # Initially, real stock equals initial stock
        self.harga_per_gram = harga_per_gram
        self.min_stok = min_stok

    def update_stok(self, jumlah_terpakai):
        """
        Update stock level after usage
        Returns True if successful, raises ValueError if insufficient stock
        """
        if self.stok_real < jumlah_terpakai:
            raise ValueError(f"Stok {self.nama_bahan} tidak mencukupi. Tersedia: {self.stok_real}, Dibutuhkan: {jumlah_terpakai}")
        
        self.stok_real -= jumlah_terpakai
        self.stok_awal = self.stok_real  # Keep stok_awal synchronized
        return True

    def adjust_stock(self, new_stock, keterangan=""):
        """
        Adjust stock based on physical count
        """
        old_stock = self.stok_real
        self.stok_real = new_stock
        self.stok_awal = new_stock  # Keep stok_awal synchronized
        
        # Create stock adjustment record
        adjustment = StockAdjustment(
            id_bahan=self.id_bahan,
            stok_sistem=old_stock,
            stok_real=new_stock,
            selisih=new_stock - old_stock,
            keterangan=keterangan
        )
        db.session.add(adjustment)

    def is_low_stock(self):
        """Check if current stock is below minimum level"""
        return self.stok_real <= self.min_stok

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id_bahan': self.id_bahan,
            'nama_bahan': self.nama_bahan,
            'satuan': self.satuan,
            'stok_awal': self.stok_awal,
            'stok_real': self.stok_real,
            'harga_per_gram': self.harga_per_gram,
            'min_stok': self.min_stok,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_low_stock': self.is_low_stock()
        }

    def __repr__(self):
        return f'<BahanBaku {self.nama_bahan}>'

@event.listens_for(BahanBaku, 'before_insert')
@event.listens_for(BahanBaku, 'before_update')
def validate_bahan(mapper, connection, target):
    """Validate bahan data before save"""
    if target.stok_real < 0:
        raise ValueError("Stok tidak boleh negatif")
    if target.harga_per_gram < 0:
        raise ValueError("Harga tidak boleh negatif")
    if target.min_stok < 0:
        raise ValueError("Minimum stok tidak boleh negatif")
