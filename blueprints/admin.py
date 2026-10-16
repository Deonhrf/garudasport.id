from flask import Blueprint, render_template, session, redirect, url_for, flash, request   
from functools import wraps
from config import get_db_connection
from werkzeug.utils import secure_filename
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'danger')
            return redirect(url_for('auth.login'))
            
        if session.get('role') != 'admin':
            flash('Akses Ditolak! Halaman ini khusus untuk Admin GarudaSport.', 'danger')
            return redirect(url_for('index'))
            
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# CONTEXT PROCESSOR ADMIN (HEADER GLOBAL)
# ==========================================
@admin_bp.context_processor
def inject_admin_data():
    """Fungsi ini otomatis mengirim variabel admin_unread_notif ke SEMUA halaman Admin"""
    if session.get('role') == 'admin':
        admin_id = session.get('user_id')
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as unread FROM notifications WHERE user_id = %s AND is_read = 0", (admin_id,))
                res = cursor.fetchone()
                return dict(admin_unread_notif=res['unread'] if res else 0)
        except:
            pass
        finally:
            connection.close()
    return dict(admin_unread_notif=0)


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    admin_id = session.get('user_id')
    connection = get_db_connection()
    stats = {}
    recent_orders = []
    pending_refunds = 0
    notifications = []
    unread_notif = 0
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT SUM(total_harga) as total_revenue FROM orders WHERE status_pesanan IN ('Diproses', 'Dikirim', 'Selesai')")
            res_rev = cursor.fetchone()
            stats['revenue'] = res_rev['total_revenue'] if res_rev and res_rev['total_revenue'] else 0
            
            cursor.execute("SELECT COUNT(*) as pending FROM orders WHERE status_pesanan IN ('Menunggu Verifikasi', 'Menunggu Pembayaran')")
            pending_res = cursor.fetchone()
            stats['pending'] = pending_res['pending'] if pending_res else 0
            
            cursor.execute("SELECT COUNT(*) as total_prod FROM products")
            res_prod = cursor.fetchone()
            stats['products'] = res_prod['total_prod'] if res_prod else 0
            
            cursor.execute("SELECT COUNT(*) as total_refund FROM orders WHERE status_pesanan = 'Menunggu Konfirmasi Refund'")
            res_refund = cursor.fetchone()
            pending_refunds = res_refund['total_refund'] if res_refund else 0
            
            cursor.execute("""
                SELECT o.id, o.created_at, o.total_harga, o.status_pesanan, o.metode_pembayaran, u.nama as customer_name 
                FROM orders o
                JOIN users u ON o.user_id = u.id
                ORDER BY o.created_at DESC LIMIT 5
            """)
            recent_orders = cursor.fetchall()

            cursor.execute("""
                SELECT * FROM notifications 
                WHERE user_id = %s 
                ORDER BY created_at DESC LIMIT 10
            """, (admin_id,))
            notifications = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) as unread FROM notifications 
                WHERE user_id = %s AND is_read = 0
            """, (admin_id,))
            unread_res = cursor.fetchone()
            unread_notif = unread_res['unread'] if unread_res else 0
            
    finally:
        connection.close()
        
    return render_template(
        'admin/dashboard.html', 
        stats=stats, 
        recent_orders=recent_orders, 
        pending_refunds=pending_refunds,
        notifications=notifications,
        unread_notif=unread_notif
    )


@admin_bp.route('/notifications/mark-read', methods=['POST'])
@admin_required
def admin_mark_notifications_read():
    admin_id = session.get('user_id')
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE notifications 
                SET is_read = 1 
                WHERE user_id = %s AND is_read = 0
            """, (admin_id,))
            connection.commit()
    except Exception as e:
        print(f"ERROR ADMIN MARK READ: {e}")
    finally:
        connection.close()
        
    return {'status': 'success'}


