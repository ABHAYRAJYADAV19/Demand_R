from flask import render_template, redirect, url_for, flash, request, jsonify
from app import app, db
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import os
from datetime import datetime,timedelta
from bson import ObjectId

# Configure upload folder
UPLOAD_FOLDER = 'd:/DemandRadar/app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Fetch reviews from MongoDB
    reviews = []
    if db is not None:
        try:
            reviews = list(db.feedback.find().sort('created_at', -1).limit(3))
        except Exception as e:
            print(f"Error fetching reviews: {e}")
    return render_template('index.html', reviews=reviews)

@app.route('/report-need', methods=['GET'])
def report_need():
    return render_template('report_need.html')

@app.route('/submit-report', methods=['POST'])
def submit_report():
    try:
        # Get form data
        data = {
            'name': request.form.get('name'),
            'email': request.form.get('email'),
            'location': request.form.get('location'),
            'service_type': request.form.get('service_type'),
            'description': request.form.get('description'),
            'submitted_at': datetime.utcnow()
        }

        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                data['image_path'] = f'uploads/{filename}'

        # Store in MongoDB
        if db is not None:
            db.user_needs.insert_one(data)
            return jsonify({'success': True, 'message': 'Report submitted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Database not available'}), 503
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/business/dashboard')
def business_dashboard():
    return render_template('business_dashboard.html')

@app.route('/insights')
def insights():
    if db is None:
        return render_template('insights.html', 
                             total_submissions=0,
                             recent_submissions=0,
                             most_requested={'service': 'Database not available', 'count': 0, 'description': ''})
    
    try:
        # Get total submissions
        total_submissions = db.user_needs.count_documents({})
        
        # Get submissions in last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_submissions = db.user_needs.count_documents({'submitted_at': {'$gte': yesterday}})
        
        # Get most requested service
        top_service = db.user_needs.aggregate([
            {'$group': {
                '_id': {
                    'service': '$service_type',
                    'description': '$description'
                },
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 1}
        ])
        
        top_service = list(top_service)
        most_requested = {
            'service': 'No requests yet',
            'count': 0,
            'description': ''
        }
        
        if top_service:
            most_requested = {
                'service': top_service[0]['_id']['service'],
                'count': top_service[0]['count'],
                'description': top_service[0]['_id']['description'][:50] + '...' if top_service[0]['_id']['description'] else ''
            }
        
        return render_template('insights.html', 
                             total_submissions=total_submissions,
                             recent_submissions=recent_submissions,
                             most_requested=most_requested)
    except Exception as e:
        print(f"Error in insights: {e}")
        return render_template('insights.html', 
                             total_submissions=0,
                             recent_submissions=0,
                             most_requested={'service': 'Error loading data', 'count': 0, 'description': ''})

# Add email configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "yourgmail.com"  # Replace with your Gmail address
SMTP_PASSWORD = "app password"  # Replace with your App Password

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Detailed email error: {str(e)}")
        return False

@app.route('/send-referral', methods=['POST'])
def send_referral():
    try:
        data = request.get_json()
        email = data.get('email')
        
        subject = "You've been invited to join your neighborhood community!"
        body = "Hey! Your friend thinks you'd love this platform for requesting local services. Join them today!"
        
        if send_email(email, subject, body):
            return jsonify({'success': True, 'message': 'Referral sent'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send email'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/subscribe-newsletter', methods=['POST'])
def subscribe_newsletter():
    try:
        data = request.get_json()
        email = data.get('email')
        
        # Store subscriber in database
        if db is not None:
            db.subscribers.insert_one({
                'email': email,
                'subscribed_at': datetime.utcnow()
            })
        
        subject = "You've subscribed to Neighborhood Updates!"
        body = "Thanks for subscribing. You'll now get the latest updates on community needs and services."
        
        if send_email(email, subject, body):
            return jsonify({'success': True, 'message': 'Subscription successful'})
        else:
            return jsonify({'success': False, 'message': 'Subscription saved but email failed'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json()
        feedback = {
            'name': data.get('name'),
            'rating': data.get('rating'),
            'feedback': data.get('feedback'),
            'created_at': datetime.utcnow()
        }
        
        # Using db instead of mongo
        if db is not None:
            db.feedback.insert_one(feedback)
            return jsonify({'success': True, 'message': 'Feedback submitted successfully'}), 200
        else:
            return jsonify({'success': False, 'message': 'Database not available'}), 503
    except Exception as e:
        print('Error:', str(e))  # For debugging
        return jsonify({'success': False, 'message': str(e)}), 500