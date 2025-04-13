from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import google.generativeai as genai
import logging
import os
import uuid
import json
import time
from datetime import datetime, timedelta
from threading import Lock
from functools import wraps
import pytz
from dateutil import parser
import random
import string
import re
from io import BytesIO
import base64
from PIL import Image
import mimetypes

# ===== التهيئة الأساسية =====
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# ===== إعدادات السجل =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== تهيئة نموذج Gemini =====
genai.configure(api_key="AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")
model = genai.GenerativeModel('gemini-1.5-flash')

# ===== فئات التكوين =====
class AppConfig:
    class Security:
        PASSWORD_HASH_METHOD = 'pbkdf2:sha256'
        SALT_LENGTH = 16
        SESSION_TOKEN_LENGTH = 32
        CSRF_TOKEN_LENGTH = 32
        
    class Upload:
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'txt', 'docx'}
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        
    class Conversation:
        HISTORY_LIMIT = 10
        TIMEOUT = 5 * 60 * 60  # 5 hours
        MAX_MESSAGE_LENGTH = 2000

# ===== محاكاة قاعدة البيانات =====
class Database:
    def __init__(self):
        self.users = {}
        self.conversations = {}
        self.files = {}
        self.lock = Lock()
        self.load_data()
        
    def load_data(self):
        try:
            if os.path.exists('data/users.json'):
                with open('data/users.json', 'r') as f:
                    self.users = json.load(f)
                    
            if os.path.exists('data/conversations.json'):
                with open('data/conversations.json', 'r') as f:
                    self.conversations = json.load(f)
                    
            if os.path.exists('data/files.json'):
                with open('data/files.json', 'r') as f:
                    self.files = json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل البيانات: {str(e)}")
            
    def save_data(self):
        try:
            os.makedirs('data', exist_ok=True)
            
            with open('data/users.json', 'w') as f:
                json.dump(self.users, f, indent=2)
                
            with open('data/conversations.json', 'w') as f:
                json.dump(self.conversations, f, indent=2)
                
            with open('data/files.json', 'w') as f:
                json.dump(self.files, f, indent=2)
        except Exception as e:
            logger.error(f"خطأ في حفظ البيانات: {str(e)}")
            
    def add_user(self, username, email, password):
        user_id = str(uuid.uuid4())
        self.users[username] = {
            'id': user_id,
            'username': username,
            'email': email,
            'password': generate_password_hash(
                password,
                method=AppConfig.Security.PASSWORD_HASH_METHOD,
                salt_length=AppConfig.Security.SALT_LENGTH
            ),
            'created_at': datetime.now(pytz.utc).isoformat(),
            'last_login': None,
            'is_admin': False,
            'profile': {
                'avatar': None,
                'bio': ''
            }
        }
        self.save_data()
        return user_id
        
    def verify_user(self, username, password):
        user = self.users.get(username)
        if user and check_password_hash(user['password'], password):
            return user
        return None
        
    def get_conversation(self, user_id):
        if user_id not in self.conversations:
            self.conversations[user_id] = {
                'history': [],
                'created_at': datetime.now(pytz.utc).isoformat(),
                'last_active': time.time()
            }
        return self.conversations[user_id]
        
    def add_file(self, user_id, filename, file_type, file_size):
        file_id = str(uuid.uuid4())
        self.files[file_id] = {
            'user_id': user_id,
            'filename': filename,
            'file_type': file_type,
            'file_size': file_size,
            'uploaded_at': datetime.now(pytz.utc).isoformat()
        }
        self.save_data()
        return file_id
        
    def cleanup_old_conversations(self):
        current_time = time.time()
        to_delete = []
        
        for user_id, conv in self.conversations.items():
            if current_time - conv['last_active'] > AppConfig.Conversation.TIMEOUT:
                to_delete.append(user_id)
                
        for user_id in to_delete:
            del self.conversations[user_id]
            
        self.save_data()
        return len(to_delete)

# ===== تهيئة قاعدة البيانات =====
db = Database()

# ===== وظائف مساعدة =====
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in AppConfig.Upload.ALLOWED_EXTENSIONS

def generate_csrf_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=AppConfig.Security.CSRF_TOKEN_LENGTH))

def format_timestamp(timestamp):
    if isinstance(timestamp, str):
        dt = parser.parse(timestamp)
    else:
        dt = datetime.fromtimestamp(timestamp, pytz.utc)
    return dt.astimezone(pytz.timezone('Asia/Riyadh')).strftime('%Y-%m-%d %H:%M:%S')