@admin_bp.route('/order/verify/<int:order_id>', methods=['GET', 'POST'])
@admin_required
def verify_order(order_id):
    connection = get_db_connection()
    
    if request.method == 'POST':
        new_status = request.form.get('status_pesanan')
        no_resi = request.form.get('no_resi', '').strip()  # <--- Tangkap input Nomor Resi
        
        try:
            with connection.cursor() as cursor:
                # Update status pesanan dan no_resi (jika diisi)
                if no_resi:
                    cursor.execute("""
                        UPDATE orders SET status_pesanan = %s, no_resi = %s WHERE id = %s
                    """, (new_status, no_resi, order_id))
                else:
                    cursor.execute("""
                        UPDATE orders SET status_pesanan = %s WHERE id = %s
                    """, (new_status, order_id))

                # Ambil pemilik pesanan & kirim notifikasi update status + resi
                cursor.execute("SELECT user_id FROM orders WHERE id = %s", (order_id,))
                ord_data = cursor.fetchone()
                
                if ord_data:
                    customer_id = ord_data['user_id']
                    msg = f"Status pesanan #{order_id} Anda sekarang: {new_status}."
                    if no_resi:
                        msg += f" No. Resi: {no_resi}"
                        
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, type, is_read)
                        VALUES (%s, %s, %s, %s, 0)
                    """, (customer_id, "Status Pesanan Diperbarui", msg, "order"))

                connection.commit()
                flash(f'Status pesanan #{order_id} berhasil diperbarui!', 'success')
        except Exception as e:
            connection.rollback()
            flash(f'Terjadi kesalahan: {e}', 'danger')
        finally:
            connection.close()
        return redirect(url_for('admin.manage_orders'))

    order = None
    items = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, u.nama as customer_name, u.email 
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.id = %s
            """, (order_id,))
            order = cursor.fetchone()
            
            cursor.execute("""
                SELECT oi.*, p.name as product_name, p.brand, p.image 
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            items = cursor.fetchall()
    finally:
        connection.close()
        
    if not order:
        flash('Pesanan tidak ditemukan.', 'danger')
        return redirect(url_for('admin.manage_orders'))
        
    return render_template('admin/order_detail.html', order=order, items=items)

@admin_bp.route('/products')
@admin_required
def manage_products():
    connection = get_db_connection()
    products = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM products ORDER BY id DESC")
            products = cursor.fetchall()
    finally:
        connection.close()
        
    return render_template('admin/products.html', products=products)


@admin_bp.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    connection = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand = request.form.get('brand', '').strip()
        category = request.form.get('category', '').strip()
        price = request.form.get('price', 0)
        outsole = request.form.get('outsole', '').strip()
        description = request.form.get('description', '').strip()
        
        # Ambil input stok untuk masing-masing ukuran
        sizes = ['38', '39', '40', '41', '42', '43', '44']
    
        total_stock = 0
        variant_stocks = {}
        
        for sz in sizes:
            qty = int(request.form.get(f'stock_size_{sz}', 0))
            variant_stocks[sz] = qty
            total_stock += qty  # Update total global stok
            
        file = request.files.get('image')
        
        try:
            with connection.cursor() as cursor:
                # 1. Update tabel products utama
                if file and file.filename != '':
                    image_filename = secure_filename(f"product_{file.filename}")
                    upload_folder = os.path.join('static', 'uploads', 'products')
                    os.makedirs(upload_folder, exist_ok=True)
                    file.save(os.path.join(upload_folder, image_filename))
                    image_path = f"uploads/products/{image_filename}"
                    
                    cursor.execute("""
                        UPDATE products 
                        SET name=%s, brand=%s, category=%s, price=%s, stock=%s, outsole=%s, description=%s, image=%s 
                        WHERE id=%s
                    """, (name, brand, category, price, total_stock, outsole, description, image_path, product_id))
                else:
                    cursor.execute("""
                        UPDATE products 
                        SET name=%s, brand=%s, category=%s, price=%s, stock=%s, outsole=%s, description=%s 
                        WHERE id=%s
                    """, (name, brand, category, price, total_stock, outsole, description, product_id))
                
                # 2. Update tabel product_variants (Hapus yang lama, insert yang baru agar sinkron)
                cursor.execute("DELETE FROM product_variants WHERE product_id = %s", (product_id,))
                
                for sz, qty in variant_stocks.items():
                    cursor.execute("""
                        INSERT INTO product_variants (product_id, size, stock)
                        VALUES (%s, %s, %s)
                    """, (product_id, sz, qty))
                    
                connection.commit()
                flash('Data produk dan stok varian berhasil diperbarui!', 'success')
        except Exception as e:
            connection.rollback()
            flash(f'Terjadi kesalahan: {e}', 'danger')
        finally:
            connection.close()
            
        return redirect(url_for('admin.manage_products'))

    # Jika method GET (Menampilkan form edit)
    product = None
    variants = {}
    try:
        with connection.cursor() as cursor:
            # Ambil data utama produk
            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            
            # Ambil data stok per ukuran
            cursor.execute("SELECT size, stock FROM product_variants WHERE product_id = %s", (product_id,))
            var_rows = cursor.fetchall()
            
            # Ubah data ukuran menjadi dictionary agar mudah dipanggil di HTML (Contoh: {'39': 5, '40': 10})
            for row in var_rows:
                variants[row['size']] = row['stock']
                
    finally:
        connection.close()
        
    if not product:
        flash('Produk tidak ditemukan.', 'danger')
        return redirect(url_for('admin.manage_products'))

    # Kirim data 'product' dan 'variants' ke template
    return render_template('admin/edit_product.html', product=product, variants=variants)

@admin_bp.route('/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Hapus dari product_variants terlebih dahulu agar tidak terjadi error relasi database
            cursor.execute("DELETE FROM product_variants WHERE product_id = %s", (product_id,))
            
            # Hapus produk dari products
            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            connection.commit()
            flash('Produk beserta stok ukurannya berhasil dihapus dari katalog.', 'success')
    except Exception as e:
        connection.rollback()
        flash(f'Gagal menghapus produk: {e}', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('admin.manage_products'))


# --- MANAJEMEN PELANGGAN (DENGAN FITUR PENCARIAN) ---
@admin_bp.route('/customers')
@admin_required
def manage_customers():
    # Tangkap parameter pencarian 'q' jika admin melakukan pencarian
    search_query = request.args.get('q', '').strip()
    
    connection = get_db_connection()
    customers = []
    try:
        with connection.cursor() as cursor:
            if search_query:
                # Query jika ada pencarian nama atau email
                cursor.execute("""
                    SELECT u.*, 
                           COUNT(o.id) as total_orders, 
                           COALESCE(SUM(o.total_harga), 0) as total_spent
                    FROM users u
                    LEFT JOIN orders o ON u.id = o.user_id
                    WHERE u.role != 'admin' AND (u.nama LIKE %s OR u.email LIKE %s)
                    GROUP BY u.id
                    ORDER BY u.id DESC
                """, (f"%{search_query}%", f"%{search_query}%"))
            else:
                # Query default tampilkan semua
                cursor.execute("""
                    SELECT u.*, 
                           COUNT(o.id) as total_orders, 
                           COALESCE(SUM(o.total_harga), 0) as total_spent
                    FROM users u
                    LEFT JOIN orders o ON u.id = o.user_id
                    WHERE u.role != 'admin'
                    GROUP BY u.id
                    ORDER BY u.id DESC
                """)
            customers = cursor.fetchall()
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        connection.close()
        
    return render_template('admin/customers.html', customers=customers, search_query=search_query)


# --- FITUR BLOKIR / AKTIFKAN AKUN PELANGGAN ---
@admin_bp.route('/customer/toggle-status/<int:user_id>', methods=['POST'])
@admin_required
def toggle_customer_status(user_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Cek status saat ini
            cursor.execute("SELECT status FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if user:
                # Jika Aktif ubah ke Diblokir, jika Diblokir ubah ke Aktif
                new_status = 'Diblokir' if user['status'] == 'Aktif' else 'Aktif'
                cursor.execute("UPDATE users SET status = %s WHERE id = %s", (new_status, user_id))
                connection.commit()
                flash(f'Status akun pelanggan berhasil diubah menjadi {new_status}.', 'success')
    except Exception as e:
        connection.rollback()
        flash(f'Gagal mengubah status: {e}', 'danger')
    finally:
        connection.close()
    return redirect(url_for('admin.manage_customers'))


@admin_bp.route('/customers/orders/<int:user_id>')
@admin_required
def customer_orders(user_id):
    connection = get_db_connection()
    customer = None
    orders = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            customer = cursor.fetchone()
            
            cursor.execute("""
                SELECT * FROM orders 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            """, (user_id,))
            orders = cursor.fetchall()
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        connection.close()

    if not customer:
        flash('Pelanggan tidak ditemukan.', 'danger')
        return redirect(url_for('admin.manage_customers'))

    return render_template('admin/customer_orders.html', customer=customer, orders=orders)


# --- TAMBAH PRODUK BARU (DENGAN BRAND, DESKRIPSI, STOK UKURAN) ---
@admin_bp.route('/products/add', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        brand = request.form.get('brand', 'Mills').strip()
        category = request.form.get('category', 'Indoor').strip()
        price = request.form.get('price', 0)
        outsole = request.form.get('outsole', '').strip()
        description = request.form.get('description', '').strip() # Ambil deskripsi
        
        # Ambil input stok untuk masing-masing ukuran
        sizes = ['38', '39', '40', '41', '42', '43', '44']
        total_stock = 0
        variant_stocks = {}
        
        for sz in sizes:
            qty = int(request.form.get(f'stock_size_{sz}', 0))
            variant_stocks[sz] = qty
            total_stock += qty  # Hitung total global stok
            
        file = request.files.get('image')
        image_path = "uploads/products/default.png"
        
        if file and file.filename != '':
            image_filename = secure_filename(f"product_{file.filename}")
            upload_folder = os.path.join('static', 'uploads', 'products')
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, image_filename))
            image_path = f"uploads/products/{image_filename}"

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # 1. Masukkan ke tabel products utama (menyertakan total_stock global dan deskripsi)
                cursor.execute("""
                    INSERT INTO products (name, brand, category, price, stock, outsole, description, image)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (name, brand, category, price, total_stock, outsole, description, image_path))
                
                # Dapatkan ID produk yang baru saja dibuat
                product_id = cursor.lastrowid
                
                # 2. Masukkan ke tabel product_variants untuk masing-masing ukuran
                for sz, qty in variant_stocks.items():
                    cursor.execute("""
                        INSERT INTO product_variants (product_id, size, stock)
                        VALUES (%s, %s, %s)
                    """, (product_id, sz, qty))

                connection.commit()
                flash('Produk beserta varian ukuran berhasil ditambahkan!', 'success')
        except Exception as e:
            connection.rollback()
            print(f"ERROR DATABASE: {e}")
            flash('Gagal menambahkan produk.', 'danger')
        finally:
            connection.close()
            
        return redirect(url_for('admin.manage_products'))

    return render_template('admin/add_product.html')


