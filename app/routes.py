import os
import re
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from flask import (jsonify, redirect, render_template, request, session,
                   url_for)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from app import app, db

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
SERVICE_TYPES = ['Fitness Center', 'Bakery', 'Coffee Shop', 'Child Care', 'Other']
BUSINESS_CATEGORIES = ['Retail', 'Restaurant', 'Healthcare', 'Education', 'Fitness', 'Other']
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# ---------------------------------------------------------------- helpers
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def ok(message, status=200, **extra):
    return jsonify({'success': True, 'message': message, **extra}), status


def fail(message, status=400, **extra):
    return jsonify({'success': False, 'message': message, **extra}), status


def valid_email(value):
    return bool(value) and bool(EMAIL_RE.match(value))


def clean(value, limit=500):
    return (value or '').strip()[:limit]


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def send_email(to_email, subject, body):
    """Send via SMTP when configured. Returns 'sent', 'skipped' or 'failed'."""
    user, password = app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD']
    if not user or not password:
        print(f'[email] SMTP not configured; skipped "{subject}" to {to_email}')
        return 'skipped'
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = user, to_email, subject
        msg.attach(MIMEText(body, 'plain'))
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'], timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return 'sent'
    except Exception as exc:  # noqa: BLE001
        print(f'[email] failed: {exc}')
        return 'failed'


def business_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get('business_email'):
            if request.path.startswith('/api/'):
                return fail('Business subscription required', 401)
            return redirect(url_for('business_dashboard') + '#subscribe')
        return view(*args, **kwargs)
    return wrapper


def build_stats(category=None):
    """Aggregate anonymised demand data (no personal fields)."""
    query = {}
    if category and category != 'all':
        query['service_type'] = category
    needs = list(db.user_needs.find(query))
    day_ago = datetime.utcnow() - timedelta(days=1)

    by_category = {}
    clusters = {}
    for n in needs:
        svc = n.get('service_type') or 'Other'
        by_category[svc] = by_category.get(svc, 0) + 1
        lat, lng = n.get('lat'), n.get('lng')
        if lat is not None and lng is not None:
            key = (round(lat, 1), round(lng, 1))
            c = clusters.setdefault(key, {'lat': key[0], 'lng': key[1], 'count': 0,
                                          'services': {}, 'location': n.get('location', '')})
            c['count'] += 1
            c['services'][svc] = c['services'].get(svc, 0) + 1

    cluster_list = []
    for c in clusters.values():
        top = max(c['services'].items(), key=lambda kv: kv[1])[0]
        cluster_list.append({'lat': c['lat'], 'lng': c['lng'], 'count': c['count'],
                             'top_service': top, 'location': c['location']})
    cluster_list.sort(key=lambda c: -c['count'])

    return {
        'total': len(needs),
        'recent': sum(1 for n in needs if n.get('submitted_at') and n['submitted_at'] >= day_ago),
        'categories': sorted(({'name': k, 'count': v} for k, v in by_category.items()),
                             key=lambda x: -x['count']),
        'clusters': cluster_list,
    }


@app.context_processor
def inject_globals():
    return {'now_year': datetime.utcnow().year}


# ---------------------------------------------------------------- pages
@app.route('/')
def index():
    reviews = []
    try:
        reviews = list(db.feedback.find().sort('created_at', -1).limit(3))
    except Exception as exc:  # noqa: BLE001
        print(f'Error fetching reviews: {exc}')
    return render_template('index.html', reviews=reviews, service_types=SERVICE_TYPES)


@app.route('/report-need', methods=['GET'])
def report_need():
    return render_template('report_need.html', service_types=SERVICE_TYPES)


@app.route('/insights')
def insights():
    stats = build_stats()
    top = stats['categories'][0] if stats['categories'] else None
    return render_template('insights.html', stats=stats, top=top)


