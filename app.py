import os
import uuid
import hashlib
import logging
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import requests

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-'+str(uuid.uuid4()))
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_AI')

# API Tokens
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Database simulation
users_db = {
    "admin": {
        "id": str(uuid.uuid4()),
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "created_at": datetime.now()
    }
}

conversations_db = {}

# Modern Arabic UI with DeepSeek-like design
def base_template(content, user=None):
    nav_links = """
    <div class="nav-links">
        <a href="/login" class="btn btn-outline">تسجيل الدخول</a>
        <a href="/register" class="btn btn-primary">إنشاء حساب</a>
    </div>
    """ if not user else f"""
    <div class="nav-links">
        <span style="margin-left:15px;">مرحباً، {user}</span>
        <a href="/chat" class="btn btn-outline">الدردشة</a>
        <a href="/logout" class="btn btn-primary">تسجيل الخروج</a>
    </div>
    """
    
    return f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTH AI - الذكاء الاصطناعي المتقدم</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #7C4DFF;
            --primary-dark: #5E35B1;
            --secondary: #FF4081;
            --dark: #263238;
            --light: #f5f7fa;
            --gray: #607D8B;
            --code-bg: #282c34;
        }}
        
        body {{
            font-family: 'Tajawal', sans-serif;
            background-color: var(--light);
            color: var(--dark);
            margin: 0;
            padding: 0;
        }}
        
        .navbar {{
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 15px 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }}
        
        .nav-container {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .logo {{
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
        }}
        
        .btn {{
            display: inline-block;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
        }}
        
        .btn-primary {{
            background-color: var(--primary);
            color: white;
        }}
        
        .btn-primary:hover {{
            background-color: var(--primary-dark);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(124, 77, 255, 0.2);
        }}
        
        .btn-outline {{
            border: 1px solid var(--primary);
            color: var(--primary);
            background: transparent;
        }}
        
        .chat-container {{
            display: grid;
            grid-template-columns: 300px 1fr;
            height: calc(100vh - 70px);
        }}
        
        .chat-messages {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            background-color: #f9f9f9;
        }}
        
        .message {{
            margin-bottom: 15px;
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
        }}
        
        .user-message {{
            margin-left: auto;
            background-color: var(--primary);
            color: white;
            border-radius: 18px 18px 0 18px;
        }}
        
        .bot-message {{
            margin-right: auto;
            background-color: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-radius: 18px 18px 18px 0;
        }}
        
        .chat-input-container {{
            padding: 15px;
            background: white;
            border-top: 1px solid #eee;
        }}
        
        #message-input {{
            width: 100%;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }}
        
        .auth-container {{
            max-width: 500px;
            margin: 50px auto;
            padding: 40px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.05);
        }}
        
        .form-group {{
            margin-bottom: 20px;
        }}
        
        .error {{
            color: #dc3545;
            margin-top: 5px;
        }}
        
        @media (max-width: 768px) {{
            .chat-container {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container nav-container">
            <a href="/" class="logo">
                <i class="fas fa-robot"></i>
                <span>OTH AI</span>
            </a>
            {nav_links}
        </div>
    </nav>
    
    {content}
</body>
</html>
"""

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    features = """
    <div class="container" style="padding: 40px 0;">
        <h1 style="text-align: center; color: var(--primary); margin-bottom: 30px;">منصة الذكاء الاصطناعي المتكاملة</h1>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; margin-top: 50px;">
            <div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
                <h3 style="color: var(--primary);"><i class="fas fa-brain" style="margin-left: 10px;"></i> ذكاء اصطناعي متقدم</h3>
                <p>تفاعل مع نموذج Gemini 1.5 Flash من جوجل</p>
            </div>
            
            <div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
                <h3 style="color: var(--primary);"><i class="fas fa-image" style="margin-left: 10px;"></i> تحليل الصور</h3>
                <p>قم بتحليل الصور وفهم محتواها</p>
            </div>
            
            <div style="background: white; padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
                <h3 style="color: var(--primary);"><i class="fas fa-code" style="margin-left: 10px;"></i> تحليل الأكواد</h3>
                <p>احصل على شرح وتحليل للأكواد البرمجية</p>
            </div>
        </div>
    </div>
    """
    
    return base_template(features)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = users_db.get(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            return redirect(url_for('chat'))
        else:
            error = "اسم المستخدم أو كلمة المرور غير صحيحة"
    
    login_form = f"""
    <div class="auth-container">
        <h2 style="text-align: center; color: var(--primary); margin-bottom: 30px;">تسجيل الدخول</h2>
        <form method="POST" action="/login">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px;">
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px;">
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">تسجيل الدخول</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
        </div>
        {f'<div class="error" style="text-align: center; margin-top: 15px;">{error}</div>' if error else ''}
    </div>
    """
    
    return base_template(login_form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if len(username) < 4:
            error = "اسم المستخدم يجب أن يكون 4 أحرف على الأقل"
        elif len(password) < 6:
            error = "كلمة المرور يجب أن تكون 6 أحرف على الأقل"
        elif password != confirm_password:
            error = "كلمتا المرور غير متطابقتين"
        elif username in users_db:
            error = "اسم المستخدم موجود بالفعل"
        else:
            user_id = str(uuid.uuid4())
            users_db[username] = {
                'id': user_id,
                'username': username,
                'password': generate_password_hash(password),
                'created_at': datetime.now()
            }
            return redirect(url_for('login'))
    
    register_form = f"""
    <div class="auth-container">
        <h2 style="text-align: center; color: var(--primary); margin-bottom: 30px;">إنشاء حساب جديد</h2>
        <form method="POST" action="/register">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required minlength="4" style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px;">
                <small style="color: var(--gray);">يجب أن يكون 4 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required minlength="6" style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px;">
                <small style="color: var(--gray);">يجب أن تكون 6 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>تأكيد كلمة المرور</label>
                <input type="password" name="confirm_password" required style="width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px;">
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">إنشاء حساب</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
        </div>
        {f'<div class="error" style="text-align: center; margin-top: 15px;">{error}</div>' if error else ''}
    </div>
    """
    
    return base_template(register_form)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if not message:
            return jsonify({'error': 'الرجاء إدخال رسالة'}), 400
        
        try:
            response = model.generate_content(message)
            return jsonify({'response': response.text})
        except Exception as e:
            logger.error(f"AI Error: {str(e)}")
            return jsonify({'error': 'حدث خطأ أثناء معالجة طلبك'}), 500
    
    chat_html = """
    <div class="container" style="padding: 20px 0;">
        <div class="chat-container">
            <div style="background: white; padding: 20px; border-right: 1px solid #eee;">
                <h3>المحادثات الحديثة</h3>
                <div style="margin-top: 20px;">
                    <div style="padding: 10px; background: #f5f5f5; border-radius: 8px; margin-bottom: 10px;">
                        محادثة جديدة
                    </div>
                </div>
            </div>
            
            <div style="display: flex; flex-direction: column; height: 100%;">
                <div class="chat-messages" id="chat-messages">
                    <div class="message bot-message">
                        مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟
                    </div>
                </div>
                
                <div class="chat-input-container">
                    <form id="chat-form" onsubmit="sendMessage(); return false;">
                        <input type="text" id="message-input" placeholder="اكتب رسالتك هنا...">
                        <button type="submit" class="btn btn-primary" style="margin-top: 10px;">إرسال</button>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script>
        function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            const chatMessages = document.getElementById('chat-messages');
            
            // Add user message
            const userMsg = document.createElement('div');
            userMsg.className = 'message user-message';
            userMsg.textContent = message;
            chatMessages.appendChild(userMsg);
            
            input.value = '';
            
            // Send to server
            fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `message=${encodeURIComponent(message)}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                
                // Add bot response
                const botMsg = document.createElement('div');
                botMsg.className = 'message bot-message';
                botMsg.textContent = data.response;
                chatMessages.appendChild(botMsg);
                
                // Scroll to bottom
                chatMessages.scrollTop = chatMessages.scrollHeight;
            })
            .catch(error => {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message bot-message';
                errorMsg.textContent = error.message;
                chatMessages.appendChild(errorMsg);
            });
        }
        
        // Handle Enter key
        document.getElementById('message-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
    """
    
    return base_template(chat_html, user=session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        hub_verify_token = request.args.get('hub.verify_token')
        if hub_verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                
                if 'message' in event:
                    message_text = event['message'].get('text', '')
                    if message_text:
                        response = model.generate_content(message_text)
                        
                        requests.post(
                            f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
                            json={
                                'recipient': {'id': sender_id},
                                'message': {'text': response.text}
                            }
                        )
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run()
