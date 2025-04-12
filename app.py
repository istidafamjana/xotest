from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import requests
import google.generativeai as genai
import logging
import tempfile
import urllib.request
import os
import hashlib
import time
from threading import Lock
from datetime import datetime, timedelta
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_very_secure_secret_key_here'
app.permanent_session_lifetime = timedelta(hours=5)  # جلسة لمدة 5 ساعات

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات المؤقتة
conversations = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
user_locks = {}  # أقفال لكل مستخدم
global_lock = Lock()  # قفل عام للوصول إلى conversations

# مسار ملفات التخزين
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
CHATS_FILE = os.path.join(DATA_DIR, 'chats.json')

# تحميل بيانات المستخدمين والمحادثات
def load_data():
    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        users = {}
    
    try:
        with open(CHATS_FILE, 'r') as f:
            chats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        chats = {}
    
    return users, chats

# حفظ بيانات المستخدمين والمحادثات
def save_data(users, chats):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)
    
    with open(CHATS_FILE, 'w') as f:
        json.dump(chats, f, indent=2)

# تهيئة البيانات
users_db, chats_db = load_data()

# ديكورات التحقق من تسجيل الدخول
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# وظائف المساعدة
def get_user_id(sender_id):
    """إنشاء معرف فريد للمستخدم"""
    return hashlib.md5(sender_id.encode()).hexdigest()

def get_user_lock(user_id):
    """الحصول على قفل للمستخدم"""
    with global_lock:
        if user_id not in user_locks:
            user_locks[user_id] = Lock()
        return user_locks[user_id]

