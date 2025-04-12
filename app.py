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
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'oth-ia-secret-key-2024'
app.permanent_session_lifetime = timedelta(hours=5)

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

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect('database/users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id TEXT NOT NULL,
            history TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# تخزين المحادثات المؤقتة
conversations = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
user_locks = {}  # أقفال لكل مستخدم
global_lock = Lock()  # قفل عام للوصول إلى conversations

# ========== وظائف المساعدة ==========
def get_user_id(sender_id):
    """إنشاء معرف فريد للمستخدم"""
    return hashlib.md5(sender_id.encode()).hexdigest()

def get_user_lock(user_id):
    """الحصول على قفل للمستخدم"""
    with global_lock:
        if user_id not in user_locks:
            user_locks[user_id] = Lock()
        return user_locks[user_id]

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

def get_chat_context(user_id):
    """الحصول على سياق المحادثة (آخر 5 رسائل)"""
    with global_lock:
        if user_id in conversations:
            return "\n".join(conversations[user_id]["history"][-5:])
        return ""

def save_conversation_to_db(user_id, conversation_id, history):
    """حفظ المحادثة في قاعدة البيانات"""
    try:
        conn = sqlite3.connect('database/users.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, conversation_id, history, last_active)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(conversation_id) DO UPDATE SET
            history = excluded.history,
            last_active = excluded.last_active
        ''', (user_id, conversation_id, history))
        conn.commit()
    except Exception as e:
        logger.error(f"خطأ في حفظ المحادثة: {str(e)}")
    finally:
        conn.close()

def load_conversation_from_db(user_id, conversation_id):
    """تحميل المحادثة من قاعدة البيانات"""
    try:
        conn = sqlite3.connect('database/users.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT history FROM conversations 
            WHERE user_id = ? AND conversation_id = ?
        ''', (user_id, conversation_id))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"خطأ في تحميل المحادثة: {str(e)}")
        return None
    finally:
        conn.close()

# ========== واجهة الماسنجر ==========
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
                "text": "مرحبًا بك في OTH IA! انقر على 'ابدأ' للتفاعل مع الذكاء الاصطناعي"
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد الواجهة: {str(e)}")

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

# ========== معالجة الأوامر والمحادثات ==========
def handle_new_user(sender_id, user_id):
    """معالجة المستخدم الجديد"""
    welcome_msg = """
    🎉 أهلاً بك في OTH IA - الذكاء الاصطناعي المتقدم!
    
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
            - واجهة ويب ثلاثية الأبعاد
            
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

# ========== واجهة الويب ==========
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            conn = sqlite3.connect('database/users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user[2], password):
                session.permanent = True
                session['user_id'] = user[0]
                session['username'] = user[1]
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('home'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
        except Exception as e:
            logger.error(f"خطأ في تسجيل الدخول: {str(e)}")
            flash('حدث خطأ أثناء تسجيل الدخول', 'danger')
        finally:
            conn.close()
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('كلمة المرور غير متطابقة', 'danger')
            return redirect(url_for('register'))
        
        try:
            conn = sqlite3.connect('database/users.db')
            cursor = conn.cursor()
            hashed_password = generate_password_hash(password, method='sha256')
            cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('اسم المستخدم موجود مسبقا', 'danger')
        except Exception as e:
            logger.error(f"خطأ في التسجيل: {str(e)}")
            flash('حدث خطأ أثناء إنشاء الحساب', 'danger')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('login'))

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مصرح به'}), 401
    
    data = request.get_json()
    message = data.get('message')
    user_id = session['user_id']
    
    try:
        # تحميل المحادثة من قاعدة البيانات إذا وجدت
        conversation_id = f"web_{user_id}"
        history = load_conversation_from_db(user_id, conversation_id)
        
        if history:
            context = history
        else:
            context = ""
        
        prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {message}" if context else message
        response = model.generate_content(prompt)
        
        # حفظ المحادثة في قاعدة البيانات
        new_history = f"{context}\nالمستخدم: {message}\nالبوت: {response.text}"
        save_conversation_to_db(user_id, conversation_id, new_history)
        
        return jsonify({
            'response': response.text,
            'formatted_response': format_response(response.text)
        })
    except Exception as e:
        logger.error(f"خطأ في الدردشة: {str(e)}")
        return jsonify({'error': 'حدث خطأ أثناء معالجة طلبك'}), 500

def format_response(text):
    """تنسيق النص لعرض الأكواد البرمجية بشكل مميز"""
    # هذا مثال بسيط، يمكن تطويره ليدعم لغات متعددة
    if '```' in text:
        parts = text.split('```')
        formatted = []
        for i, part in enumerate(parts):
            if i % 2 == 1:  # جزء الكود
                formatted.append(f'<div class="code-block"><pre><code>{part}</code></pre><button class="copy-btn" onclick="copyCode(this)">نسخ</button></div>')
            else:
                formatted.append(part.replace('\n', '<br>'))
        return ''.join(formatted)
    return text.replace('\n', '<br>')

# ========== واجهة فيسبوك ==========
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

if __name__ == '__main__':
    setup_messenger_profile()
    app.run(debug=True)
