import os
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from threading import Lock
from flask import Flask, request, jsonify, redirect, url_for, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-' + str(uuid.uuid4()))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_COOKIE_SECURE'] = True

# التوكنات المطلوبة
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# تخزين البيانات
users = {
    "admin": {
        "id": str(uuid.uuid4()),
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "created_at": datetime.now()
    }
}

conversations = {}
data_lock = Lock()

# HTML Templates
home_page = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTH AI - الذكاء الاصطناعي المتقدم</title>
    <style>
        body {
            font-family: 'Tajawal', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f7fa;
            color: #333;
        }
        .navbar {
            background: linear-gradient(135deg, #6C63FF, #4D44DB);
            color: white;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-top: 3rem;
        }
        .feature-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            transition: transform 0.3s ease;
        }
        .feature-card:hover {
            transform: translateY(-5px);
        }
        .btn {
            display: inline-block;
            padding: 0.75rem 1.5rem;
            background-color: #6C63FF;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        .btn:hover {
            background-color: #4D44DB;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <nav class="navbar">
        <a href="/" style="color: white; text-decoration: none; font-size: 1.5rem; font-weight: 700;">OTH AI</a>
        <div>
            <a href="/login" class="btn">تسجيل الدخول</a>
            <a href="/register" class="btn" style="margin-right: 1rem;">إنشاء حساب</a>
        </div>
    </nav>

    <div class="container">
        <h1 style="text-align: center; color: #4D44DB;">مرحباً بك في OTH AI</h1>
        <p style="text-align: center; font-size: 1.2rem;">منصة الذكاء الاصطناعي المتقدم للدردشة وتحليل المحتوى</p>
        
        <div class="features">
            <div class="feature-card">
                <h3>💎 ذكاء اصطناعي متقدم</h3>
                <p>محادثات ذكية مع أحدث نماذج الذكاء الاصطناعي من جوجل</p>
            </div>
            <div class="feature-card">
                <h3>📷 تحليل الصور</h3>
                <p>القدرة على تحليل الصور وإعطاء وصف دقيق لمحتواها</p>
            </div>
            <div class="feature-card">
                <h3>💬 متعدد المنصات</h3>
                <p>عمل على الويب وتطبيقات الماسنجر معاً</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

login_page = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - OTH AI</title>
    <style>
        body {
            font-family: 'Tajawal', sans-serif;
            background-color: #f5f7fa;
            direction: rtl;
            padding: 2rem;
        }
        .auth-container {
            max-width: 400px;
            margin: 2rem auto;
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        input {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background-color: #6C63FF;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-family: 'Tajawal', sans-serif;
            font-weight: 500;
        }
        .error {
            color: #ff4444;
            text-align: center;
            margin-bottom: 1rem;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="auth-container">
        <h2 style="text-align: center; margin-bottom: 1.5rem;">تسجيل الدخول</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form action="/login" method="POST">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">تسجيل الدخول</button>
        </form>
        <div style="text-align: center; margin-top: 1.5rem;">
            ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
        </div>
    </div>
</body>
</html>
"""

register_page = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إنشاء حساب - OTH AI</title>
    <style>
        body {
            font-family: 'Tajawal', sans-serif;
            background-color: #f5f7fa;
            direction: rtl;
            padding: 2rem;
        }
        .auth-container {
            max-width: 400px;
            margin: 2rem auto;
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        }
        .form-group {
            margin-bottom: 1.5rem;
        }
        input {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }
        button {
            width: 100%;
            padding: 0.75rem;
            background-color: #6C63FF;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-family: 'Tajawal', sans-serif;
            font-weight: 500;
        }
        .error {
            color: #ff4444;
            text-align: center;
            margin-bottom: 1rem;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="auth-container">
        <h2 style="text-align: center; margin-bottom: 1.5rem;">إنشاء حساب جديد</h2>
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        <form action="/register" method="POST">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required minlength="4">
                <small style="color: #666;">يجب أن يكون 4 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required minlength="6">
                <small style="color: #666;">يجب أن تكون 6 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>تأكيد كلمة المرور</label>
                <input type="password" name="confirm_password" required>
            </div>
            <button type="submit">إنشاء حساب</button>
        </form>
        <div style="text-align: center; margin-top: 1.5rem;">
            لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
        </div>
    </div>
</body>
</html>
"""

chat_page = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الدردشة - OTH AI</title>
    <style>
        body {
            font-family: 'Tajawal', sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f7fa;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        .chat-header {
            background: linear-gradient(135deg, #6C63FF, #4D44DB);
            color: white;
            padding: 1rem;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .chat-messages {
            flex: 1;
            padding: 1rem;
            overflow-y: auto;
            background-color: #f9f9f9;
        }
        .message {
            margin-bottom: 1rem;
            padding: 0.75rem 1rem;
            border-radius: 12px;
            max-width: 80%;
            word-wrap: break-word;
        }
        .user-message {
            background-color: #e3f2fd;
            margin-left: auto;
        }
        .bot-message {
            background-color: #f1f1f1;
            margin-right: auto;
        }
        .chat-input {
            display: flex;
            padding: 1rem;
            background-color: white;
            border-top: 1px solid #eee;
        }
        .chat-input input {
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
        }
        .chat-input button {
            margin-right: 0.5rem;
            padding: 0.75rem 1.5rem;
            background-color: #6C63FF;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-family: 'Tajawal', sans-serif;
        }
        .code-block {
            background: #f5f5f5;
            border-radius: 4px;
            padding: 10px;
            margin: 10px 0;
            position: relative;
        }
        .copy-btn {
            position: absolute;
            top: 5px;
            left: 5px;
            background: #6C63FF;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 2px 5px;
            font-size: 12px;
            cursor: pointer;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h3>OTH AI - الدردشة</h3>
        </div>
        <div class="chat-messages" id="chat-messages">
            <!-- سيتم ملء المحادثة بواسطة JavaScript -->
        </div>
        <div class="chat-input">
            <input type="text" id="user-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
            <button id="send-btn">إرسال</button>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const chatMessages = document.getElementById('chat-messages');
            const userInput = document.getElementById('user-input');
            const sendBtn = document.getElementById('send-btn');
            
            function addMessage(message, isUser) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
                
                // Handle code blocks formatting
                if (!isUser && message.includes('```')) {
                    const parts = message.split('```');
                    let formattedMessage = '';
                    
                    for (let i = 0; i < parts.length; i++) {
                        if (i % 2 === 1) {
                            // Code block
                            const lang = parts[i].split('\n')[0].trim();
                            const codeContent = parts[i].substring(lang.length).trim();
                            formattedMessage += `
                                <div class="code-block">
                                    <button class="copy-btn" onclick="copyCode(this)">نسخ الكود</button>
                                    <pre><code>${codeContent}</code></pre>
                                </div>
                            `;
                        } else {
                            // Regular text
                            formattedMessage += parts[i].replace(/\n/g, '<br>');
                        }
                    }
                    
                    messageDiv.innerHTML = formattedMessage;
                } else {
                    messageDiv.textContent = message;
                }
                
                chatMessages.appendChild(messageDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
            
            function copyCode(button) {
                const codeBlock = button.parentElement;
                const code = codeBlock.querySelector('code').textContent;
                navigator.clipboard.writeText(code).then(() => {
                    button.textContent = 'تم النسخ!';
                    setTimeout(() => {
                        button.textContent = 'نسخ الكود';
                    }, 2000);
                });
            }
            
            window.copyCode = copyCode;
            
            function sendMessage() {
                const message = userInput.value.trim();
                if (!message) return;
                
                addMessage(message, true);
                userInput.value = '';
                
                fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
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
            
            userInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
            
            sendBtn.addEventListener('click', sendMessage);
            
            // Load conversation history
            fetch('/conversation')
                .then(response => response.json())
                .then(data => {
                    if (data.history && data.history.length > 0) {
                        data.history.forEach(item => {
                            if (item.startsWith('User:')) {
                                addMessage(item.replace('User:', '').trim(), true);
                            } else if (item.startsWith('Bot:')) {
                                addMessage(item.replace('Bot:', '').trim(), false);
                            }
                        });
                    } else {
                        addMessage('مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟', false);
                    }
                });
        });
    </script>
</body>
</html>
"""

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
        logging.error(f"AI Error: {str(e)}")
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
        logging.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logging.error(f"خطأ في إعداد واجهة الماسنجر: {str(e)}")

def handle_messenger_command(sender_id, command):
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
        send_messenger_message(sender_id, welcome_msg)
    elif command == "HELP_CMD":
        help_msg = """
        🆘 مركز المساعدة:

        • اكتب سؤالك مباشرة لأحصل على إجابة ذكية
        • أرسل صورة لتحليل محتواها
        • استخدم الأوامر التالية:
        
        /new - بدء محادثة جديدة
        /help - عرض هذه المساعدة
        """
        send_messenger_message(sender_id, help_msg)

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
        logging.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return home_page

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with data_lock:
            user = users.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                
                # Initialize conversation if not exists
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": datetime.now()
                    }
                
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
        else:
            with data_lock:
                if username in users:
                    error = "اسم المستخدم موجود بالفعل"
                else:
                    user_id = str(uuid.uuid4())
                    users[username] = {
                        'id': user_id,
                        'username': username,
                        'password': generate_password_hash(password),
                        'created_at': datetime.now()
                    }
                    
                    # Initialize conversation
                    conversations[user_id] = {
                        "history": ["بدأ المستخدم محادثة جديدة"],
                        "last_active": datetime.now()
                    }
                    
                    return redirect(url_for('login'))
    
    return register_page.replace("{% if error %}<div class=\"error\">{{ error }}</div>{% endif %}", 
                               f"<div class=\"error\">{error}</div>" if error else "")

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"error": "الرجاء إدخال رسالة صالحة"}), 400
        
        with data_lock:
            if user_id not in conversations:
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": datetime.now()
                }
            
            conversations[user_id]["history"].append(f"User: {message}")
            conversations[user_id]["last_active"] = datetime.now()
            
            try:
                response = analyze_text(message)
                conversations[user_id]["history"].append(f"Bot: {response}")
                
                return jsonify({"response": response})
            except Exception as e:
                logging.error(f"Error in chat: {str(e)}")
                return jsonify({"error": "حدث خطأ أثناء معالجة طلبك"}), 500
    
    return chat_page

@app.route('/conversation')
@login_required
def get_conversation():
    user_id = session['user_id']
    with data_lock:
        if user_id in conversations:
            return jsonify({
                "history": conversations[user_id]["history"],
                "last_active": str(conversations[user_id]["last_active"])
            })
        return jsonify({"history": []})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

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
                
                if 'postback' in event:
                    handle_messenger_command(sender_id, event['postback']['payload'])
                    continue
                    
                if 'message' in event:
                    message = event['message']
                    
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        if user_message.lower() in ['مساعدة', 'help']:
                            handle_messenger_command(sender_id, "HELP_CMD")
                        else:
                            response = analyze_text(user_message)
                            send_messenger_message(sender_id, response)
    
    except Exception as e:
        logging.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