def setup_messenger_profile():
    """إعداد واجهة الماسنجر مع القائمة الدائمة والمظهر"""
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
                        "title": "🌐 الموقع الرسمي",
                        "url": "https://oth-ia.vercel.app",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "web_url",
                        "title": "📸 إنستجرام",
                        "url": "https://instagram.com/mx.fo",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "postback",
                        "title": "ℹ️ عن البوت",
                        "payload": "INFO_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://oth-ia.vercel.app"],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت الذكاء الاصطناعي OTH IA! انقر على 'ابدأ' للتفاعل مع البوت"
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
    """تحميل الصورة من الرابط المؤقت"""
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
    """تحليل الصورة مع السياق"""
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
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    """إرسال رسالة مع أزرار"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {},
        "messaging_type": "RESPONSE"
    }

    if buttons:
        payload["message"] = {
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
        payload["message"] = {"text": message_text}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def get_chat_context(user_id):
    """الحصول على سياق المحادثة (آخر 5 رسائل)"""
    with global_lock:
        if user_id in conversations:
            return "\n".join(conversations[user_id]["history"][-5:])
        return ""

def handle_new_user(sender_id, user_id):
    """معالجة المستخدم الجديد"""
    welcome_msg = """
    🎉 أهلاً بك في بوت الذكاء الاصطناعي المتقدم OTH IA!
    
    🤖 ما يمكنني فعله لك:
    • الإجابة على أسئلتك بذكاء
    • تحليل الصور ووصف محتواها
    • تذكر سياق المحادثة (حتى 5 ساعات)
    
    💡 يمكنك البدء بإرسال رسالتك الآن
    """
    
    with global_lock:
        conversations[user_id] = {
            "history": ["بدأ المستخدم محادثة جديدة"],
            "last_active": time.time()
        }
    
    send_message(sender_id, welcome_msg)

def handle_command(sender_id, user_id, command):
    """معالجة الأوامر"""
    user_lock = get_user_lock(user_id)
    
    with user_lock:
        if command == "GET_STARTED":
            start_msg = "مرحبًا! يمكنك البدء بإرسال أي سؤال أو صورة وسأساعدك."
            send_message(sender_id, start_msg)
            
        elif command == "INFO_CMD":
            info_msg = """
            ℹ️ معلومات عن OTH IA:
            
            الإصدار: 5.0
            التقنية: Gemini AI من جوجل
            الميزات:
            - فهم الأسئلة المعقدة
            - تحليل الصور المتقدم
            - دعم جلسات فردية لكل مستخدم
            - واجهة ويب متكاملة
            
            📅 آخر تحديث: 2024
            """
            send_message(sender_id, info_msg)

def process_user_message(sender_id, user_id, message):
    """معالجة رسالة المستخدم بشكل تسلسلي"""
    user_lock = get_user_lock(user_id)
    
    with user_lock:
        # تحديث وقت النشاط
        with global_lock:
            if user_id not in conversations:
                handle_new_user(sender_id, user_id)
                return
                
            conversations[user_id]["last_active"] = time.time()
        
        # معالجة الصور
        if 'attachments' in message:
            for attachment in message['attachments']:
                if attachment['type'] == 'image':
                    send_message(sender_id, "🔍 جاري تحليل الصورة...")
                    image_url = attachment['payload']['url']
                    image_path = download_image(image_url)
                    
                    if image_path:
                        context = get_chat_context(user_id)
                        analysis = analyze_image(image_path, context)
                        
                        if analysis:
                            with global_lock:
                                conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                            send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                        else:
                            send_message(sender_id, "⚠️ لم أتمكن من تحليل الصورة")
            return
        
        # معالجة النصوص
        if 'text' in message:
            user_message = message['text'].strip()
            
            if user_message.lower() in ['مساعدة', 'help']:
                handle_command(sender_id, user_id, "INFO_CMD")
            else:
                try:
                    context = get_chat_context(user_id)
                    prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {user_message}" if context else user_message
                    
                    response = model.generate_content(prompt)
                    
                    with global_lock:
                        conversations[user_id]["history"].append(f"المستخدم: {user_message}")
                        conversations[user_id]["history"].append(f"البوت: {response.text}")
                    
                    send_message(sender_id, response.text)
                    
                except Exception as e:
                    logger.error(f"خطأ في الذكاء الاصطناعي: {str(e)}")
                    send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك")

# مسارات الويب
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users_db and users_db[username]['password'] == password:
            session.permanent = True
            session['user_id'] = username
            session['user_name'] = users_db[username].get('name', username)
            flash('تم تسجيل الدخول بنجاح!', 'success')
            next_page = request.args.get('next', url_for('chat'))
            return redirect(next_page)
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users_db:
            flash('اسم المستخدم موجود بالفعل', 'danger')
        elif len(username) < 4:
            flash('اسم المستخدم يجب أن يكون على الأقل 4 أحرف', 'danger')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون على الأقل 6 أحرف', 'danger')
        else:
            users_db[username] = {
                'password': password,
                'created_at': datetime.now().isoformat()
            }
            save_data(users_db, chats_db)
            flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    user_id = session['user_id']
    if user_id not in chats_db:
        chats_db[user_id] = []
    
    return render_template('chat.html', 
                         username=session.get('user_name', 'مستخدم'),
                         chats=chats_db[user_id])

@app.route('/send_message', methods=['POST'])
@login_required
def send_web_message():
    user_id = session['user_id']
    user_message = request.form.get('message')
    
    if not user_message:
        return jsonify({'error': 'الرسالة فارغة'}), 400
    
    try:
        context = "\n".join([msg['content'] for msg in chats_db.get(user_id, [])[-5:] if msg['sender'] == 'user'])
        prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {user_message}" if context else user_message
        
        response = model.generate_content(prompt)
        
        # حفظ المحادثة
        if user_id not in chats_db:
            chats_db[user_id] = []
        
        chats_db[user_id].append({
            'sender': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat()
        })
        
        chats_db[user_id].append({
            'sender': 'bot',
            'content': response.text,
            'timestamp': datetime.now().isoformat()
        })
        
        save_data(users_db, chats_db)
        
        return jsonify({
            'response': response.text,
            'timestamp': datetime.now().strftime('%H:%M')
        })
    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {str(e)}")
        return jsonify({'error': 'حدث خطأ أثناء معالجة رسالتك'}), 500

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('home'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
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
                
                # تنظيف المحادثات القديمة (أكثر من 5 ساعات)
                with global_lock:
                    for uid in list(conversations.keys()):
                        if current_time - conversations[uid]["last_active"] > CONVERSATION_TIMEOUT:
                            del conversations[uid]
                            if uid in user_locks:
                                del user_locks[uid]
                
                # معالجة Postback (أزرار القائمة)
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    process_user_message(sender_id, user_id, message)
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%H:%M'):
    """فلتر لتنسيق التاريخ للعرض"""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime(format)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
