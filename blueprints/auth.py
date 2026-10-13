from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import pymysql
import os
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

# Fungsi helper untuk koneksi database
def get_db_connection():
    db_url = os.getenv('DATABASE_URL')
    
    if db_url:
        # Koneksi ke Railway (Production Vercel)
        parsed_url = urlparse(db_url)
        return pymysql.connect(
            host=parsed_url.hostname,
            user=parsed_url.username,
            password=parsed_url.password,
            database=parsed_url.path[1:],
            port=parsed_url.port or 3306,
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        # Koneksi lokal XAMPP (Development)
        return pymysql.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'garudasport_db'),
            port=int(os.getenv('DB_PORT', 3306)),
            cursorclass=pymysql.cursors.DictCursor
        )
# --- ROUTE REGISTER ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nama = request.form['nama']
        email = request.form['email']
        password = request.form['password']
        
        # Enkripsi password agar aman di database
        hashed_password = generate_password_hash(password)
        
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # Cek apakah email sudah terdaftar
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    flash('Email sudah terdaftar! Silakan gunakan email lain atau login.', 'danger')
                    return redirect(url_for('auth.register'))
                
                # Masukkan user baru ke database (Status default otomatis 'Aktif' dari MySQL)
                cursor.execute(
                    "INSERT INTO users (nama, email, password, role) VALUES (%s, %s, %s, 'user')",
                    (nama, email, hashed_password)
                )
                connection.commit()
                flash('Registrasi berhasil! Silakan masuk menggunakan akunmu.', 'success')
                return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Terjadi kesalahan: {e}', 'danger')
        finally:
            connection.close()
            
    return render_template('register.html')

# --- ROUTE LOGIN ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cursor.fetchone()
                
                # Cek password cocok atau tidak
                if user and check_password_hash(user['password'], password):
                    
                    # ==========================================
                    # [BARU] VALIDASI CEK STATUS AKUN DIBLOKIR
                    # ==========================================
                    if user['role'] != 'admin' and user.get('status') == 'Diblokir':
                        flash('Akun Anda telah diblokir karena aktivitas yang melanggar ketentuan. Silakan hubungi Admin.', 'danger')
                        return redirect(url_for('auth.login'))
                    # ==========================================
                    
                    # Simpan data penting ke Session Flask
                    session['user_id'] = user['id']
                    session['nama'] = user['nama']
                    session['role'] = user['role']
                    
                    flash(f"Selamat datang kembali, {user['nama']}!", 'success')
                    
                    # Lempar halaman sesuai role user
                    if user['role'] == 'admin':
                        return redirect(url_for('admin.dashboard')) 
                    else:
                        return redirect(url_for('customer.dashboard')) 
                else:
                    flash('Email atau password salah! Silakan coba lagi.', 'danger')
        finally:
            connection.close()
            
    return render_template('login.html')

# --- ROUTE LOGOUT ---
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Anda telah keluar dari akun.', 'info')
    return redirect(url_for('auth.login'))