from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import google.generativeai as genai
import logging
import tempfile
import urllib.request
import os
import hashlib
import time
import uuid
import json
import re
from datetime import datetime, timedelta
from threading import Lock, Thread
from functools import wraps
from io import BytesIO
import base64
from PIL import Image
import pytz
from dateutil import parser
import random
import string

# ======== Initialization ========
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

# ======== Enhanced Logging Configuration ========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ======== Configuration Classes ========
class AppConfig:
    class Security:
        PASSWORD_HASH_METHOD = 'pbkdf2:sha256'
        PASSWORD_SALT_LENGTH = 16
        SESSION_TOKEN_LENGTH = 32
        CSRF_TOKEN_LENGTH = 32
        RATE_LIMIT = 100  # Requests per minute
        
    class Gemini:
        MODEL_NAME = 'gemini-1.5-flash'
        SAFETY_SETTINGS = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
        
    class Conversation:
        HISTORY_LIMIT = 20
        TIMEOUT = 5 * 60 * 60  # 5 hours
        MAX_MESSAGE_LENGTH = 2000
        
    class FileUpload:
        ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'txt'}
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ======== API Keys and External Services ========
class ApiConfig:
    FACEBOOK = {
        'PAGE_ACCESS_TOKEN': "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD",
        'VERIFY_TOKEN': "d51ee4e3183dbbd9a27b7d2c1af8c655",
        'API_VERSION': 'v17.0'
    }
    
    GEMINI = {
        'API_KEY': "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU",
        'GENERATION_CONFIG': {
            'temperature': 0.7,
            'top_p': 0.9,
            'top_k': 40,
            'max_output_tokens': 2048
        }
    }

# ======== Database Simulation ========
class Database:
    def __init__(self):
        self.users = {}
        self.conversations = {}
        self.sessions = {}
        self.lock = Lock()
        self.load_data()
        
    def load_data(self):
        try:
            if os.path.exists('users.json'):
                with open('users.json', 'r') as f:
                    self.users = json.load(f)
                    
            if os.path.exists('conversations.json'):
                with open('conversations.json', 'r') as f:
                    self.conversations = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load data: {str(e)}")
            
    def save_data(self):
        try:
            with open('users.json', 'w') as f:
                json.dump(self.users, f, indent=2)
                
            with open('conversations.json', 'w') as f:
                json.dump(self.conversations, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save data: {str(e)}")
            
    def add_user(self, username, password, email=None):
        user_id = str(uuid.uuid4())
        self.users[username] = {
            'id': user_id,
            'username': username,
            'password': generate_password_hash(
                password,
                method=AppConfig.Security.PASSWORD_HASH_METHOD,
                salt_length=AppConfig.Security.PASSWORD_SALT_LENGTH
            ),
            'email': email,
            'created_at': datetime.now(pytz.utc).isoformat(),
            'last_login': None,
            'is_admin': False,
            'preferences': {
                'theme': 'light',
                'language': 'ar'
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
                'last_active': time.time(),
                'metadata': {
                    'model': AppConfig.Gemini.MODEL_NAME,
                    'context_window': AppConfig.Conversation.HISTORY_LIMIT
                }
            }
        return self.conversations[user_id]
        
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

# ======== Initialize Services ========
db = Database()
genai.configure(api_key=ApiConfig.GEMINI['API_KEY'])
model = genai.GenerativeModel(
    model_name=AppConfig.Gemini.MODEL_NAME,
    generation_config=ApiConfig.GEMINI['GENERATION_CONFIG'],
    safety_settings=AppConfig.Gemini.SAFETY_SETTINGS
)

# ======== Utility Functions ========
def generate_csrf_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=AppConfig.Security.CSRF_TOKEN_LENGTH))

def validate_username(username):
    return re.match(r'^[a-zA-Z0-9_]{4,20}$', username)

def validate_password(password):
    return len(password) >= 6

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
        logger.error(f"Image processing error: {str(e)}")
        return None

# ======== Security Middlewares ========
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