def process_image(file):
    try:
        img = Image.open(BytesIO(file.read()))
        img.thumbnail((800, 800))
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {str(e)}")
        return None

# ===== وسائط الأمان =====
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
        if 'user_id' not in session or not db.users.get(session.get('username'), {}).get('is_admin'):
            flash('غير مسموح بالوصول', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ===== مسارات الموقع =====
@app.route('/')
def home():
    return render_template_string(BASE_TEMPLATE, content=HOME_CONTENT, title="الرئيسية")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = db.verify_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = username
            session['csrf_token'] = generate_csrf_token()
            
            user['last_login'] = datetime.now(pytz.utc).isoformat()
            db.save_data()
            
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template_string(BASE_TEMPLATE, content=LOGIN_CONTENT, title="تسجيل الدخول")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if len(username) < 4:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل', 'danger')
        elif not re.match(r'^[\w.@+-]+$', username):
            flash('اسم المستخدم يحتوي على أحرف غير مسموحة', 'danger')
        elif not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('البريد الإلكتروني غير صالح', 'danger')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        elif password != confirm_password:
            flash('كلمات المرور غير متطابقة', 'danger')
        elif username in db.users:
            flash('اسم المستخدم موجود بالفعل', 'danger')
        else:
            user_id = db.add_user(username, email, password)
            session['user_id'] = user_id
            session['username'] = username
            session['csrf_token'] = generate_csrf_token()
            
            flash('تم إنشاء الحساب بنجاح!', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template_string(BASE_TEMPLATE, content=REGISTER_CONTENT, title="إنشاء حساب")

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = db.users.get(session['username'])
    conversation = db.get_conversation(session['user_id'])
    
    stats = {
        'messages': len(conversation['history']),
        'last_active': format_timestamp(conversation['last_active']),
        'joined_date': format_timestamp(user['created_at'])
    }
    
    return render_template_string(
        BASE_TEMPLATE,
        content=DASHBOARD_CONTENT.format(
            username=session['username'],
            stats=stats
        ),
        title="لوحة التحكم"
    )

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = db.users.get(session['username'])
    
    if request.method == 'POST':
        bio = request.form.get('bio', '').strip()
        avatar = request.files.get('avatar')
        
        if avatar and allowed_file(avatar.filename):
            filename = secure_filename(f"{session['user_id']}_{avatar.filename}")
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            user['profile']['avatar'] = filename
            
        user['profile']['bio'] = bio
        db.save_data()
        flash('تم تحديث الملف الشخصي بنجاح', 'success')
        return redirect(url_for('profile'))
    
    return render_template_string(
        BASE_TEMPLATE,
        content=PROFILE_CONTENT.format(
            username=user['username'],
            email=user['email'],
            bio=user['profile']['bio'],
            avatar=user['profile']['avatar'] or 'default_avatar.png'
        ),
        title="الملف الشخصي"
    )

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/chat')
@login_required
def chat():
    conversation = db.get_conversation(session['user_id'])
    return render_template_string(
        BASE_TEMPLATE,
        content=CHAT_CONTENT,
        title="الدردشة",
        messages=conversation['history']
    )

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'الرسالة فارغة'}), 400
    
    with db.lock:
        conversation = db.get_conversation(session['user_id'])
        
        conversation['history'].append({
            'sender': 'user',
            'message': message,
            'timestamp': time.time()
        })
        
        try:
            context = "\n".join(
                f"{msg['sender']}: {msg['message']}" 
                for msg in conversation['history'][-AppConfig.Conversation.HISTORY_LIMIT:]
            )
            
            response = model.generate_content(f"{context}\n\nassistant:")
            reply = response.text
            
            conversation['history'].append({
                'sender': 'bot',
                'message': reply,
                'timestamp': time.time()
            })
            conversation['last_active'] = time.time()
            db.save_data()
            
            return jsonify({
                'reply': reply,
                'timestamp': format_timestamp(time.time())
            })
        except Exception as e:
            logger.error(f"خطأ في الدردشة: {str(e)}")
            return jsonify({'error': 'حدث خطأ أثناء معالجة رسالتك'}), 500

@app.route('/files', methods=['GET', 'POST'])
@login_required
def files():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            file_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            file_size = os.path.getsize(filepath)
            
            db.add_file(
                session['user_id'],
                filename,
                file_type,
                file_size
            )
            
            flash('تم رفع الملف بنجاح', 'success')
            return redirect(url_for('files'))
        else:
            flash('نوع الملف غير مسموح به', 'danger')
    
    user_files = [
        f for f in db.files.values() 
        if f['user_id'] == session['user_id']
    ]
    
    return render_template_string(
        BASE_TEMPLATE,
        content=FILES_CONTENT.format(files=user_files),
        title="الملفات"
    )