@app.route('/business/dashboard')
def business_dashboard():
    return render_template('business_dashboard.html',
                           categories=BUSINESS_CATEGORIES,
                           service_types=SERVICE_TYPES,
                           business=session.get('business_name'),
                           business_email=session.get('business_email'))


@app.route('/business/requests')
@business_required
def business_requests():
    return render_template('business_requests.html', service_types=SERVICE_TYPES,
                           business=session.get('business_name'))


@app.route('/business/logout')
def business_logout():
    session.pop('business_email', None)
    session.pop('business_name', None)
    return redirect(url_for('business_dashboard'))


# ---------------------------------------------------------------- APIs
@app.route('/submit-report', methods=['POST'])
def submit_report():
    name = clean(request.form.get('name'), 100)
    email = clean(request.form.get('email'), 150)
    location = clean(request.form.get('location'), 200)
    service_type = clean(request.form.get('service_type'), 50)
    description = clean(request.form.get('description'), 1000)

    errors = {}
    if len(name) < 2:
        errors['name'] = 'Please enter your name.'
    if not valid_email(email):
        errors['email'] = 'Please enter a valid email address.'
    if len(location) < 2:
        errors['location'] = 'Please enter a location.'
    if service_type not in SERVICE_TYPES:
        errors['service_type'] = 'Please choose a service type.'

    lat, lng = parse_float(request.form.get('lat')), parse_float(request.form.get('lng'))
    if lat is not None and lng is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
        lat = lng = None
    elif (lat is None) != (lng is None):
        lat = lng = None

    image_path = None
    file = request.files.get('image')
    if file and file.filename:
        if not allowed_file(file.filename):
            errors['image'] = 'Image must be JPG, PNG or GIF.'
        else:
            filename = f'{uuid.uuid4().hex[:10]}_{secure_filename(file.filename)}'
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f'uploads/{filename}'

    if errors:
        return fail('Please fix the highlighted fields.', 422, errors=errors)

    doc = {'name': name, 'email': email, 'location': location, 'service_type': service_type,
           'description': description, 'lat': lat, 'lng': lng,
           'submitted_at': datetime.utcnow()}
    if image_path:
        doc['image_path'] = image_path
    db.user_needs.insert_one(doc)
    return ok('Report submitted successfully')


@app.route('/api/stats')
def api_stats():
    return jsonify(build_stats(request.args.get('category')))


@app.route('/api/needs')
@business_required
def api_needs():
    category = request.args.get('category')
    query = {}
    if category and category != 'all':
        query['service_type'] = category
    needs = db.user_needs.find(query).sort('submitted_at', -1).limit(200)
    items = [{
        'service_type': n.get('service_type'),
        'location': n.get('location'),
        'description': n.get('description', ''),
        'lat': n.get('lat'), 'lng': n.get('lng'),
        'image': n.get('image_path'),
        'submitted_at': n['submitted_at'].strftime('%d %b %Y') if n.get('submitted_at') else '',
    } for n in needs]
    return jsonify({'items': items})


@app.route('/send-referral', methods=['POST'])
def send_referral():
    data = request.get_json(silent=True) or {}
    email = clean(data.get('email'), 150)
    if not valid_email(email):
        return fail('Please enter a valid email address.', 422)
    db.referrals.insert_one({'email': email, 'created_at': datetime.utcnow()})
    status = send_email(email, "You've been invited to join your neighborhood community!",
                        "Hey! Your friend thinks you'd love DemandRadar, a platform for "
                        "requesting local services. Join them today!")
    if status == 'failed':
        return fail('Referral saved, but the email could not be sent.', 502)
    msg = 'Referral sent!' if status == 'sent' else 'Referral recorded (email delivery is not configured).'
    return ok(msg)


