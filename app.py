from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
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
from datetime import datetime, timedelta
from threading import Lock
from functools import wraps

# تكوين التطبيق الأساسي
app = Flask(__name__, template_folder='.', static_folder='static')
app.secret_key = 'oth-ia-secret-key-123456'  # تغيير هذا في الإنتاج
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# تهيئة نموذج Gemini
genai.configure(api_key="AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")
model = genai.GenerativeModel('gemini-1.5-flash')

# بيانات التطبيق
users_db = {}
conversations_db = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات
data_lock = Lock()

# ========== وظائف مساعدة ==========
def send_facebook_message(recipient_id, message_text):
    """إرسال رسالة عبر فيسبوك ماسنجر"""
    try:
        url = "https://graph.facebook.com/v17.0/me/messages"
        params = {
            'access_token': "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
        }
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text},
            "messaging_type": "RESPONSE"
        }
        response = requests.post(url, params=params, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def analyze_image(image_path, context=None):
    """تحليل الصورة باستخدام Gemini AI"""
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل هذه الصورة بدقة:"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {str(e)}")
        return None

def cleanup_old_conversations():
    """تنظيف المحادثات القديمة"""
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations_db.keys()):
            if current_time - conversations_db[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations_db[user_id]

# ========== ديكورات المسارات ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ========== مسارات الويب ==========
@app.route('/')
def home():
    return render_template_string("""
    {% extends 'base.html' %}
    {% block content %}
    <div class="hero">
        <h1>مرحباً بكم في OTH IA</h1>
        <p>منصة الذكاء الاصطناعي المتقدم للدردشة وتحليل الصور</p>
        <div class="hero-buttons">
            <a href="/login" class="btn btn-primary">تسجيل الدخول</a>
            <a href="/register" class="btn btn-outline">إنشاء حساب</a>
        </div>
    </div>
    {% endblock %}
    """)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with data_lock:
            user = users_db.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                session.permanent = True
                
                if user['id'] not in conversations_db:
                    conversations_db[user['id']] = {
                        "history": [],
                        "last_active": time.time()
                    }
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('chat'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template_string("""
    {% extends 'base.html' %}
    {% block content %}
    <div class="auth-container">
        <h2>تسجيل الدخول</h2>
        <form method="POST">
            <div class="form-group">
                <label for="username">اسم المستخدم</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">كلمة المرور</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">تسجيل الدخول</button>
        </form>
        <div class="auth-switch">
            <span>ليس لديك حساب؟</span>
            <a href="/register">إنشاء حساب</a>
        </div>
    </div>
    {% endblock %}
    """)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        with data_lock:
            if username in users_db:
                flash('اسم المستخدم موجود بالفعل', 'danger')
            elif len(username) < 4 or len(password) < 6:
                flash('يجب أن يكون اسم المستخدم 4 أحرف على الأقل وكلمة المرور 6 أحرف', 'danger')
            else:
                user_id = str(uuid.uuid4())
                users_db[username] = {
                    'id': user_id,
                    'username': username,
                    'password': generate_password_hash(password),
                    'created_at': time.time()
                }
                
                conversations_db[user_id] = {
                    "history": [],
                    "last_active": time.time()
                }
                
                flash('تم إنشاء الحساب بنجاح!', 'success')
                return redirect(url_for('login'))
    
    return render_template_string("""
    {% extends 'base.html' %}
    {% block content %}
    <div class="auth-container">
        <h2>إنشاء حساب جديد</h2>
        <form method="POST">
            <div class="form-group">
                <label for="username">اسم المستخدم</label>
                <input type="text" id="username" name="username" required>
                <small>يجب أن يكون 4 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label for="password">كلمة المرور</label>
                <input type="password" id="password" name="password" required>
                <small>يجب أن تكون 6 أحرف على الأقل</small>
            </div>
            <button type="submit" class="btn btn-primary">إنشاء حساب</button>
        </form>
        <div class="auth-switch">
            <span>لديك حساب بالفعل؟</span>
            <a href="/login">تسجيل الدخول</a>
        </div>
    </div>
    {% endblock %}
    """)

@app.route('/chat')
@login_required
def chat():
    return render_template_string("""
    {% extends 'base.html' %}
    {% block content %}
    <div class="chat-container">
        <div class="chat-header">
            <h2>محادثة OTH IA</h2>
        </div>
        <div class="chat-messages" id="chat-messages">
            {% for msg in conversations_db[session['user_id']]['history'] %}
            <div class="message {% if msg.sender == 'user' %}user-message{% else %}bot-message{% endif %}">
                <p>{{ msg.content }}</p>
                <span class="timestamp">{{ msg.timestamp|datetime }}</span>
            </div>
            {% endfor %}
        </div>
        <div class="chat-input">
            <input type="text" id="message-input" placeholder="اكتب رسالتك هنا...">
            <button id="send-btn">إرسال</button>
        </div>
    </div>
    <div class="text-center">
        <a href="/logout" class="btn btn-outline">تسجيل الخروج</a>
    </div>
    {% endblock %}
    """)

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

# ========== واجهة فيسبوك ماسنجر ==========
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == "d51ee4e3183dbbd9a27b7d2c1af8c655":
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                user_id = hashlib.md5(sender_id.encode()).hexdigest()
                
                cleanup_old_conversations()
                
                if 'postback' in event:
                    handle_facebook_command(sender_id, event['postback']['payload'])
                    continue
                    
                if 'message' in event:
                    handle_facebook_message(sender_id, user_id, event['message'])
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

def handle_facebook_command(sender_id, command):
    if command == "GET_STARTED":
        send_facebook_message(sender_id, "مرحباً بك في OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")
    elif command == "HELP_CMD":
        send_facebook_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")

def handle_facebook_message(sender_id, user_id, message):
    with data_lock:
        if user_id not in conversations_db:
            conversations_db[user_id] = {
                "history": [],
                "last_active": time.time()
            }
            send_facebook_message(sender_id, "مرحباً بك في بوت OTH IA! 💎")
        
        conversations_db[user_id]["last_active"] = time.time()
        
        if 'attachments' in message:
            for attachment in message['attachments']:
                if attachment['type'] == 'image':
                    send_facebook_message(sender_id, "⏳ جاري تحليل الصورة...")
                    image_url = attachment['payload']['url']
                    
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                            with urllib.request.urlopen(image_url) as response:
                                tmp_file.write(response.read())
                            tmp_path = tmp_file.name
                        
                        context = "\n".join([msg['content'] for msg in conversations_db[user_id]["history"][-5:]])
                        analysis = analyze_image(tmp_path, context)
                        
                        if analysis:
                            conversations_db[user_id]["history"].append({
                                'type': 'text',
                                'content': f"📸 صورة: {analysis[:200]}...",
                                'sender': 'user',
                                'timestamp': time.time()
                            })
                            
                            bot_response = f"📸 تحليل الصورة:\n\n{analysis[:1000]}"
                            send_facebook_message(sender_id, bot_response)
                            
                            conversations_db[user_id]["history"].append({
                                'type': 'text',
                                'content': bot_response,
                                'sender': 'bot',
                                'timestamp': time.time()
                            })
                        else:
                            send_facebook_message(sender_id, "⚠️ تعذر تحليل الصورة")
                    except Exception as e:
                        logger.error(f"خطأ في معالجة صورة الفيسبوك: {str(e)}")
                        send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة الصورة")
            return
        
        if 'text' in message:
            user_message = message['text'].strip()
            
            if user_message.lower() in ['مساعدة', 'help']:
                send_facebook_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")
            else:
                try:
                    context = "\n".join([msg['content'] for msg in conversations_db[user_id]["history"][-5:]])
                    prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
                    response = model.generate_content(prompt)
                    
                    conversations_db[user_id]["history"].append({
                        'type': 'text',
                        'content': user_message,
                        'sender': 'user',
                        'timestamp': time.time()
                    })
                    
                    conversations_db[user_id]["history"].append({
                        'type': 'text',
                        'content': response.text,
                        'sender': 'bot',
                        'timestamp': time.time()
                    })
                    
                    send_facebook_message(sender_id, response.text)
                except Exception as e:
                    logger.error(f"خطأ في معالجة رسالة الفيسبوك: {str(e)}")
                    send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة رسالتك")

# ========== تشغيل التطبيق ==========
if __name__ == '__main__':
    app.run(threaded=True)
