import os
import pymysql
from urllib.parse import urlparse

# Blok pengaman agar aman di Vercel/Production jika python-dotenv tidak terinstal
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'garudasport-rahasia-banget-2026')
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    # Fallback lokal (XAMPP/Laragon) jika DATABASE_URL tidak ada
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'garudasport_db')
    DB_PORT = int(os.getenv('DB_PORT', 3306))

# Fungsi global untuk mengambil koneksi database MySQL
def get_db_connection():
    db_url = Config.DATABASE_URL
    
    if db_url:
        # Koneksi menggunakan URL dari Railway (Vercel Production)
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
        # Koneksi lokal (XAMPP/Laragon)
        return pymysql.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            port=Config.DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )

def create_notification(cursor, user_id, title, message, notif_type='info'):
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type, is_read)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, title, message, notif_type))

    