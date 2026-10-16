import os
import pymysql
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'garudasport-rahasia-banget-2026')
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'garudasport_db')
    DB_PORT = int(os.getenv('DB_PORT', 3306))

def get_db_connection():
    db_url = Config.DATABASE_URL
    
    if db_url:
        parsed_url = urlparse(db_url)
        conn = pymysql.connect(
            host=parsed_url.hostname,
            user=parsed_url.username,
            password=parsed_url.password,
            database=parsed_url.path[1:],
            port=parsed_url.port or 3306,
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        conn = pymysql.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            port=Config.DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
    
    # PAKSA ZONE WAKTU INDONESIA (WIB / GMT+7)
    with conn.cursor() as cursor:
        cursor.execute("SET time_zone = '+07:00';")
        
    return conn

def create_notification(cursor, user_id, title, message, notif_type='info'):
    cursor.execute("""
        INSERT INTO notifications (user_id, title, message, type, is_read)
        VALUES (%s, %s, %s, %s, 0)
    """, (user_id, title, message, notif_type))