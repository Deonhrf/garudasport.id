from flask import Flask, render_template, request, session
from config import Config, get_db_connection
from blueprints.customer import customer_bp
from blueprints.chat import chat_bp
import pymysql


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
# --- FILTER RUPIAH UNTUK JINJA2 ---
# --- FILTER RUPIAH UNTUK JINJA2 ---
def format_rupiah(value) -> str:
    try:
        # HAPUS * 1000 karena data di database sekarang sudah utuh (misal: 649000)
        val = float(value) 
        return f"Rp{val:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"

app.jinja_env.filters["rupiah"] = format_rupiah

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
    # Menangkap parameter dari HTML (sekarang kita pakai 'brand', bukan 'category')
    selected_brand = request.args.get("brand", "") 
    search_query = request.args.get("q", "")
    
    connection = get_db_connection()
    cart_count = 0  # Default keranjang 0 jika user belum login
    
    try:
        # Gunakan DictCursor agar hasil query berbentuk dictionary
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. Query dasar mengambil produk dari database MySQL
            sql = "SELECT * FROM products WHERE 1=1"
            params = []
            
            # 2. Jika user mengetik pencarian (search)
            if search_query:
                sql += " AND (name LIKE %s OR brand LIKE %s OR description LIKE %s)"
                params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
                
            # 3. Jika user menekan tombol filter Brand (Specs / Ortus / Mills)
            if selected_brand:
                sql += " AND brand = %s"
                params.append(selected_brand)
                
            # Urutkan dari produk terbaru
            sql += " ORDER BY id DESC"
            
            # Eksekusi query produk
            cursor.execute(sql, params)
            filtered_products = cursor.fetchall()
                
            # --- Logika mengambil jumlah keranjang ---
            if 'user_id' in session:
                try:
                    cursor.execute("SELECT SUM(quantity) as total_items FROM cart WHERE user_id = %s", (session['user_id'],))
                    cart_result = cursor.fetchone()
                    cart_count = int(cart_result['total_items']) if cart_result and cart_result['total_items'] else 0
                except:
                    cart_count = 0
            # --------------------------------------------------------

    finally:
        connection.close()

    # Variabel CATEGORIES dihapus karena tombol filter brand sekarang sudah diatur langsung di HTML

    return render_template(
        "catalog.html",
        products=filtered_products,
        selected_brand=selected_brand, # Kirim parameter brand kembali ke HTML
        search_query=search_query,
        cart_count=cart_count
    )

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)