import os
import uuid
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import requests
import logging

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-'+str(uuid.uuid4()))
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_AI')

# API Tokens (replace with your actual tokens)
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

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

# HTML Templates with modern design
def base_template(content):
    return f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTH AI - الذكاء الاصطناعي المتقدم</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #6C63FF;
            --primary-dark: #4D44DB;
            --light: #F8F9FA;
            --dark: #212529;
            --gray: #6C757D;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Tajawal', sans-serif;
            background-color: #F5F7FA;
            color: var(--dark);
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 15px;
        }}
        .navbar {{
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 1rem 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .navbar .container {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .logo {{
            font-size: 1.5rem;
            font-weight: 700;
            color: white;
            text-decoration: none;
        }}
        .nav-links {{
            display: flex;
            gap: 1rem;
        }}
        .btn {{
            display: inline-block;
            padding: 0.5rem 1.5rem;
            background-color: var(--primary);
            color: white;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}
        .btn:hover {{
            background-color: var(--primary-dark);
            transform: translateY(-2px);
        }}
        .auth-container {{
            max-width: 500px;
            margin: 2rem auto;
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        }}
        .form-group {{
            margin-bottom: 1.5rem;
        }}
        .form-group label {{
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 500;
        }}
        .form-control {{
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }}
        .error {{
            color: #dc3545;
            margin-bottom: 1rem;
            text-align: center;
        }}
        .chat-container {{
            display: flex;
            flex-direction: column;
            height: calc(100vh - 60px);
        }}
        .chat-header {{
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 1rem;
            text-align: center;
        }}
        .chat-messages {{
            flex: 1;
            padding: 1rem;
            overflow-y: auto;
            background-color: #F8F9FA;
        }}
        .message {{
            margin-bottom: 1rem;
            padding: 0.75rem 1rem;
            border-radius: 12px;
            max-width: 80%;
            word-wrap: break-word;
        }}
        .user-message {{
            background-color: #E3F2FD;
            margin-left: auto;
        }}
        .bot-message {{
            background-color: white;
            margin-right: auto;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }}
        .chat-input {{
            display: flex;
            padding: 1rem;
            background-color: white;
            border-top: 1px solid #eee;
        }}
        #message-input {{
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }}
        #send-btn {{
            margin-right: 0.5rem;
            padding: 0.75rem 1.5rem;
            background-color: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-family: 'Tajawal', sans-serif;
        }}
        .features {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin: 3rem 0;
        }}
        .feature-card {{
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            transition: transform 0.3s ease;
        }}
        .feature-card:hover {{
            transform: translateY(-5px);
        }}
        .feature-icon {{
            font-size: 2rem;
            margin-bottom: 1rem;
            color: var(--primary);
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <a href="/" class="logo">OTH AI</a>
            <div class="nav-links">
                <a href="/login" class="btn">تسجيل الدخول</a>
                <a href="/register" class="btn">إنشاء حساب</a>
            </div>
        </div>
    </nav>
    {content}
</body>
</html>
    """

home_page = base_template("""
<div class="container">
    <div style="text-align: center; padding: 3rem 0;">
        <h1 style="color: var(--primary); margin-bottom: 1rem;">مرحباً بك في OTH AI</h1>
        <p style="font-size: 1.2rem; color: var(--gray);">منصة الذكاء الاصطناعي المتقدم للدردشة الذكية</p>
    </div>
    
    <div class="features">
        <div class="feature-card">
            <div class="feature-icon">💎</div>
            <h3>ذكاء اصطناعي متقدم</h3>
            <p>محادثات ذكية مع أحدث نماذج الذكاء الاصطناعي من جوجل</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🤖</div>
            <h3>إجابات دقيقة</h3>
            <p>احصل على إجابات دقيقة لأسئلتك في مختلف المجالات</p>
        </div>
        <div class="feature-card">
            <div class="feature-icon">🔒</div>
            <h3>آمن وخاص</h3>
            <p>بياناتك محمية دائماً مع أنظمة تشفير متقدمة</p>
        </div>
    </div>
</div>
""")

login_page = base_template("""
<div class="auth-container">
    <h2 style="text-align: center; margin-bottom: 1.5rem;">تسجيل الدخول</h2>
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST" action="/login">
        <div class="form-group">
            <label for="username">اسم المستخدم</label>
            <input type="text" id="username" name="username" class="form-control" required>
        </div>
        <div class="form-group">
            <label for="password">كلمة المرور</label>
            <input type="password" id="password" name="password" class="form-control" required>
        </div>
        <button type="submit" class="btn" style="width: 100%;">تسجيل الدخول</button>
    </form>
    <div style="text-align: center; margin-top: 1.5rem;">
        ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
    </div>
</div>
""")

register_page = base_template("""
<div class="auth-container">
    <h2 style="text-align: center; margin-bottom: 1.5rem;">إنشاء حساب جديد</h2>
    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST" action="/register">
        <div class="form-group">
            <label for="username">اسم المستخدم</label>
            <input type="text" id="username" name="username" class="form-control" required minlength="4">
            <small style="color: var(--gray);">يجب أن يكون 4 أحرف على الأقل</small>
        </div>
        <div class="form-group">
            <label for="password">كلمة المرور</label>
            <input type="password" id="password" name="password" class="form-control" required minlength="6">
            <small style="color: var(--gray);">يجب أن تكون 6 أحرف على الأقل</small>
        </div>
        <div class="form-group">
            <label for="confirm_password">تأكيد كلمة المرور</label>
            <input type="password" id="confirm_password" name="confirm_password" class="form-control" required>
        </div>
        <button type="submit" class="btn" style="width: 100%;">إنشاء حساب</button>
    </form>
    <div style="text-align: center; margin-top: 1.5rem;">
        لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
    </div>
</div>
""")

chat_page = base_template("""
<div class="chat-container">
    <div class="chat-header">
        <h3>OTH AI - الدردشة</h3>
    </div>
    <div class="chat-messages" id="chat-messages">
        <!-- سيتم ملء المحادثة بواسطة JavaScript -->
    </div>
    <div class="chat-input">
        <input type="text" id="message-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
        <button id="send-btn">إرسال</button>
    </div>
</div>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const chatMessages = document.getElementById('chat-messages');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        
        function addMessage(text, isUser) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
            messageDiv.textContent = text;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            
            addMessage(message, true);
            messageInput.value = '';
            
            fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    addMessage('حدث خطأ: ' + data.error, false);
                } else {
                    addMessage(data.response, false);
                }
            })
            .catch(error => {
                addMessage('حدث خطأ في الاتصال بالخادم', false);
            });
        }
        
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        sendBtn.addEventListener('click', sendMessage);
        
        // Load initial message
        addMessage('مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟', false);
    });