@admin_bp.route('/orders', methods=['GET'])
@admin_required
def manage_orders():
    status_filter = request.args.get('status', 'Semua')
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT o.*, u.nama as customer_name, u.email as customer_email 
                FROM orders o
                JOIN users u ON o.user_id = u.id
            """
            params = []
            
            if status_filter != 'Semua':
                if status_filter == 'Menunggu Verifikasi':
                    query += " WHERE o.status_pesanan IN ('Menunggu Verifikasi', 'Menunggu Pembayaran')"
                elif status_filter == 'Diproses':
                    query += " WHERE o.status_pesanan IN ('Diproses', 'Dikirim')"
                elif status_filter == 'Menunggu Konfirmasi Refund':
                    query += " WHERE o.status_pesanan = 'Menunggu Konfirmasi Refund'"
                elif status_filter == 'Selesai':
                    query += " WHERE o.status_pesanan = 'Selesai'"
                elif status_filter == 'Dibatalkan':
                    query += " WHERE o.status_pesanan = 'Dibatalkan'"
            
            query += " ORDER BY o.created_at DESC"
            cursor.execute(query, params)
            orders = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as cnt FROM orders WHERE status_pesanan IN ('Menunggu Verifikasi', 'Menunggu Pembayaran')")
            count_verif = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM orders WHERE status_pesanan = 'Menunggu Konfirmasi Refund'")
            count_refund = cursor.fetchone()['cnt']
            
    except Exception as e:
        print(f"ERROR MANAGE ORDERS: {e}")
        orders = []
        count_verif = 0
        count_refund = 0
    finally:
        connection.close()
        
    return render_template(
        'admin/orders.html', 
        orders=orders, 
        current_tab=status_filter,
        count_verif=count_verif,
        count_refund=count_refund
    )


@admin_bp.route('/orders/refund/approve/<int:order_id>', methods=['POST'])
@admin_required
def approve_refund(order_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
            order = cursor.fetchone()
            
            if not order:
                flash('Pesanan tidak ditemukan.', 'danger')
                return redirect(url_for('admin.manage_orders'))
                
            cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
            items = cursor.fetchall()
            
            for item in items:
                cursor.execute("""
                    UPDATE products SET stock = stock + %s WHERE id = %s
                """, (item['quantity'], item['product_id']))
                
            cursor.execute("""
                UPDATE orders 
                SET status_pesanan = 'Dibatalkan', 
                    status_refund = 'Selesai'
                WHERE id = %s
            """, (order_id,))
            
            # [NOTIFIKASI] Kirim notifikasi ke customer bahwa refund disetujui
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read)
                VALUES (%s, %s, %s, %s, 0)
            """, (order['user_id'], "Refund Disetujui", f"Pengembalian dana untuk pesanan #{order_id} telah disetujui.", "refund"))
            
            connection.commit()
            flash(f'Refund untuk pesanan #{order_id} berhasil disetujui & stok produk telah dikembalikan.', 'success')
            
    except Exception as e:
        connection.rollback()
        print(f"ERROR APPROVE REFUND: {e}")
        flash('Terjadi kesalahan saat menyetujui refund.', 'danger')
    finally:
        connection.close()
        
    return redirect(url_for('admin.manage_orders', status='Menunggu Konfirmasi Refund'))


