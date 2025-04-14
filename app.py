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

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح (خاص بفيسبوك)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات المؤقتة
conversations = {}
users = {}  # تخزين مؤقت للمستخدمين
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
data_lock = Lock()

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

# مسارات الموقع
@app.route('/')
def home():
    return render_template('OTH-IA.html')

@app.route('/app')
def app_page():
    return render_template('app.html')

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
                
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": time.time()
                    }
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('app_page'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>تسجيل الدخول</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h3 class="text-center">تسجيل الدخول</h3>
                        </div>
                        <div class="card-body">
                            <form method="POST">
                                <div class="mb-3">
                                    <label for="username" class="form-label">اسم المستخدم</label>
                                    <input type="text" class="form-control" id="username" name="username" required>
                                </div>
                                <div class="mb-3">
                                    <label for="password" class="form-label">كلمة المرور</label>
                                    <input type="password" class="form-control" id="password" name="password" required>
                                </div>
                                <button type="submit" class="btn btn-primary w-100">تسجيل الدخول</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

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
                
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": time.time()
                }
                
                flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
                return redirect(url_for('login'))
    
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>إنشاء حساب</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h3 class="text-center">إنشاء حساب جديد</h3>
                        </div>
                        <div class="card-body">
                            <form method="POST">
                                <div class="mb-3">
                                    <label for="username" class="form-label">اسم المستخدم</label>
                                    <input type="text" class="form-control" id="username" name="username" required>
                                    <small class="text-muted">يجب أن يكون 4 أحرف على الأقل</small>
                                </div>
                                <div class="mb-3">
                                    <label for="password" class="form-label">كلمة المرور</label>
                                    <input type="password" class="form-control" id="password" name="password" required>
                                    <small class="text-muted">يجب أن تكون 6 أحرف على الأقل</small>
                                </div>
                                <button type="submit" class="btn btn-primary w-100">إنشاء حساب</button>
                            </form>
                            <div class="mt-3 text-center">
                                <p>لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a></p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

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

# مسارات البوت (خاص بفيسبوك)
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
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>الصفحة غير موجودة</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <div class="row justify-content-center">
                <div class="col-md-6 text-center">
                    <h1 class="display-1 text-danger">404</h1>
                    <h2 class="mb-4">الصفحة غير موجودة</h2>
                    <p class="lead">عذراً، الصفحة التي تبحث عنها غير موجودة.</p>
                    <a href="/" class="btn btn-primary">العودة للصفحة الرئيسية</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', 404

# تشغيل التنظيف الدوري كل ساعة
def periodic_cleanup():
    while True:
        time.sleep(3600)
        cleanup_old_conversations()

# بدء التنظيف الدوري في خيط منفصل
import threading
cleanup_thread = threading.Thread(target=periodic_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    setup_messenger_profile()
    app.run(threaded=True)
