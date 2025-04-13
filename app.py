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
import base64

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', str(uuid.uuid4()))
app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create uploads directory if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_AI')

PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# Initialize Gemini AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    logger.error(f"Failed to initialize Gemini AI: {str(e)}")
    model = None

# Database simulation
users_db = {}
conversations_db = {}
user_conversations = {}

# Add default admin user
if not users_db.get("admin"):
    users_db["admin"] = {
        "id": str(uuid.uuid4()),
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "created_at": datetime.now()
    }

def cleanup_old_conversations():
    now = datetime.now()
    for user_id, convs in list(user_conversations.items()):
        user_conversations[user_id] = [
            conv for conv in convs 
            if now - conv['created_at'] < timedelta(hours=5)
        ]

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
    <title>OTH AI - الذكاء الاصطناعي المتقدم</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #6C63FF;
            --primary-dark: #5649FF;
            --secondary: #FF6584;
            --dark: #121212;
            --darker: #0A0A0A;
            --light: #E0E0E0;
            --lighter: #F5F5F5;
            --gray: #424242;
            --card-bg: #1E1E1E;
            --nav-bg: #121212;
            --input-bg: #252525;
            --message-user: #6C63FF;
            --message-bot: #424242;
            --error: #FF6584;
            --success: #4CAF50;
        }}
        
        body {{
            font-family: 'Tajawal', sans-serif;
            background-color: var(--dark);
            color: var(--light);
            margin: 0;
            padding: 0;
        }}
        
        .navbar {{
            background: var(--nav-bg);
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
        
        .chat-container {{
            display: grid;
            grid-template-columns: 250px 1fr;
            gap: 15px;
        }}
        
        .chat-messages {{
            height: calc(100vh - 150px);
            overflow-y: auto;
        }}
        
        .message {{
            margin-bottom: 15px;
            padding: 12px 16px;
            border-radius: 18px;
        }}
        
        .user-message {{
            background-color: var(--message-user);
            color: white;
        }}
        
        .bot-message {{
            background-color: var(--message-bot);
            color: var(--light);
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
    <div style="max-width: 400px; margin: 0 auto;">
        <h2>تسجيل الدخول</h2>
        <form method="POST">
            <input type="text" name="username" placeholder="اسم المستخدم" required>
            <input type="password" name="password" placeholder="كلمة المرور" required>
            <button type="submit">دخول</button>
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
                logger.error(f"AI Error: {str(e)}")
    
    return base_template("""
    <div class="chat-container">
        <div class="sidebar">
            <h3>المحادثات</h3>
        </div>
        <div class="chat-area">
            <div class="chat-messages" id="chat-messages">
                <div class="message bot-message">
                    مرحباً! كيف يمكنني مساعدتك اليوم؟
                </div>
            </div>
            <form id="chat-form">
                <input type="text" id="message-input" placeholder="اكتب رسالتك...">
                <button type="submit">إرسال</button>
            </form>
        </div>
    </div>
    
    <script>
        const form = document.getElementById('chat-form');
        form.addEventListener('submit', async (e) => {{
            e.preventDefault();
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (message) {{
                // Add user message
                const userMsg = document.createElement('div');
                userMsg.className = 'message user-message';
                userMsg.textContent = message;
                document.getElementById('chat-messages').appendChild(userMsg);
                
                input.value = '';
                
                // Get AI response
                try {{
                    const response = await fetch('/chat', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded',
                        }},
                        body: `message=${{encodeURIComponent(message)}}`
                    }});
                    
                    const data = await response.json();
                    if (data.response) {{
                        const botMsg = document.createElement('div');
                        botMsg.className = 'message bot-message';
                        botMsg.textContent = data.response;
                        document.getElementById('chat-messages').appendChild(botMsg);
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                }}
            }}
        }});
    </script>
    """, session.get('username'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
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
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run()
