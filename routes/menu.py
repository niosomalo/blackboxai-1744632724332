from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Menu, Resep, BahanBaku
from sqlalchemy.exc import IntegrityError

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/', methods=['GET'])
@jwt_required()
def get_all_menu():
    """Get all menus with optional recipe details"""
    try:
        include_resep = request.args.get('include_resep', 'false').lower() == 'true'
        menu_list = Menu.query.all()
        return jsonify({
            'data': [menu.to_dict(include_resep=include_resep) for menu in menu_list]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/<int:id_menu>', methods=['GET'])
@jwt_required()
def get_menu(id_menu):
    """Get specific menu by ID with its recipe"""
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404
        return jsonify(menu.to_dict(include_resep=True)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/', methods=['POST'])
@jwt_required()
def create_menu():
    """
    Create new menu with recipe
    Expects JSON: {
        "nama_menu": "string",
        "harga_jual": float,
        "deskripsi": "string" (optional),
        "resep": [
            {
                "id_bahan": int,
                "jumlah": float,
                "waste_percent": float
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        if not all(key in data for key in ['nama_menu', 'harga_jual']):
            return jsonify({
                'error': 'Nama menu dan harga jual harus diisi'
            }), 400

        # Start transaction
        db.session.begin_nested()

        # Create menu
        new_menu = Menu(
            nama_menu=data['nama_menu'],
            harga_jual=float(data['harga_jual']),
            deskripsi=data.get('deskripsi')
        )
        db.session.add(new_menu)
        db.session.flush()  # Get menu ID

        # Create recipe if provided
        if 'resep' in data:
            for item in data['resep']:
                # Validate recipe item
                if not all(key in item for key in ['id_bahan', 'jumlah']):
                    raise ValueError('Detail resep tidak lengkap')

                # Verify bahan exists
                bahan = BahanBaku.query.get(item['id_bahan'])
                if not bahan:
                    raise ValueError(f'Bahan dengan ID {item["id_bahan"]} tidak ditemukan')

                # Create recipe item
                resep_item = Resep(
                    id_menu=new_menu.id_menu,
                    id_bahan=item['id_bahan'],
                    jumlah=float(item['jumlah']),
                    waste_percent=float(item.get('waste_percent', 0))
                )
                db.session.add(resep_item)

        # Commit transaction
        db.session.commit()

        return jsonify({
            'message': 'Menu berhasil ditambahkan',
            'data': new_menu.to_dict(include_resep=True)
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Menu dengan nama tersebut sudah ada'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/<int:id_menu>', methods=['PUT'])
@jwt_required()
def update_menu(id_menu):
    """
    Update menu and optionally its recipe
    Expects JSON with any of these fields: {
        "nama_menu": "string",
        "harga_jual": float,
        "deskripsi": "string",
        "is_active": boolean,
        "resep": [
            {
                "id_bahan": int,
                "jumlah": float,
                "waste_percent": float
            },
            ...
        ]
    }
    """
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404

        data = request.get_json()
        
        # Start transaction
        db.session.begin_nested()

        # Update menu fields if provided
        if 'nama_menu' in data:
            menu.nama_menu = data['nama_menu']
        if 'harga_jual' in data:
            menu.harga_jual = float(data['harga_jual'])
        if 'deskripsi' in data:
            menu.deskripsi = data['deskripsi']
        if 'is_active' in data:
            menu.is_active = bool(data['is_active'])

        # Update recipe if provided
        if 'resep' in data:
            # Remove existing recipe
            Resep.query.filter_by(id_menu=id_menu).delete()
            
            # Add new recipe items
            for item in data['resep']:
                if not all(key in item for key in ['id_bahan', 'jumlah']):
                    raise ValueError('Detail resep tidak lengkap')

                bahan = BahanBaku.query.get(item['id_bahan'])
                if not bahan:
                    raise ValueError(f'Bahan dengan ID {item["id_bahan"]} tidak ditemukan')

                resep_item = Resep(
                    id_menu=id_menu,
                    id_bahan=item['id_bahan'],
                    jumlah=float(item['jumlah']),
                    waste_percent=float(item.get('waste_percent', 0))
                )
                db.session.add(resep_item)

        # Commit transaction
        db.session.commit()

        return jsonify({
            'message': 'Menu berhasil diupdate',
            'data': menu.to_dict(include_resep=True)
        }), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Nama menu sudah digunakan'}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/<int:id_menu>', methods=['DELETE'])
@jwt_required()
def delete_menu(id_menu):
    """Delete menu and its recipe"""
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404

        # Check if menu has any sales
        if menu.penjualan:
            # Instead of deleting, mark as inactive
            menu.is_active = False
            db.session.commit()
            return jsonify({
                'message': 'Menu dinonaktifkan karena memiliki data penjualan'
            }), 200

        # If no sales, delete menu (cascade will delete recipe)
        db.session.delete(menu)
        db.session.commit()

        return jsonify({
            'message': 'Menu berhasil dihapus'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/<int:id_menu>/resep', methods=['GET'])
@jwt_required()
def get_menu_recipe(id_menu):
    """Get recipe details for specific menu"""
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404

        recipe_items = Resep.query.filter_by(id_menu=id_menu).all()
        return jsonify({
            'menu': menu.to_dict(include_resep=False),
            'resep': [item.to_dict() for item in recipe_items]
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/adjust/<int:id_menu>', methods=['POST'])
@jwt_required()
def adjust_menu_stock(id_menu):
    """
    Adjust stock level for a menu item
    Expects JSON: {
        "stok_real": float,
        "keterangan": "string"
    }
    """
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404

        data = request.get_json()
        if 'stok_real' not in data:
            return jsonify({'error': 'Stok real harus diisi'}), 400

        stok_real = float(data['stok_real'])
        keterangan = data.get('keterangan', '')

        if stok_real < 0:
            return jsonify({'error': 'Stok tidak boleh negatif'}), 400

        # Start transaction
        db.session.begin_nested()

        try:
            # Update stock
            menu.adjust_stock(stok_real, keterangan)
            
            # Commit transaction
            db.session.commit()

            return jsonify({
                'message': 'Stok menu berhasil disesuaikan',
                'data': menu.to_dict()
            }), 200

        except Exception as e:
            db.session.rollback()
            raise e

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@menu_bp.route('/check-stock/<int:id_menu>', methods=['GET'])
@jwt_required()
def check_menu_stock(id_menu):
    """Check if enough stock is available to make specified quantity of menu"""
    try:
        menu = Menu.query.get(id_menu)
        if not menu:
            return jsonify({'error': 'Menu tidak ditemukan'}), 404

        quantity = request.args.get('quantity', 1, type=int)
        if quantity < 1:
            return jsonify({'error': 'Quantity harus lebih dari 0'}), 400

        available, shortages = menu.check_stock_availability(quantity)
        
        response = {
            'menu': menu.to_dict(include_resep=False),
            'quantity': quantity,
            'available': available
        }
        
        if not available:
            response['shortages'] = shortages

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
