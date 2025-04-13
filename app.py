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
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey123!')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)

# ======== إعدادات السجل ========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======== مفاتيح API ========
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

# ======== قوالب HTML في الملف ========
BASE_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body { font-family: 'Tahoma', Arial, sans-serif; line-height: 1.6; margin: 0; padding: 0; background: #f9f9f9; }
        .container { max-width: 1000px; margin: 0 auto; padding: 20px; }
        header { background: #4285f4; color: white; padding: 15px 0; text-align: center; }
        nav { background: #2c3e50; overflow: hidden; }
        nav a { float: right; color: white; text-align: center; padding: 14px 16px; text-decoration: none; font-size: 16px; }
        nav a:hover { background: #34495e; }
        .flash { padding: 12px; margin: 15px 0; border-radius: 4px; font-size: 15px; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        form { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin: 20px 0; }
        input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }
        button { background: #4285f4; color: white; border: none; padding: 12px 25px; cursor: pointer; border-radius: 4px; font-size: 16px; width: 100%; }
        button:hover { background: #3367d6; }
        .chat-container { background: white; height: 500px; overflow-y: auto; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .message { margin: 12px 0; padding: 12px; border-radius: 8px; font-size: 15px; max-width: 80%; }
        .user-message { background: #e3f2fd; margin-left: auto; text-align: left; }
        .bot-message { background: #f1f1f1; margin-right: auto; text-align: right; }
        .dashboard-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin: 15px 0; }
        @media (max-width: 768px) {
            nav a { float: none; display: block; text-align: center; }
            .message { max-width: 90%; }
        }
    </style>
</head>
<body>
    <header>
        <h1>نظام OTH AI الذكاء الاصطناعي</h1>
    </header>
    <nav>
        {% if 'user_id' in session %}
            <a href="{{ url_for('logout') }}">تسجيل الخروج</a>
            <a href="{{ url_for('chat') }}">الدردشة الذكية</a>
            <a href="{{ url_for('dashboard') }}">لوحة التحكم</a>
        {% else %}
            <a href="{{ url_for('login') }}">تسجيل الدخول</a>
            <a href="{{ url_for('register') }}">إنشاء حساب</a>
        {% endif %}
        <a href="{{ url_for('home') }}">الرئيسية</a>
    </nav>
    <div class="container">
        {% for category, message in get_flashed_messages(with_categories=true) %}
            <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
        
        {% block content %}{% endblock %}
    </div>
</body>
</html>
'''

HOME_PAGE = '''
{% extends "base" %}
{% block content %}
    <h2 style="color: #2c3e50;">مرحبًا بك في نظام الذكاء الاصطناعي المتقدم</h2>
    <div class="dashboard-card">
        <h3>مميزات النظام:</h3>
        <ul>
            <li>دردشة ذكية باستخدام Gemini AI</li>
            <li>تحليل الصور والملفات</li>
            <li>ذاكرة محادثة خلال الجلسة</li>
            <li>واجهة مستخدم متكاملة</li>
        </ul>
    </div>
    {% if 'user_id' not in session %}
        <p style="text-align: center; margin-top: 30px;">
            <a href="{{ url_for('login') }}" style="background: #34a853; padding: 10px 20px; color: white; text-decoration: none; border-radius: 4px;">سجل الدخول للبدء</a>
        </p>
    {% endif %}
{% endblock %}
'''

LOGIN_PAGE = '''
{% extends "base" %}
{% block content %}
    <h2 style="text-align: center; color: #2c3e50;">تسجيل الدخول إلى حسابك</h2>
    <form method="POST" action="{{ url_for('login') }}">
        <input type="text" name="username" placeholder="اسم المستخدم" required>
        <input type="password" name="password" placeholder="كلمة المرور" required>
        <button type="submit">تسجيل الدخول</button>
    </form>
    <p style="text-align: center;">ليس لديك حساب؟ <a href="{{ url_for('register') }}">أنشئ حساب جديد</a></p>
{% endblock %}
'''

REGISTER_PAGE = '''
{% extends "base" %}
{% block content %}
    <h2 style="text-align: center; color: #2c3e50;">إنشاء حساب جديد</h2>
    <form method="POST" action="{{ url_for('register') }}">
        <input type="text" name="username" placeholder="اسم المستخدم (4 أحرف على الأقل)" required>
        <input type="password" name="password" placeholder="كلمة المرور (6 أحرف على الأقل)" required>
        <input type="password" name="confirm_password" placeholder="تأكيد كلمة المرور" required>
        <button type="submit">إنشاء حساب</button>
    </form>
    <p style="text-align: center;">لديك حساب بالفعل؟ <a href="{{ url_for('login') }}">سجل الدخول هنا</a></p>
{% endblock %}
'''

DASHBOARD_PAGE = '''
{% extends "base" %}
{% block content %}
    <h2 style="color: #2c3e50;">لوحة التحكم - مرحبًا {{ username }}!</h2>
    
    <div class="dashboard-card">
        <h3>معلومات الحساب:</h3>
        <p><strong>اسم المستخدم:</strong> {{ username }}</p>
        <p><strong>تاريخ التسجيل:</strong> {{ join_date }}</p>
    </div>
    
    <div class="dashboard-card">
        <h3>إحصائيات:</h3>
        <p><strong>عدد المحادثات النشطة:</strong> {{ active_chats }}</p>
    </div>
    
    <div style="text-align: center; margin-top: 30px;">
        <a href="{{ url_for('chat') }}" style="background: #4285f4; padding: 12px 25px; color: white; text-decoration: none; border-radius: 4px; display: inline-block;">الذهاب إلى الدردشة</a>
    </div>
{% endblock %}
'''

CHAT_PAGE = '''
{% extends "base" %}
{% block content %}
    <h2 style="color: #2c3e50;">الدردشة مع الذكاء الاصطناعي</h2>
    
    <div class="chat-container" id="chat-box">
        {% for msg in conversation %}
            <div class="message {% if 'المستخدم:' in msg %}user-message{% else %}bot-message{% endif %}">
                {{ msg.replace('المستخدم:', '').replace('البوت:', '') }}
            </div>
        {% endfor %}
    </div>
    
    <form id="chat-form" onsubmit="sendMessage(); return false;">
        <input type="text" id="user-message" placeholder="اكتب رسالتك هنا..." autocomplete="off" required>
        <button type="submit">إرسال الرسالة</button>
    </form>
    
    <script>
        function scrollToBottom() {
            const chatBox = document.getElementById('chat-box');
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
        function sendMessage() {
            const messageInput = document.getElementById('user-message');
            const message = messageInput.value.trim();
            
            if (!message) return;
            
            // إضافة الرسالة فورًا لواجهة المستخدم
            const chatBox = document.getElementById('chat-box');
            chatBox.innerHTML += `<div class="message user-message">${message}</div>`;
            messageInput.value = '';
            scrollToBottom();
            
            // إرسال إلى الخادم
            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                chatBox.innerHTML += `<div class="message bot-message">${data.reply}</div>`;
                scrollToBottom();
            })
            .catch(error => {
                chatBox.innerHTML += `<div class="message bot-message" style="color:red;">حدث خطأ في الاتصال بالخادم</div>`;
                scrollToBottom();
            });
        }
        
        // التمرير للأسفل عند التحميل
        window.onload = scrollToBottom;
        
        // إرسال بالضغط على Enter
        document.getElementById('user-message').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
{% endblock %}
'''

# ======== وظائف مساعدة ========
def setup_messenger_profile():
    """إعداد صفحة الماسنجر"""
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
                        "url": "https://yourdomain.com/chat",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "postback",
                        "title": "🆘 المساعدة",
                        "payload": "HELP"
                    }
                ]
            }
        ],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت OTH AI! كيف يمكنني مساعدتك اليوم؟"
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد صفحة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد صفحة الماسنجر: {str(e)}")

def handle_facebook_message(sender_id, message):
    """معالجة رسائل فيسبوك"""
    with data_lock:
        if sender_id not in conversations:
            conversations[sender_id] = {
                "history": ["بدأ المحادثة مع بوت فيسبوك"],
                "last_active": time.time()
            }
        
        conversations[sender_id]["history"].append(f"المستخدم: {message}")
        conversations[sender_id]["last_active"] = time.time()
        
        try:
            context = "\n".join(conversations[sender_id]["history"][-5:])
            response = model.generate_content(f"{context}\n\nالرسالة الجديدة: {message}")
            reply = response.text
            
            conversations[sender_id]["history"].append(f"البوت: {reply}")
            send_facebook_message(sender_id, reply)
        except Exception as e:
            logger.error(f"خطأ في معالجة رسالة فيسبوك: {str(e)}")
            send_facebook_message(sender_id, "عذرًا، حدث خطأ أثناء معالجة رسالتك.")

def send_facebook_message(recipient_id, text):
    """إرسال رسالة إلى مستخدم فيسبوك"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"خطأ في إرسال رسالة فيسبوك: {str(e)}")

# ======== مسارات الويب ========
@app.route('/')
def home():
    return render_template_string(BASE_TEMPLATE.replace('{% extends "base" %}', '').replace('{% block content %}', HOME_PAGE), 
                                title="الرئيسية - OTH AI")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = users_db.get(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template_string(BASE_TEMPLATE.replace('{% extends "base" %}', '').replace('{% block content %}', LOGIN_PAGE), 
                                title="تسجيل الدخول")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if len(username) < 4:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل', 'error')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'error')
        elif password != confirm_password:
            flash('كلمات المرور غير متطابقة', 'error')
        elif username in users_db:
            flash('اسم المستخدم موجود بالفعل', 'error')
        else:
            user_id = str(uuid.uuid4())
            users_db[username] = {
                'id': user_id,
                'username': username,
                'password': generate_password_hash(password),
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            flash('تم إنشاء الحساب بنجاح. يمكنك تسجيل الدخول الآن.', 'success')
            return redirect(url_for('login'))
    
    return render_template_string(BASE_TEMPLATE.replace('{% extends "base" %}', '').replace('{% block content %}', REGISTER_PAGE), 
                                title="إنشاء حساب")

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = next((u for u in users_db.values() if u['id'] == user_id), None)
    
    if not user:
        session.clear()
        return redirect(url_for('login'))
    
    active_chats = len([c for c in conversations.values() if time.time() - c['last_active'] < CONVERSATION_TIMEOUT])
    
    return render_template_string(BASE_TEMPLATE.replace('{% extends "base" %}', '').replace('{% block content %}', DASHBOARD_PAGE), 
                                title="لوحة التحكم",
                                username=user['username'],
                                join_date=user['created_at'],
                                active_chats=active_chats)

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    if user_id not in conversations:
        conversations[user_id] = {
            "history": ["بدأت محادثة جديدة"],
            "last_active": time.time()
        }
    
    return render_template_string(BASE_TEMPLATE.replace('{% extends "base" %}', '').replace('{% block content %}', CHAT_PAGE), 
                                title="الدردشة",
                                conversation=conversations[user_id]['history'])

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return jsonify({"error": "غير مسموح"}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({"error": "الرسالة فارغة"}), 400
    
    with data_lock:
        if user_id not in conversations:
            conversations[user_id] = {
                "history": ["بدأت محادثة جديدة"],
                "last_active": time.time()
            }
        
        conversations[user_id]['history'].append(f"المستخدم: {message}")
        conversations[user_id]['last_active'] = time.time()
        
        try:
            context = "\n".join(conversations[user_id]['history'][-5:])
            response = model.generate_content(f"{context}\n\nالرسالة الجديدة: {message}")
            reply = response.text
            
            conversations[user_id]['history'].append(f"البوت: {reply}")
            return jsonify({"reply": reply})
        except Exception as e:
            logger.error(f"خطأ في معالجة الرسالة: {str(e)}")
            return jsonify({"error": "حدث خطأ أثناء معالجة رسالتك"}), 500

# ======== مسار ويب هوك فيسبوك ========
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # التحقق من التوكن
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "توكن التحقق غير صحيح", 403
    
    # معالجة رسائل فيسبوك
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for messaging_event in entry.get('messaging', []):
                sender_id = messaging_event['sender']['id']
                
                if messaging_event.get('message'):
                    message_text = messaging_event['message'].get('text', '')
                    if message_text:
                        handle_facebook_message(sender_id, message_text)
                
                elif messaging_event.get('postback'):
                    payload = messaging_event['postback']['payload']
                    if payload == 'GET_STARTED':
                        send_facebook_message(sender_id, "مرحبًا بك في بوت OTH AI! اكتب رسالتك وسأساعدك.")
                    elif payload == 'HELP':
                        send_facebook_message(sender_id, "مركز المساعدة:\n\n- اكتب سؤالك مباشرة\n- أرسل 'مساعدة' للحصول على خيارات إضافية")
    except Exception as e:
        logger.error(f"خطأ في ويب هوك فيسبوك: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

# ======== تشغيل التطبيق ========
if __name__ == '__main__':
    # تنظيف المحادثات القديمة بانتظام
    def cleanup_old_conversations():
        while True:
            time.sleep(3600)  # كل ساعة
            current_time = time.time()
            with data_lock:
                for user_id in list(conversations.keys()):
                    if current_time - conversations[user_id]['last_active'] > CONVERSATION_TIMEOUT:
                        del conversations[user_id]
                        logger.info(f"تم تنظيف محادثة المستخدم {user_id} لانتهاء المهلة")
    
    import threading
    cleanup_thread = threading.Thread(target=cleanup_old_conversations)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    # تشغيل التطبيق
    app.run(threaded=True)
