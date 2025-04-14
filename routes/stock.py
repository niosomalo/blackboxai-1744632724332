from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, BahanBaku, StockAdjustment, LogPemakaian
from datetime import datetime, timedelta
from sqlalchemy import func

stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/current', methods=['GET'])
@jwt_required()
def get_current_stock():
    """
    Get current stock levels for all materials
    Query parameters:
    - include_low_stock: boolean (filter only low stock items)
    - include_usage: boolean (include usage statistics)
    """
    try:
        include_low_stock = request.args.get('include_low_stock', 'false').lower() == 'true'
        include_usage = request.args.get('include_usage', 'false').lower() == 'true'

        query = BahanBaku.query

        if include_low_stock:
            query = query.filter(BahanBaku.stok_real <= BahanBaku.min_stok)

        bahan_list = query.all()
        response = []

        for bahan in bahan_list:
            bahan_dict = bahan.to_dict()

            if include_usage:
                # Get usage statistics for last 30 days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)

                usage_stats = LogPemakaian.get_usage_summary(
                    start_date=start_date.date(),
                    end_date=end_date.date(),
                    id_bahan=bahan.id_bahan
                )
                bahan_dict['usage_stats'] = usage_stats

            response.append(bahan_dict)

        return jsonify({'data': response}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@stock_bp.route('/adjustments', methods=['GET'])
@jwt_required()
def get_stock_adjustments():
    """
    Get stock adjustment history
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - id_bahan: int (optional)
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        id_bahan = request.args.get('id_bahan', type=int)

        query = StockAdjustment.query

        if start_date:
            query = query.filter(StockAdjustment.tanggal >= 
                datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(StockAdjustment.tanggal <= 
                datetime.strptime(end_date, '%Y-%m-%d').date())
        if id_bahan:
            query = query.filter_by(id_bahan=id_bahan)

        adjustments = query.order_by(StockAdjustment.tanggal.desc()).all()

        return jsonify({
            'data': [adj.to_dict() for adj in adjustments]
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@stock_bp.route('/adjust/<int:id_bahan>', methods=['POST'])
@jwt_required()
def adjust_stock(id_bahan):
    """
    Adjust stock level for a material
    Expects JSON: {
        "stok_real": float,
        "keterangan": "string"
    }
    """
    try:
        bahan = BahanBaku.query.get(id_bahan)
        if not bahan:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404

        data = request.get_json()
        if 'stok_real' not in data:
            return jsonify({'error': 'Stok real harus diisi'}), 400

        stok_real = float(data['stok_real'])
        keterangan = data.get('keterangan', '')

        if stok_real < 0:
            return jsonify({'error': 'Stok tidak boleh negatif'}), 400

        # Start transaction
        db.session.begin_nested()

        # Create adjustment record
        adjustment = StockAdjustment(
            id_bahan=id_bahan,
            stok_sistem=bahan.stok_real,
            stok_real=stok_real,
            keterangan=keterangan,
            created_by=get_jwt_identity()
        )
        db.session.add(adjustment)

        # Update stock
        bahan.adjust_stock(stok_real, keterangan)

        # Commit transaction
        db.session.commit()

        return jsonify({
            'message': 'Stok berhasil disesuaikan',
            'data': {
                'bahan': bahan.to_dict(),
                'adjustment': adjustment.to_dict()
            }
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@stock_bp.route('/usage-stats', methods=['GET'])
@jwt_required()
def get_usage_statistics():
    """
    Get usage statistics for materials
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - id_bahan: int (optional)
    - group_by: 'day' or 'month' (default: 'day')
    """
    try:
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))
        id_bahan = request.args.get('id_bahan', type=int)
        group_by = request.args.get('group_by', 'day')

        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Base query
        query = db.session.query(
            LogPemakaian.id_bahan,
            BahanBaku.nama_bahan,
            func.sum(LogPemakaian.jumlah_terpakai).label('total_used'),
            func.sum(LogPemakaian.waste_amount).label('total_waste'),
            func.sum(LogPemakaian.cost).label('total_cost')
        ).join(BahanBaku)

        # Apply filters
        query = query.join(Penjualan).filter(Penjualan.tanggal.between(start, end))
        if id_bahan:
            query = query.filter(LogPemakaian.id_bahan == id_bahan)

        # Group by
        if group_by == 'month':
            query = query.group_by(
                LogPemakaian.id_bahan,
                BahanBaku.nama_bahan,
                func.extract('year', Penjualan.tanggal),
                func.extract('month', Penjualan.tanggal)
            )
        else:  # group by day
            query = query.group_by(
                LogPemakaian.id_bahan,
                BahanBaku.nama_bahan,
                Penjualan.tanggal
            )

        results = query.all()

        # Format response
        stats = []
        for r in results:
            total_used = float(r.total_used or 0)
            total_waste = float(r.total_waste or 0)
            
            stats.append({
                'id_bahan': r.id_bahan,
                'nama_bahan': r.nama_bahan,
                'total_used': total_used,
                'total_waste': total_waste,
                'total_cost': float(r.total_cost or 0),
                'waste_percentage': (
                    (total_waste / total_used) * 100 if total_used > 0 else 0
                )
            })

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'group_by': group_by
            },
            'data': stats
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
