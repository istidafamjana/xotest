import os
import time
import uuid
import hashlib
import logging
import tempfile
import urllib.request
from datetime import timedelta
from threading import Lock
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import google.generativeai as genai

# تهيئة التطبيق
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-oth-ia-advanced')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_IA')

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات والمستخدمين
conversations = {}
users = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
data_lock = Lock()

# ==============================================
# ديكورات المسارات ووظائف المساعدة
# ==============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_user_id(sender_id):
    return hashlib.sha256(sender_id.encode()).hexdigest()

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
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
                    },
                    {
                        "type": "postback",
                        "title": "🚪 تسجيل الخروج",
                        "payload": "LOGOUT_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://your-app.vercel.app"],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك."
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد واجهة الماسنجر: {str(e)}")

def download_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (OTH IA Image Downloader)'}
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
        prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً مع تمييز الأجزاء المهمة:"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return format_response(response.text)
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
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

def format_response(text):
    if "```" in text:
        parts = text.split("```")
        formatted = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                formatted.append(f'<div class="code-block"><pre><code>{part}</code></pre><button class="copy-btn" onclick="copyCode(this)">نسخ الكود</button></div>')
            else:
                formatted.append(part.replace("\n", "<br>"))
        return "".join(formatted)
    return text.replace("\n", "<br>")

def cleanup_old_conversations():
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations.keys()):
            if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations[user_id]
                logger.info(f"تم حذف محادثة المستخدم {user_id} لانتهاء المهلة")

def handle_command(sender_id, user_id, command):
    if command == "GET_STARTED":
        send_message(sender_id, "مرحباً بك في OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")
    elif command == "HELP_CMD":
        send_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")
    elif command == "LOGOUT_CMD":
        with data_lock:
            if user_id in conversations:
                del conversations[user_id]
        send_message(sender_id, "تم تسجيل الخروج بنجاح. يمكنك العودة في أي وقت!")

