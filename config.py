import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-change-me'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/demandradar'
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME') or 'demandradar'
    # When MongoDB is unreachable the app falls back to an in-memory store that is
    # snapshotted to this JSON file so data survives restarts.
    FALLBACK_DB_FILE = os.environ.get('FALLBACK_DB_FILE') or os.path.join(BASE_DIR, 'instance', 'local_db.json')
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    # Optional SMTP settings (emails are skipped, not faked, when unset)
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
