from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash
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
from datetime import datetime
from threading import Lock
from functools import wraps

# ======== تهيئة التطبيق ========
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 5  # 5 ساعات

# ======== إعدادات السجل ========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======== مفاتيح وتهيئة API ========
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# ======== تهيئة نموذج Gemini ========
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# ======== تخزين البيانات ========
conversations = {}
users_db = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات
data_lock = Lock()

# ======== قوالب HTML ========
BASE_HTML = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        header { background: #4285f4; color: white; padding: 10px 0; text-align: center; }
        nav { background: #333; overflow: hidden; }
        nav a { float: right; color: white; text-align: center; padding: 14px 16px; text-decoration: none; }
        nav a:hover { background: #ddd; color: black; }
        .flash { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .success { background: #dff0d8; color: #3c763d; }
        .error { background: #f2dede; color: #a94442; }
        form { background: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #4285f4; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; }
        button:hover { background: #3367d6; }
        .chat-container { background: white; height: 500px; overflow-y: scroll; padding: 20px; border-radius: 5px; }
        .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
        .user-message { background: #e3f2fd; text-align: left; }
        .bot-message { background: #f1f1f1; text-align: right; }
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
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
'''

HOME_HTML = '''
{% extends "base.html" %}
{% block content %}
    <h2>مرحبًا بك في نظام الذكاء الاصطناعي OTH</h2>
    <p>نظام متقدم للدردشة والتحليل باستخدام Gemini AI</p>
    {% if 'user_id' not in session %}
        <p>سجل الدخول أو أنشئ حسابًا للبدء</p>
    {% endif %}
{% endblock %}
'''

LOGIN_HTML = '''
{% extends "base.html" %}
{% block content %}
    <h2>تسجيل الدخول</h2>
    <form method="POST" action="{{ url_for('login') }}">
        <input type="text" name="username" placeholder="اسم المستخدم" required>
        <input type="password" name="password" placeholder="كلمة المرور" required>
        <button type="submit">تسجيل الدخول</button>
    </form>
{% endblock %}
'''

REGISTER_HTML = '''
{% extends "base.html" %}
{% block content %}
    <h2>إنشاء حساب جديد</h2>
    <form method="POST" action="{{ url_for('register') }}">
        <input type="text" name="username" placeholder="اسم المستخدم (4 أحرف على الأقل)" required>
        <input type="password" name="password" placeholder="كلمة المرور (6 أحرف على الأقل)" required>
        <input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور" required>
        <button type="submit">إنشاء حساب</button>
    </form>
{% endblock %}
'''

DASHBOARD_HTML = '''
{% extends "base.html" %}
{% block content %}
    <h2>لوحة التحكم</h2>
    <p>مرحبًا بك {{ username }}!</p>
    <p>عدد المحادثات النشطة: {{ active_chats }}</p>
    <p>تاريخ التسجيل: {{ join_date }}</p>
    <a href="{{ url_for('chat') }}" class="button">الذهاب إلى الدردشة</a>
{% endblock %}
'''

CHAT_HTML = '''
{% extends "base.html" %}
{% block content %}
    <h2>دردشة OTH AI</h2>
    <div class="chat-container" id="chat-box">
        {% for msg in conversation %}
            <div class="message {% if 'المستخدم:' in msg %}user-message{% else %}bot-message{% endif %}">
                {{ msg }}
            </div>
        {% endfor %}
    </div>
    <form id="chat-form" onsubmit="sendMessage(); return false;">
        <input type="text" id="user-message" placeholder="اكتب رسالتك هنا..." required>
        <button type="submit">إرسال</button>
    </form>
    <script>
        function sendMessage() {
            const message = document.getElementById('user-message').value;
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                const chatBox = document.getElementById('chat-box');
                chatBox.innerHTML += `
                    <div class="message user-message">المستخدم: ${message}</div>
                    <div class="message bot-message">البوت: ${data.reply}</div>
                `;
                document.getElementById('user-message').value = '';
                chatBox.scrollTop = chatBox.scrollHeight;
            });
        }
    </script>
{% endblock %}
'''

# ======== وظائف مساعدة ========
def get_user_id(sender_id):
    return hashlib.md5(sender_id.encode()).hexdigest()

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

def cleanup_old_conversations():
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations.keys()):
            if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations[user_id]
                logger.info(f"تم حذف محادثة المستخدم {user_id} لانتهاء المهلة")

# ======== مسارات الويب ========
@app.route('/')
def home():
    return render_template_string(BASE_HTML + HOME_HTML, title="الرئيسية")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with data_lock:
            user = users_db.get(username)
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
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template_string(BASE_HTML + LOGIN_HTML, title="تسجيل الدخول")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if len(username) < 4 or len(password) < 6:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل وكلمة المرور 6 أحرف', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('كلمة المرور غير متطابقة', 'danger')
            return redirect(url_for('register'))
        
        with data_lock:
            if username in users_db:
                flash('اسم المستخدم موجود بالفعل', 'danger')
            else:
                user_id = str(uuid.uuid4())
                users_db[username] = {
                    'id': user_id,
                    'username': username,
                    'password': generate_password_hash(password),
                    'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": time.time()
                }
                
                flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
                return redirect(url_for('login'))
    
    return render_template_string(BASE_HTML + REGISTER_HTML, title="إنشاء حساب")

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    with data_lock:
        if user_id in conversations:
            del conversations[user_id]
    
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    with data_lock:
        active_chats = len(conversations)
        user_data = next((u for u in users_db.values() if u['id'] == session['user_id']), None)
    
    if not user_data:
        session.clear()
        return redirect(url_for('login'))
    
    return render_template_string(
        BASE_HTML + DASHBOARD_HTML,
        title="لوحة التحكم",
        username=user_data['username'],
        active_chats=active_chats,
        join_date=user_data.get('created_at', 'غير معروف')
    )

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    with data_lock:
        if user_id not in conversations:
            conversations[user_id] = {
                "history": ["بدأ المستخدم محادثة جديدة"],
                "last_active": time.time()
            }
        
        conversation = conversations[user_id]["history"]
    
    return render_template_string(
        BASE_HTML + CHAT_HTML,
        title="الدردشة",
        conversation=conversation
    )

@app.route('/api/chat', methods=['POST'])
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
            
            conversations[user_id]["last_active"] = time.time()
            conversations[user_id]["history"].append(f"المستخدم: {user_message}")
            
            context = "\n".join(conversations[user_id]["history"][-5:])
            prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
            response = model.generate_content(prompt)
            reply = response.text
            
            conversations[user_id]["history"].append(f"البوت: {reply}")
            
            return jsonify({"reply": reply}), 200
            
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        return jsonify({"reply": "حدث خطأ أثناء معالجة طلبك"}), 500

# ======== مسارات فيسبوك (بدون تعديل) ========
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
    return render_template_string(BASE_HTML + "<h2>الصفحة غير موجودة</h2>", title="404"), 404

# ======== التشغيل والصيانة ========
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