# ===== قوالب HTML =====
BASE_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - OTH AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-color: #4285f4;
            --secondary-color: #34a853;
            --dark-color: #202124;
            --light-color: #f8f9fa;
        }
        
        body {
            font-family: 'Tajawal', sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }
        
        .navbar {
            background-color: var(--dark-color);
        }
        
        .navbar-brand, .nav-link {
            color: white !important;
        }
        
        .card {
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
            border: none;
        }
        
        .btn-primary {
            background-color: var(--primary-color);
            border-color: var(--primary-color);
        }
        
        .chat-container {
            height: 500px;
            overflow-y: auto;
            background-color: white;
            border-radius: 10px;
            padding: 15px;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 10px 15px;
            border-radius: 10px;
            max-width: 80%;
        }
        
        .user-message {
            background-color: var(--primary-color);
            color: white;
            margin-left: auto;
        }
        
        .bot-message {
            background-color: #e9ecef;
            margin-right: auto;
        }
        
        .avatar {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            object-fit: cover;
        }
        
        .file-icon {
            font-size: 3rem;
            color: var(--primary-color);
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="/"><i class="fas fa-home"></i> الرئيسية</a>
                    </li>
                    {% if 'user_id' in session %}
                    <li class="nav-item">
                        <a class="nav-link" href="/dashboard"><i class="fas fa-tachometer-alt"></i> لوحة التحكم</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/chat"><i class="fas fa-comments"></i> الدردشة</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/files"><i class="fas fa-file-upload"></i> الملفات</a>
                    </li>
                    {% endif %}
                </ul>
                <ul class="navbar-nav">
                    {% if 'user_id' in session %}
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="fas fa-user-circle"></i> {{ session['username'] }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/profile"><i class="fas fa-user"></i> الملف الشخصي</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="/logout"><i class="fas fa-sign-out-alt"></i> تسجيل الخروج</a></li>
                        </ul>
                    </li>
                    {% else %}
                    <li class="nav-item">
                        <a class="nav-link" href="/login"><i class="fas fa-sign-in-alt"></i> تسجيل الدخول</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/register"><i class="fas fa-user-plus"></i> إنشاء حساب</a>
                    </li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <div class="container my-5">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {{ content | safe }}
    </div>

    <footer class="bg-dark text-white py-4 mt-5">
        <div class="container text-center">
            <p>جميع الحقوق محفوظة &copy; OTH AI 2023</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // JavaScript for chat functionality
        document.addEventListener('DOMContentLoaded', function() {
            // Auto-scroll chat to bottom
            const chatContainer = document.querySelector('.chat-container');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
                
                // Handle chat form submission
                const chatForm = document.getElementById('chat-form');
                if (chatForm) {
                    chatForm.addEventListener('submit', function(e) {
                        e.preventDefault();
                        const input = document.getElementById('message-input');
                        const message = input.value.trim();
                        
                        if (message) {
                            // Add user message to chat
                            const userMessage = document.createElement('div');
                            userMessage.className = 'message user-message';
                            userMessage.innerHTML = `
                                <div class="message-content">${message}</div>
                                <div class="message-time">${new Date().toLocaleTimeString()}</div>
                            `;
                            chatContainer.appendChild(userMessage);
                            
                            // Clear input
                            input.value = '';
                            
                            // Scroll to bottom
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                            
                            // Send to server
                            fetch('/api/chat', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({ message: message })
                            })
                            .then(response => response.json())
                            .then(data => {
                                if (data.error) {
                                    throw new Error(data.error);
                                }
                                
                                // Add bot response to chat
                                const botMessage = document.createElement('div');
                                botMessage.className = 'message bot-message';
                                botMessage.innerHTML = `
                                    <div class="message-content">${data.reply}</div>
                                    <div class="message-time">${new Date().toLocaleTimeString()}</div>
                                `;
                                chatContainer.appendChild(botMessage);
                                
                                // Scroll to bottom
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            })
                            .catch(error => {
                                console.error('Error:', error);
                            });
                        }
                    });
                }
            }
        });
    </script>
