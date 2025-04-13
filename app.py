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
import json

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

# API Tokens (يجب تعيينها في متغيرات البيئة)
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

# Database simulation (في الإنتاج استخدم قاعدة بيانات حقيقية)
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
            min-height: 100vh;
        }}
        
        .navbar {{
            background: var(--nav-bg);
            box-shadow: 0 2px 15px rgba(0,0,0,0.3);
            padding: 15px 0;
            position: sticky;
            top: 0;
            z-index: 100;
            border-bottom: 1px solid var(--gray);
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
        
        .logo:hover {{
            color: var(--secondary);
        }}
        
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.3s ease;
            cursor: pointer;
            border: none;
            font-family: 'Tajawal', sans-serif;
        }}
        
        .btn i {{
            font-size: 0.9em;
        }}
        
        .btn-primary {{
            background-color: var(--primary);
            color: white;
        }}
        
        .btn-primary:hover {{
            background-color: var(--primary-dark);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(108, 99, 255, 0.3);
        }}
        
        .btn-outline {{
            border: 1px solid var(--primary);
            color: var(--primary);
            background: transparent;
        }}
        
        .btn-outline:hover {{
            background-color: rgba(108, 99, 255, 0.1);
        }}
        
        .btn-danger {{
            background-color: var(--error);
            color: white;
        }}
        
        .btn-danger:hover {{
            background-color: #e04f6d;
            transform: translateY(-2px);
        }}
        
        .nav-links {{
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        
        .nav-link {{
            color: var(--light);
            text-decoration: none;
            padding: 8px 15px;
            border-radius: 8px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .nav-link:hover {{
            background-color: rgba(255, 255, 255, 0.1);
        }}
        
        .nav-link.active {{
            background-color: var(--primary);
            color: white;
        }}
        
        .welcome-msg {{
            margin-left: 15px;
            color: var(--light);
            opacity: 0.8;
        }}
        
        .chat-container {{
            display: grid;
            grid-template-columns: 250px 1fr;
            height: calc(100vh - 70px);
            gap: 15px;
        }}
        
        .sidebar {{
            background-color: var(--darker);
            border-radius: 12px;
            padding: 15px;
            overflow-y: auto;
        }}
        
        .conversation-list {{
            margin-top: 15px;
        }}
        
        .conversation-item {{
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .conversation-item:hover {{
            background-color: rgba(108, 99, 255, 0.2);
        }}
        
        .conversation-item.active {{
            background-color: var(--primary);
        }}
        
        .new-chat-btn {{
            width: 100%;
            margin-bottom: 15px;
        }}
        
        .chat-area {{
            display: flex;
            flex-direction: column;
            height: 100%;
        }}
        
        .chat-messages {{
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            background-color: var(--darker);
            border-radius: 12px;
            margin-bottom: 15px;
        }}
        
        .message {{
            margin-bottom: 15px;
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
            line-height: 1.6;
            animation: fadeIn 0.3s ease;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .user-message {{
            margin-left: auto;
            background-color: var(--message-user);
            color: white;
            border-radius: 18px 18px 0 18px;
        }}
        
        .bot-message {{
            margin-right: auto;
            background-color: var(--message-bot);
            color: var(--light);
            border-radius: 18px 18px 18px 0;
        }}
        
        .message img {{
            max-width: 100%;
            border-radius: 8px;
            margin-top: 10px;
        }}
        
        .message-file {{
            display: inline-block;
            padding: 8px 12px;
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            margin-top: 8px;
        }}
        
        .chat-input-container {{
            padding: 15px;
            background: var(--darker);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        
        #message-input {{
            width: 100%;
            padding: 12px 15px;
            border: 1px solid var(--gray);
            border-radius: 8px;
            font-family: 'Tajawal', sans-serif;
            background-color: var(--input-bg);
            color: var(--light);
            resize: none;
        }}
        
        #message-input:focus {{
            outline: none;
            border-color: var(--primary);
        }}
        
        .input-actions {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .file-input {{
            display: none;
        }}
        
        .file-label {{
            padding: 8px 12px;
            border-radius: 8px;
            background-color: var(--gray);
            color: var(--light);
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .file-label:hover {{
            background-color: var(--primary);
        }}
        
        .auth-container {{
            max-width: 500px;
            margin: 50px auto;
            padding: 40px;
            background: var(--card-bg);
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.2);
        }}
        
        .auth-title {{
            text-align: center;
            color: var(--primary);
            margin-bottom: 30px;
        }}
        
        .form-group {{
            margin-bottom: 20px;
        }}
        
        .form-group label {{
            display: block;
            margin-bottom: 8px;
            color: var(--light);
        }}
        
        .form-group input {{
            width: 100%;
            padding: 12px;
            border: 1px solid var(--gray);
            border-radius: 8px;
            background-color: var(--input-bg);
            color: var(--light);
        }}
        
        .form-group input:focus {{
            outline: none;
            border-color: var(--primary);
        }}
        
        .error {{
            color: var(--error);
            margin-top: 5px;
            text-align: center;
        }}
        
        .success {{
            color: var(--success);
            margin-top: 5px;
            text-align: center;
        }}
        
        .history-container {{
            background-color: var(--darker);
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }}
        
        .history-item {{
            padding: 15px;
            border-bottom: 1px solid var(--gray);
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .history-item:hover {{
            background-color: rgba(108, 99, 255, 0.1);
        }}
        
        .history-item:last-child {{
            border-bottom: none;
        }}
        
        .history-title {{
            font-weight: 500;
            margin-bottom: 5px;
            color: var(--primary);
        }}
        
        .history-preview {{
            color: var(--gray);
            font-size: 0.9em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        .history-date {{
            color: var(--gray);
            font-size: 0.8em;
            margin-top: 5px;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: var(--gray);
        }}
        
        .empty-state i {{
            font-size: 3em;
            margin-bottom: 15px;
            opacity: 0.5;
        }}
        
        @media (max-width: 768px) {{
            .chat-container {{
                grid-template-columns: 1fr;
            }}
            
            .sidebar {{
                display: none;
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
    
    features = """
    <div style="padding: 40px 0;">
        <h1 style="text-align: center; color: var(--primary); margin-bottom: 30px;">منصة الذكاء الاصطناعي المتكاملة</h1>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; margin-top: 50px;">
            <div style="background: var(--card-bg); padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
                <h3 style="color: var(--primary);"><i class="fas fa-brain" style="margin-left: 10px;"></i> ذكاء اصطناعي متقدم</h3>
                <p>تفاعل مع نموذج Gemini 1.5 Flash من جوجل</p>
            </div>
            
            <div style="background: var(--card-bg); padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
                <h3 style="color: var(--primary);"><i class="fas fa-image" style="margin-left: 10px;"></i> تحليل الصور</h3>
                <p>قم بتحليل الصور وفهم محتواها</p>
            </div>
            
            <div style="background: var(--card-bg); padding: 25px; border-radius: 12px; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
                <h3 style="color: var(--primary);"><i class="fas fa-file" style="margin-left: 10px;"></i> معالجة الملفات</h3>
                <p>تحليل PDF، Word، Excel وغيرها</p>
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
            
            # Initialize conversation history if not exists
            if user['id'] not in user_conversations:
                user_conversations[user['id']] = []
            
            return redirect(url_for('chat'))
        else:
            error = "اسم المستخدم أو كلمة المرور غير صحيحة"
    
    login_form = f"""
    <div class="auth-container">
        <h2 class="auth-title">تسجيل الدخول</h2>
        <form method="POST" action="/login">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">تسجيل الدخول</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
        </div>
        {f'<div class="error">{error}</div>' if error else ''}
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
            
            # Initialize empty conversation history
            user_conversations[user_id] = []
            
            return redirect(url_for('login'))
    
    register_form = f"""
    <div class="auth-container">
        <h2 class="auth-title">إنشاء حساب جديد</h2>
        <form method="POST" action="/register">
            <div class="form-group">
                <label>اسم المستخدم</label>
                <input type="text" name="username" required minlength="4">
                <small style="color: var(--gray);">يجب أن يكون 4 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>كلمة المرور</label>
                <input type="password" name="password" required minlength="6">
                <small style="color: var(--gray);">يجب أن تكون 6 أحرف على الأقل</small>
            </div>
            <div class="form-group">
                <label>تأكيد كلمة المرور</label>
                <input type="password" name="confirm_password" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">إنشاء حساب</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
        </div>
        {f'<div class="error">{error}</div>' if error else ''}
    </div>
    """
    
    return base_template(register_form)

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    username = session['username']
    
    # Get current conversation or create new one
    current_conv_id = request.args.get('conv_id', str(uuid.uuid4()))
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        file = request.files.get('file')
        
        if not message and not file:
            return jsonify({'error': 'الرجاء إدخال رسالة أو تحميل ملف'}), 400
        
        try:
            # Prepare conversation history
            if current_conv_id not in conversations_db:
                conversations_db[current_conv_id] = {
                    'user_id': user_id,
                    'created_at': datetime.now(),
                    'messages': []
                }
            
            # Add user message to conversation
            user_message = {
                'id': str(uuid.uuid4()),
                'content': message,
                'is_user': True,
                'timestamp': datetime.now(),
                'file': None
            }
            
            # Handle file upload
            file_data = None
            if file:
                filename = f"{uuid.uuid4()}_{file.filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Store file info
                file_data = {
                    'filename': filename,
                    'original_name': file.filename,
                    'content_type': file.content_type
                }
                
                user_message['file'] = file_data
            
            conversations_db[current_conv_id]['messages'].append(user_message)
            
            # Generate AI response
            if file and file.content_type.startswith('image/'):
                # Process image with Gemini
                img = Image.open(file.stream)
                response = model.generate_content([
                    "وصف هذه الصورة بشكل مفصل باللغة العربية:",
                    img
                ])
                ai_response = response.text
            elif file:
                # Process other file types
                file.stream.seek(0)
                file_content = file.stream.read()
                
                if file.content_type == 'application/pdf':
                    prompt = "قم بتحليل هذا الملف PDF وقدم ملخصاً باللغة العربية:"
                elif 'word' in file.content_type:
                    prompt = "قم بتحليل هذا الملف Word وقدم ملخصاً باللغة العربية:"
                elif 'excel' in file.content_type or 'spreadsheet' in file.content_type:
                    prompt = "قم بتحليل هذا الملف Excel وقدم ملخصاً باللغة العربية:"
                else:
                    prompt = "قم بتحليل هذا الملف وقدم ملخصاً باللغة العربية:"
                
                response = model.generate_content([
                    prompt,
                    file_content
                ])
                ai_response = response.text
            else:
                # Text-only message
                response = model.generate_content(message)
                ai_response = response.text
            
            # Add AI response to conversation
            ai_message = {
                'id': str(uuid.uuid4()),
                'content': ai_response,
                'is_user': False,
                'timestamp': datetime.now()
            }
            
            conversations_db[current_conv_id]['messages'].append(ai_message)
            
            # Update conversation in user's history if it's new
            if not any(conv['id'] == current_conv_id for conv in user_conversations[user_id]):
                user_conversations[user_id].append({
                    'id': current_conv_id,
                    'title': message[:50] + ('...' if len(message) > 50 else ''),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
            else:
                # Update existing conversation timestamp
                for conv in user_conversations[user_id]:
                    if conv['id'] == current_conv_id:
                        conv['updated_at'] = datetime.now()
                        break
            
            # Clean up old conversations
            cleanup_old_conversations()
            
            return jsonify({
                'response': ai_response,
                'conv_id': current_conv_id
            })
        except Exception as e:
            logger.error(f"AI Error: {str(e)}")
            return jsonify({'error': 'حدث خطأ أثناء معالجة طلبك'}), 500
    
    # Get conversation messages if exists
    messages = []
    if current_conv_id in conversations_db:
        messages = conversations_db[current_conv_id]['messages']
    
    # Get user's conversation history
    conv_history = sorted(
        user_conversations.get(user_id, []),
        key=lambda x: x['updated_at'],
        reverse=True
    )
    
    # Generate messages HTML
    messages_html = ""
    for msg in messages:
        if msg['is_user']:
            messages_html += f"""
            <div class="message user-message" id="msg-{msg['id']}">
                {msg['content']}
                {f'<div class="message-file"><i class="fas fa-file"></i> {msg["file"]["original_name"]}</div>' if msg['file'] else ''}
            </div>
            """
        else:
            messages_html += f"""
            <div class="message bot-message" id="msg-{msg['id']}">
                {msg['content']}
            </div>
            """
    
    if not messages_html:
        messages_html = """
        <div class="message bot-message">
            مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟
        </div>
        """
    
    # Generate conversation list HTML
    conv_list_html = ""
    for conv in conv_history:
        active_class = "active" if conv['id'] == current_conv_id else ""
        conv_list_html += f"""
        <div class="conversation-item {active_class}" onclick="loadConversation('{conv['id']}')">
            <div>{conv['title']}</div>
            <small style="color: var(--gray);">{conv['updated_at'].strftime('%Y-%m-%d %H:%M')}</small>
        </div>
        """
    
    if not conv_list_html:
        conv_list_html = """
        <div class="empty-state">
            <i class="fas fa-comments"></i>
            <p>لا توجد محادثات سابقة</p>
        </div>
        """
    
    chat_html = f"""
    <div class="chat-container">
        <div class="sidebar">
            <button class="btn btn-primary new-chat-btn" onclick="newConversation()">
                <i class="fas fa-plus"></i> محادثة جديدة
            </button>
            <h3>المحادثات السابقة</h3>
            <div class="conversation-list">
                {conv_list_html}
            </div>
        </div>
        
        <div class="chat-area">
            <div class="chat-messages" id="chat-messages">
                {messages_html}
            </div>
            
            <div class="chat-input-container">
                <form id="chat-form" onsubmit="sendMessage(); return false;">
                    <textarea id="message-input" placeholder="اكتب رسالتك هنا..." rows="3"></textarea>
                    <div class="input-actions">
                        <label for="file-upload" class="file-label">
                            <i class="fas fa-paperclip"></i> إرفاق ملف
                        </label>
                        <input type="file" id="file-upload" class="file-input" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx">
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-paper-plane"></i> إرسال
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <script>
        // Scroll to bottom on page load
        window.onload = function() {{
            scrollToBottom();
        }};
        
        // Load a conversation
        function loadConversation(convId) {{
            window.location.href = `/chat?conv_id=${{convId}}`;
        }}
        
        // Start new conversation
        function newConversation() {{
            window.location.href = '/chat';
        }}
        
        // Send message to server
        function sendMessage() {{
            const input = document.getElementById('message-input');
            const fileInput = document.getElementById('file-upload');
            const message = input.value.trim();
            const file = fileInput.files[0];
            
            if (!message && !file) return;
            
            const chatMessages = document.getElementById('chat-messages');
            const convId = new URLSearchParams(window.location.search).get('conv_id') || '{current_conv_id}';
            
            // Add user message to UI immediately
            if (message) {{
                const userMsg = document.createElement('div');
                userMsg.className = 'message user-message';
                userMsg.textContent = message;
                chatMessages.appendChild(userMsg);
            }}
            
            // Add file info if uploaded
            if (file) {{
                const userMsg = document.createElement('div');
                userMsg.className = 'message user-message';
                
                if (message) {{
                    userMsg.textContent = message;
                }} else {{
                    userMsg.textContent = 'إرسال ملف:';
                }}
                
                const fileInfo = document.createElement('div');
                fileInfo.className = 'message-file';
                fileInfo.innerHTML = `<i class="fas fa-file"></i> ${{file.name}}`;
                userMsg.appendChild(fileInfo);
                
                chatMessages.appendChild(userMsg);
            }}
            
            input.value = '';
            fileInput.value = '';
            
            // Scroll to bottom
            scrollToBottom();
            
            // Prepare form data
            const formData = new FormData();
            if (message) formData.append('message', message);
            if (file) formData.append('file', file);
            
            // Send to server
            fetch(`/chat?conv_id=${{convId}}`, {{
                method: 'POST',
                body: formData
            }})
            .then(response => response.json())
            .then(data => {{
                if (data.error) {{
                    throw new Error(data.error);
                }}
                
                // Add bot response
                const botMsg = document.createElement('div');
                botMsg.className = 'message bot-message';
                botMsg.textContent = data.response;
                chatMessages.appendChild(botMsg);
                
                // Update URL with new conversation ID if this is a new conversation
                if (data.conv_id && data.conv_id !== convId) {{
                    window.history.replaceState({{}}, '', `?conv_id=${{data.conv_id}}`);
                }}
                
                // Scroll to bottom
                scrollToBottom();
            }})
            .catch(error => {{
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message bot-message';
                errorMsg.textContent = error.message;
                chatMessages.appendChild(errorMsg);
                scrollToBottom();
            }});
        }}
        
        // Handle Enter key (but allow Shift+Enter for new lines)
        document.getElementById('message-input').addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});
    </script>
    """
    
    return base_template(chat_html, user=username, active_tab='chat')

@app.route('/history')
def conversation_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    username = session['username']
    
    # Get user's conversation history
    conv_history = sorted(
        user_conversations.get(user_id, []),
        key=lambda x: x['updated_at'],
        reverse=True
    )
    
    # Generate history HTML
    history_html = ""
    for conv in conv_history:
        # Get first message content for preview
        preview = ""
        if conv['id'] in conversations_db and conversations_db[conv['id']]['messages']:
            first_msg = conversations_db[conv['id']]['messages'][0]
            preview = first_msg['content'][:100] + ('...' if len(first_msg['content']) > 100 else '')
        
        history_html += f"""
        <div class="history-item" onclick="window.location.href='/chat?conv_id={conv['id']}'">
            <div class="history-title">{conv['title']}</div>
            <div class="history-preview">{preview}</div>
            <div class="history-date">{conv['updated_at'].strftime('%Y-%m-%d %H:%M')}</div>
        </div>
        """
    
    if not history_html:
        history_html = """
        <div class="empty-state">
            <i class="fas fa-comments"></i>
            <p>لا توجد محادثات سابقة</p>
        </div>
        """
    
    history_page = f"""
    <h2 style="color: var(--primary); margin-top: 20px;">سجل المحادثات</h2>
    <div class="history-container">
        {history_html}
    </div>
    """
    
    return base_template(history_page, user=username, active_tab='history')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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
                    message = event['message']
                    
                    # Handle text message
                    if 'text' in message:
                        message_text = message['text']
                        if model:
                            response = model.generate_content(message_text)
                            requests.post(
                                f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
                                json={
                                    'recipient': {'id': sender_id},
                                    'message': {'text': response.text}
                                }
                            )
                    
                    # Handle image attachment
                    elif 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image' and model:
                                image_url = attachment['payload']['url']
                                image_data = requests.get(image_url).content
                                
                                # Process image with Gemini
                                img = Image.open(io.BytesIO(image_data))
                                ai_response = model.generate_content([
                                    "وصف هذه الصورة بشكل مفصل باللغة العربية:",
                                    img
                                ])
                                
                                requests.post(
                                    f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}",
                                    json={
                                        'recipient': {'id': sender_id},
                                        'message': {'text': ai_response.text}
                                    }
                                )
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run()
