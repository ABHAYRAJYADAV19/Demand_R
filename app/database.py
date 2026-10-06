"""Database bootstrap.

Primary store is MongoDB. If it cannot be reached, a mongomock in-memory database
(same pymongo API) is used and persisted to a JSON file after every write, so the
whole app stays functional on machines without MongoDB installed.
"""
import json
import os
from datetime import datetime

from bson import ObjectId, json_util

COLLECTIONS = ['user_needs', 'feedback', 'subscribers', 'business_subscribers',
               'contact_messages', 'referrals']


def _persist_wrapper(db, path):
    """Monkey-patch write operations on mongomock collections to snapshot to disk."""
    def save():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        dump = {name: list(db[name].find()) for name in COLLECTIONS}
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(json_util.dumps(dump))
        os.replace(tmp, path)

    for name in COLLECTIONS:
        col = db[name]
        for method in ('insert_one', 'insert_many', 'update_one', 'delete_one', 'delete_many'):
            original = getattr(col, method)

            def make(orig):
                def wrapped(*a, **kw):
                    result = orig(*a, **kw)
                    save()
                    return result
                return wrapped
            setattr(col, method, make(original))
    return save


def init_db(config):
    try:
        from pymongo import MongoClient
        client = MongoClient(config['MONGO_URI'], serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        print('[db] MongoDB connected')
        return client[config['MONGO_DB_NAME']], 'mongodb'
    except Exception as exc:  # noqa: BLE001
        print(f'[db] MongoDB unavailable ({exc.__class__.__name__}); using local file-backed fallback store')

    import mongomock
    db = mongomock.MongoClient()[config['MONGO_DB_NAME']]
    path = config['FALLBACK_DB_FILE']
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as fh:
                data = json_util.loads(fh.read())
            for name, docs in data.items():
                if docs:
                    db[name].insert_many(docs)
        except Exception as exc:  # noqa: BLE001
            print(f'[db] Could not load snapshot: {exc}')
    _persist_wrapper(db, path)
    return db, 'local-file'
