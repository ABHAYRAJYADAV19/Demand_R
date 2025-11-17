from flask import Flask
from pymongo import MongoClient
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize MongoDB with error handling
try:
    client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
    # Test connection
    client.admin.command('ping')
    db = client.demandradar
    print("✓ MongoDB connected successfully")
except Exception as e:
    print(f"⚠ MongoDB connection failed: {e}")
    print("⚠ App will run with limited functionality")
    # Create a mock db object
    db = None

from app import routes