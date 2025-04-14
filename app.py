import os
import json
import hashlib
import uuid
import time
from datetime import datetime, timedelta
from threading import Lock, Thread
from functools import wraps
import tempfile
import urllib.request
import logging
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import google.generativeai as genai

# تكوين التطبيق الأساسي
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح (ابقاء جزء فيسبوك كما هو)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين البيانات
DATA_FILE = "users_data.json"
conversations = {}
users = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
data_lock = Lock()

# تعريف القوالب المضمنة
TEMPLATES = {
    'index.html': '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTH AI - منصة الذكاء الاصطناعي</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .hero-section { background: linear-gradient(135deg, #6e8efb, #a777e3); }
        .feature-icon { font-size: 2rem; color: #6e8efb; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
            <div class="collapse navbar-collapse">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="/chat">المحادثة</a></li>
                </ul>
                <div class="d-flex">
                    {% if 'user_id' in session %}
                        <a href="/logout" class="btn btn-outline-light">تسجيل الخروج</a>
                    {% else %}
                        <a href="/login" class="btn btn-outline-light me-2">تسجيل الدخول</a>
                        <a href="/register" class="btn btn-primary">إنشاء حساب</a>
                    {% endif %}
                </div>
            </div>
        </div>
    </nav>

    <section class="hero-section text-white py-5">
        <div class="container py-5 text-center">
            <h1 class="display-4 fw-bold">منصة الذكاء الاصطناعي OTH</h1>
            <p class="lead">تجربة محادثة متقدمة مع Gemini 1.5 Flash</p>
            {% if 'user_id' not in session %}
                <a href="/register" class="btn btn-light btn-lg mt-3">ابدأ الآن</a>
            {% else %}
                <a href="/chat" class="btn btn-light btn-lg mt-3">اذهب إلى المحادثة</a>
            {% endif %}
        </div>
    </section>

    <div class="container py-5">
        <div class="row g-4">
            <div class="col-md-4">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <div class="feature-icon mb-3">💎</div>
                        <h3>ذكاء اصطناعي متقدم</h3>
                        <p>محادثات ذكية مع نموذج Gemini 1.5 Flash من جوجل</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <div class="feature-icon mb-3">📸</div>
                        <h3>تحليل الصور</h3>
                        <p>فهم وتحليل الصور والمحتوى المرئي</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <div class="feature-icon mb-3">🔒</div>
                        <h3>آمن وسري</h3>
                        <p>نظام تسجيل دخول آمن وحماية البيانات</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <footer class="bg-dark text-white py-4">
        <div class="container text-center">
            <p>© 2023 OTH AI. جميع الحقوق محفوظة.</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''',
    
    'login.html': '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - OTH AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .login-card { max-width: 500px; margin: 0 auto; border-radius: 10px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
        </div>
    </nav>

    <div class="container py-5">
        <div class="login-card card shadow">
            <div class="card-body p-5">
                <h2 class="card-title text-center mb-4">تسجيل الدخول</h2>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <form method="POST" action="/login">
                    <input type="hidden" name="next" value="{{ request.args.get('next', '') }}">
                    
                    <div class="mb-3">
                        <label for="username" class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    
                    <div class="mb-4">
                        <label for="password" class="form-label">كلمة المرور</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100 py-2">تسجيل الدخول</button>
                </form>
                
                <div class="text-center mt-3">
                    <p>ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a></p>
                    <p><a href="/">العودة للصفحة الرئيسية</a></p>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''',
    
    'register.html': '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إنشاء حساب - OTH AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .register-card { max-width: 500px; margin: 0 auto; border-radius: 10px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
        </div>
    </nav>

    <div class="container py-5">
        <div class="register-card card shadow">
            <div class="card-body p-5">
                <h2 class="card-title text-center mb-4">إنشاء حساب جديد</h2>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <form method="POST" action="/register">
                    <div class="mb-3">
                        <label for="username" class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                        <div class="form-text">يجب أن يكون 4 أحرف على الأقل</div>
                    </div>
                    
                    <div class="mb-4">
                        <label for="password" class="form-label">كلمة المرور</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                        <div class="form-text">يجب أن تكون 6 أحرف على الأقل</div>
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100 py-2">إنشاء حساب</button>
                </form>
                
                <div class="text-center mt-3">
                    <p>لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a></p>
                    <p><a href="/">العودة للصفحة الرئيسية</a></p>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''',
    
    'chat.html': '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>المحادثة - OTH AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; }
        .chat-container { max-width: 800px; margin: 0 auto; border-radius: 10px; }
        .chat-messages { height: 500px; overflow-y: auto; }
        .message { max-width: 80%; margin-bottom: 10px; }
        .user-message { margin-left: auto; background-color: #e3f2fd; }
        .bot-message { margin-right: auto; background-color: #f1f1f1; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
            <div class="d-flex">
                <a href="/logout" class="btn btn-outline-light">تسجيل الخروج</a>
            </div>
        </div>
    </nav>

    <div class="container py-4">
        <div class="chat-container card shadow">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">محادثة مع OTH AI</h5>
            </div>
            
            <div class="card-body">
                <div id="chat-messages" class="chat-messages mb-3 p-3">
                    <!-- سيتم ملء الرسائل هنا عبر JavaScript -->
                </div>
                
                <form id="chat-form" class="d-flex">
                    <input type="text" id="user-input" class="form-control me-2" placeholder="اكتب رسالتك هنا..." required>
                    <button type="submit" class="btn btn-primary">إرسال</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const chatForm = document.getElementById('chat-form');
            const userInput = document.getElementById('user-input');
            const chatMessages = document.getElementById('chat-messages');
            
            function addMessage(sender, message) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message p-3 rounded ${sender === 'user' ? 'user-message' : 'bot-message'}`;
                messageDiv.textContent = message;
                chatMessages.appendChild(messageDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
            chatForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const message = userInput.value.trim();
                if (message) {
                    addMessage('user', message);
                    userInput.value = '';
                    
                    fetch('/api/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ message: message })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.reply) {
                            addMessage('bot', data.reply);
                        } else if (data.error) {
                            addMessage('bot', 'حدث خطأ: ' + data.error);
                        }
                    })
                    .catch(error => {
                        addMessage('bot', 'حدث خطأ في الاتصال بالخادم');
                        console.error('Error:', error);
                    });
                }
            });
        });
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''',
    
    '404.html': '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الصفحة غير موجودة - OTH AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="/">OTH AI</a>
        </div>
    </nav>

    <div class="container py-5 text-center">
        <h1 class="display-1 text-danger">404</h1>
        <h2 class="mb-4">الصفحة غير موجودة</h2>
        <p class="lead">عذراً، الصفحة التي تبحث عنها غير موجودة.</p>
        <a href="/" class="btn btn-primary">العودة للصفحة الرئيسية</a>
    </div>
</body>
</html>
    '''
}

# وظائف إدارة البيانات
def load_users():
    global users
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                users = json.load(f)
        else:
            users = {}
    except Exception as e:
        logger.error(f"Error loading users: {str(e)}")
        users = {}

def save_users():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving users: {str(e)}")

# تحميل المستخدمين عند البدء
load_users()

# ديكورات المسارات
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# وظائف مساعدة
def get_user_id(sender_id):
    return hashlib.md5(sender_id.encode()).hexdigest()

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v22.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "web_url",
                        "title": "🌐 الانتقال للويب",
                        "url": "https://your-app.vercel.app/chat",
                        "webview_height_ratio": "full",
                        "messenger_extensions": True
                    },
                    {
                        "type": "postback",
                        "title": "🆘 المساعدة",
                        "payload": "HELP_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://your-app.vercel.app"],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت OTH IA! 💎"
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد الواجهة: {str(e)}")

def download_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            return tmp_file.name
    except Exception as e:
        logger.error(f"خطأ في تحميل الصورة: {str(e)}")
        return None

def analyze_image(image_path, context=None):
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً:"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    url = f"https://graph.facebook.com/v22.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text} if not buttons else {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": message_text,
                    "buttons": buttons
                }
            }
        },
        "messaging_type": "RESPONSE"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def cleanup_old_conversations():
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations.keys()):
            if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations[user_id]
                logger.info(f"تم حذف محادثة المستخدم {user_id} لانتهاء المهلة")

# تعديل دالة render_template لاستخدام القوالب المضمنة
def render_template(template_name, **context):
    if template_name in TEMPLATES:
        return render_template_string(TEMPLATES[template_name], **context)
    raise Exception(f"Template {template_name} not found")

# مسارات الويب
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with data_lock:
            user = users.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                session['session_id'] = str(uuid.uuid4())
                session.permanent = True
                
                # إنشاء محادثة جديدة للمستخدم إذا لم تكن موجودة
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('chat'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if len(username) < 4 or len(password) < 6:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل وكلمة المرور 6 أحرف', 'danger')
            return redirect(url_for('register'))
        
        with data_lock:
            if username in users:
                flash('اسم المستخدم موجود بالفعل', 'danger')
            else:
                user_id = str(uuid.uuid4())
                users[username] = {
                    'id': user_id,
                    'username': username,
                    'password': generate_password_hash(password),
                    'created_at': datetime.now().isoformat()
                }
                save_users()
                
                # إنشاء محادثة جديدة للمستخدم
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": time.time()
                }
                
                flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
                return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    user_id = session.get('user_id')
    with data_lock:
        if user_id in conversations:
            del conversations[user_id]
    
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح به"}), 401
    
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({"reply": "الرجاء إدخال رسالة صالحة"}), 400
        
        user_id = session['user_id']
        
        with data_lock:
            if user_id not in conversations:
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": time.time()
                }
            
            # تحديث وقت النشاط
            conversations[user_id]["last_active"] = time.time()
            
            # إضافة رسالة المستخدم
            conversations[user_id]["history"].append(f"المستخدم: {user_message}")
            
            # الحصول على سياق المحادثة
            context = "\n".join(conversations[user_id]["history"][-5:])
            
            # توليد الرد
            prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
            response = model.generate_content(prompt)
            reply = response.text
            
            # إضافة رد البوت
            conversations[user_id]["history"].append(f"البوت: {reply}")
            
            return jsonify({"reply": reply}), 200
            
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        return jsonify({"reply": "حدث خطأ أثناء معالجة طلبك"}), 500

# مسارات البوت (ابقاء جزء فيسبوك كما هو)
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                user_id = get_user_id(sender_id)
                current_time = time.time()
                
                # تنظيف المحادثات القديمة
                cleanup_old_conversations()
                
                # معالجة Postback (أزرار القائمة)
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    with data_lock:
                        if user_id not in conversations:
                            conversations[user_id] = {
                                "history": ["بدأ المستخدم محادثة جديدة"],
                                "last_active": current_time
                            }
                            send_message(sender_id, "مرحباً بك في بوت OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")
                        
                        # تحديث وقت النشاط
                        conversations[user_id]["last_active"] = current_time
                        
                        # معالجة الصور
                        if 'attachments' in message:
                            for attachment in message['attachments']:
                                if attachment['type'] == 'image':
                                    send_message(sender_id, "⏳ جاري تحليل الصورة...")
                                    image_url = attachment['payload']['url']
                                    image_path = download_image(image_url)
                                    
                                    if image_path:
                                        context = "\n".join(conversations[user_id]["history"][-5:])
                                        analysis = analyze_image(image_path, context)
                                        
                                        if analysis:
                                            conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                                            send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                        else:
                                            send_message(sender_id, "⚠️ تعذر تحليل الصورة")
                            continue
                        
                        # معالجة النصوص
                        if 'text' in message:
                            user_message = message['text'].strip()
                            
                            if user_message.lower() in ['مساعدة', 'help']:
                                send_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")
                            else:
                                try:
                                    context = "\n".join(conversations[user_id]["history"][-5:])
                                    prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
                                    
                                    response = model.generate_content(prompt)
                                    reply = response.text
                                    
                                    conversations[user_id]["history"].append(f"المستخدم: {user_message}")
                                    conversations[user_id]["history"].append(f"البوت: {reply}")
                                    
                                    send_message(sender_id, reply)
                                except Exception as e:
                                    logger.error(f"AI Error: {str(e)}")
                                    send_message(sender_id, "⚠️ حدث خطأ أثناء المعالجة، يرجى المحاولة لاحقاً")
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

def handle_command(sender_id, user_id, command):
    if command == "GET_STARTED":
        send_message(sender_id, "مرحباً بك في OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")
    elif command == "HELP_CMD":
        send_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# تشغيل التنظيف الدوري كل ساعة
def periodic_cleanup():
    while True:
        time.sleep(3600)  # كل ساعة
        cleanup_old_conversations()
        save_users()  # حفظ بيانات المستخدمين بانتظام

# بدء التنظيف الدوري في خيط منفصل
cleanup_thread = Thread(target=periodic_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    setup_messenger_profile()
    app.run(debug=True)