# --- LAPORAN & STATISTIK PENJUALAN ---
@admin_bp.route('/reports')
@admin_required
def sales_reports():
    connection = get_db_connection()
    reports = []
    top_products = []
    total_pendapatan = 0  # Kita hitung di sini agar HTML bersih
    
    try:
        with connection.cursor() as cursor:
            # Ambil rekap transaksi yang sudah selesai
            cursor.execute("""
                SELECT o.id, o.created_at, o.total_harga, o.metode_pembayaran, u.nama as customer_name
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.status_pesanan = 'Selesai'
                ORDER BY o.created_at DESC
            """)
            reports = cursor.fetchall()

            # Hitung total pendapatan dari backend
            for rep in reports:
                total_pendapatan += rep['total_harga']

            # Ambil statistik produk terlaris
            cursor.execute("""
                SELECT p.name, p.brand, SUM(oi.quantity) as total_sold
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                GROUP BY p.id
                ORDER BY total_sold DESC LIMIT 5
            """)
            top_products = cursor.fetchall()
    finally:
        connection.close()
        
    return render_template(
        'admin/reports.html', 
        reports=reports, 
        top_products=top_products,
        total_pendapatan=total_pendapatan # Lempar ke HTML
    )

# ==========================================
# RUTE CETAK INVOICE DARI SISI ADMIN
# ==========================================
@admin_bp.route('/invoice/<int:order_id>')
@admin_required
def admin_invoice(order_id):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Ambil data pesanan tanpa membatasi user_id (karena ini admin yang mengakses)
            cursor.execute("""
                SELECT o.*, u.nama as customer_nama, u.email as customer_email 
                FROM orders o
                JOIN users u ON o.user_id = u.id
                WHERE o.id = %s
            """, (order_id,))
            order = cursor.fetchone()
            
            cursor.execute("""
                SELECT oi.quantity, oi.price, oi.size, p.name as product_name, p.brand 
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
            """, (order_id,))
            order_items = cursor.fetchall()
    finally:
        connection.close()
        
    if not order:
        flash('Pesanan tidak ditemukan.', 'danger')
        return redirect(url_for('admin.manage_orders'))

    # Meminjam template invoice milik customer agar bentuknya persis sama 100%
    return render_template('customer/invoice.html', order=order, order_items=order_items)