@app.route('/subscribe-newsletter', methods=['POST'])
def subscribe_newsletter():
    data = request.get_json(silent=True) or {}
    email = clean(data.get('email'), 150).lower()
    if not valid_email(email):
        return fail('Please enter a valid email address.', 422)
    if db.subscribers.find_one({'email': email}):
        return ok("You're already subscribed. Thanks!")
    db.subscribers.insert_one({'email': email, 'subscribed_at': datetime.utcnow()})
    status = send_email(email, "You've subscribed to Neighborhood Updates!",
                        "Thanks for subscribing. You'll now get the latest updates on "
                        "community needs and services.")
    msg = 'Subscription successful!' if status != 'failed' else 'Subscribed, but the confirmation email failed.'
    return ok(msg)


@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    data = request.get_json(silent=True) or {}
    name = clean(data.get('name'), 80)
    text = clean(data.get('feedback'), 800)
    try:
        rating = int(data.get('rating'))
    except (TypeError, ValueError):
        rating = 0
    if not name or not text:
        return fail('Please provide your name and feedback.', 422)
    if not 1 <= rating <= 5:
        return fail('Please choose a rating from 1 to 5.', 422)
    db.feedback.insert_one({'name': name, 'rating': rating, 'feedback': text,
                            'created_at': datetime.utcnow()})
    return ok('Feedback submitted successfully')


@app.route('/business/subscribe', methods=['POST'])
def business_subscribe():
    data = request.get_json(silent=True) or {}
    name, company = clean(data.get('name'), 100), clean(data.get('company'), 150)
    email, phone = clean(data.get('email'), 150).lower(), clean(data.get('phone'), 30)
    category = clean(data.get('category'), 50)
    errors = {}
    if len(name) < 2:
        errors['name'] = 'Enter your name.'
    if len(company) < 2:
        errors['company'] = 'Enter your company name.'
    if not valid_email(email):
        errors['email'] = 'Enter a valid email.'
    if len(re.sub(r'\D', '', phone)) < 7:
        errors['phone'] = 'Enter a valid phone number.'
    if category.title() not in BUSINESS_CATEGORIES:
        errors['category'] = 'Select a category.'
    if errors:
        return fail('Please fix the highlighted fields.', 422, errors=errors)

    existing = db.business_subscribers.find_one({'email': email})
    if not existing:
        db.business_subscribers.insert_one({
            'name': name, 'company': company, 'email': email, 'phone': phone,
            'category': category, 'created_at': datetime.utcnow()})
    session['business_email'] = email
    session['business_name'] = (existing or {}).get('company') or company
    return ok('Welcome aboard! Opening your dashboard...', redirect=url_for('business_requests'))


@app.route('/business/login', methods=['POST'])
def business_login():
    data = request.get_json(silent=True) or {}
    email = clean(data.get('email'), 150).lower()
    if not valid_email(email):
        return fail('Enter a valid email.', 422)
    biz = db.business_subscribers.find_one({'email': email})
    if not biz:
        return fail('No subscription found for that email. Please subscribe first.', 404)
    session['business_email'] = email
    session['business_name'] = biz.get('company')
    return ok('Signed in', redirect=url_for('business_requests'))


@app.route('/contact', methods=['POST'])
def contact():
    data = request.get_json(silent=True) or {}
    name, email, message = clean(data.get('name'), 100), clean(data.get('email'), 150), clean(data.get('message'), 2000)
    if len(name) < 2 or not valid_email(email) or len(message) < 5:
        return fail('Please provide your name, a valid email and a message.', 422)
    db.contact_messages.insert_one({'name': name, 'email': email, 'message': message,
                                    'created_at': datetime.utcnow()})
    return ok("Message sent. We'll get back to you soon.")


# ---------------------------------------------------------------- errors
@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return fail('File is too large (max 10MB).', 413)


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith(('/api/', '/submit', '/send', '/business/')) and request.method != 'GET':
        return fail('Not found', 404)
    return render_template('error.html', code=404, title='Page not found',
                           text="The page you're looking for doesn't exist."), 404


@app.errorhandler(500)
def server_error(_):
    return render_template('error.html', code=500, title='Something went wrong',
                           text='An unexpected error occurred. Please try again.'), 500
