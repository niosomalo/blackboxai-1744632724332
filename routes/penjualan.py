from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Penjualan, Menu, LogPemakaian
from datetime import datetime, timedelta
from sqlalchemy import func

penjualan_bp = Blueprint('penjualan', __name__)

@penjualan_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_penjualan():
    """
    Get all sales with optional date range filter
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - include_details: boolean (include usage details)
    """
    try:
        # Parse date filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_details = request.args.get('include_details', 'false').lower() == 'true'

        query = Penjualan.query

        if start_date:
            query = query.filter(Penjualan.tanggal >= datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(Penjualan.tanggal <= datetime.strptime(end_date, '%Y-%m-%d').date())

        # Order by date descending
        penjualan_list = query.order_by(Penjualan.tanggal.desc()).all()

        return jsonify({
            'data': [penjualan.to_dict(include_details=include_details) 
                    for penjualan in penjualan_list]
        }), 200

    except ValueError as e:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@penjualan_bp.route('/<int:id_penjualan>', methods=['GET'])
@jwt_required()
def get_penjualan(id_penjualan):
    """Get specific sale by ID with all details"""
    try:
        penjualan = Penjualan.query.get(id_penjualan)
        if not penjualan:
            return jsonify({'error': 'Data penjualan tidak ditemukan'}), 404

        return jsonify(penjualan.to_dict(include_details=True)), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@penjualan_bp.route('/', methods=['POST'])
@jwt_required()
def create_penjualan():
    """
    Create new sale
    Expects JSON: {
        "tanggal": "YYYY-MM-DD",
        "id_menu": int,
        "jumlah_terjual": int
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['tanggal', 'id_menu', 'jumlah_terjual']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Data tidak lengkap',
                'required_fields': required_fields
            }), 400

        # Validate date
        try:
            tanggal = datetime.strptime(data['tanggal'], '%Y-%m-%d').date()
            if tanggal > datetime.now().date():
                return jsonify({
                    'error': 'Tanggal penjualan tidak boleh di masa depan'
                }), 400
        except ValueError:
            return jsonify({
                'error': 'Format tanggal tidak valid (YYYY-MM-DD)'
            }), 400

        # Validate menu exists
        menu = Menu.query.get(data['id_menu'])
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404
        if not menu.is_active:
            return jsonify({'error': 'Menu tidak aktif'}), 400

        # Validate quantity
        jumlah_terjual = int(data['jumlah_terjual'])
        if jumlah_terjual <= 0:
            return jsonify({'error': 'Jumlah terjual harus lebih dari 0'}), 400

        # Check stock availability
        available, shortages = menu.check_stock_availability(jumlah_terjual)
        if not available:
            return jsonify({
                'error': 'Stok tidak mencukupi',
                'shortages': shortages
            }), 400

        # Start transaction
        db.session.begin_nested()

        # Create sale
        new_penjualan = Penjualan(
            tanggal=tanggal,
            id_menu=data['id_menu'],
            jumlah_terjual=jumlah_terjual
        )
        db.session.add(new_penjualan)
        db.session.flush()  # Get sale ID

        # Process the sale (update stock, create logs)
        success, message = new_penjualan.process_sale()
        if not success:
            raise ValueError(message)

        # Commit transaction
        db.session.commit()

        return jsonify({
            'message': 'Penjualan berhasil dicatat',
            'data': new_penjualan.to_dict(include_details=True)
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@penjualan_bp.route('/summary', methods=['GET'])
@jwt_required()
def get_sales_summary():
    """
    Get sales summary for a period
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - group_by: 'day' or 'month' (default: 'day')
    """
    try:
        # Parse date filters
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))
        group_by = request.args.get('group_by', 'day')

        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Base query
        query = db.session.query(
            Penjualan.tanggal,
            func.count(Penjualan.id_penjualan).label('total_transactions'),
            func.sum(Penjualan.jumlah_terjual).label('total_items'),
            func.sum(Penjualan.total_sales).label('total_sales'),
            func.sum(Penjualan.total_cogs).label('total_cogs'),
            func.sum(Penjualan.profit).label('total_profit')
        )

        # Apply date filter
        query = query.filter(Penjualan.tanggal.between(start, end))

        # Group by period
        if group_by == 'month':
            query = query.group_by(
                func.extract('year', Penjualan.tanggal),
                func.extract('month', Penjualan.tanggal)
            ).order_by(
                func.extract('year', Penjualan.tanggal),
                func.extract('month', Penjualan.tanggal)
            )
        else:  # group by day
            query = query.group_by(Penjualan.tanggal).order_by(Penjualan.tanggal)

        results = query.all()

        # Format response
        summary = []
        for result in results:
            summary.append({
                'tanggal': result.tanggal.isoformat(),
                'total_transactions': result.total_transactions,
                'total_items': float(result.total_items or 0),
                'total_sales': float(result.total_sales or 0),
                'total_cogs': float(result.total_cogs or 0),
                'total_profit': float(result.total_profit or 0),
                'profit_margin': (
                    (float(result.total_profit or 0) / float(result.total_sales or 1)) * 100
                    if result.total_sales
                    else 0
                )
            })

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'group_by': group_by
            },
            'summary': summary,
            'totals': {
                'transactions': sum(item['total_transactions'] for item in summary),
                'items': sum(item['total_items'] for item in summary),
                'sales': sum(item['total_sales'] for item in summary),
                'cogs': sum(item['total_cogs'] for item in summary),
                'profit': sum(item['total_profit'] for item in summary),
                'avg_profit_margin': (
                    sum(item['profit_margin'] for item in summary) / len(summary)
                    if summary
                    else 0
                )
            }
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@penjualan_bp.route('/top-menu', methods=['GET'])
@jwt_required()
def get_top_menu():
    """
    Get top selling menu items
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    - limit: int (default: 10)
    """
    try:
        # Parse parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = request.args.get('limit', 10, type=int)

        # Build query
        query = db.session.query(
            Menu.id_menu,
            Menu.nama_menu,
            func.sum(Penjualan.jumlah_terjual).label('total_sold'),
            func.sum(Penjualan.total_sales).label('total_sales'),
            func.sum(Penjualan.profit).label('total_profit')
        ).join(Penjualan)

        if start_date:
            query = query.filter(Penjualan.tanggal >= 
                datetime.strptime(start_date, '%Y-%m-%d').date())
        if end_date:
            query = query.filter(Penjualan.tanggal <= 
                datetime.strptime(end_date, '%Y-%m-%d').date())

        results = query.group_by(Menu.id_menu, Menu.nama_menu)\
            .order_by(func.sum(Penjualan.jumlah_terjual).desc())\
            .limit(limit)\
            .all()

        return jsonify({
            'data': [{
                'id_menu': r.id_menu,
                'nama_menu': r.nama_menu,
                'total_sold': int(r.total_sold or 0),
                'total_sales': float(r.total_sales or 0),
                'total_profit': float(r.total_profit or 0),
                'profit_margin': (
                    (float(r.total_profit or 0) / float(r.total_sales or 1)) * 100
                    if r.total_sales
                    else 0
                )
            } for r in results]
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
