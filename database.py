# database.py
import pyodbc
import os
from dotenv import load_dotenv
import traceback

load_dotenv()

class DatabaseConnection:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
            cls._instance._initialize_connection()
        return cls._instance

    def _initialize_connection(self):
        try:
            self.conn = pyodbc.connect(
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={os.getenv('DB_SERVER', 'Vincenza')};"
                f"DATABASE={os.getenv('DB_NAME', 'Kutuphane_Sistemi')};"
                f"UID={os.getenv('DB_USER', 'KutuphaneUygulamasi')};"
                f"PWD={os.getenv('DB_PASSWORD', 'YeniSifreniz123!')}"
            )
            print("Veritabanı bağlantısı başarılı.")
        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            print(f"Veritabanı bağlantı hatası: SQLState: {sqlstate}")
            traceback.print_exc()
            self.conn = None
        except Exception as e:
            # Diğer genel hatalar için
            print(f"Genel hata: {e}")
            traceback.print_exc()
            self.conn = None

    def get_connection(self):
        """Veritabanı bağlantısını döndürür."""
        if self.conn and not self.conn.closed:
            return self.conn
        else:
            # Bağlantı kapalıysa yeniden kurmaya çalış
            self._initialize_connection()
            return self.conn

    def close_connection(self):
        """Veritabanı bağlantısını kapatır."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            print("Veritabanı bağlantısı kapatıldı.")
        self._instance = None


# Global bağlantı fonksiyonu
def get_db_connection():
    """Veritabanı bağlantısını sağlar (singleton pattern)."""
    db = DatabaseConnection()
    return db.get_connection()