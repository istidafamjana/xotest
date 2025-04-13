import os
import time
import uuid
import hashlib
import logging
import tempfile
import urllib.request
from datetime import datetime, timedelta
from threading import Lock, Thread
from functools import wraps
import mimetypes
import json

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
import google.generativeai as genai
from PIL import Image
import io
import base64

# تهيئة التطبيق
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-oth-ia-advanced-v2')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'mp3', 'mp4'}

# إنشاء مجلد التحميلات إذا لم يكن موجودًا
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_IA_V2')

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = ("EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD")
VERIFY_TOKEN = ("d51ee4e3183dbbd9a27b7d2c1af8c655")
GEMINI_API_KEY = ("AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")
RECAPTCHA_SITE_KEY = ("OTHV1")
RECAPTCHA_SECRET_KEY = ("OTHV1")
# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات والمستخدمين والإعدادات
conversations = {}
users = {}
user_settings = {}
notifications = {}
CONVERSATION_TIMEOUT = 24 * 60 * 60  # 24 ساعة بالثواني
data_lock = Lock()

# ==============================================
# وظائف المساعدة والديكورات
# ==============================================

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
        if 'user_id' not in session or not users.get(session['username'], {}).get('is_admin', False):
            flash('الوصول مرفوع. هذه الصفحة للإدارة فقط', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_id(sender_id):
    return hashlib.sha256(sender_id.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_response(text):
    # تحسين تنسيق النصوص البرمجية
    if "```" in text:
        parts = text.split("```")
        formatted = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # تحديد لغة البرمجة إذا كانت محددة
                lang = part.split('\n')[0].strip() if '\n' in part else ''
                code_content = part[len(lang):] if lang else part
                formatted.append(f'<div class="code-block"><pre><code class="{lang}">{code_content}</code></pre><button class="copy-btn" onclick="copyCode(this)">نسخ الكود</button></div>')
            else:
                formatted.append(part.replace("\n", "<br>"))
        return "".join(formatted)
    return text.replace("\n", "<br>")

def generate_avatar(name):
    # إنشاء صورة رمزية بسيطة بناء على اسم المستخدم
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']
    color = colors[hash(name) % len(colors)]
    
    initials = ''.join([part[0].upper() for part in name.split()[:2]])
    if len(initials) < 2:
        initials = name[:2].upper()
    
    svg = f'''
    <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" rx="50" fill="{color}"/>
        <text x="50" y="60" font-family="Arial" font-size="40" fill="white" text-anchor="middle" dominant-baseline="middle">{initials}</text>
    </svg>
    '''
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

def verify_recaptcha(response_token):
    try:
        data = {
            'secret': RECAPTCHA_SECRET_KEY,
            'response': response_token
        }
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
        result = response.json()
        return result.get('success', False)
    except Exception as e:
        logger.error(f"خطأ في التحقق من reCAPTCHA: {str(e)}")
        return False

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
                        "title": "⚙️ الإعدادات",
                        "payload": "SETTINGS_CMD"
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
                "text": "مرحبًا بك في بوت OTH IA! 💎\n\nيمكنك إرسال أي سؤال، صورة، ملف وسأساعدك في تحليلها وفهمها."
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد واجهة الماسنجر: {str(e)}")

def download_file(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (OTH IA File Downloader)'}
        req = urllib.request.Request(url, headers=headers)
        
        # الحصول على معلومات الملف
        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get('Content-Type', '')
            file_size = int(response.headers.get('Content-Length', 0))
            
            if file_size > app.config['MAX_CONTENT_LENGTH']:
                raise ValueError("حجم الملف يتجاوز الحد المسموح")
                
            ext = mimetypes.guess_extension(content_type.split(';')[0]) or '.bin'
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.read())
                
            return filepath, content_type
    except Exception as e:
        logger.error(f"خطأ في تحميل الملف: {str(e)}")
        return None, None

def analyze_file(filepath, content_type, context=None):
    try:
        if content_type.startswith('image/'):
            img = genai.upload_file(filepath)
            prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً مع تمييز الأجزاء المهمة:"
            if context:
                prompt = f"سياق المحادثة:\n{context}\n{prompt}"
            response = model.generate_content([prompt, img])
            return format_response(response.text)
        
        elif content_type == 'application/pdf':
            file = genai.upload_file(filepath)
            prompt = "حلل هذا الملف PDF وقدم ملخصاً محتوياته مع النقاط الرئيسية:"
            if context:
                prompt = f"سياق المحادثة:\n{context}\n{prompt}"
            response = model.generate_content([prompt, file])
            return format_response(response.text)
        
        elif content_type.startswith('text/'):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            prompt = "حلل هذا الملف النصي وقدم ملخصاً لمحتواه:"
            if context:
                prompt = f"سياق المحادثة:\n{context}\n{prompt}"
            response = model.generate_content([prompt, content])
            return format_response(response.text)
        
        else:
            return "⚠️ نوع الملف غير مدعوم للتحليل المباشر. يمكنك إرسال سؤال محدد عنه."
            
    except Exception as e:
        logger.error(f"خطأ في تحليل الملف: {str(e)}")
        return None
    finally:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)

def send_message(recipient_id, message_text, buttons=None, quick_replies=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    message_payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE"
    }
    
    if quick_replies:
        message_payload["message"] = {
            "text": message_text,
            "quick_replies": quick_replies
        }
    elif buttons:
        message_payload["message"] = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": message_text,
                    "buttons": buttons
                }
            }
        }
    else:
        message_payload["message"] = {"text": message_text}
    
    try:
        response = requests.post(url, json=message_payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def handle_command(sender_id, user_id, command):
    if command == "GET_STARTED":
        welcome_msg = """
        مرحباً بك في OTH IA! 💎

        أنا مساعدك الذكي الذي يمكنه:
        - الإجابة على أسئلتك بذكاء
        - تحليل الصور والملفات
        - مساعدتك في البرمجة والتحليل
        - شرح المفاهيم المعقدة ببساطة

        يمكنك البدء بإرسال سؤالك أو صورة الآن!
        """
        send_message(sender_id, welcome_msg, quick_replies=[
            {"content_type": "text", "title": "🆘 المساعدة", "payload": "HELP_CMD"},
            {"content_type": "text", "title": "📷 تحليل صورة", "payload": "UPLOAD_IMAGE"},
            {"content_type": "text", "title": "💬 محادثة جديدة", "payload": "NEW_CHAT"}
        ])
        
    elif command == "HELP_CMD":
        help_msg = """
        🆘 مركز المساعدة:

        • اكتب سؤالك مباشرة لأحصل على إجابة ذكية
        • أرسل صورة لتحليل محتواها
        • أرسل ملف PDF أو نصي لتحليله
        • استخدم الأوامر التالية:
        
        /new - بدء محادثة جديدة
        /help - عرض هذه المساعدة
        /settings - عرض الإعدادات
        """
        send_message(sender_id, help_msg)
        
    elif command == "SETTINGS_CMD":
        settings_msg = "⚙️ إعدادات المحادثة:\n\nيمكنك تعديل إعداداتك من خلال الموقع الإلكتروني"
        send_message(sender_id, settings_msg, buttons=[
            {
                "type": "web_url",
                "title": "فتح الإعدادات",
                "url": "https://your-app.vercel.app/settings",
                "webview_height_ratio": "full",
                "messenger_extensions": True
            }
        ])
        
    elif command == "LOGOUT_CMD":
        with data_lock:
            if user_id in conversations:
                del conversations[user_id]
        send_message(sender_id, "تم تسجيل الخروج بنجاح. يمكنك العودة في أي وقت!")

def cleanup_old_conversations():
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations.keys()):
            if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations[user_id]
                logger.info(f"تم حذف محادثة المستخدم {user_id} لانتهاء المهلة")

