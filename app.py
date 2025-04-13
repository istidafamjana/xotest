import os
import uuid
import hashlib
import logging
import tempfile
import urllib.request
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
from threading import Lock
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pytz
import pdfplumber
import docx
from PIL import Image
import arabic_reshaper
from bidi.algorithm import get_display
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = "oth-ai-super-secret-key-" + str(uuid.uuid4())
app.config.update(
    UPLOAD_FOLDER='static/uploads',
    ALLOWED_EXTENSIONS={'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'txt'},
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=5),
    TIMEZONE='Asia/Riyadh',
    TEMPLATES_AUTO_RELOAD=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('oth-ai')
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

class UserManager:
    def __init__(self):
        self.users = {}
        self.conversations = {}
        self.files = {}
        self._lock = Lock()
        self.create_default_admin()

    def create_default_admin(self):
        admin_id = str(uuid.uuid4())
        self.users["admin"] = {
            'id': admin_id,
            'username': 'admin',
            'password': generate_password_hash('admin123'),
            'email': 'admin@oth.ai',
            'role': 'admin',
            'created_at': self.current_time,
            'last_login': None,
            'settings': {'theme': 'dark', 'language': 'ar'}
        }
        self.conversations[admin_id] = {
            'history': [],
            'created_at': self.current_time,
            'updated_at': self.current_time,
            'title': 'محادثة جديدة'
        }

    @property
    def current_time(self):
        return datetime.now(pytz.timezone(app.config['TIMEZONE']))

    def add_user(self, username, password, email):
        with self._lock:
            if username in self.users:
                return False
            user_id = str(uuid.uuid4())
            self.users[username] = {
                'id': user_id,
                'username': username,
                'password': generate_password_hash(password),
                'email': email,
                'role': 'user',
                'created_at': self.current_time,
                'last_login': None,
                'settings': {'theme': 'light', 'language': 'ar'}
            }
            self.conversations[user_id] = {
                'history': [],
                'created_at': self.current_time,
                'updated_at': self.current_time,
                'title': 'محادثة جديدة'
            }
            return True

    def verify_user(self, username, password):
        user = self.users.get(username)
        if user and check_password_hash(user['password'], password):
            user['last_login'] = self.current_time
            return user
        return None

    def get_conversation(self, user_id):
        return self.conversations.get(user_id)

    def add_message(self, user_id, message, sender='user'):
        with self._lock:
            if user_id not in self.conversations:
                self.conversations[user_id] = {
                    'history': [],
                    'created_at': self.current_time,
                    'updated_at': self.current_time,
                    'title': message[:30] + ('...' if len(message) > 30 else '')
                }
            self.conversations[user_id]['history'].append({
                'id': str(uuid.uuid4()),
                'content': message,
                'timestamp': self.current_time,
                'sender': sender
            })
            self.conversations[user_id]['updated_at'] = self.current_time

    def get_user_conversations(self, user_id):
        return {user_id: self.conversations.get(user_id, {'history': []})}

db = UserManager()

genai.configure(api_key="AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")
model = genai.GenerativeModel('gemini-1.5-flash')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = db.users.get(session.get('username'))
        if not user or user.get('role') != 'admin':
            flash('غير مصرح بالوصول', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def process_uploaded_file(file):
    try:
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        file_id = str(uuid.uuid4())
        new_filename = f"{file_id}.{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        
        if file_ext in ['png', 'jpg', 'jpeg', 'gif']:
            return {'type': 'image', 'path': filepath, 'original_name': filename}
        elif file_ext == 'pdf':
            text = ""
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            return {'type': 'pdf', 'path': filepath, 'original_name': filename, 'content': text[:500]}
        elif file_ext == 'docx':
            doc = docx.Document(filepath)
            text = "\n".join([para.text for para in doc.paragraphs])
            return {'type': 'docx', 'path': filepath, 'original_name': filename, 'content': text[:500]}
        else:
            return {'type': 'file', 'path': filepath, 'original_name': filename}
    except Exception as e:
        logger.error(f"File processing error: {str(e)}")
        return None

def generate_ai_response(prompt, context=None):
    try:
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        logger.error(f"AI generation error: {str(e)}")
        return "عذرًا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا."

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = db.verify_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = username
            session.permanent = True
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        if len(username) < 4 or len(password) < 6:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل وكلمة المرور 6 أحرف', 'danger')
        elif db.add_user(username, password, email):
            flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
            return redirect(url_for('login'))
        else:
            flash('اسم المستخدم موجود بالفعل', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = db.users.get(session.get('username'))
    conversations = db.get_user_conversations(session['user_id'])
    return render_template('dashboard.html', user=user, conversations=conversations)

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    user_id = session['user_id']
    conversation = db.get_conversation(user_id)
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        file = request.files.get('file')
        
        if not message and not file:
            flash('الرجاء إدخال رسالة أو تحميل ملف', 'warning')
        else:
            if file and allowed_file(file.filename):
                file_info = process_uploaded_file(file)
                if file_info:
                    db.add_message(user_id, f"ملف مرفق: {file_info['original_name']}")
            
            if message:
                db.add_message(user_id, message)
                response = generate_ai_response(message)
                db.add_message(user_id, response, 'bot')
        
        return redirect(url_for('chat'))
    
    return render_template('chat.html', conversation=conversation)

@app.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def api_chat():
    user_id = session['user_id']
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({'error': 'طلب غير صالح'}), 400
    
    message = data['message'].strip()
    if not message:
        return jsonify({'error': 'الرسالة لا يمكن أن تكون فارغة'}), 400
    
    db.add_message(user_id, message)
    response = generate_ai_response(message)
    db.add_message(user_id, response, 'bot')
    
    return jsonify({'reply': response}), 200

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = db.users.get(session.get('username'))
    
    if request.method == 'POST':
        theme = request.form.get('theme')
        language = request.form.get('language')
        email = request.form.get('email')
        
        user['settings']['theme'] = theme
        user['settings']['language'] = language
        user['email'] = email
        
        flash('تم تحديث الإعدادات بنجاح', 'success')
        return redirect(url_for('settings'))
    
    return render_template('settings.html', user=user)

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/admin')
@admin_required
def admin_panel():
    users = db.users
    return render_template('admin.html', users=users)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(threaded=True)
