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
from threading import Lock, Thread
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين البيانات
users = {}
conversations = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات
data_lock = Lock()

# وظائف مساعدة
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def cleanup_old_data():
    while True:
        time.sleep(3600)  # تنظيف كل ساعة
        current_time = time.time()
        with data_lock:
            # تنظيف المحادثات القديمة
            for user_id in list(conversations.keys()):
                if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                    del conversations[user_id]
            
            # تنظيف المستخدمين غير النشطين
            for username in list(users.keys()):
                if current_time - users[username].get('last_active', 0) > CONVERSATION_TIMEOUT:
                    del users[username]

# بدء عملية التنظيف الدوري
cleanup_thread = Thread(target=cleanup_old_data)
cleanup_thread.daemon = True
cleanup_thread.start()

# ديكورات المسارات
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

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
                session.permanent = True
                
                # إنشاء محادثة جديدة إذا لزم الأمر
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": [],
                        "last_active": time.time()
                    }
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('chat'))
            else:
                flash('بيانات الدخول غير صحيحة', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with data_lock:
            if username in users:
                flash('اسم المستخدم موجود بالفعل', 'danger')
            elif len(username) < 4 or len(password) < 6:
                flash('يجب أن يكون اسم المستخدم 4 أحرف على الأقل وكلمة المرور 6 أحرف', 'danger')
            else:
                user_id = str(uuid.uuid4())
                users[username] = {
                    'id': user_id,
                    'username': username,
                    'password': generate_password_hash(password),
                    'created_at': time.time()
                }
                
                conversations[user_id] = {
                    "history": [],
                    "last_active": time.time()
                }
                
                flash('تم إنشاء الحساب بنجاح!', 'success')
                return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    user_id = session['user_id']
    message = request.form.get('message')
    file = request.files.get('image')
    
    if not message and not file:
        return jsonify({'error': 'الرجاء إدخال رسالة أو تحميل صورة'}), 400
    
    with data_lock:
        if user_id not in conversations:
            conversations[user_id] = {
                "history": [],
                "last_active": time.time()
            }
        
        conversations[user_id]["last_active"] = time.time()
        
        # معالجة الصورة إذا تم تحميلها
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{user_id}_{int(time.time())}.{file.filename.rsplit('.', 1)[1].lower()}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                analysis = analyze_image(filepath)
                if analysis:
                    conversations[user_id]["history"].append({
                        'type': 'image',
                        'content': analysis,
                        'image_path': filename,
                        'timestamp': time.time()
                    })
                    return jsonify({
                        'reply': analysis,
                        'image_path': filename
                    })
            except Exception as e:
                logger.error(f"Image analysis error: {str(e)}")
                return jsonify({'error': 'حدث خطأ أثناء تحليل الصورة'}), 500
        
        # معالجة الرسالة النصية
        if message:
            try:
                context = "\n".join([msg['content'] for msg in conversations[user_id]["history"][-5:]])
                prompt = f"{context}\n\nالسؤال: {message}" if context else message
                response = model.generate_content(prompt)
                
                conversations[user_id]["history"].append({
                    'type': 'text',
                    'content': message,
                    'sender': 'user',
                    'timestamp': time.time()
                })
                
                conversations[user_id]["history"].append({
                    'type': 'text',
                    'content': response.text,
                    'sender': 'bot',
                    'timestamp': time.time()
                })
                
                return jsonify({
                    'reply': response.text
                })
            except Exception as e:
                logger.error(f"AI error: {str(e)}")
                return jsonify({'error': 'حدث خطأ أثناء معالجة رسالتك'}), 500
    
    return jsonify({'error': 'طلب غير صالح'}), 400

@app.route('/api/get_chat_history')
@login_required
def get_chat_history():
    user_id = session['user_id']
    with data_lock:
        if user_id in conversations:
            return jsonify({'history': conversations[user_id]["history"]})
    return jsonify({'history': []})

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)
