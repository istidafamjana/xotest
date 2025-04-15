from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import langid
import time
import secrets
import json
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask App
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Keys (Replace with your actual keys)
PAGE_ACCESS_TOKEN = "YOUR_FACEBOOK_PAGE_ACCESS_TOKEN"
VERIFY_TOKEN = "YOUR_FACEBOOK_VERIFY_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# Data Storage
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Custom Template Filter
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime(format)

# Database Functions
def load_users():
    try:
        with open(f"{DATA_DIR}/users.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users):
    with open(f"{DATA_DIR}/users.json", "w") as f:
        json.dump(users, f, indent=2)

def load_conversations():
    try:
        with open(f"{DATA_DIR}/conversations.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_conversations(conversations):
    with open(f"{DATA_DIR}/conversations.json", "w") as f:
        json.dump(conversations, f, indent=2)

def add_user(username, password):
    users = load_users()
    if username in users:
        return False
    
    user_id = str(uuid.uuid4())
    users[username] = {
        "id": user_id,
        "password": generate_password_hash(password),
        "theme": "dark",
        "created_at": datetime.now().isoformat(),
        "last_login": datetime.now().isoformat()
    }
    save_users(users)
    return True

def get_user(username):
    users = load_users()
    return users.get(username)

def verify_user(username, password):
    user = get_user(username)
    if not user:
        return False
    return check_password_hash(user["password"], password)

def add_conversation(user_id, message, response, is_image=False):
    conversations = load_conversations()
    if user_id not in conversations:
        conversations[user_id] = []
    
    conversations[user_id].append({
        "message": message,
        "response": response,
        "is_image": is_image,
        "timestamp": datetime.now().isoformat()
    })
    
    # Keep last 20 conversations
    conversations[user_id] = conversations[user_id][-20:]
    save_conversations(conversations)

def get_conversations(user_id):
    conversations = load_conversations()
    return conversations.get(user_id, [])

def update_user_theme(username, theme):
    users = load_users()
    if username in users:
        users[username]["theme"] = theme
        save_users(users)

# AI Functions
async def generate_response(prompt, user_id=None, lang='ar'):
    try:
        context = ""
        if user_id:
            conversations = get_conversations(user_id)
            last_conversations = conversations[-5:] if len(conversations) > 5 else conversations
            context = "\n".join([f"User: {conv['message']}\nBot: {conv['response']}" for conv in last_conversations])
        
        if lang == 'ar':
            full_prompt = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {prompt}"
        else:
            full_prompt = f"Previous context:\n{context}\n\nNew question: {prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(full_prompt)
        )
        return response.text
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "⚠️ حدث خطأ في معالجة طلبك" if lang == 'ar' else "⚠️ Error processing your request"

async def analyze_image_with_prompt(image_path, prompt, lang='ar'):
    try:
        img = genai.upload_file(image_path)
        
        if lang == 'ar':
            full_prompt = f"بناءً على طلب المستخدم: {prompt}\n\nقم بتحليل هذه الصورة بدقة:"
        else:
            full_prompt = f"Based on user request: {prompt}\n\nAnalyze this image in detail:"
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([full_prompt, img])
        )
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return "⚠️ حدث خطأ في تحليل الصورة" if lang == 'ar' else "⚠️ Error analyzing image"
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except:
                pass

