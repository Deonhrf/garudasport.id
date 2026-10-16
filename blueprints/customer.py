from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify
from config import get_db_connection
import os
import midtransclient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

customer_bp = Blueprint('customer', __name__, url_prefix='/customer')

# Konfigurasi Midtrans Client Key & Server Key
MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', '')
MIDTRANS_CLIENT_KEY = os.getenv('MIDTRANS_CLIENT_KEY', '')
snap = midtransclient.Snap(
    is_production=False,  # Tetap False karena ini Mode Sandbox
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)

# --- 1. DASHBOARD UTAMA USER ---
@customer_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    notifications = []
    unread_notif = 0

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            
            try:
                cursor.execute("SELECT COUNT(*) as total FROM orders WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
                order_count = result['total'] if result else 0
            except:
                order_count = 0 
                
            try:
                cursor.execute("SELECT SUM(quantity) as total_items FROM cart WHERE user_id = %s", (user_id,))
                cart_result = cursor.fetchone()
                cart_count = int(cart_result['total_items']) if cart_result and cart_result['total_items'] else 0
            except:
                cart_count = 0

            cursor.execute("""
                SELECT * FROM notifications 
                WHERE user_id = %s 
                ORDER BY created_at DESC LIMIT 10
            """, (user_id,))
            notifications = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) as unread FROM notifications 
                WHERE user_id = %s AND is_read = 0
            """, (user_id,))
            unread_res = cursor.fetchone()
            unread_notif = unread_res['unread'] if unread_res else 0
                
    finally:
        connection.close()
        
    return render_template(
        'customer/dashboard.html', 
        user=user_data, 
        order_count=order_count, 
        cart_count=cart_count,
        notifications=notifications,
        unread_notif=unread_notif
    )


# --- [NOTIFIKASI] RUTE MARK AS READ CUSTOMER ---
@customer_bp.route('/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    if 'user_id' not in session:
        return {'status': 'unauthorized'}, 401
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE notifications 
                SET is_read = 1 
                WHERE user_id = %s AND is_read = 0
            """, (user_id,))
            connection.commit()
    except Exception as e:
        print(f"ERROR MARK READ: {e}")
    finally:
        connection.close()
        
    return {'status': 'success'}


# --- 2. PROFIL PENGGUNA & BUKU ALAMAT ---
@customer_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                nama = request.form.get('nama', '').strip()
                no_telepon = request.form.get('no_telepon', '').strip()
                
                cursor.execute("""
                    UPDATE users SET nama = %s, no_telepon = %s WHERE id = %s
                """, (nama, no_telepon, user_id))
                connection.commit()
                
                session['nama'] = nama
                flash('Informasi pribadi berhasil diperbarui!', 'success')
                return redirect(url_for('customer.profile'))

            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user_profile = cursor.fetchone()

            cursor.execute("SELECT * FROM user_addresses WHERE user_id = %s", (user_id,))
            user_addresses = cursor.fetchall()
            
    finally:
        connection.close()
        
    return render_template('customer/profile.html', user=user_profile, addresses=user_addresses)


