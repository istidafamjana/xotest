from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import google.generativeai as genai
import logging
import tempfile
import urllib.request
import os
import hashlib
import time
from datetime import datetime, timedelta
from threading import Lock
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=5)

db = SQLAlchemy(app)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# نماذج قاعدة البيانات
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_bot = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(hours=5))

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# وظائف المساعدة
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_user_conversations(user_id, limit=5):
    # تنظيف المحادثات المنتهية
    Conversation.query.filter(Conversation.expires_at < datetime.utcnow()).delete()
    db.session.commit()
    
    return Conversation.query.filter_by(user_id=user_id).order_by(Conversation.created_at.desc()).limit(limit).all()

# مسارات الويب
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat')
@login_required
def chat():
    user_id = session['user_id']
    conversations = get_user_conversations(user_id)
    return render_template('chat.html', conversations=conversations)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('chat'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'danger')
        else:
            hashed_password = generate_password_hash(password, method='sha256')
            new_user = User(username=username, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            
            flash('تم إنشاء الحساب بنجاح! يرجى تسجيل الدخول', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    try:
        user_id = session['user_id']
        user_message = request.json.get('message', '').strip()
        
        if not user_message:
            return jsonify({"reply": "الرجاء إدخال رسالة صالحة"}), 400
        
        # حفظ رسالة المستخدم
        user_msg = Conversation(
            user_id=user_id,
            message=user_message,
            is_bot=False
        )
        db.session.add(user_msg)
        
        # توليد الرد
        context_messages = get_user_conversations(user_id, limit=5)
        context = "\n".join([f"{'البوت' if msg.is_bot else 'المستخدم'}: {msg.message}" for msg in reversed(context_messages)])
        
        response = model.generate_content(f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {user_message}")
        bot_reply = response.text
        
        # حفظ رد البوت
        bot_msg = Conversation(
            user_id=user_id,
            message=bot_reply,
            is_bot=True
        )
        db.session.add(bot_msg)
        db.session.commit()
        
        return jsonify({"reply": bot_reply}), 200
        
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        return jsonify({"reply": "حدث خطأ أثناء معالجة طلبك"}), 500

# مسار ويب هوك للفيسبوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                message = event.get('message', {})
                
                # معالجة الرسائل هنا (كما في الكود السابق)
                # ...
                
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