# Routes
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template_string(HOME_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = get_user(session['username'])
    if not user:
        session.pop('username', None)
        return redirect(url_for('login'))
    
    conversations = get_conversations(user["id"])
    return render_template_string(DASHBOARD_TEMPLATE,
                               username=session['username'],
                               theme=user["theme"],
                               conversations=conversations[::-1])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template_string(LOGIN_TEMPLATE, error='يجب إدخال اسم المستخدم وكلمة المرور')
        
        if verify_user(username, password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        return render_template_string(LOGIN_TEMPLATE, error='بيانات الدخول غير صحيحة')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template_string(REGISTER_TEMPLATE, error='يجب إدخال اسم المستخدم وكلمة المرور')
        
        if len(password) < 8:
            return render_template_string(REGISTER_TEMPLATE, error='كلمة المرور يجب أن تكون 8 أحرف على الأقل')
        
        if not add_user(username, password):
            return render_template_string(REGISTER_TEMPLATE, error='اسم المستخدم موجود بالفعل')
        
        return redirect(url_for('login'))
    
    return render_template_string(REGISTER_TEMPLATE)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user(session['username'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    message = request.json.get('message')
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    lang = detect_language(message)
    response = asyncio.run(generate_response(message, user["id"], lang))
    
    add_conversation(user["id"], message, response)
    
    return jsonify({'response': response})

@app.route('/api/image', methods=['POST'])
def api_image():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    user = get_user(session['username'])
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    image_file = request.files['image']
    message = request.form.get('message', 'Describe this image')
    
    temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}_{image_file.filename}")
    image_file.save(temp_path)
    
    lang = detect_language(message)
    response = asyncio.run(analyze_image_with_prompt(temp_path, message, lang))
    
    add_conversation(user["id"], f"[Image] {message}", response, is_image=True)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    return jsonify({'response': response})

# Helper Functions
def detect_language(text):
    try:
        lang, _ = langid.classify(text)
        return lang
    except:
        return 'ar'

# Templates
BASE_STYLE = '''
:root {
    --primary: #6c5ce7;
    --primary-light: #a29bfe;
    --primary-dark: #5649c0;
    --secondary: #00b894;
    --danger: #d63031;
    --dark: #2d3436;
    --light: #f5f6fa;
    --gray: #636e72;
    --white: #ffffff;
    --shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    --radius: 8px;
    --transition: all 0.3s ease;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Tajawal', sans-serif;
    line-height: 1.6;
    background-color: var(--light);
    color: var(--dark);
}

.dark-mode {
    background-color: var(--dark);
    color: var(--light);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

.btn {
    display: inline-block;
    padding: 10px 20px;
    border-radius: var(--radius);
    text-decoration: none;
    font-weight: 700;
    transition: var(--transition);
    border: none;
    cursor: pointer;
}

.btn-primary {
    background-color: var(--primary);
    color: white;
}

.btn-primary:hover {
    background-color: var(--primary-dark);
    transform: translateY(-2px);
    box-shadow: var(--shadow);
}

.btn-secondary {
    background-color: var(--secondary);
    color: white;
}

.btn-danger {
    background-color: var(--danger);
    color: white;
}

.card {
    background-color: var(--white);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 20px;
    margin-bottom: 20px;
}

.dark-mode .card {
    background-color: #3d3d3d;
}

.form-group {
    margin-bottom: 15px;
}

.form-control {
    width: 100%;
    padding: 10px 15px;
    border: 1px solid #ddd;
    border-radius: var(--radius);
    font-family: inherit;
    transition: var(--transition);
}

.form-control:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 2px rgba(108, 92, 231, 0.2);
}

.text-center {
    text-align: center;
}

.mt-3 { margin-top: 1rem; }
.mt-4 { margin-top: 1.5rem; }
.mt-5 { margin-top: 3rem; }

/* Responsive */
@media (max-width: 768px) {
    .container {
        padding: 0 15px;
    }
}
'''

HOME_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>بوت الذكاء الاصطناعي</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>{BASE_STYLE}</style>
</head>
<body>
    <header style="background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: white; padding: 60px 0; text-align: center;">
        <div class="container">
            <h1 style="font-size: 2.5rem; margin-bottom: 20px;"><i class="fas fa-robot"></i> بوت الذكاء الاصطناعي</h1>
            <p style="font-size: 1.2rem; max-width: 800px; margin: 0 auto 30px;">تفاعل مع أحدث تقنيات الذكاء الاصطناعي في محادثات ذكية وتحليل الصور</p>
            <div style="display: flex; justify-content: center; gap: 15px;">
                <a href="/login" class="btn btn-primary" style="padding: 12px 30px;"><i class="fas fa-sign-in-alt"></i> تسجيل الدخول</a>
                <a href="/register" class="btn btn-secondary" style="padding: 12px 30px;"><i class="fas fa-user-plus"></i> إنشاء حساب</a>
            </div>
        </div>
    </header>

    <section class="container" style="padding: 60px 0;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px;">
            <div class="card">
                <div style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;">
                    <i class="fas fa-comments"></i>
                </div>
                <h3 style="margin-bottom: 15px;">محادثات ذكية</h3>
                <p>تحدث مع بوت ذكي يفهم السياق ويقدم إجابات دقيقة باستخدام أحدث تقنيات الذكاء الاصطناعي</p>
            </div>
            
            <div class="card">
                <div style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;">
                    <i class="fas fa-image"></i>
                </div>
                <h3 style="margin-bottom: 15px;">تحليل الصور</h3>
                <p>قم بتحميل الصور واحصل على وصف دقيق وتحليل لمحتوياتها باستخدام تقنيات الرؤية الحاسوبية</p>
            </div>
            
            <div class="card">
                <div style="font-size: 2.5rem; color: var(--primary); margin-bottom: 15px;">
                    <i class="fas fa-history"></i>
                </div>
                <h3 style="margin-bottom: 15px;">سجل المحادثات</h3>
                <p>احتفظ بسجل لمحادثاتك السابقة لتحصل على إجابات أكثر دقة وتخصيصًا</p>
            </div>
        </div>
    </section>

    <footer style="background-color: var(--dark); color: var(--light); padding: 30px 0; text-align: center; margin-top: 60px;">
        <div class="container">
            <p>© 2023 بوت الذكاء الاصطناعي. جميع الحقوق محفوظة.</p>
        </div>
    </footer>
</body>
</html>
'''

DASHBOARD_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>لوحة التحكم - بوت الذكاء الاصطناعي</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        {BASE_STYLE}
        
        .chat-container {{
            height: 60vh;
            overflow-y: auto;
            padding: 20px;
            background-color: var(--white);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            margin-bottom: 20px;
        }}
        
        .dark-mode .chat-container {{
            background-color: #3d3d3d;
        }}
        
        .message {{
            margin-bottom: 15px;
            padding: 12px 18px;
            border-radius: 20px;
            max-width: 80%;
            position: relative;
            word-wrap: break-word;
            animation: fadeIn 0.3s ease;
        }}
        
        .user-message {{
            background-color: var(--primary-light);
            color: white;
            margin-left: auto;
            margin-right: 10px;
            border-bottom-right-radius: 5px;
        }}
        
        .dark-mode .user-message {{
            background-color: var(--primary-dark);
        }}
        
        .bot-message {{
            background-color: #f1f1f1;
            color: var(--dark);
            margin-right: auto;
            margin-left: 10px;
            border-bottom-left-radius: 5px;
        }}
        
        .dark-mode .bot-message {{
            background-color: #4a4a4a;
            color: var(--light);
        }}
        
        .timestamp {{
            font-size: 0.8rem;
            color: var(--gray);
            margin-top: 5px;
            text-align: left;
        }}
        
        .input-area {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }}
        
        #message-input {{
            flex: 1;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 25px;
            font-family: inherit;
        }}
        
        .dark-mode #message-input {{
            background-color: #4a4a4a;
            color: var(--light);
            border-color: #555;
        }}
        
        .image-upload {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 15px;
        }}
        
        .image-preview {{
            max-width: 100px;
            max-height: 100px;
            border-radius: 5px;
            display: none;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .typing-indicator {{
            display: inline-block;
            padding: 10px 15px;
            background-color: #f1f1f1;
            border-radius: 20px;
            margin-bottom: 15px;
            color: var(--dark);
        }}
        
        .dark-mode .typing-indicator {{
            background-color: #4a4a4a;
            color: var(--light);
        }}
        
        .typing-dots {{
            display: inline-flex;
            align-items: center;
            height: 17px;
        }}
        
        .typing-dots span {{
            width: 8px;
            height: 8px;
            margin: 0 2px;
            background-color: var(--gray);
            border-radius: 50%;
            display: inline-block;
            animation: typingAnimation 1.4s infinite both;
        }}
        
        .typing-dots span:nth-child(1) {{
            animation-delay: 0s;
        }}
        
        .typing-dots span:nth-child(2) {{
            animation-delay: 0.2s;
        }}
        
        .typing-dots span:nth-child(3) {{
            animation-delay: 0.4s;
        }}
        
        @keyframes typingAnimation {{
            0%, 60%, 100% {{ transform: translateY(0); }}
            30% {{ transform: translateY(-5px); }}
        }}
    </style>
</head>
<body class="{% if theme == 'dark' %}dark-mode{% endif %}">
    <header style="background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: white; padding: 20px 0;">
        <div class="container" style="display: flex; justify-content: space-between; align-items: center;">
            <h1><i class="fas fa-robot"></i> بوت الذكاء الاصطناعي</h1>
            <div style="display: flex; align-items: center; gap: 15px;">
                <span style="margin-left: 10px;"><i class="fas fa-user"></i> {{ username }}</span>
                <button onclick="toggleTheme()" style="background: none; border: none; color: white; font-size: 1.2rem; cursor: pointer;">
                    <i class="fas {% if theme == 'dark' %}fa-sun{% else %}fa-moon{% endif %}"></i>
                </button>
                <a href="/logout" class="btn btn-danger"><i class="fas fa-sign-out-alt"></i> تسجيل الخروج</a>
            </div>
        </div>
    </header>

    <main class="container" style="padding: 30px 0;">
        <div class="chat-container" id="chat-container">
            {% for conv in conversations %}
                <div class="message user-message">{{ conv.message }}</div>
                <div class="message bot-message">
                    {{ conv.response }}
                    <div class="timestamp">{{ conv.timestamp|datetimeformat }}</div>
                </div>
            {% endfor %}
        </div>
        
        <div class="card">
            <div class="input-area">
                <input type="text" id="message-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
                <button onclick="sendMessage()" class="btn btn-primary">
                    <i class="fas fa-paper-plane"></i> إرسال
                </button>
            </div>
            
            <div class="image-upload">
                <div style="position: relative;">
                    <button class="btn btn-secondary" style="padding: 10px 15px;">
                        <i class="fas fa-image"></i> اختر صورة
                    </button>
                    <input type="file" id="image-input" accept="image/*" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer;">
                </div>
                <img id="image-preview" class="image-preview">
                <button onclick="sendImage()" class="btn btn-secondary">
                    <i class="fas fa-upload"></i> تحليل الصورة
                </button>
            </div>
        </div>
    </main>

    <script>
        // Scroll to bottom of chat
        function scrollToBottom() {{
            const chatContainer = document.getElementById('chat-container');
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }}
        
        // Send message function
        function sendMessage() {{
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            addMessage(message, 'user');
            input.value = '';
            
            // Show typing indicator
            showTypingIndicator();
            
            // Send to server
            fetch('/api/chat', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }},
                body: JSON.stringify({{ message: message }})
            }})
            .then(response => response.json())
            .then(data => {{
                removeTypingIndicator();
                addMessage(data.response, 'bot');
            }})
            .catch(error => {{
                removeTypingIndicator();
                addMessage('حدث خطأ في الاتصال بالخادم', 'bot');
                console.error('Error:', error);
            }});
        }}
        
        // Send image function
        function sendImage() {{
            const fileInput = document.getElementById('image-input');
            const file = fileInput.files[0];
            const messageInput = document.getElementById('message-input');
            const message = messageInput.value.trim() || 'ما هذا في الصورة؟';
            
            if (!file) {{
                alert('الرجاء اختيار صورة أولاً');
                return;
            }}
            
            const formData = new FormData();
            formData.append('image', file);
            formData.append('message', message);
            
            // Add user message to chat
            addMessage('[صورة] ' + message, 'user');
            fileInput.value = '';
            document.getElementById('image-preview').style.display = 'none';
            messageInput.value = '';
            
            // Show typing indicator
            showTypingIndicator();
            
            // Send to server
            fetch('/api/image', {{
                method: 'POST',
                body: formData
            }})
            .then(response => response.json())
            .then(data => {{
                removeTypingIndicator();
                addMessage(data.response, 'bot');
            }})
            .catch(error => {{
                removeTypingIndicator();
                addMessage('حدث خطأ في تحميل الصورة', 'bot');
                console.error('Error:', error);
            }});
        }}
        
        // Add message to chat
        function addMessage(text, sender) {{
            const chatContainer = document.getElementById('chat-container');
            const messageDiv = document.createElement('div');
            messageDiv.classList.add('message');
            messageDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
            
            const now = new Date();
            const timeString = now.toLocaleTimeString([], {{ hour: '2-digit', minute: '2-digit' }});
            
            messageDiv.innerHTML = `
                ${{text}}
                <div class="timestamp">${{timeString}}</div>
            `;
            
            chatContainer.appendChild(messageDiv);
            scrollToBottom();
        }}
        
        // Show typing indicator
        function showTypingIndicator() {{
            const chatContainer = document.getElementById('chat-container');
            const typingDiv = document.createElement('div');
            typingDiv.className = 'typing-indicator';
            typingDiv.innerHTML = `
                <span>البوت يكتب...</span>
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            `;
            chatContainer.appendChild(typingDiv);
            scrollToBottom();
        }}
        
        // Remove typing indicator
        function removeTypingIndicator() {{
            const indicators = document.querySelectorAll('.typing-indicator');
            indicators.forEach(indicator => indicator.remove());
        }}
        
        // Toggle theme
        function toggleTheme() {{
            fetch('/toggle-theme', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                }}
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.theme) {{
                    location.reload();
                }}
            }})
            .catch(error => {{
                console.error('Error:', error);
            }});
        }}
        
        // Preview image
        document.getElementById('image-input').addEventListener('change', function(e) {{
            if (e.target.files.length > 0) {{
                const file = e.target.files[0];
                const reader = new FileReader();
                
                reader.onload = function(event) {{
                    const preview = document.getElementById('image-preview');
                    preview.src = event.target.result;
                    preview.style.display = 'block';
                }};
                
                reader.readAsDataURL(file);
            }}
        }});
        
        // Send message on Enter key
        document.getElementById('message-input').addEventListener('keypress', function(e) {{
            if (e.key === 'Enter') {{
                sendMessage();
            }}
        }});
        
        // Scroll to bottom on page load
        window.onload = scrollToBottom;
    </script>
</body>
</html>
'''

LOGIN_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول - بوت الذكاء الاصطناعي</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        {BASE_STYLE}
        
        .auth-container {{
            max-width: 400px;
            margin: 60px auto;
            padding: 40px;
            background-color: var(--white);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
        }}
        
        .dark-mode .auth-container {{
            background-color: #3d3d3d;
        }}
        
        .auth-logo {{
            text-align: center;
            margin-bottom: 30px;
            color: var(--primary);
        }}
        
        .auth-logo i {{
            font-size: 3.5rem;
        }}
        
        .auth-title {{
            text-align: center;
            margin-bottom: 20px;
            color: var(--primary);
        }}
        
        .auth-link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: var(--primary);
            text-decoration: none;
        }}
        
        .auth-link:hover {{
            text-decoration: underline;
        }}
        
        .error-message {{
            color: var(--danger);
            margin-bottom: 15px;
            text-align: center;
        }}
    </style>
</head>
<body class="dark-mode">
    <div class="auth-container">
        <div class="auth-logo">
            <i class="fas fa-robot"></i>
        </div>
        <h2 class="auth-title">تسجيل الدخول</h2>
        
        {% if error %}
            <div class="error-message">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <input type="text" name="username" class="form-control" placeholder="اسم المستخدم" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" class="form-control" placeholder="كلمة المرور" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">
                <i class="fas fa-sign-in-alt"></i> تسجيل الدخول
            </button>
        </form>
        
        <a href="/register" class="auth-link">ليس لديك حساب؟ سجل الآن</a>
    </div>
</body>
</html>
'''

REGISTER_TEMPLATE = f'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>إنشاء حساب - بوت الذكاء الاصطناعي</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        {BASE_STYLE}
        
        .auth-container {{
            max-width: 400px;
            margin: 60px auto;
            padding: 40px;
            background-color: var(--white);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
        }}
        
        .dark-mode .auth-container {{
            background-color: #3d3d3d;
        }}
        
        .auth-logo {{
            text-align: center;
            margin-bottom: 30px;
            color: var(--primary);
        }}
        
        .auth-logo i {{
            font-size: 3.5rem;
        }}
        
        .auth-title {{
            text-align: center;
            margin-bottom: 20px;
            color: var(--primary);
        }}
        
        .auth-link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: var(--primary);
            text-decoration: none;
        }}
        
        .auth-link:hover {{
            text-decoration: underline;
        }}
        
        .error-message {{
            color: var(--danger);
            margin-bottom: 15px;
            text-align: center;
        }}
    </style>
</head>
<body class="dark-mode">
    <div class="auth-container">
        <div class="auth-logo">
            <i class="fas fa-robot"></i>
        </div>
        <h2 class="auth-title">إنشاء حساب جديد</h2>
        
        {% if error %}
            <div class="error-message">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <input type="text" name="username" class="form-control" placeholder="اسم المستخدم" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" class="form-control" placeholder="كلمة المرور" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">
                <i class="fas fa-user-plus"></i> إنشاء حساب
            </button>
        </form>
        
        <a href="/login" class="auth-link">لديك حساب بالفعل؟ سجل الدخول</a>
    </div>
</body>
</html>
'''

# Run the application
if __name__ == '__main__':
    executor = ThreadPoolExecutor(max_workers=4)
    fb_conversations = {}
    app.run(debug=True)
