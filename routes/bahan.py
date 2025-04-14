from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, BahanBaku, User, StockAdjustment
from datetime import datetime
from sqlalchemy.exc import IntegrityError

bahan_bp = Blueprint('bahan', __name__)

@bahan_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_bahan():
    """Get all raw materials"""
    try:
        bahan_list = BahanBaku.query.all()
        return jsonify({
            'data': [bahan.to_dict() for bahan in bahan_list]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bahan_bp.route('/<int:id_bahan>', methods=['GET'])
@jwt_required()
def get_bahan(id_bahan):
    """Get specific raw material by ID"""
    try:
        bahan = BahanBaku.query.get(id_bahan)
        if not bahan:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404
        return jsonify(bahan.to_dict()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bahan_bp.route('/', methods=['POST'])
@jwt_required()
def create_bahan():
    """
    Create new raw material
    Expects JSON: {
        "nama_bahan": "string",
        "satuan": "string",
        "stok_awal": float,
        "harga_per_gram": float,
        "min_stok": float (optional)
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['nama_bahan', 'satuan', 'stok_awal', 'harga_per_gram']
        if not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Missing required fields',
                'required_fields': required_fields
            }), 400

        # Create new bahan
        new_bahan = BahanBaku(
            nama_bahan=data['nama_bahan'],
            satuan=data['satuan'],
            stok_awal=float(data['stok_awal']),
            harga_per_gram=float(data['harga_per_gram']),
            min_stok=float(data.get('min_stok', 0))
        )
        
        db.session.add(new_bahan)
        db.session.commit()

        return jsonify({
            'message': 'Bahan berhasil ditambahkan',
            'data': new_bahan.to_dict()
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Bahan dengan nama tersebut sudah ada'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bahan_bp.route('/<int:id_bahan>', methods=['PUT'])
@jwt_required()
def update_bahan(id_bahan):
    """
    Update existing raw material
    Expects JSON with any of these fields: {
        "nama_bahan": "string",
        "satuan": "string",
        "harga_per_gram": float,
        "min_stok": float
    }
    """
    try:
        bahan = BahanBaku.query.get(id_bahan)
        if not bahan:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404

        data = request.get_json()
        
        # Update fields if provided
        if 'nama_bahan' in data:
            bahan.nama_bahan = data['nama_bahan']
        if 'satuan' in data:
            bahan.satuan = data['satuan']
        if 'harga_per_gram' in data:
            bahan.harga_per_gram = float(data['harga_per_gram'])
        if 'min_stok' in data:
            bahan.min_stok = float(data['min_stok'])

        db.session.commit()

        return jsonify({
            'message': 'Bahan berhasil diupdate',
            'data': bahan.to_dict()
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Nama bahan sudah digunakan'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bahan_bp.route('/<int:id_bahan>', methods=['DELETE'])
@jwt_required()
def delete_bahan(id_bahan):
    """Delete raw material"""
    try:
        bahan = BahanBaku.query.get(id_bahan)
        if not bahan:
            return jsonify({'error': 'Bahan tidak ditemukan'}), 404

        # Check if bahan is used in any recipe
        if bahan.resep:
            return jsonify({
                'error': 'Bahan tidak dapat dihapus karena masih digunakan dalam resep'
            }), 400

        db.session.delete(bahan)
        db.session.commit()

        return jsonify({
            'message': 'Bahan berhasil dihapus'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bahan_bp.route('/adjust-stock/<int:id_bahan>', methods=['POST'])
@jwt_required()
def adjust_stock(id_bahan):
    """
    Adjust stock based on physical count
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

        # Create stock adjustment record
        adjustment = StockAdjustment(
            id_bahan=id_bahan,
            stok_sistem=bahan.stok_real,
            stok_real=stok_real,
            keterangan=keterangan,
            created_by=get_jwt_identity()
        )

        # Update bahan stock
        bahan.adjust_stock(stok_real, keterangan)
        
        db.session.add(adjustment)
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

@bahan_bp.route('/low-stock', methods=['GET'])
@jwt_required()
def get_low_stock():
    """Get list of materials with stock below minimum level"""
    try:
        low_stock = BahanBaku.query\
            .filter(BahanBaku.stok_real <= BahanBaku.min_stok)\
            .all()
        
        return jsonify({
            'data': [bahan.to_dict() for bahan in low_stock]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
