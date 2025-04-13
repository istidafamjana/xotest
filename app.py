import os
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import requests
from PIL import Image
import io

# Initialize Flask app
app = Flask(__name__)

# التوكنات والمفاتيح المضمنة مباشرة
app.secret_key = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

# إعدادات التطبيق
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Gemini AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    logging.error(f"Failed to initialize Gemini AI: {str(e)}")
    model = None

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
user_conversations = {}

def cleanup_old_conversations():
    now = datetime.now()
    for user_id, convs in list(user_conversations.items()):
        user_conversations[user_id] = [conv for conv in convs if now - conv['created_at'] < timedelta(hours=5)]

def base_template(content, user=None, active_tab='chat'):
    nav_links = """
    <div class="nav-links">
        <a href="/login" class="btn btn-outline">تسجيل الدخول</a>
        <a href="/register" class="btn btn-primary">إنشاء حساب</a>
    </div>
    """ if not user else f"""
    <div class="nav-links">
        <span class="welcome-msg">مرحباً، {user}</span>
        <a href="/chat" class="nav-link {'active' if active_tab == 'chat' else ''}"><i class="fas fa-comments"></i> الدردشة</a>
        <a href="/history" class="nav-link {'active' if active_tab == 'history' else ''}"><i class="fas fa-history"></i> المحادثات</a>
        <a href="/logout" class="btn btn-danger"><i class="fas fa-sign-out-alt"></i> تسجيل الخروج</a>
    </div>
    """
    
    return f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTH AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #6C63FF;
            --dark: #121212;
            --light: #E0E0E0;
        }}
        body {{
            font-family: 'Tajawal', sans-serif;
            background-color: var(--dark);
            color: var(--light);
            margin: 0;
            padding: 0;
        }}
        .navbar {{
            background: var(--dark);
            padding: 15px 0;
        }}
        .chat-container {{
            display: grid;
            grid-template-columns: 250px 1fr;
            height: calc(100vh - 70px);
        }}
        .message {{
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 18px;
        }}
        .user-message {{
            background-color: var(--primary);
            color: white;
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <a href="/" class="logo">
                <i class="fas fa-robot"></i>
                <span>OTH AI</span>
            </a>
            {nav_links}
        </div>
    </nav>
    <div class="container">
        {content}
    </div>
    <script>
        function scrollToBottom() {{
            const chatMessages = document.getElementById('chat-messages');
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }}
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return base_template("""
    <div style="text-align: center; padding: 50px 0;">
        <h1>مرحباً بكم في OTH AI</h1>
        <p>منصة الذكاء الاصطناعي المتكاملة</p>
    </div>
    """)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users_db.get(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            return redirect(url_for('chat'))
    return base_template("""
    <div style="max-width: 400px; margin: 0 auto; padding: 20px;">
        <h2>تسجيل الدخول</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="اسم المستخدم" required style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <input type="password" name="password" placeholder="كلمة المرور" required style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <button type="submit" style="background-color: #6C63FF; color: white; padding: 10px 20px; border: none; border-radius: 5px;">تسجيل الدخول</button>
        </form>
    </div>
    """)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        message = request.form.get('message')
        if message and model:
            try:
                response = model.generate_content(message)
                return jsonify({'response': response.text})
            except Exception as e:
                logging.error(f"AI Error: {str(e)}")
                return jsonify({'error': 'حدث خطأ أثناء معالجة طلبك'}), 500
    
    return base_template("""
    <div class="chat-container">
        <div style="background: #1E1E1E; padding: 15px; border-radius: 8px;">
            <button onclick="newConversation()" style="background: #6C63FF; color: white; width: 100%; padding: 10px; margin-bottom: 15px; border: none; border-radius: 5px;">
                <i class="fas fa-plus"></i> محادثة جديدة
            </button>
            <h3>المحادثات السابقة</h3>
            <div id="conversation-list"></div>
        </div>
        <div style="display: flex; flex-direction: column; height: 100%;">
            <div id="chat-messages" style="flex: 1; overflow-y: auto; padding: 20px; background: #1E1E1E; border-radius: 8px; margin-bottom: 15px;">
                <div class="message bot-message" style="background: #424242; color: #E0E0E0;">
                    مرحباً! كيف يمكنني مساعدتك اليوم؟
                </div>
            </div>
            <form id="chat-form" onsubmit="sendMessage(); return false;" style="padding: 15px; background: #1E1E1E; border-radius: 8px;">
                <textarea id="message-input" placeholder="اكتب رسالتك هنا..." rows="3" style="width: 100%; padding: 12px; border: 1px solid #424242; border-radius: 8px; background: #252525; color: #E0E0E0;"></textarea>
                <div style="display: flex; justify-content: space-between; margin-top: 10px;">
                    <label for="file-upload" style="background: #424242; color: #E0E0E0; padding: 8px 12px; border-radius: 8px; cursor: pointer;">
                        <i class="fas fa-paperclip"></i> إرفاق ملف
                    </label>
                    <input type="file" id="file-upload" style="display: none;">
                    <button type="submit" style="background: #6C63FF; color: white; padding: 8px 20px; border: none; border-radius: 8px;">
                        <i class="fas fa-paper-plane"></i> إرسال
                    </button>
                </div>
            </form>
        </div>
    </div>
    <script>
        function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (!message) return;
            
            const chatMessages = document.getElementById('chat-messages');
            const userMsg = document.createElement('div');
            userMsg.className = 'message user-message';
            userMsg.textContent = message;
            chatMessages.appendChild(userMsg);
            input.value = '';
            
            fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `message=${encodeURIComponent(message)}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                
                const botMsg = document.createElement('div');
                botMsg.className = 'message bot-message';
                botMsg.style.background = '#424242';
                botMsg.style.color = '#E0E0E0';
                botMsg.textContent = data.response;
                chatMessages.appendChild(botMsg);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            })
            .catch(error => {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message bot-message';
                errorMsg.style.background = '#FF6584';
                errorMsg.textContent = error.message;
                chatMessages.appendChild(errorMsg);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        }
        
        document.getElementById('message-input').addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
    """, session.get('username'), 'chat')

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    try:
        data = request.get_json()
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                if 'message' in event and 'text' in event['message']:
                    message_text = event['message']['text']
                    if model:
                        response = model.generate_content(message_text)
                        requests.post(
                            f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
                            json={
                                'recipient': {'id': sender_id},
                                'message': {'text': response.text}
                            }
                        )
    except Exception as e:
        logging.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run()
