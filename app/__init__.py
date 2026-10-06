import os

from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

from app.database import init_db  # noqa: E402

db, DB_MODE = init_db(app.config)
app.config['DB_MODE'] = DB_MODE

from app import routes  # noqa: E402,F401