def add_notification(user_id, message, notification_type="info"):
    with data_lock:
        if user_id not in notifications:
            notifications[user_id] = []
        
        notifications[user_id].append({
            "id": str(uuid.uuid4()),
            "message": message,
            "type": notification_type,
            "timestamp": time.time(),
            "read": False
        })

def mark_notifications_read(user_id):
    with data_lock:
        if user_id in notifications:
            for note in notifications[user_id]:
                note['read'] = True

# ==============================================
# مسارات الويب
# ==============================================

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    return render_template('home.html', 
                         recaptcha_site_key=RECAPTCHA_SITE_KEY,
                         features=[
                             {"icon": "fa-robot", "title": "ذكاء اصطناعي متقدم", "desc": "محادثات ذكية مع أحدث نماذج الذكاء الاصطناعي"},
                             {"icon": "fa-code", "title": "تحليل الأكواد", "desc": "فهم وتحليل أكواد البرمجة بجميع اللغات"},
                             {"icon": "fa-image", "title": "تحليل الصور", "desc": "وصف وتحليل محتوى الصور بدقة عالية"},
                             {"icon": "fa-file-pdf", "title": "تحليل المستندات", "desc": "قراءة و تلخيص ملفات PDF والنصوص"},
                             {"icon": "fa-mobile", "title": "متعدد المنصات", "desc": "عمل على الويب وتطبيقات الموبايل"},
                             {"icon": "fa-shield", "title": "آمن وخاص", "desc": "بياناتك محمية ومشفرة دائماً"}
                         ])

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    username = session['username']
    
    # تنظيف المحادثات القديمة
    cleanup_old_conversations()
    
    # الحصول على الإحصائيات
    with data_lock:
        user_conversation = conversations.get(user_id, {})
        unread_notifications = sum(1 for note in notifications.get(user_id, []) if not note['read'])
    
    return render_template('dashboard.html',
                         username=username,
                         avatar=generate_avatar(username),
                         unread_notifications=unread_notifications,
                         last_active=datetime.fromtimestamp(user_conversation.get('last_active', time.time()) if user_conversation else None)

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    user_id = session['user_id']
    username = session['username']
    
    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # تحليل الملف
                content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
                
                with data_lock:
                    context = "\n".join(conversations[user_id]["history"][-5:]) if user_id in conversations else None
                    conversations[user_id]["last_active"] = time.time()
                    conversations[user_id]["history"].append(f"المستخدم: أرسل ملف {filename}")
                
                analysis = analyze_file(filepath, content_type, context)
                
                if analysis:
                    with data_lock:
                        conversations[user_id]["history"].append(f"البوت: {analysis[:500]}...")
                    return jsonify({"success": True, "reply": analysis})
                else:
                    return jsonify({"success": False, "error": "تعذر تحليل الملف"})
        
        message = request.form.get('message', '').strip()
        if message:
            with data_lock:
                if user_id not in conversations:
                    conversations[user_id] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                
                conversations[user_id]["last_active"] = time.time()
                conversations[user_id]["history"].append(f"المستخدم: {message}")
                
                context = "\n".join(conversations[user_id]["history"][-5:])
                prompt = f"{context}\n\nالسؤال: {message}" if context else message
                
                try:
                    response = model.generate_content(prompt)
                    reply = format_response(response.text)
                    
                    conversations[user_id]["history"].append(f"البوت: {reply}")
                    
                    return jsonify({"success": True, "reply": reply})
                except Exception as e:
                    logger.error(f"خطأ في نموذج الذكاء الاصطناعي: {str(e)}")
                    return jsonify({"success": False, "error": "حدث خطأ أثناء المعالجة"})
    
    # GET request - عرض واجهة الدردشة
    with data_lock:
        conversation_history = conversations.get(user_id, {}).get("history", [])
    
    return render_template('chat.html',
                         username=username,
                         avatar=generate_avatar(username),
                         conversation_history=conversation_history)

@app.route('/new-chat', methods=['POST'])
@login_required
def new_chat():
    user_id = session['user_id']
    
    with data_lock:
        conversations[user_id] = {
            "history": ["بدأ المستخدم محادثة جديدة"],
            "last_active": time.time()
        }
    
    return jsonify({"success": True, "message": "تم بدء محادثة جديدة"})

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings_page():
    user_id = session['user_id']
    username = session['username']
    
    if request.method == 'POST':
        theme = request.form.get('theme', 'light')
        language = request.form.get('language', 'ar')
        notifications_enabled = request.form.get('notifications', 'off') == 'on'
        
        with data_lock:
            if user_id not in user_settings:
                user_settings[user_id] = {}
            
            user_settings[user_id].update({
                'theme': theme,
                'language': language,
                'notifications': notifications_enabled,
                'updated_at': time.time()
            })
        
        flash('تم تحديث الإعدادات بنجاح', 'success')
        return redirect(url_for('user_settings_page'))
    
    # GET request
    with data_lock:
        settings = user_settings.get(user_id, {
            'theme': 'light',
            'language': 'ar',
            'notifications': True
        })
    
    return render_template('settings.html',
                         username=username,
                         avatar=generate_avatar(username),
                         settings=settings)

@app.route('/notifications')
@login_required
def user_notifications():
    user_id = session['user_id']
    
    with data_lock:
        user_notes = notifications.get(user_id, [])
        mark_notifications_read(user_id)
    
    return render_template('notifications.html',
                         username=session['username'],
                         avatar=generate_avatar(session['username']),
                         notifications=user_notes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        recaptcha_response = request.form.get('g-recaptcha-response')
        
        if not verify_recaptcha(recaptcha_response):
            flash('التحقق من reCAPTCHA فشل', 'danger')
            return redirect(url_for('login'))
        
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
                
                # إضافة إشعار ترحيبي
                add_notification(user['id'], "مرحباً بعودتك! كيف يمكننا مساعدتك اليوم؟", "welcome")
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('auth/login.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        recaptcha_response = request.form.get('g-recaptcha-response')
        
        if not verify_recaptcha(recaptcha_response):
            flash('التحقق من reCAPTCHA فشل', 'danger')
            return redirect(url_for('register'))
        
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
                        'email': email,
                        'password': generate_password_hash(password),
                        'created_at': time.time(),
                        'is_admin': False,
                        'verified': False
                    }
                    
                    conversations[user_id] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                    
                    # إضافة إشعار ترحيبي
                    add_notification(user_id, "مرحباً بك في OTH IA! يمكنك البدء بإرسال أسئلتك الآن.", "welcome")
                    
                    flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
                    return redirect(url_for('login'))
    
    return render_template('auth/register.html', recaptcha_site_key=RECAPTCHA_SITE_KEY)

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

@app.route('/admin')
@admin_required
def admin_dashboard():
    with data_lock:
        stats = {
            'total_users': len(users),
            'active_conversations': len(conversations),
            'notifications': sum(len(v) for v in notifications.values())
        }
        recent_users = sorted(users.values(), key=lambda x: x.get('created_at', 0), reverse=True)[:10]
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_users=recent_users)

# ==============================================
# مسارات API
# ==============================================

@app.route('/api/chat/history', methods=['GET'])
@login_required
def get_chat_history():
    user_id = session['user_id']
    
    with data_lock:
        if user_id in conversations:
            return jsonify({
                "success": True,
                "history": conversations[user_id]["history"]
            })
        return jsonify({"success": False, "history": []})

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    user_id = session['user_id']
    
    with data_lock:
        if user_id in notifications:
            return jsonify({
                "success": True,
                "notifications": notifications[user_id]
            })
        return jsonify({"success": False, "notifications": []})

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_as_read():
    user_id = session['user_id']
    mark_notifications_read(user_id)
    return jsonify({"success": True})

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
                            handle_command(sender_id, user_id, "GET_STARTED")
                        
                        conversations[user_id]["last_active"] = current_time
                        
                        if 'attachments' in message:
                            for attachment in message['attachments']:
                                if attachment['type'] == 'image':
                                    send_message(sender_id, "⏳ جاري تحليل الصورة...")
                                    image_url = attachment['payload']['url']
                                    image_path, content_type = download_file(image_url)
                                    
                                    if image_path:
                                        context = "\n".join(conversations[user_id]["history"][-5:])
                                        analysis = analyze_file(image_path, content_type, context)
                                        
                                        if analysis:
                                            conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                                            send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                        else:
                                            send_message(sender_id, "⚠️ تعذر تحليل الصورة")
                                elif attachment['type'] == 'file':
                                    send_message(sender_id, "⏳ جاري تحليل الملف...")
                                    file_url = attachment['payload']['url']
                                    file_path, content_type = download_file(file_url)
                                    
                                    if file_path:
                                        context = "\n".join(conversations[user_id]["history"][-5:])
                                        analysis = analyze_file(file_path, content_type, context)
                                        
                                        if analysis:
                                            conversations[user_id]["history"].append(f"ملف: {analysis[:200]}...")
                                            send_message(sender_id, f"📄 تحليل الملف:\n\n{analysis}")
                                        else:
                                            send_message(sender_id, "⚠️ تعذر تحليل الملف")
                            continue
                        
                        if 'text' in message:
                            user_message = message['text'].strip()
                            
                            if user_message.lower() in ['مساعدة', 'help', '/help']:
                                handle_command(sender_id, user_id, "HELP_CMD")
                            elif user_message.lower() in ['new', '/new', 'جديد']:
                                conversations[user_id] = {
                                    "history": ["بدأ المستخدم محادثة جديدة"],
                                    "last_active": current_time
                                }
                                send_message(sender_id, "تم بدء محادثة جديدة. كيف يمكنني مساعدتك؟")
                            elif user_message.lower() in ['settings', 'إعدادات', '/settings']:
                                handle_command(sender_id, user_id, "SETTINGS_CMD")
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

# ==============================================
# مسارات الملفات والموارد
# ==============================================

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ==============================================
# معالجة الأخطاء
# ==============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(e):
    return render_template('errors/500.html'), 500

# ==============================================
# التشغيل والصيانة
# ==============================================

def periodic_tasks():
    while True:
        time.sleep(3600)  # كل ساعة
        cleanup_old_conversations()
        logger.info("تم تنظيف المحادثات القديمة")

if __name__ == '__main__':
    # بدء خلفية المهام الدورية
    Thread(target=periodic_tasks, daemon=True).start()
    
    # إعداد واجهة الماسنجر
    setup_messenger_profile()
    
    # تشغيل التطبيق
    app.run(threaded=True)
