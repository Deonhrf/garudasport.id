from flask import Flask, render_template, request, session, jsonify
from config import Config, get_db_connection
from blueprints.customer import customer_bp
from blueprints.chat import chat_bp
import pymysql
import midtransclient
import os


app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY


from blueprints.auth import auth_bp
from blueprints.customer import customer_bp
from blueprints.admin import admin_bp

app.register_blueprint(auth_bp)
app.register_blueprint(customer_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(chat_bp)
# --- FILTER RUPIAH UNTUK JINJA2 ---


# Mengambil key dari environment variable Railway / Local (SUDAH DIPERBAIKI)
MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', 'SB-Mid-server-awM2edpzq162Ig2U9uynS5wf')
MIDTRANS_CLIENT_KEY = os.getenv('MIDTRANS_CLIENT_KEY', 'SB-Mid-client-oRb_QKiAIxTmcFNR')

snap = midtransclient.Snap(
    is_production=False,  # Set False untuk mode Sandbox
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)


def format_rupiah(value) -> str:
    try:
        val = float(value) 
        return f"Rp{val:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

app.jinja_env.filters["rupiah"] = format_rupiah


# =========================================================================
# WEBHOOK CALLBACK MIDTRANS (Verifikasi Pembayaran Otomatis Real-time)
# =========================================================================
@app.route('/api/payment-notification', methods=['POST'])
def payment_notification():
    notification_data = request.get_json()
    if not notification_data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    order_id_raw = str(notification_data.get('order_id', ''))  # Contoh ID: GS-105
    order_id = order_id_raw.replace('GS-', '')
    transaction_status = notification_data.get('transaction_status')
    fraud_status = notification_data.get('fraud_status')
    transaction_id = notification_data.get('transaction_id')

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            order = cursor.fetchone()
            if not order:
                return jsonify({'status': 'not_found'}), 404

            current_status = order['status_pesanan']

            # Pembayaran LUNAS via QRIS / Virtual Account
            if transaction_status in ['capture', 'settlement']:
                if fraud_status == 'accept' or not fraud_status:
                    cursor.execute("""
                        UPDATE orders 
                        SET status_pesanan = 'Diproses', 
                            midtrans_transaction_id = %s
                        WHERE id = %s
                    """, (transaction_id, order_id))

                    if current_status != 'Diproses':
                        cursor.execute("""
                            INSERT INTO notifications (user_id, title, message, type, is_read)
                            VALUES (%s, %s, %s, %s, 0)
                        """, (order['user_id'], "Pembayaran Berhasil", f"Pembayaran untuk pesanan #{order_id} telah berhasil diverifikasi otomatis oleh Midtrans.", "order"))

                        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
                        admin_obj = cursor.fetchone()
                        admin_id = admin_obj['id'] if admin_obj else 1
                        cursor.execute("""
                            INSERT INTO notifications (user_id, title, message, type, is_read)
                            VALUES (%s, %s, %s, %s, 0)
                        """, (admin_id, "Pesanan Lunas (Midtrans)", f"Pesanan #{order_id} telah dilunasi via Midtrans.", "order"))

            elif transaction_status in ['cancel', 'deny', 'expire']:
                if current_status != 'Dibatalkan':
                    cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
                    items = cursor.fetchall()
                    for item in items:
                        cursor.execute("UPDATE products SET stock = stock + %s WHERE id = %s", (item['quantity'], item['product_id']))

                    cursor.execute("""
                        UPDATE orders 
                        SET status_pesanan = 'Dibatalkan', 
                            midtrans_transaction_id = %s
                        WHERE id = %s
                    """, (transaction_id, order_id))

                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, type, is_read)
                        VALUES (%s, %s, %s, %s, 0)
                    """, (order['user_id'], "Pembayaran Dibatalkan / Kadaluarsa", f"Pesanan #{order_id} dibatalkan karena pembayaran tidak diselesaikan.", "order"))

            elif transaction_status == 'pending':
                cursor.execute("""
                    UPDATE orders 
                    SET status_pesanan = 'Menunggu Pembayaran', 
                        midtrans_transaction_id = %s
                    WHERE id = %s
                """, (transaction_id, order_id))

            connection.commit()
    except Exception as e:
        connection.rollback()
        print(f"ERROR MIDTRANS WEBHOOK: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        connection.close()

    return jsonify({'status': 'OK'}), 200


# --- HALAMAN UTAMA / BERANDA ---
@app.route('/')
def index():
    selected_category = request.args.get("category", "all")
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM products")
            all_products = cursor.fetchall()
            
            if selected_category == "all":
                filtered_products = all_products
            elif selected_category in ("ic", "tf"):
                filtered_products = [p for p in all_products if p["outsole"].lower() == selected_category]
            else:
                filtered_products = [p for p in all_products if p["category"] == selected_category]
    finally:
        connection.close()

    CATEGORIES = [
        {"key": "all", "label": "Semua Koleksi"},
        {"key": "specs-inspired", "label": "Specs-inspired"},
        {"key": "ortuseight-style", "label": "Ortuseight-style"},
        {"key": "mills-line", "label": "Mills-line"},
        {"key": "ic", "label": "Indoor Court (IC)"},
        {"key": "tf", "label": "Turf (TF)"},
    ]

    cart_count = 0 

    return render_template(
        "index.html",
        products=filtered_products,
        categories=CATEGORIES,
        selected_category=selected_category,
        cart_count=cart_count
    )

# --- HALAMAN KATALOG PRODUK / ETALASE ---
@app.route('/catalog')
def catalog():
    selected_brand = request.args.get("brand", "") 
    search_query = request.args.get("q", "")
    
    connection = get_db_connection()
    cart_count = 0
    
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = "SELECT * FROM products WHERE 1=1"
            params = []
            
            if search_query:
                sql += " AND (name LIKE %s OR brand LIKE %s OR description LIKE %s)"
                params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
                
            if selected_brand:
                sql += " AND brand = %s"
                params.append(selected_brand)
                
            sql += " ORDER BY id DESC"
            
            cursor.execute(sql, params)
            filtered_products = cursor.fetchall()
                
            if 'user_id' in session:
                try:
                    cursor.execute("SELECT SUM(quantity) as total_items FROM cart WHERE user_id = %s", (session['user_id'],))
                    cart_result = cursor.fetchone()
                    cart_count = int(cart_result['total_items']) if cart_result and cart_result['total_items'] else 0
                except:
                    cart_count = 0

    finally:
        connection.close()

    return render_template(
        "catalog.html",
        products=filtered_products,
        selected_brand=selected_brand,
        search_query=search_query,
        cart_count=cart_count
    )

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)