</body>
</html>
"""

HOME_CONTENT = """
<div class="row">
    <div class="col-md-8 mx-auto text-center">
        <h1 class="display-4 mb-4">مرحبًا بك في OTH AI</h1>
        <p class="lead">نظام الذكاء الاصطناعي المتقدم للدردشة وتحليل المحتوى</p>
        
        {% if 'user_id' not in session %}
        <div class="d-grid gap-2 d-sm-flex justify-content-sm-center mt-4">
            <a href="/login" class="btn btn-primary btn-lg px-4 gap-3">
                <i class="fas fa-sign-in-alt"></i> تسجيل الدخول
            </a>
            <a href="/register" class="btn btn-outline-secondary btn-lg px-4">
                <i class="fas fa-user-plus"></i> إنشاء حساب
            </a>
        </div>
        {% else %}
        <div class="d-grid gap-2 d-sm-flex justify-content-sm-center mt-4">
            <a href="/chat" class="btn btn-primary btn-lg px-4 gap-3">
                <i class="fas fa-comments"></i> بدء الدردشة
            </a>
            <a href="/dashboard" class="btn btn-outline-primary btn-lg px-4">
                <i class="fas fa-tachometer-alt"></i> لوحة التحكم
            </a>
        </div>
        {% endif %}
    </div>
</div>

<div class="row mt-5">
    <div class="col-md-4 mb-4">
        <div class="card h-100">
            <div class="card-body text-center">
                <i class="fas fa-robot fa-3x mb-3 text-primary"></i>
                <h3 class="card-title">ذكاء اصطناعي متقدم</h3>
                <p class="card-text">نظام دردشة ذكي يستخدم أحدث تقنيات الذكاء الاصطناعي</p>
            </div>
        </div>
    </div>
    
    <div class="col-md-4 mb-4">
        <div class="card h-100">
            <div class="card-body text-center">
                <i class="fas fa-file-upload fa-3x mb-3 text-primary"></i>
                <h3 class="card-title">تحليل الملفات</h3>
                <p class="card-text">قم بتحميل الملفات واحصل على تحليل مفصل لمحتواها</p>
            </div>
        </div>
    </div>
    
    <div class="col-md-4 mb-4">
        <div class="card h-100">
            <div class="card-body text-center">
                <i class="fas fa-history fa-3x mb-3 text-primary"></i>
                <h3 class="card-title">سجل المحادثات</h3>
                <p class="card-text">احتفظ بسجل كامل لمحادثاتك للرجوع إليها لاحقًا</p>
            </div>
        </div>
    </div>
</div>
"""

LOGIN_CONTENT = """
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">تسجيل الدخول</h3>
            </div>
            <div class="card-body">
                <form method="POST" action="/login">
                    <div class="mb-3">
                        <label for="username" class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">كلمة المرور</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-sign-in-alt"></i> تسجيل الدخول
                    </button>
                </form>
                <div class="mt-3 text-center">
                    <p>ليس لديك حساب؟ <a href="/register">سجل الآن</a></p>
                </div>
            </div>
        </div>
    </div>
</div>
"""

REGISTER_CONTENT = """
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">إنشاء حساب جديد</h3>
            </div>
            <div class="card-body">
                <form method="POST" action="/register">
                    <div class="mb-3">
                        <label for="username" class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                        <div class="form-text">4 أحرف على الأقل (أحرف إنجليزية، أرقام، _)</div>
                    </div>
                    <div class="mb-3">
                        <label for="email" class="form-label">البريد الإلكتروني</label>
                        <input type="email" class="form-control" id="email" name="email" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">كلمة المرور</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                        <div class="form-text">6 أحرف على الأقل</div>
                    </div>
                    <div class="mb-3">
                        <label for="confirm_password" class="form-label">تأكيد كلمة المرور</label>
                        <input type="password" class="form-control" id="confirm_password" name="confirm_password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-user-plus"></i> إنشاء حساب
                    </button>
                </form>
                <div class="mt-3 text-center">
                    <p>لديك حساب بالفعل؟ <a href="/login">سجل الدخول هنا</a></p>
                </div>
            </div>
        </div>
    </div>
</div>
"""

DASHBOARD_CONTENT = """
<div class="row">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">مرحبًا {username}</h3>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-4">
                        <div class="card text-center">
                            <div class="card-body">
                                <h5><i class="fas fa-comment-dots"></i> عدد الرسائل</h5>
                                <p class="display-6">{stats[messages]}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card text-center">
                            <div class="card-body">
                                <h5><i class="fas fa-calendar-check"></i> تاريخ الانضمام</h5>
                                <p class="display-6">{stats[joined_date]}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card text-center">
                            <div class="card-body">
                                <h5><i class="fas fa-clock"></i> آخر نشاط</h5>
                                <p class="display-6">{stats[last_active]}</p>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mt-4">
                    <div class="col-md-6">
                        <a href="/chat" class="btn btn-primary btn-lg w-100">
                            <i class="fas fa-comments"></i> بدء محادثة جديدة
                        </a>
                    </div>
                    <div class="col-md-6">
                        <a href="/profile" class="btn btn-outline-primary btn-lg w-100">
                            <i class="fas fa-user"></i> تعديل الملف الشخصي
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""