</script>
""")

# Helper functions
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def analyze_text(text):
    try:
        response = model.generate_content(text)
        return response.text
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
        return "عذرًا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا."

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت OTH AI! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك."
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد واجهة الماسنجر: {str(e)}")

def send_messenger_message(recipient_id, message_text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
        "messaging_type": "RESPONSE"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return home_page.replace("{% if error %}<div class=\"error\">{{ error }}</div>{% endif %}", "")

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
    
    return login_page.replace("{% if error %}<div class=\"error\">{{ error }}</div>{% endif %}", 
                            f"<div class=\"error\">{error}</div>" if error else "")

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
    
    return register_page.replace("{% if error %}<div class=\"error\">{{ error }}</div>{% endif %}", 
                               f"<div class=\"error\">{error}</div>" if error else "")

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"error": "الرجاء إدخال رسالة صالحة"}), 400
        
        response = analyze_text(message)
        return jsonify({"response": response})
    
    return chat_page.replace("{% if error %}<div class=\"error\">{{ error }}</div>{% endif %}", "")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        hub_verify_token = request.args.get('hub.verify_token')
        if hub_verify_token == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "فشل التحقق", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if 'postback' in event:
                    if event['postback']['payload'] == "GET_STARTED":
                        welcome_msg = """
                        مرحباً بك في OTH AI! 💎
                        
                        يمكنك إرسال أي سؤال وسأحاول مساعدتك في الإجابة عليه.
                        """
                        send_messenger_message(sender_id, welcome_msg)
                
                if 'message' in event:
                    message_text = event['message'].get('text', '')
                    if message_text.lower() in ['مساعدة', 'help']:
                        help_msg = """
                        🆘 مركز المساعدة:
                        
                        • اكتب سؤالك مباشرة
                        • للبدء من جديد اكتب /جديد
                        """
                        send_messenger_message(sender_id, help_msg)
                    else:
                        response = analyze_text(message_text)
                        send_messenger_message(sender_id, response)
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