# ======== Facebook Messenger Integration ========
class FacebookBot:
    @staticmethod
    def setup_messenger_profile():
        url = f"https://graph.facebook.com/{ApiConfig.FACEBOOK['API_VERSION']}/me/messenger_profile"
        params = {'access_token': ApiConfig.FACEBOOK['PAGE_ACCESS_TOKEN']}
        
        profile_data = {
            "get_started": {"payload": "GET_STARTED"},
            "persistent_menu": [
                {
                    "locale": "default",
                    "composer_input_disabled": False,
                    "call_to_actions": [
                        {
                            "type": "web_url",
                            "title": "🌐 الانتقال للويب",
                            "url": "https://yourdomain.com/chat",
                            "webview_height_ratio": "full",
                            "messenger_extensions": True
                        },
                        {
                            "type": "postback",
                            "title": "🆘 المساعدة",
                            "payload": "HELP"
                        }
                    ]
                }
            ],
            "whitelisted_domains": ["https://yourdomain.com"],
            "greeting": [
                {
                    "locale": "default",
                    "text": "مرحبًا بك في بوت OTH AI! 💎"
                }
            ]
        }
        
        try:
            response = requests.post(url, params=params, json=profile_data)
            response.raise_for_status()
            logger.info("Facebook messenger profile setup successful")
            return True
        except Exception as e:
            logger.error(f"Facebook profile setup failed: {str(e)}")
            return False

    @staticmethod
    def send_message(recipient_id, message, quick_replies=None):
        url = f"https://graph.facebook.com/{ApiConfig.FACEBOOK['API_VERSION']}/me/messages"
        params = {'access_token': ApiConfig.FACEBOOK['PAGE_ACCESS_TOKEN']}
        
        message_data = {
            "recipient": {"id": recipient_id},
            "messaging_type": "RESPONSE",
            "message": {"text": message}
        }
        
        if quick_replies:
            message_data["message"]["quick_replies"] = quick_replies
            
        try:
            response = requests.post(url, params=params, json=message_data)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Facebook message: {str(e)}")
            return False

    @staticmethod
    def handle_message(sender_id, message):
        with db.lock:
            conversation = db.get_conversation(sender_id)
            
            if len(message) > AppConfig.Conversation.MAX_MESSAGE_LENGTH:
                message = message[:AppConfig.Conversation.MAX_MESSAGE_LENGTH] + "..."
                
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
                
                FacebookBot.send_message(sender_id, reply)
            except Exception as e:
                logger.error(f"Failed to generate response: {str(e)}")
                FacebookBot.send_message(sender_id, "عذرًا، حدث خطأ أثناء معالجة رسالتك.")

# ======== Web Routes ========
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
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not validate_username(username):
            flash('اسم المستخدم يجب أن يكون بين 4-20 حرفًا (أحرف إنجليزية، أرقام، _)', 'danger')
        elif not validate_password(password):
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        elif password != confirm_password:
            flash('كلمات المرور غير متطابقة', 'danger')
        elif username in db.users:
            flash('اسم المستخدم موجود بالفعل', 'danger')
        else:
            user_id = db.add_user(username, password)
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
        'conversation_count': len(conversation['history']),
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
            
            return jsonify({
                'reply': reply,
                'timestamp': format_timestamp(time.time())
            })
        except Exception as e:
            logger.error(f"Chat API error: {str(e)}")
            return jsonify({'error': 'حدث خطأ أثناء معالجة رسالتك'}), 500

# ======== Facebook Webhook ========
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == ApiConfig.FACEBOOK['VERIFY_TOKEN']:
            if FacebookBot.setup_messenger_profile():
                return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if event.get('message'):
                    message = event['message'].get('text', '')
                    if message:
                        FacebookBot.handle_message(sender_id, message)
                
                elif event.get('postback'):
                    payload = event['postback']['payload']
                    if payload == 'GET_STARTED':
                        FacebookBot.send_message(sender_id, "مرحبًا بك في بوت OTH AI! اكتب رسالتك وسأساعدك.")
                    elif payload == 'HELP':
                        FacebookBot.send_message(
                            sender_id,
                            "مركز المساعدة:\n\n- اكتب سؤالك مباشرة\n- أرسل 'مساعدة' للحصول على خيارات إضافية",
                            quick_replies=[
                                {
                                    "content_type": "text",
                                    "title": "البدء",
                                    "payload": "GET_STARTED"
                                }
                            ]
                        )
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'}), 200

# ======== Background Tasks ========
def background_cleanup():
    while True:
        time.sleep(3600)  # Run hourly
        try:
            cleaned = db.cleanup_old_conversations()
            logger.info(f"Cleaned up {cleaned} old conversations")
        except Exception as e:
            logger.error(f"Cleanup task failed: {str(e)}")

# ======== HTML Templates ========
BASE_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - OTH AI</title>
    <style>
        /* CSS styles here (over 150 lines) */
    </style>