PROFILE_CONTENT = """
<div class="row justify-content-center">
    <div class="col-md-8">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">الملف الشخصي</h3>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-4 text-center">
                        <img src="{{ url_for('uploaded_file', filename=avatar) }}" class="avatar mb-3" alt="صورة الملف الشخصي">
                        <form method="POST" action="/profile" enctype="multipart/form-data">
                            <div class="mb-3">
                                <input type="file" class="form-control" name="avatar" accept="image/*">
                            </div>
                    </div>
                    <div class="col-md-8">
                        <div class="mb-3">
                            <label class="form-label">اسم المستخدم</label>
                            <input type="text" class="form-control" value="{username}" readonly>
                        </div>
                        <div class="mb-3">
                            <label class="form-label">البريد الإلكتروني</label>
                            <input type="text" class="form-control" value="{email}" readonly>
                        </div>
                        <div class="mb-3">
                            <label for="bio" class="form-label">نبذة عنك</label>
                            <textarea class="form-control" id="bio" name="bio" rows="3">{bio}</textarea>
                        </div>
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-save"></i> حفظ التغييرات
                        </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""

CHAT_CONTENT = """
<div class="card">
    <div class="card-header bg-primary text-white">
        <h3 class="mb-0">الدردشة مع الذكاء الاصطناعي</h3>
    </div>
    <div class="card-body">
        <div class="chat-container" id="chat-box">
            {% for msg in messages %}
            <div class="message {% if msg.sender == 'user' %}user-message{% else %}bot-message{% endif %}">
                <div class="message-content">{{ msg.message }}</div>
                <div class="message-time">{{ format_timestamp(msg.timestamp) }}</div>
            </div>
            {% endfor %}
        </div>
        
        <form id="chat-form" class="mt-3">
            <div class="input-group">
                <input type="text" id="message-input" class="form-control" placeholder="اكتب رسالتك هنا..." autocomplete="off">
                <button class="btn btn-primary" type="submit">
                    <i class="fas fa-paper-plane"></i> إرسال
                </button>
            </div>
        </form>
    </div>
</div>
"""

FILES_CONTENT = """
<div class="card">
    <div class="card-header bg-primary text-white">
        <h3 class="mb-0">إدارة الملفات</h3>
    </div>
    <div class="card-body">
        <form method="POST" action="/files" enctype="multipart/form-data">
            <div class="mb-3">
                <label for="file" class="form-label">رفع ملف جديد</label>
                <input class="form-control" type="file" id="file" name="file" required>
                <div class="form-text">الملفات المسموحة: PNG, JPG, PDF, TXT, DOCX (بحد أقصى 10MB)</div>
            </div>
            <button type="submit" class="btn btn-primary">
                <i class="fas fa-upload"></i> رفع الملف
            </button>
        </form>
        
        <hr>
        
        <h4 class="mt-4">ملفاتك</h4>
        {% if files %}
        <div class="row">
            {% for file in files %}
            <div class="col-md-3 mb-4">
                <div class="card text-center">
                    <div class="card-body">
                        <i class="fas fa-file-alt file-icon"></i>
                        <h5 class="card-title mt-2">{{ file.filename }}</h5>
                        <p class="card-text text-muted">{{ (file.file_size / 1024 / 1024)|round(2) }} MB</p>
                        <a href="{{ url_for('uploaded_file', filename=file.filename) }}" class="btn btn-sm btn-outline-primary">
                            <i class="fas fa-download"></i> تحميل
                        </a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="alert alert-info">
            لا توجد ملفات مرفوعة بعد
        </div>
        {% endif %}
    </div>
</div>
"""

# ===== تشغيل التطبيق =====
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # Start background cleanup thread
    def cleanup_task():
        while True:
            time.sleep(3600)  # Run hourly
            cleaned = db.cleanup_old_conversations()
            logger.info(f"تم تنظيف {cleaned} محادثة قديمة")
    
    import threading
    cleanup_thread = threading.Thread(target=cleanup_task)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    app.run(threaded=True)
