from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from models import db, Penjualan, Menu, BahanBaku, LogPemakaian, StockAdjustment
from datetime import datetime, timedelta
from sqlalchemy import func, and_
import pandas as pd
import numpy as np

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/daily-summary', methods=['GET'])
@jwt_required()
def get_daily_summary():
    """
    Get daily summary of sales, costs, and profits
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    """
    try:
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))

        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Ensure end date is not before start date
            if end < start:
                return jsonify({'error': 'End date cannot be before start date'}), 422
                
            # Adjust future dates to today
            today = datetime.now().date()
            if start > today:
                start = today
            if end > today:
                end = today
                
        except ValueError:
            return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 422

        # Get daily totals with coalesce
        daily_sales = db.session.query(
            Penjualan.tanggal,
            func.coalesce(func.count(Penjualan.id_penjualan), 0).label('total_transactions'),
            func.coalesce(func.sum(Penjualan.jumlah_terjual), 0).label('items_sold'),
            func.coalesce(func.sum(Penjualan.total_sales), 0).label('total_sales'),
            func.coalesce(func.sum(Penjualan.total_cogs), 0).label('total_cogs'),
            func.coalesce(func.sum(Penjualan.profit), 0).label('total_profit')
        ).filter(
            Penjualan.tanggal.between(start, end)
        ).group_by(
            Penjualan.tanggal
        ).order_by(
            Penjualan.tanggal
        ).all()

        # Format results
        summary = []
        for day in daily_sales:
            profit_margin = (
                (float(day.total_profit) / float(day.total_sales)) * 100
                if day.total_sales > 0
                else 0
            )
            
            summary.append({
                'tanggal': day['tanggal'].isoformat(),
                'total_transactions': day['total_transactions'],
                'items_sold': day['items_sold'],
                'total_sales': day['total_sales'],
                'total_cogs': day['total_cogs'],
                'total_profit': day['total_profit'],
                'profit_margin': profit_margin
            })

        # Calculate period totals and averages
        if summary:
            period_summary = {
                'total_transactions': sum(day['total_transactions'] for day in summary),
                'total_items_sold': sum(day['items_sold'] for day in summary),
                'total_sales': sum(day['total_sales'] for day in summary),
                'total_cogs': sum(day['total_cogs'] for day in summary),
                'total_profit': sum(day['total_profit'] for day in summary),
                'avg_daily_sales': sum(day['total_sales'] for day in summary) / len(summary),
                'avg_daily_profit': sum(day['total_profit'] for day in summary) / len(summary),
                'avg_profit_margin': sum(day['profit_margin'] for day in summary) / len(summary)
            }
        else:
            period_summary = {
                'total_transactions': 0,
                'total_items_sold': 0,
                'total_sales': 0,
                'total_cogs': 0,
                'total_profit': 0,
                'avg_daily_sales': 0,
                'avg_daily_profit': 0,
                'avg_profit_margin': 0
            }

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'total_days': len(summary)
            },
            'daily_summary': summary,
            'period_summary': period_summary
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/menu-performance', methods=['GET'])
@jwt_required()
def get_menu_performance():
    """
    Get performance metrics for each menu item
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    """
    try:
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))

        # Get menu performance data
        performance = db.session.query(
            Menu.id_menu,
            Menu.nama_menu,
            func.count(Penjualan.id_penjualan).label('total_orders'),
            func.sum(Penjualan.jumlah_terjual).label('total_sold'),
            func.sum(Penjualan.total_sales).label('total_revenue'),
            func.sum(Penjualan.total_cogs).label('total_cost'),
            func.sum(Penjualan.profit).label('total_profit')
        ).join(
            Penjualan, Menu.id_menu == Penjualan.id_menu
        ).filter(
            Penjualan.tanggal.between(
                datetime.strptime(start_date, '%Y-%m-%d').date(),
                datetime.strptime(end_date, '%Y-%m-%d').date()
            )
        ).group_by(
            Menu.id_menu,
            Menu.nama_menu
        ).all()

        # Calculate metrics
        menu_stats = []
        for menu in performance:
            total_revenue = float(menu.total_revenue or 0)
            total_cost = float(menu.total_cost or 0)
            total_profit = float(menu.total_profit or 0)
            total_sold = int(menu.total_sold or 0)

            menu_stats.append({
                'id_menu': menu.id_menu,
                'nama_menu': menu.nama_menu,
                'total_orders': menu.total_orders,
                'total_sold': total_sold,
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'profit_margin': (
                    (total_profit / total_revenue) * 100
                    if total_revenue > 0
                    else 0
                ),
                'average_order_value': (
                    total_revenue / menu.total_orders
                    if menu.total_orders > 0
                    else 0
                )
            })

        # Sort by total profit descending
        menu_stats.sort(key=lambda x: x['total_profit'], reverse=True)

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'menu_performance': menu_stats
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/inventory-analysis', methods=['GET'])
@jwt_required()
def get_inventory_analysis():
    """
    Get detailed inventory analysis including usage patterns and costs
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

        # Get usage data for each ingredient
        usage_data = db.session.query(
            BahanBaku.id_bahan,
            BahanBaku.nama_bahan,
            BahanBaku.satuan,
            BahanBaku.stok_real,
            BahanBaku.harga_per_gram,
            func.sum(LogPemakaian.jumlah_terpakai).label('total_used'),
            func.sum(LogPemakaian.waste_amount).label('total_waste'),
            func.sum(LogPemakaian.cost).label('total_cost')
        ).join(
            LogPemakaian, BahanBaku.id_bahan == LogPemakaian.id_bahan
        ).join(
            Penjualan, LogPemakaian.id_penjualan == Penjualan.id_penjualan
        ).filter(
            Penjualan.tanggal.between(start, end)
        ).group_by(
            BahanBaku.id_bahan,
            BahanBaku.nama_bahan,
            BahanBaku.satuan,
            BahanBaku.stok_real,
            BahanBaku.harga_per_gram
        ).all()

        # Calculate metrics for each ingredient
        inventory_analysis = []
        for item in usage_data:
            total_used = float(item.total_used or 0)
            total_waste = float(item.total_waste or 0)
            current_stock = float(item.stok_real)
            
            # Calculate daily usage
            days_in_period = (end - start).days + 1
            avg_daily_usage = total_used / days_in_period if days_in_period > 0 else 0
            
            # Calculate days of stock remaining
            days_remaining = (
                current_stock / avg_daily_usage
                if avg_daily_usage > 0
                else float('inf')
            )

            inventory_analysis.append({
                'id_bahan': item.id_bahan,
                'nama_bahan': item.nama_bahan,
                'satuan': item.satuan,
                'current_stock': current_stock,
                'harga_per_gram': float(item.harga_per_gram),
                'total_used': total_used,
                'total_waste': total_waste,
                'total_cost': float(item.total_cost or 0),
                'waste_percentage': (
                    (total_waste / total_used) * 100
                    if total_used > 0
                    else 0
                ),
                'avg_daily_usage': avg_daily_usage,
                'days_of_stock_remaining': days_remaining,
                'stock_value': current_stock * float(item.harga_per_gram)
            })

        # Sort by total cost descending
        inventory_analysis.sort(key=lambda x: x['total_cost'], reverse=True)

        # Calculate overall metrics
        total_stock_value = sum(item['stock_value'] for item in inventory_analysis)
        total_usage_cost = sum(item['total_cost'] for item in inventory_analysis)
        total_waste_cost = sum(
            item['total_waste'] * item['harga_per_gram']
            for item in inventory_analysis
        )

        summary = {
            'total_stock_value': total_stock_value,
            'total_usage_cost': total_usage_cost,
            'total_waste_cost': total_waste_cost,
            'avg_waste_percentage': (
                sum(item['waste_percentage'] for item in inventory_analysis) /
                len(inventory_analysis)
                if inventory_analysis
                else 0
            )
        }

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'days': (end - start).days + 1
            },
            'inventory_analysis': inventory_analysis,
            'summary': summary
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@reports_bp.route('/waste-analysis', methods=['GET'])
@jwt_required()
def get_waste_analysis():
    """
    Get detailed waste analysis by ingredient and menu
    Query parameters:
    - start_date: YYYY-MM-DD
    - end_date: YYYY-MM-DD
    """
    try:
        start_date = request.args.get('start_date', 
            (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', 
            datetime.now().strftime('%Y-%m-%d'))

        # Get waste data by ingredient
        ingredient_waste = db.session.query(
            BahanBaku.id_bahan,
            BahanBaku.nama_bahan,
            func.sum(LogPemakaian.waste_amount).label('total_waste'),
            func.sum(LogPemakaian.jumlah_terpakai).label('total_used'),
            func.sum(LogPemakaian.cost).label('total_cost')
        ).join(
            LogPemakaian
        ).join(
            Penjualan
        ).filter(
            Penjualan.tanggal.between(
                datetime.strptime(start_date, '%Y-%m-%d').date(),
                datetime.strptime(end_date, '%Y-%m-%d').date()
            )
        ).group_by(
            BahanBaku.id_bahan,
            BahanBaku.nama_bahan
        ).all()

        # Get waste data by menu
        menu_waste = db.session.query(
            Menu.id_menu,
            Menu.nama_menu,
            func.sum(LogPemakaian.waste_amount).label('total_waste'),
            func.sum(LogPemakaian.jumlah_terpakai).label('total_used'),
            func.sum(LogPemakaian.cost).label('total_cost')
        ).join(
            Penjualan
        ).join(
            LogPemakaian
        ).filter(
            Penjualan.tanggal.between(
                datetime.strptime(start_date, '%Y-%m-%d').date(),
                datetime.strptime(end_date, '%Y-%m-%d').date()
            )
        ).group_by(
            Menu.id_menu,
            Menu.nama_menu
        ).all()

        # Format ingredient waste data
        ingredient_analysis = []
        for item in ingredient_waste:
            total_waste = float(item.total_waste or 0)
            total_used = float(item.total_used or 0)
            
            ingredient_analysis.append({
                'id_bahan': item.id_bahan,
                'nama_bahan': item.nama_bahan,
                'total_waste': total_waste,
                'total_used': total_used,
                'waste_percentage': (
                    (total_waste / total_used) * 100
                    if total_used > 0
                    else 0
                ),
                'total_cost': float(item.total_cost or 0)
            })

        # Format menu waste data
        menu_analysis = []
        for item in menu_waste:
            total_waste = float(item.total_waste or 0)
            total_used = float(item.total_used or 0)
            
            menu_analysis.append({
                'id_menu': item.id_menu,
                'nama_menu': item.nama_menu,
                'total_waste': total_waste,
                'total_used': total_used,
                'waste_percentage': (
                    (total_waste / total_used) * 100
                    if total_used > 0
                    else 0
                ),
                'total_cost': float(item.total_cost or 0)
            })

        # Calculate overall summary
        total_waste = sum(item['total_waste'] for item in ingredient_analysis)
        total_used = sum(item['total_used'] for item in ingredient_analysis)
        total_cost = sum(item['total_cost'] for item in ingredient_analysis)

        summary = {
            'total_waste': total_waste,
            'total_used': total_used,
            'overall_waste_percentage': (
                (total_waste / total_used) * 100
                if total_used > 0
                else 0
            ),
            'total_waste_cost': total_cost
        }

        return jsonify({
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'ingredient_waste': ingredient_analysis,
            'menu_waste': menu_analysis,
            'summary': summary
        }), 200

    except ValueError:
        return jsonify({'error': 'Format tanggal tidak valid (YYYY-MM-DD)'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