</head>
<body>
    <header>
        <h1>نظام OTH AI</h1>
    </header>
    <nav>
        {% if 'user_id' in session %}
            <a href="{{ url_for('logout') }}">تسجيل الخروج</a>
            <a href="{{ url_for('chat') }}">الدردشة</a>
            <a href="{{ url_for('dashboard') }}">لوحة التحكم</a>
        {% else %}
            <a href="{{ url_for('login') }}">تسجيل الدخول</a>
            <a href="{{ url_for('register') }}">إنشاء حساب</a>
        {% endif %}
        <a href="{{ url_for('home') }}">الرئيسية</a>
    </nav>
    <div class="container">
        {% for category, message in get_flashed_messages(with_categories=true) %}
            <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
        {{ content | safe }}
    </div>
    <script>
        /* JavaScript code here (over 100 lines) */
    </script>
</body>
</html>
"""

HOME_CONTENT = """
<div class="hero">
    <h2>مرحبًا بك في نظام الذكاء الاصطناعي المتقدم</h2>
    <p>نظام متكامل للدردشة الذكية وتحليل المحتوى</p>
    {% if 'user_id' not in session %}
        <div class="auth-buttons">
            <a href="{{ url_for('login') }}" class="btn btn-primary">تسجيل الدخول</a>
            <a href="{{ url_for('register') }}" class="btn btn-secondary">إنشاء حساب</a>
        </div>
    {% endif %}
</div>
"""

LOGIN_CONTENT = """
<div class="auth-form">
    <h2>تسجيل الدخول</h2>
    <form method="POST" action="{{ url_for('login') }}">
        <input type="text" name="username" placeholder="اسم المستخدم" required>
        <input type="password" name="password" placeholder="كلمة المرور" required>
        <button type="submit" class="btn btn-primary">تسجيل الدخول</button>
    </form>
    <p>ليس لديك حساب؟ <a href="{{ url_for('register') }}">سجل الآن</a></p>
</div>
"""

REGISTER_CONTENT = """
<div class="auth-form">
    <h2>إنشاء حساب جديد</h2>
    <form method="POST" action="{{ url_for('register') }}">
        <input type="text" name="username" placeholder="اسم المستخدم" required>
        <input type="password" name="password" placeholder="كلمة المرور" required>
        <input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور" required>
        <button type="submit" class="btn btn-primary">إنشاء حساب</button>
    </form>
    <p>لديك حساب بالفعل؟ <a href="{{ url_for('login') }}">سجل الدخول</a></p>
</div>
"""

DASHBOARD_CONTENT = """
<div class="dashboard">
    <h2>مرحبًا {username}!</h2>
    <div class="stats">
        <div class="stat-card">
            <h3>معلومات الحساب</h3>
            <p><strong>تاريخ الانضمام:</strong> {stats[joined_date]}</p>
            <p><strong>آخر نشاط:</strong> {stats[last_active]}</p>
        </div>
        <div class="stat-card">
            <h3>إحصائيات المحادثة</h3>
            <p><strong>عدد الرسائل:</strong> {stats[conversation_count]}</p>
        </div>
    </div>
    <div class="actions">
        <a href="{{ url_for('chat') }}" class="btn btn-primary">بدء محادثة جديدة</a>
    </div>
</div>
"""

CHAT_CONTENT = """
<div class="chat-container">
    <div class="chat-header">
        <h2>الدردشة مع الذكاء الاصطناعي</h2>
    </div>
    <div class="chat-messages" id="chat-messages">
        {% for msg in messages %}
            <div class="message {% if msg.sender == 'user' %}user-message{% else %}bot-message{% endif %}">
                <div class="message-content">{{ msg.message }}</div>
                <div class="message-time">{{ format_timestamp(msg.timestamp) }}</div>
            </div>
        {% endfor %}
    </div>
    <div class="chat-input">
        <form id="chat-form">
            <input type="text" id="message-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
            <button type="submit" class="btn btn-primary">إرسال</button>
        </form>
    </div>
</div>
<script>
    // JavaScript for chat functionality
</script>
"""

# ======== Main Execution ========
if __name__ == '__main__':
    # Start background tasks
    cleanup_thread = Thread(target=background_cleanup)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    # Configure and run the app
    app.run(
        threaded=True,
        debug=False,
        ssl_context='adhoc' if os.environ.get('FLASK_ENV') == 'production' else None
    )
    
