from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from config import get_db_connection

# Blueprint tunggal untuk menangani chat customer dan admin sekaligus
chat_bp = Blueprint('chat', __name__, template_folder='templates')

# ==========================================
# 1. SISI CUSTOMER: RUANG CHAT DENGAN ADMIN
# ==========================================
@chat_bp.route('/customer/chat', methods=['GET', 'POST'])
def customer_chat():
    if 'user_id' not in session or session.get('role') == 'admin':
        flash('Silakan login sebagai pembeli untuk mengakses layanan chat.', 'danger')
        return redirect(url_for('auth.login'))
        
    user_id = session['user_id']
    customer_name = session.get('nama', 'Pelanggan')
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Cari ID Admin di database
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            admin = cursor.fetchone()
            admin_id = admin['id'] if admin else 1
            
            # Kirim pesan baru dari customer
            if request.method == 'POST':
                message = request.form.get('message', '').strip()
                if message:
                    cursor.execute("""
                        INSERT INTO chats (sender_id, receiver_id, message) 
                        VALUES (%s, %s, %s)
                    """, (user_id, admin_id, message))
                    
                    # [NOTIFIKASI] Kirim notifikasi otomatis ke admin bahwa ada pesan baru dari customer
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, type, is_read)
                        VALUES (%s, %s, %s, %s, 0)
                    """, (admin_id, "Pesan Chat Baru", f"Ada pesan baru dari {customer_name}.", "chat"))

                    connection.commit()
                return redirect(url_for('chat.customer_chat'))
                
            # Ambil riwayat chat antara customer ini dan admin
            cursor.execute("""
                SELECT * FROM chats 
                WHERE (sender_id = %s AND receiver_id = %s) 
                   OR (sender_id = %s AND receiver_id = %s)
                ORDER BY created_at ASC
            """, (user_id, admin_id, admin_id, user_id))
            messages = cursor.fetchall()
            
    except Exception as e:
        print(f"ERROR CUSTOMER CHAT: {e}")
        messages = []
        admin_id = 1
    finally:
        connection.close()
        
    return render_template('customer/chat.html', messages=messages, admin_id=admin_id)


# ==========================================
# 2. SISI ADMIN: DAFTAR INBOX & BALAS PESAN
# ==========================================
@chat_bp.route('/admin/chats', methods=['GET'])
def admin_chats():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Silakan login sebagai admin.', 'danger')
        return redirect(url_for('auth.login'))
        
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Ambil daftar customer yang pernah berinteraksi via chat
            cursor.execute("""
                SELECT DISTINCT u.id, u.nama, u.email 
                FROM users u
                JOIN chats c ON c.sender_id = u.id OR c.receiver_id = u.id
                WHERE u.role != 'admin'
            """)
            customers = cursor.fetchall()
    except Exception as e:
        print(f"ERROR ADMIN MANAGE CHATS: {e}")
        customers = []
    finally:
        connection.close()
        
    return render_template('admin/chats.html', customers=customers)


@chat_bp.route('/admin/chats/<int:customer_id>', methods=['GET', 'POST'])
def admin_chat_detail(customer_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Silakan login sebagai admin.', 'danger')
        return redirect(url_for('auth.login'))
        
    admin_id = session['user_id']
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Kirim balasan dari admin ke customer tertentu
            if request.method == 'POST':
                message = request.form.get('message', '').strip()
                if message:
                    cursor.execute("""
                        INSERT INTO chats (sender_id, receiver_id, message) 
                        VALUES (%s, %s, %s)
                    """, (admin_id, customer_id, message))
                    
                    # [NOTIFIKASI] Kirim notifikasi otomatis ke customer bahwa admin membalas pesan mereka
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, type, is_read)
                        VALUES (%s, %s, %s, %s, 0)
                    """, (customer_id, "Balasan Pesan", "Admin telah membalas pesan Anda.", "chat"))

                    connection.commit()
                return redirect(url_for('chat.admin_chat_detail', customer_id=customer_id))
                
            # Ambil detail informasi customer
            cursor.execute("SELECT * FROM users WHERE id = %s", (customer_id,))
            customer = cursor.fetchone()
            
            # Ambil riwayat percakapan antara admin dan customer ini
            cursor.execute("""
                SELECT * FROM chats 
                WHERE (sender_id = %s AND receiver_id = %s) 
                   OR (sender_id = %s AND receiver_id = %s)
                ORDER BY created_at ASC
            """, (admin_id, customer_id, customer_id, admin_id))
            messages = cursor.fetchall()
            
    except Exception as e:
        print(f"ERROR ADMIN CHAT DETAIL: {e}")
        messages = []
        customer = None
    finally:
        connection.close()
        
    return render_template('admin/chat_detail.html', messages=messages, customer=customer, admin_id=admin_id)