# --- 3. KERANJANG BELANJA ---
@customer_bp.route('/cart')
def cart():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu untuk melihat keranjang.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT c.id as cart_id, c.quantity, c.size, p.id as product_id, p.name, p.price, p.image, p.outsole, p.brand, p.stock
                FROM cart c
                JOIN products p ON c.product_id = p.id
                WHERE c.user_id = %s
            """
            cursor.execute(sql, (user_id,))
            cart_items = cursor.fetchall()
            
            total_harga = sum(item['price'] * item['quantity'] for item in cart_items)
            
            cursor.execute("SELECT SUM(quantity) as total_items FROM cart WHERE user_id = %s", (user_id,))
            cart_res = cursor.fetchone()
            cart_count = int(cart_res['total_items']) if cart_res and cart_res['total_items'] else 0
    finally:
        connection.close()
        
    return render_template('customer/cart.html', cart_items=cart_items, total_harga=total_harga, cart_count=cart_count)


@customer_bp.route('/cart/delete/<int:cart_id>', methods=['POST'])
def delete_cart_item(cart_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM cart WHERE id = %s AND user_id = %s", (cart_id, user_id))
            connection.commit()
            flash('Produk berhasil dihapus dari keranjang.', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/update/<int:cart_id>', methods=['POST'])
def update_cart_item(cart_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    new_qty = int(request.form.get('quantity', 1))
    
    if new_qty < 1:
        new_qty = 1

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s AND user_id = %s", (new_qty, cart_id, user_id))
            connection.commit()
    except Exception as e:
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.cart'))



# --- 4. RIWAYAT PESANAN ---
@customer_bp.route('/orders')
def order_history():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    selected_status = request.args.get('status', 'Semua')
    
    connection = get_db_connection()
    orders = []
    try:
        with connection.cursor() as cursor:
            if selected_status == 'Semua':
                sql = """
                    SELECT id, total_harga, metode_pembayaran, status_pesanan, 
                           alamat_pengiriman, no_telepon, created_at, snap_token, no_resi
                    FROM orders
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """
                cursor.execute(sql, (user_id,))
            else:
                sql = """
                    SELECT id, total_harga, metode_pembayaran, status_pesanan, 
                           alamat_pengiriman, no_telepon, created_at, snap_token, no_resi
                    FROM orders
                    WHERE user_id = %s AND status_pesanan = %s
                    ORDER BY created_at DESC
                """
                cursor.execute(sql, (user_id, selected_status))
                
            orders = cursor.fetchall()
    except Exception as e:
        print(f"ERROR ORDER HISTORY: {e}")
    finally:
        connection.close()
        
    return render_template('customer/orders.html', orders=orders, client_key=MIDTRANS_CLIENT_KEY)



# --- 4. RIWAYAT PESANAN (PEMBATALAN LANGSUNG UNTUK COD & UNPAID) ---
@customer_bp.route('/order/cancel/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Ambil data pesanan
            cursor.execute("""
                SELECT id, status_pesanan, metode_pembayaran 
                FROM orders 
                WHERE id = %s AND user_id = %s
            """, (order_id, user_id))
            order = cursor.fetchone()
            
            if not order:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('customer.order_history'))

            status = order['status_pesanan']
            metode = order['metode_pembayaran'] or ''

            # Validasi: Hanya bisa dibatalkan langsung jika Menunggu Pembayaran ATAU COD yang masih Diproses/Menunggu Verifikasi
            is_cod = 'COD' in metode.upper()
            can_direct_cancel = (status == 'Menunggu Pembayaran') or (is_cod and status in ['Menunggu Verifikasi', 'Diproses'])

            if not can_direct_cancel:
                flash('Pesanan ini tidak dapat dibatalkan langsung.', 'danger')
                return redirect(url_for('customer.order_history'))
            
            # 1. KEMBALIKAN STOK PRODUK KE DATABASE
            cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
            items = cursor.fetchall()
            
            for item in items:
                cursor.execute("""
                    UPDATE products SET stock = stock + %s WHERE id = %s
                """, (item['quantity'], item['product_id']))
                
            # 2. UBAH STATUS PESANAN MENJADI DIBATALKAN
            cursor.execute("""
                UPDATE orders SET status_pesanan = 'Dibatalkan' WHERE id = %s
            """, (order_id,))
            
            # 3. NOTIFIKASI KE CUSTOMER
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (user_id, "Pesanan Dibatalkan", f"Pesanan #{order_id} berhasil dibatalkan dan stok produk telah dikembalikan.", "order"))

            # 4. NOTIFIKASI KE ADMIN
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin_obj = cursor.fetchone()
            admin_id = admin_obj['id'] if admin_obj else 1
            
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (admin_id, "Pesanan Dibatalkan Pembeli", f"Pesanan #{order_id} ({metode}) telah dibatalkan oleh pembeli. Stok otomatis dikembalikan.", "order"))

            connection.commit()
            flash(f'Pesanan #{order_id} berhasil dibatalkan.', 'success')
    except Exception as e:
        connection.rollback()
        print(f"ERROR CANCEL ORDER: {e}")
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.order_history'))

# --- 5. DETAIL PRODUK ---
@customer_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    connection = get_db_connection()
    cart_count = 0
    variants = {}
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            
            if not product:
                flash('Produk tidak ditemukan.', 'danger')
                return redirect(url_for('catalog'))
                
            cursor.execute("SELECT size, stock FROM product_variants WHERE product_id = %s", (product_id,))
            var_rows = cursor.fetchall()
            for row in var_rows:
                variants[str(row['size'])] = row['stock']
                
            if 'user_id' in session:
                try:
                    cursor.execute("SELECT SUM(quantity) as total_items FROM cart WHERE user_id = %s", (session['user_id'],))
                    cart_result = cursor.fetchone()
                    cart_count = int(cart_result['total_items']) if cart_result and cart_result['total_items'] else 0
                except:
                    cart_count = 0
    finally:
        connection.close()
        
    return render_template('customer/product_detail.html', product=product, variants=variants, cart_count=cart_count)

@customer_bp.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu untuk membeli produk.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    selected_size = request.form.get('size', '40') 
    quantity = int(request.form.get('quantity', 1))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, quantity FROM cart WHERE user_id = %s AND product_id = %s AND size = %s", 
                (user_id, product_id, selected_size)
            )
            existing_item = cursor.fetchone()
            
            if existing_item:
                new_qty = existing_item['quantity'] + quantity
                cursor.execute("UPDATE cart SET quantity = %s WHERE id = %s", (new_qty, existing_item['id']))
            else:
                cursor.execute(
                    "INSERT INTO cart (user_id, product_id, quantity, size) VALUES (%s, %s, %s, %s)", 
                    (user_id, product_id, quantity, selected_size)
                )
            connection.commit()
            flash('Produk berhasil ditambahkan ke keranjang!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.cart'))


# --- 7. CHECKOUT & PEMPROSESAN PESANAN ---
@customer_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        if request.method == 'GET':
            selected_items = request.args.getlist('selected_items')
            if not selected_items:
                flash('Pilih minimal satu produk untuk di-checkout.', 'danger')
                return redirect(url_for('customer.cart'))
            session['checkout_items'] = selected_items 
        else:
            selected_items = session.get('checkout_items', [])
            if not selected_items:
                flash('Sesi checkout tidak valid. Silakan ulangi dari keranjang.', 'danger')
                return redirect(url_for('customer.cart'))

        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_profile = cursor.fetchone()

        cursor.execute("SELECT * FROM user_addresses WHERE user_id = %s", (user_id,))
        user_addresses = cursor.fetchall()

        format_strings = ','.join(['%s'] * len(selected_items))
        query_cart = f"""
            SELECT c.id as cart_id, c.product_id, c.quantity, c.size, p.price, p.name, p.stock 
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = %s AND c.id IN ({format_strings})
        """
        params = [user_id] + selected_items
        cursor.execute(query_cart, params)
        cart_items = cursor.fetchall()
        
        if not cart_items:
            flash('Produk yang dipilih tidak ditemukan di keranjang.', 'danger')
            return redirect(url_for('customer.cart'))
            
        subtotal_produk = sum(item['price'] * item['quantity'] for item in cart_items)
        ongkir = 0 if subtotal_produk > 500000 else 25000
        total_harga = subtotal_produk + ongkir
        
        if request.method == 'POST':
            if request.is_json:
                json_data = request.get_json()
                alamat = json_data.get('alamat_pengiriman', '').strip()
                no_telp = json_data.get('no_telepon', '').strip()
                metode = json_data.get('metode_pembayaran', 'Transfer Bank')
                kurir_pilihan = json_data.get('kurir', 'JNE Regular')
            else:
                alamat = request.form.get('alamat_pengiriman', '').strip()
                no_telp = request.form.get('no_telepon', '').strip()
                metode = request.form.get('metode_pembayaran', 'Transfer Bank')
                kurir_pilihan = request.form.get('kurir', 'JNE Regular')
            
            kurir = f"{kurir_pilihan} (Gratis Ongkir)" if subtotal_produk > 500000 else f"{kurir_pilihan} (Rp 25.000)"
            
            if not alamat or not no_telp:
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Alamat dan nomor telepon wajib diisi.'}), 400
                flash('Alamat dan nomor telepon wajib diisi.', 'danger')
                return redirect(url_for('customer.checkout'))

            for item in cart_items:
                if item['stock'] < item['quantity']:
                    connection.rollback()
                    msg = f"Mohon maaf, stok untuk produk '{item['name']}' tidak mencukupi."
                    if request.is_json:
                        return jsonify({'success': False, 'message': msg}), 400
                    flash(msg, "danger")
                    return redirect(url_for('customer.cart'))

                cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (item['quantity'], item['product_id']))

            status_pesanan = 'Diproses' if 'COD' in metode.upper() else 'Menunggu Pembayaran'

            cursor.execute("""
                INSERT INTO orders (user_id, address_id, total_harga, metode_pembayaran, status_pesanan, alamat_pengiriman, no_telepon, kurir, ongkir)
                VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, total_harga, metode, status_pesanan, alamat, no_telp, kurir, ongkir))
            order_id = cursor.lastrowid
            
            for item in cart_items:
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price, size)
                    VALUES (%s, %s, %s, %s, %s)
                """, (order_id, item['product_id'], item['quantity'], item['price'], item['size']))
            
            query_delete = f"DELETE FROM cart WHERE user_id = %s AND id IN ({format_strings})"
            cursor.execute(query_delete, params)
            
            session.pop('checkout_items', None)

            # INTEGRASI MIDTRANS
            snap_token = None
            snap_error_msg = None
            if 'COD' not in metode.upper():
                try:
                    enabled_payments = ["gopay", "shopeepay", "qris"] if 'qris' in metode.lower() else ["bca_va", "bni_va", "bri_va", "mandiri_va", "permata_va", "gopay", "shopeepay", "qris"]
                    param = {
                        "transaction_details": {
                            "order_id": f"GS-{order_id}",
                            "gross_amount": int(total_harga)
                        },
                        "enabled_payments": enabled_payments,
                        "customer_details": {
                            "first_name": user_profile.get('nama', 'Customer') if user_profile else 'Customer',
                            "email": user_profile.get('email', '') if user_profile else '',
                            "phone": no_telp
                        }
                    }
                    transaction = snap.create_transaction(param)
                    snap_token = transaction.get('token')
                    if snap_token:
                        cursor.execute("UPDATE orders SET snap_token = %s WHERE id = %s", (snap_token, order_id))
                except Exception as snap_err:
                    snap_error_msg = str(snap_err)
                    print(f"ERROR MIDTRANS SNAP: {snap_err}")

            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (user_id, "Pesanan Berhasil Dibuat", f"Pesanan #{order_id} berhasil dibuat. Silakan selesaikan pembayaran.", "order"))

            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin_obj = cursor.fetchone()
            admin_id = admin_obj['id'] if admin_obj else 1
            
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (admin_id, "Pesanan Masuk Baru", f"Pesanan baru #{order_id} masuk dari pelanggan {session.get('nama', 'Pembeli')}.", "order"))

            connection.commit()
            
            # Jika Panggilan dari JavaScript / AJAX
            if request.is_json:
                if 'COD' in metode.upper():
                    return jsonify({
                        'success': True,
                        'is_midtrans': False,
                        'redirect_url': url_for('customer.invoice', order_id=order_id)
                    })
                else:
                    if not snap_token:
                        return jsonify({
                            'success': False,
                            'message': f'Gagal mendapatkan token Midtrans: {snap_error_msg or "Key tidak valid"}'
                        }), 400
                    return jsonify({
                        'success': True,
                        'is_midtrans': True,
                        'snap_token': snap_token,
                        'order_id': order_id,
                        'client_key': MIDTRANS_CLIENT_KEY,
                        'redirect_url': url_for('customer.payment_instruction', order_id=order_id)
                    })

            if 'COD' in metode.upper():
                flash('Pesanan COD berhasil dibuat dan sedang diproses!', 'success')
                return redirect(url_for('customer.invoice', order_id=order_id))
            else:
                flash('Pesanan berhasil dibuat! Silakan lakukan pembayaran.', 'success')
                return redirect(url_for('customer.payment_instruction', order_id=order_id))

    except Exception as e:
        connection.rollback()
        print(f"ERROR CHECKOUT: {e}")
        if request.is_json:
            return jsonify({'success': False, 'message': 'Terjadi kesalahan saat memproses pesanan.'}), 500
        flash('Terjadi kesalahan saat memproses pesanan.', 'danger')
        return redirect(url_for('customer.cart'))
        
    finally:
        cursor.close()
        connection.close()
        
    return render_template('customer/checkout.html', 
                           subtotal_produk=subtotal_produk,
                           ongkir=ongkir,
                           total_harga=total_harga, 
                           cart_items=cart_items, 
                           user=user_profile, 
                           addresses=user_addresses,
                           client_key=MIDTRANS_CLIENT_KEY)

# --- 8. MANAJEMEN BUKU ALAMAT ---
@customer_bp.route('/address/add', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    label = request.form.get('label_alamat', 'Rumah').strip()
    nama = request.form.get('nama_penerima', '').strip()
    no_hp = request.form.get('no_hp_penerima', '').strip()
    alamat_lengkap = request.form.get('alamat_lengkap', '').strip()
    kota = request.form.get('kota', '').strip()
    kode_pos = request.form.get('kode_pos', '').strip()
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_addresses (user_id, label_alamat, nama_penerima, no_hp_penerima, alamat_lengkap, kota, kode_pos)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, label, nama, no_hp, alamat_lengkap, kota, kode_pos))
            connection.commit()
            flash('Alamat baru berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.profile'))


@customer_bp.route('/address/delete/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM user_addresses WHERE id = %s AND user_id = %s", (address_id, user_id))
            connection.commit()
            flash('Alamat berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.profile'))


# --- 9. INSTRUKSI PEMBAYARAN & UPLOAD BUKTI ---
@customer_bp.route('/payment/<int:order_id>', methods=['GET', 'POST'])
def payment_instruction(order_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
            order = cursor.fetchone()
            
            if not order:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('customer.order_history'))
                
            cursor.execute("""
                SELECT oi.quantity, oi.price, oi.size, p.name 
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            order_items = cursor.fetchall()
            
            if request.method == 'POST':
                file = request.files.get('bukti_pembayaran')
                if file and file.filename != '':
                    filename = secure_filename(f"order_{order_id}_{file.filename}")
                    
                    upload_folder = os.path.join('static', 'uploads', 'bukti')
                    os.makedirs(upload_folder, exist_ok=True)
                    file.save(os.path.join(upload_folder, filename))

                    cursor.execute("""
                        UPDATE orders 
                        SET bukti_pembayaran = %s, status_pesanan = 'Menunggu Verifikasi'
                        WHERE id = %s
                    """, (filename, order_id))

                    cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
                    admin_obj = cursor.fetchone()
                    admin_id = admin_obj['id'] if admin_obj else 1

                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, type, is_read)
                        VALUES (%s, %s, %s, %s, 0)
                    """, (admin_id, "Bukti Bayar Diunggah", f"Pelanggan mengunggah bukti pembayaran untuk pesanan #{order_id}. Segera verifikasi.", "order"))

                    connection.commit()
                    
                    flash('Bukti pembayaran berhasil diunggah! Admin akan segera memverifikasinya.', 'success')
                    return redirect(url_for('customer.order_history'))
                else:
                    flash('Pilih file gambar bukti pembayaran terlebih dahulu.', 'danger')
    finally:
        connection.close()
        
    return render_template('customer/payment.html', order=order, order_items=order_items, client_key=MIDTRANS_CLIENT_KEY)


@customer_bp.route('/profile/security', methods=['POST'])
def update_account_security():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    old_password = request.form.get('old_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if not old_password or not new_password or not confirm_password:
                flash('Semua kolom kata sandi wajib diisi.', 'danger')
                return redirect(url_for('customer.profile'))
            
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            current_user = cursor.fetchone()
            
            if not check_password_hash(current_user['password'], old_password):
                flash('Kata sandi saat ini yang Anda masukkan salah.', 'danger')
                return redirect(url_for('customer.profile'))
                
            if new_password != confirm_password:
                flash('Konfirmasi kata sandi baru tidak cocok.', 'danger')
                return redirect(url_for('customer.profile'))
                
            hashed_new_password = generate_password_hash(new_password)
            
            cursor.execute("""
                UPDATE users SET password = %s WHERE id = %s
            """, (hashed_new_password, user_id))
            
            connection.commit()
            flash('Kata sandi berhasil diperbarui!', 'success')
            
    except Exception as e:
        connection.rollback()
        print(f"ERROR UPDATE PASSWORD: {e}")
        flash('Terjadi kesalahan saat memperbarui kata sandi.', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.profile'))


@customer_bp.route('/invoice/<int:order_id>')
def invoice(order_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, u.nama as customer_nama, u.email as customer_email 
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.id = %s AND o.user_id = %s
            """, (order_id, user_id))
            order = cursor.fetchone()
            
            if not order:
                flash('Invoice tidak ditemukan atau Anda tidak memiliki akses.', 'danger')
                return redirect(url_for('customer.order_history'))
                
            cursor.execute("""
                SELECT oi.quantity, oi.price, oi.size, p.name as product_name, p.brand 
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            order_items = cursor.fetchall()
            
    finally:
        connection.close()
        
    return render_template('customer/invoice.html', order=order, order_items=order_items)

@customer_bp.route('/order/refund/<int:order_id>', methods=['POST'])
def request_refund(order_id):
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    bank = request.form.get('bank_refund', '').strip()
    no_rek = request.form.get('no_rekening_refund', '').strip()
    nama_pemilik = request.form.get('nama_pemilik_refund', '').strip()
    
    if not bank or not no_rek or not nama_pemilik:
        flash('Semua informasi rekening refund wajib diisi.', 'danger')
        return redirect(url_for('customer.order_history'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, metode_pembayaran FROM orders 
                WHERE id = %s AND user_id = %s AND status_pesanan IN ('Menunggu Verifikasi', 'Diproses')
            """, (order_id, user_id))
            order = cursor.fetchone()
            
            if not order:
                flash('Pesanan tidak valid untuk pengajuan refund.', 'danger')
                return redirect(url_for('customer.order_history'))
            
            # Jika pesanan COD, tolak pengajuan refund rekening
            if 'COD' in (order.get('metode_pembayaran') or '').upper():
                flash('Pesanan COD belum dibayar sehingga tidak memerlukan refund rekening. Gunakan tombol Batalkan Pesanan.', 'warning')
                return redirect(url_for('customer.order_history'))

            cursor.execute("""
                UPDATE orders 
                SET status_pesanan = 'Menunggu Konfirmasi Refund', 
                    bank_refund = %s, 
                    no_rekening_refund = %s, 
                    nama_pemilik_refund = %s, 
                    status_refund = 'Diajukan'
                WHERE id = %s
            """, (bank, no_rek, nama_pemilik, order_id))

            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (user_id, "Pengajuan Refund Diajukan", f"Permintaan refund untuk pesanan #{order_id} berhasil diajukan.", "refund"))

            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin_obj = cursor.fetchone()
            admin_id = admin_obj['id'] if admin_obj else 1

            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (admin_id, "Pengajuan Refund Masuk", f"Pelanggan mengajukan refund untuk pesanan #{order_id}. Mohon konfirmasi.", "refund"))
            
            connection.commit()
            flash(f'Pengajuan refund untuk pesanan #{order_id} berhasil dikirim dan sedang menunggu konfirmasi Admin.', 'success')
            
    except Exception as e:
        connection.rollback()
        print(f"ERROR REFUND: {e}")
        flash('Terjadi kesalahan saat memproses pengajuan refund.', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('customer.order_history'))