from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, BahanBaku, ForecastSettings, StockForecast, LogPemakaian
from datetime import datetime, timedelta
from sqlalchemy import func
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

forecast_bp = Blueprint('forecast', __name__)

@forecast_bp.route('/settings', methods=['GET', 'POST'])
@jwt_required()
def manage_forecast_settings():
    """
    Manage forecast settings for ingredients
    GET: Get all settings
    POST: Create/Update settings for an ingredient
    """
    try:
        if request.method == 'GET':
            settings = ForecastSettings.query.all()
            return jsonify({
                'data': [setting.to_dict() for setting in settings]
            }), 200

        # POST method
        data = request.get_json()
        required_fields = ['id_bahan', 'min_stok', 'lead_time', 'safety_stock']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Data tidak lengkap',
                'required_fields': required_fields
            }), 400

        # Check if bahan exists
        bahan = BahanBaku.query.get(data['id_bahan'])
        if not bahan:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404

        # Update or create settings
        setting = ForecastSettings.query.filter_by(id_bahan=data['id_bahan']).first()
        if not setting:
            setting = ForecastSettings(
                id_bahan=data['id_bahan'],
                min_stok=float(data['min_stok']),
                lead_time=int(data['lead_time']),
                safety_stock=float(data['safety_stock']),
                forecast_period=int(data.get('forecast_period', 7)),
                analysis_period=int(data.get('analysis_period', 30))
            )
            db.session.add(setting)
        else:
            setting.min_stok = float(data['min_stok'])
            setting.lead_time = int(data['lead_time'])
            setting.safety_stock = float(data['safety_stock'])
            if 'forecast_period' in data:
                setting.forecast_period = int(data['forecast_period'])
            if 'analysis_period' in data:
                setting.analysis_period = int(data['analysis_period'])

        db.session.commit()

        return jsonify({
            'message': 'Pengaturan forecast berhasil disimpan',
            'data': setting.to_dict()
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@forecast_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_forecast():
    """
    Generate forecast for specified ingredients or all ingredients
    Expects optional JSON: {
        "id_bahan": [int] (optional - if not provided, generates for all ingredients)
    }
    """
    try:
        data = request.get_json()
        if data and 'id_bahan' in data:
            bahan_list = [BahanBaku.query.get(data['id_bahan'])]
            if not bahan_list[0]:
                return jsonify({'error': 'Bahan tidak ditemukan'}), 404
        else:
            bahan_list = BahanBaku.query.all()

        results = []
        for bahan in bahan_list:
            # Get or create forecast settings
            settings = ForecastSettings.query.filter_by(id_bahan=bahan.id_bahan).first()
            if not settings:
                settings = ForecastSettings(
                    id_bahan=bahan.id_bahan,
                    min_stok=bahan.min_stok,
                    lead_time=3,  # Default lead time
                    safety_stock=bahan.min_stok * 0.5  # Default safety stock
                )
                db.session.add(settings)
                db.session.commit()

            # Generate forecast
            success, result = StockForecast.generate_forecast(bahan.id_bahan, settings)
            
            if success:
                results.append({
                    'id_bahan': bahan.id_bahan,
                    'nama_bahan': bahan.nama_bahan,
                    'forecast': [f.to_dict() for f in result]
                })
            else:
                results.append({
                    'id_bahan': bahan.id_bahan,
                    'nama_bahan': bahan.nama_bahan,
                    'error': result
                })

        return jsonify({
            'message': 'Forecast berhasil dibuat',
            'data': results
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@forecast_bp.route('/recommendations', methods=['GET'])
@jwt_required()
def get_purchase_recommendations():
    """
    Get purchase recommendations based on latest forecasts
    Query parameters:
    - include_all: boolean (include all ingredients, not just those needing purchase)
    """
    try:
        include_all = request.args.get('include_all', 'false').lower() == 'true'

        # Get latest forecasts for each ingredient
        latest_forecasts = db.session.query(
            StockForecast,
            func.max(StockForecast.created_at).label('latest_forecast')
        ).group_by(
            StockForecast.id_bahan
        ).all()

        recommendations = []
        for forecast, _ in latest_forecasts:
            bahan = BahanBaku.query.get(forecast.id_bahan)
            settings = ForecastSettings.query.filter_by(id_bahan=forecast.id_bahan).first()

            if not settings:
                continue

            current_stock = bahan.stok_real
            predicted_usage = forecast.prediksi_penggunaan
            needed_stock = (
                predicted_usage * (settings.lead_time + 1) + 
                settings.safety_stock
            )
            recommended_purchase = max(0, needed_stock - current_stock)

            if include_all or recommended_purchase > 0:
                recommendations.append({
                    'id_bahan': bahan.id_bahan,
                    'nama_bahan': bahan.nama_bahan,
                    'current_stock': current_stock,
                    'min_stok': settings.min_stok,
                    'predicted_usage': predicted_usage,
                    'safety_stock': settings.safety_stock,
                    'lead_time': settings.lead_time,
                    'recommended_purchase': recommended_purchase,
                    'confidence_level': forecast.confidence_level,
                    'last_updated': forecast.created_at.isoformat()
                })

        # Sort by recommended purchase amount (descending)
        recommendations.sort(key=lambda x: x['recommended_purchase'], reverse=True)

        return jsonify({
            'data': recommendations
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@forecast_bp.route('/accuracy', methods=['GET'])
@jwt_required()
def get_forecast_accuracy():
    """
    Get forecast accuracy metrics
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    """
    try:
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))

        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Get actual usage data
        actual_usage = db.session.query(
            LogPemakaian.id_bahan,
            func.sum(LogPemakaian.jumlah_terpakai + LogPemakaian.waste_amount).label('actual_usage')
        ).join(
            Penjualan
        ).filter(
            Penjualan.tanggal.between(start, end)
        ).group_by(
            LogPemakaian.id_bahan
        ).all()

        # Get forecasts for the same period
        forecasts = StockForecast.query.filter(
            StockForecast.tanggal.between(start, end)
        ).all()

        # Calculate accuracy metrics
        accuracy_metrics = {}
        for actual in actual_usage:
            bahan_forecasts = [f for f in forecasts if f.id_bahan == actual.id_bahan]
            if not bahan_forecasts:
                continue

            predicted_usage = sum(f.prediksi_penggunaan for f in bahan_forecasts)
            actual_usage_val = float(actual.actual_usage or 0)

            # Calculate error metrics
            if actual_usage_val > 0:
                percentage_error = abs(predicted_usage - actual_usage_val) / actual_usage_val * 100
            else:
                percentage_error = 0

            bahan = BahanBaku.query.get(actual.id_bahan)
            accuracy_metrics[actual.id_bahan] = {
                'nama_bahan': bahan.nama_bahan,
                'actual_usage': actual_usage_val,
                'predicted_usage': predicted_usage,
                'absolute_error': abs(predicted_usage - actual_usage_val),
                'percentage_error': percentage_error,
                'accuracy': max(0, 100 - percentage_error)
            }

        # Calculate overall accuracy
        if accuracy_metrics:
            overall_accuracy = sum(
                m['accuracy'] for m in accuracy_metrics.values()
            ) / len(accuracy_metrics)
        else:
            overall_accuracy = 0

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'accuracy_metrics': accuracy_metrics,
            'overall_accuracy': overall_accuracy
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
