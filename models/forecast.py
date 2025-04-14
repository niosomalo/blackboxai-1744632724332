from datetime import datetime, timedelta
from app import db
from sqlalchemy import event
import numpy as np
from sqlalchemy import func
from .log_pemakaian import LogPemakaian
from .penjualan import Penjualan

class ForecastSettings(db.Model):
    __tablename__ = 'forecast_settings'

    id = db.Column(db.Integer, primary_key=True)
    id_bahan = db.Column(db.Integer, db.ForeignKey('bahan_baku.id_bahan'), nullable=False)
    min_stok = db.Column(db.Float, nullable=False)  # Minimum stock level
    lead_time = db.Column(db.Integer, nullable=False)  # Order lead time in days
    safety_stock = db.Column(db.Float, nullable=False)  # Safety stock amount
    forecast_period = db.Column(db.Integer, nullable=False, default=7)  # Days to forecast
    analysis_period = db.Column(db.Integer, nullable=False, default=30)  # Historical days to analyze
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with forecasts
    forecasts = db.relationship('StockForecast', backref='settings', lazy=True)

    def __init__(self, id_bahan, min_stok, lead_time, safety_stock, 
                 forecast_period=7, analysis_period=30):
        self.id_bahan = id_bahan
        self.min_stok = min_stok
        self.lead_time = lead_time
        self.safety_stock = safety_stock
        self.forecast_period = forecast_period
        self.analysis_period = analysis_period

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id': self.id,
            'id_bahan': self.id_bahan,
            'min_stok': self.min_stok,
            'lead_time': self.lead_time,
            'safety_stock': self.safety_stock,
            'forecast_period': self.forecast_period,
            'analysis_period': self.analysis_period,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class StockForecast(db.Model):
    __tablename__ = 'stock_forecast'

    id = db.Column(db.Integer, primary_key=True)
    id_bahan = db.Column(db.Integer, db.ForeignKey('bahan_baku.id_bahan'), nullable=False)
    id_settings = db.Column(db.Integer, db.ForeignKey('forecast_settings.id'), nullable=False)
    tanggal = db.Column(db.Date, nullable=False)
    prediksi_penggunaan = db.Column(db.Float, nullable=False)  # Predicted usage
    rekomendasi_pembelian = db.Column(db.Float, nullable=False)  # Recommended purchase amount
    confidence_level = db.Column(db.Float, nullable=False)  # Prediction confidence (0-1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @classmethod
    def generate_forecast(cls, id_bahan, settings=None):
        """
        Generate forecast for a specific ingredient
        Returns tuple (success, result/error_message)
        """
        try:
            if not settings:
                settings = ForecastSettings.query.filter_by(id_bahan=id_bahan).first()
                if not settings:
                    return False, "Forecast settings not found for this ingredient"

            # Get historical usage data
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=settings.analysis_period)
            
            usage_data = db.session.query(
                func.date(LogPemakaian.created_at).label('date'),
                func.sum(LogPemakaian.jumlah_terpakai + LogPemakaian.waste_amount).label('total_usage')
            ).filter(
                LogPemakaian.id_bahan == id_bahan,
                LogPemakaian.created_at.between(start_date, end_date)
            ).group_by(
                func.date(LogPemakaian.created_at)
            ).all()

            if not usage_data:
                return False, "Insufficient historical data for forecast"

            # Convert to numpy arrays for calculation
            dates = np.array(range(len(usage_data)))
            usage = np.array([x.total_usage for x in usage_data])

            # Simple linear regression for prediction
            coefficients = np.polyfit(dates, usage, 1)
            polynomial = np.poly1d(coefficients)

            # Generate predictions for future dates
            future_dates = np.array(range(len(dates), len(dates) + settings.forecast_period))
            predictions = polynomial(future_dates)

            # Calculate confidence level based on R-squared
            y_mean = np.mean(usage)
            r_squared = 1 - (np.sum((usage - polynomial(dates))**2) / np.sum((usage - y_mean)**2))
            confidence = max(min(r_squared, 1), 0)  # Ensure between 0 and 1

            # Create forecast records
            forecasts = []
            current_stock = db.session.query(db.Model.bahan_baku).get(id_bahan).stok_real

            for i, pred in enumerate(predictions):
                forecast_date = end_date + timedelta(days=i+1)
                pred_usage = max(0, pred)  # Ensure non-negative prediction
                
                # Calculate recommended purchase
                projected_stock = current_stock - sum(predictions[:i+1])
                needed_stock = pred_usage * (settings.lead_time + 1) + settings.safety_stock
                
                recommended_purchase = max(0, needed_stock - projected_stock) if projected_stock < settings.min_stok else 0

                forecast = cls(
                    id_bahan=id_bahan,
                    id_settings=settings.id,
                    tanggal=forecast_date,
                    prediksi_penggunaan=pred_usage,
                    rekomendasi_pembelian=recommended_purchase,
                    confidence_level=confidence
                )
                forecasts.append(forecast)

            # Save forecasts
            for forecast in forecasts:
                db.session.add(forecast)
            db.session.commit()

            return True, forecasts

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def to_dict(self):
        """Convert object to dictionary"""
        return {
            'id': self.id,
            'id_bahan': self.id_bahan,
            'tanggal': self.tanggal.isoformat(),
            'prediksi_penggunaan': self.prediksi_penggunaan,
            'rekomendasi_pembelian': self.rekomendasi_pembelian,
            'confidence_level': self.confidence_level,
            'created_at': self.created_at.isoformat()
        }

    def __repr__(self):
        return f'<StockForecast Bahan:{self.id_bahan} Date:{self.tanggal}>'

@event.listens_for(ForecastSettings, 'before_insert')
@event.listens_for(ForecastSettings, 'before_update')
def validate_forecast_settings(mapper, connection, target):
    """Validate forecast settings before save"""
    if target.min_stok < 0:
        raise ValueError("Minimum stock cannot be negative")
    if target.lead_time < 0:
        raise ValueError("Lead time cannot be negative")
    if target.safety_stock < 0:
        raise ValueError("Safety stock cannot be negative")
    if target.forecast_period < 1:
        raise ValueError("Forecast period must be at least 1 day")
    if target.analysis_period < target.forecast_period:
        raise ValueError("Analysis period must be greater than forecast period")
