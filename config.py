import os
import pymysql

# Blok pengaman agar aman di Vercel/Production jika python-dotenv tidak terinstal
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'garudasport-rahasia-banget-2026')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'garudasport_db')

# Fungsi global untuk mengambil koneksi database MySQL
def get_db_connection():
    return pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def create_notification(cursor, user_id, title, message, notif_type='info'):
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type, is_read)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, title, message, notif_type))