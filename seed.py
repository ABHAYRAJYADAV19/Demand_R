"""Optional demo data: python seed.py  (skips if reports already exist)."""
import random
from datetime import datetime, timedelta

from app import db

CITIES = [("Connaught Place, Delhi", 28.6315, 77.2167), ("Andheri, Mumbai", 19.1136, 72.8697),
          ("Koramangala, Bengaluru", 12.9352, 77.6245), ("Salt Lake, Kolkata", 22.5867, 88.4177),
          ("Banjara Hills, Hyderabad", 17.4156, 78.4347)]
SERVICES = [("Fitness Center", 6), ("Coffee Shop", 5), ("Bakery", 3), ("Child Care", 3), ("Other", 1)]

if db.user_needs.count_documents({}) == 0:
    random.seed(7)
    pool = [s for s, w in SERVICES for _ in range(w)]
    for i in range(60):
        place, lat, lng = random.choice(CITIES)
        db.user_needs.insert_one({
            'name': f'Resident {i + 1}', 'email': f'resident{i + 1}@example.com', 'location': place,
            'service_type': random.choice(pool), 'description': 'Would love to have this nearby.',
            'lat': lat + random.uniform(-.01, .01), 'lng': lng + random.uniform(-.01, .01),
            'submitted_at': datetime.utcnow() - timedelta(hours=random.randint(0, 200))})
    db.feedback.insert_many([
        {'name': 'Priya S.', 'rating': 5, 'feedback': 'I reported a missing bakery and it was a joy to see it get attention.', 'created_at': datetime.utcnow()},
        {'name': 'Rahul M.', 'rating': 4, 'feedback': 'Simple to use, and the insights are genuinely useful for our shop.', 'created_at': datetime.utcnow() - timedelta(hours=1)},
    ])
    print('Seeded demo data.')
else:
    print('Data already present; nothing to seed.')