# ==============================================
# مسارات الويب
# ==============================================

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OTH IA - الذكاء الاصطناعي المتقدم</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary-color: #6C63FF;
                --secondary-color: #4D44DB;
                --accent-color: #FF6584;
                --dark-color: #2D3748;
                --light-color: #F7FAFC;
            }
            body {
                font-family: 'Tajawal', sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f7fa;
                color: var(--dark-color);
                direction: rtl;
            }
            .navbar {
                background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
                color: white;
                padding: 1rem 2rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .btn {
                padding: 0.75rem 1.5rem;
                background-color: var(--primary-color);
                color: white;
                border: none;
                border-radius: 8px;
                text-decoration: none;
                transition: all 0.3s ease;
            }
            .btn:hover {
                background-color: var(--secondary-color);
            }
        </style>
    </head>
    <body>
        <nav class="navbar">
            <a href="/" style="color: white; text-decoration: none; font-size: 1.5rem; font-weight: 700;">OTH IA</a>
            <div>
                <a href="/login" class="btn">تسجيل الدخول</a>
                <a href="/register" class="btn" style="margin-right: 1rem;">إنشاء حساب</a>
            </div>
        </nav>
        <div style="padding: 2rem; text-align: center;">
            <h1>مرحباً بك في OTH IA</h1>
            <p>منصة الذكاء الاصطناعي المتقدم للدردشة وتحليل الصور</p>
        </div>
    </body>
    </html>
    """

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with data_lock:
            user = users.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                session['session_id'] = str(uuid.uuid4())
                session.permanent = True
                
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                else:
                    conversations[user['id']]["last_active"] = time.time()
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('chat'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>تسجيل الدخول - OTH IA</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Tajawal', sans-serif;
                background-color: #f5f7fa;
                direction: rtl;
                padding: 2rem;
            }
            .auth-container {
                max-width: 400px;
                margin: 2rem auto;
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            }
            .form-group {
                margin-bottom: 1.5rem;
            }
            input {
                width: 100%;
                padding: 0.75rem;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            button {
                width: 100%;
                padding: 0.75rem;
                background-color: #6C63FF;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="auth-container">
            <h2 style="text-align: center; margin-bottom: 1.5rem;">تسجيل الدخول</h2>
            <form action="/login" method="POST">
                <div class="form-group">
                    <label>اسم المستخدم</label>
                    <input type="text" name="username" required>
                </div>
                <div class="form-group">
                    <label>كلمة المرور</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit">تسجيل الدخول</button>
            </form>
            <div style="text-align: center; margin-top: 1.5rem;">
                ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if len(username) < 4:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل', 'danger')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        elif password != confirm_password:
            flash('كلمتا المرور غير متطابقتين', 'danger')
        else:
            with data_lock:
                if username in users:
                    flash('اسم المستخدم موجود بالفعل', 'danger')
                else:
                    user_id = str(uuid.uuid4())
                    users[username] = {
                        'id': user_id,
                        'username': username,
                        'password': generate_password_hash(password),
                        'created_at': time.time()
                    }
                    
                    conversations[user_id] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                    
                    flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
                    return redirect(url_for('login'))
    
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>إنشاء حساب - OTH IA</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Tajawal', sans-serif;
                background-color: #f5f7fa;
                direction: rtl;
                padding: 2rem;
            }
            .auth-container {
                max-width: 400px;
                margin: 2rem auto;
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
            }
            .form-group {
                margin-bottom: 1.5rem;
            }
            input {
                width: 100%;
                padding: 0.75rem;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            button {
                width: 100%;
                padding: 0.75rem;
                background-color: #6C63FF;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="auth-container">
            <h2 style="text-align: center; margin-bottom: 1.5rem;">إنشاء حساب جديد</h2>
            <form action="/register" method="POST">
                <div class="form-group">
                    <label>اسم المستخدم</label>
                    <input type="text" name="username" required minlength="4">
                    <small style="color: #666;">يجب أن يكون 4 أحرف على الأقل</small>
                </div>
                <div class="form-group">
                    <label>كلمة المرور</label>
                    <input type="password" name="password" required minlength="6">
                    <small style="color: #666;">يجب أن تكون 6 أحرف على الأقل</small>
                </div>
                <div class="form-group">
                    <label>تأكيد كلمة المرور</label>
                    <input type="password" name="confirm_password" required>
                </div>
                <button type="submit">إنشاء حساب</button>
            </form>
            <div style="text-align: center; margin-top: 1.5rem;">
                لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
            </div>
        </div>
    </body>
    </html>
    """

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
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>الدردشة - OTH IA</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Tajawal', sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f5f7fa;
            }
            .chat-container {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }
            .chat-header {
                background: linear-gradient(135deg, #6C63FF, #4D44DB);
                color: white;
                padding: 1rem;
                text-align: center;
            }
            .chat-messages {
                flex: 1;
                padding: 1rem;
                overflow-y: auto;
                background-color: #f9f9f9;
            }
            .message {
                margin-bottom: 1rem;
                padding: 0.75rem 1rem;
                border-radius: 12px;
                max-width: 80%;
            }
            .user-message {
                background-color: #e3f2fd;
                margin-left: auto;
            }
            .bot-message {
                background-color: #f1f1f1;
                margin-right: auto;
            }
            .chat-input {
                display: flex;
                padding: 1rem;
                background-color: white;
                border-top: 1px solid #eee;
            }
            .chat-input input {
                flex: 1;
                padding: 0.75rem;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            .chat-input button {
                margin-right: 0.5rem;
                padding: 0.75rem 1.5rem;
                background-color: #6C63FF;
                color: white;
                border: none;
                border-radius: 8px;
                cursor: pointer;
            }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header">
                <h3>OTH IA - الدردشة</h3>
            </div>
            <div class="chat-messages" id="chat-messages">
                <!-- سيتم ملء المحادثة بواسطة JavaScript -->
            </div>
            <div class="chat-input">
                <input type="text" id="user-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
                <button id="send-btn">إرسال</button>
            </div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                const chatMessages = document.getElementById('chat-messages');
                const userInput = document.getElementById('user-input');
                const sendBtn = document.getElementById('send-btn');
                
                function sendMessage() {
                    const message = userInput.value.trim();
                    if (!message) return;
                    
                    addMessage(message, 'user');
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
                        if (data.error) {
                            addMessage('حدث خطأ: ' + data.error, 'bot');
                        } else {
                            addMessage(data.reply, 'bot');
                        }
                    })
                    .catch(error => {
                        addMessage('حدث خطأ في الاتصال بالخادم', 'bot');
                    });
                }
                
                function addMessage(text, sender) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `message ${sender}-message`;
                    messageDiv.textContent = text;
                    chatMessages.appendChild(messageDiv);
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }
                
                userInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        sendMessage();
                    }
                });
                
                sendBtn.addEventListener('click', sendMessage);
                
                // تحميل المحادثة السابقة
                fetch('/api/conversation')
                    .then(response => response.json())
                    .then(data => {
                        if (data.history && data.history.length > 0) {
                            data.history.forEach(item => {
                                if (item.startsWith('المستخدم:')) {
                                    addMessage(item.replace('المستخدم:', '').trim(), 'user');
                                } else if (item.startsWith('البوت:')) {
                                    addMessage(item.replace('البوت:', '').trim(), 'bot');
                                }
                            });
                        } else {
                            addMessage('مرحباً بك في OTH IA! كيف يمكنني مساعدتك اليوم؟', 'bot');
                        }
                    });
            });
        </script>
    </body>
    </html>
    """

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    if 'user_id' not in session:
        return jsonify({"error": "غير مصرح به"}), 401
    
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({"error": "الرجاء إدخال رسالة صالحة"}), 400
        
        user_id = session['user_id']
        
        with data_lock:
            if user_id not in conversations:
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": time.time()
                }
            
            conversations[user_id]["last_active"] = time.time()
            conversations[user_id]["history"].append(f"المستخدم: {user_message}")
            
            context = "\n".join(conversations[user_id]["history"][-5:])
            prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
            response = model.generate_content(prompt)
            reply = format_response(response.text)
            
            conversations[user_id]["history"].append(f"البوت: {reply}")
            
            return jsonify({
                "reply": reply,
                "conversation_id": user_id,
                "timestamp": int(time.time())
            }), 200
            
    except Exception as e:
        logger.error(f"خطأ في واجهة الدردشة: {str(e)}")
        return jsonify({"error": "حدث خطأ أثناء معالجة طلبك"}), 500

@app.route('/api/conversation', methods=['GET'])
@login_required
def get_conversation():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "غير مصرح به"}), 401
    
    with data_lock:
        if user_id in conversations:
            return jsonify({
                "history": conversations[user_id]["history"],
                "last_active": conversations[user_id]["last_active"]
            }), 200
        return jsonify({"history": []}), 200

# ==============================================
# مسارات بوت الماسنجر
# ==============================================

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "فشل التحقق", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                user_id = get_user_id(sender_id)
                current_time = time.time()
                
                cleanup_old_conversations()
                
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                if 'message' in event:
                    message = event['message']
                    
                    with data_lock:
                        if user_id not in conversations:
                            conversations[user_id] = {
                                "history": ["بدأ المستخدم محادثة جديدة"],
                                "last_active": current_time
                            }
                            send_message(sender_id, "مرحباً بك في بوت OTH IA! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")
                        
                        conversations[user_id]["last_active"] = current_time
                        
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
                        
                        if 'text' in message:
                            user_message = message['text'].strip()
                            
                            if user_message.lower() in ['مساعدة', 'help']:
                                send_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")
                            elif user_message.lower() == '/new':
                                conversations[user_id] = {
                                    "history": ["بدأ المستخدم محادثة جديدة"],
                                    "last_active": current_time
                                }
                                send_message(sender_id, "تم بدء محادثة جديدة. كيف يمكنني مساعدتك؟")
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
                                    logger.error(f"خطأ في نموذج الذكاء الاصطناعي: {str(e)}")
                                    send_message(sender_id, "⚠️ حدث خطأ أثناء المعالجة، يرجى المحاولة لاحقاً")
    
    except Exception as e:
        logger.error(f"خطأ في webhook: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

@app.errorhandler(404)
def page_not_found(e):
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>الصفحة غير موجودة - OTH IA</title>
        <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Tajawal', sans-serif;
                background-color: #f5f7fa;
                direction: rtl;
                text-align: center;
                padding: 2rem;
            }
            .error-container {
                max-width: 600px;
                margin: 2rem auto;
            }
            .btn {
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background-color: #6C63FF;
                color: white;
                text-decoration: none;
                border-radius: 8px;
            }
        </style>
    </head>
    <body>
        <div class="error-container">
            <h1>404</h1>
            <p>الصفحة التي تبحث عنها غير موجودة.</p>
            <a href="/" class="btn">العودة إلى الصفحة الرئيسية</a>
        </div>
    </body>
    </html>
    """, 404

# ==============================================
# التشغيل والصيانة
# ==============================================

def periodic_cleanup():
    while True:
        time.sleep(3600)
        cleanup_old_conversations()

if __name__ == '__main__':
    import threading
    cleanup_thread = threading.Thread(target=periodic_cleanup)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    setup_messenger_profile()
    app.run(threaded=True)
