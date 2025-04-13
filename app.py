import os
import time
import uuid
import hashlib
import logging
import tempfile
import urllib.request
from datetime import datetime, timedelta
from threading import Lock, Thread
from functools import wraps
import json

from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import google.generativeai as genai
from markdown import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

# تهيئة التطبيق
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-oth-ai-v3')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_AI')

# تهيئة نموذج Gemini
genai.configure(api_key=os.environ.get('GEMINI_API_KEY', 'your-gemini-api-key'))
model = genai.GenerativeModel('gemini-1.5-pro')

# قواعد البيانات المؤقتة
users_db = {}
conversations_db = {}
files_db = {}
CONVERSATION_TTL = 5 * 60 * 60  # 5 ساعات
db_lock = Lock()

# ==============================================
# وظائف المساعدة
# ==============================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def generate_user_id():
    return str(uuid.uuid4())

def hash_password(password):
    return generate_password_hash(password)

def check_password(hashed, password):
    return check_password_hash(hashed, password)

def save_conversation(user_id, messages):
    with db_lock:
        conversations_db[user_id] = {
            'messages': messages,
            'last_active': time.time(),
            'created_at': time.time()
        }

def get_conversation(user_id):
    with db_lock:
        return conversations_db.get(user_id, {'messages': [], 'last_active': time.time()})

def cleanup_old_conversations():
    while True:
        time.sleep(3600)  # كل ساعة
        current_time = time.time()
        with db_lock:
            for user_id in list(conversations_db.keys()):
                if current_time - conversations_db[user_id]['last_active'] > CONVERSATION_TTL:
                    del conversations_db[user_id]
                    logger.info(f"تم تنظيف محادثة المستخدم {user_id}")

def analyze_code(code, language=None):
    try:
        if language:
            lexer = get_lexer_by_name(language, stripall=True)
        else:
            lexer = get_lexer_by_name('python', stripall=True)
            
        formatter = HtmlFormatter(style='friendly', full=True, cssclass="codehilite")
        highlighted = highlight(code, lexer, formatter)
        return highlighted
    except:
        return f"<pre><code>{code}</code></pre>"

def format_ai_response(text):
    # تحويل Markdown إلى HTML
    html = markdown(text)
    
    # معالجة الأكواد البرمجية
    if '```' in html:
        parts = html.split('```')
        formatted = []
        for i, part in enumerate(parts):
            if i % 2 == 1:  # هذا جزء كود
                lang, *code = part.split('\n', 1)
                lang = lang.strip() or 'text'
                code = code[0] if code else ''
                formatted.append(analyze_code(code, language=lang))
            else:
                formatted.append(part)
        return ''.join(formatted)
    return html

def render_template(template_name, **context):
    templates = {
        'base.html': BASE_TEMPLATE,
        'index.html': INDEX_TEMPLATE,
        'auth/login.html': LOGIN_TEMPLATE,
        'auth/register.html': REGISTER_TEMPLATE,
        'dashboard/index.html': DASHBOARD_TEMPLATE,
        'dashboard/chat.html': CHAT_TEMPLATE,
        'dashboard/settings.html': SETTINGS_TEMPLATE,
        '404.html': NOT_FOUND_TEMPLATE
    }
    
    if template_name not in templates:
        return "Template not found", 404
    
    base_template = templates['base.html']
    content_template = templates[template_name]
    
    # دمج القوالب
    full_template = base_template.replace('{% block content %}', content_template)
    
    # معالجة المتغيرات
    for key, value in context.items():
        full_template = full_template.replace(f'{{{{ {key} }}}}', str(value))
    
    # إزالة البلوكات غير المستخدمة
    full_template = full_template.replace('{% block extra_css %}', '')
    full_template = full_template.replace('{% endblock %}', '')
    full_template = full_template.replace('{% block extra_js %}', '')
    
    return render_template_string(full_template)

# ==============================================
# القوالب المضمنة
# ==============================================

BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}OTH AI{% endblock %}</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a56d4;
            --secondary: #3f37c9;
            --success: #4cc9f0;
            --warning: #f8961e;
            --danger: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --gray: #6c757d;
            --gray-light: #e9ecef;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Tajawal', sans-serif;
        }
        
        body {
            background-color: #f5f7fb;
            color: var(--dark);
            direction: rtl;
        }
        
        .navbar {
            background: white;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--primary);
            text-decoration: none;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .btn {
            display: inline-block;
            padding: 0.75rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }
        
        .btn-primary {
            background-color: var(--primary);
            color: white;
        }
        
        .btn-primary:hover {
            background-color: var(--primary-dark);
        }
        
        .alert {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        
        .alert-success {
            background-color: #d1fae5;
            color: #065f46;
        }
        
        .alert-danger {
            background-color: #fee2e2;
            color: #b91c1c;
        }
        
        .code-block {
            position: relative;
            margin: 1rem 0;
            border-radius: 8px;
            overflow: hidden;
        }
        
        .code-header {
            background-color: var(--dark);
            color: white;
            padding: 0.5rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .copy-btn {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
        }
        
        pre {
            margin: 0;
            padding: 1rem;
            background-color: #f8f9fa;
            overflow-x: auto;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
        }
    </style>
    {% block extra_css %}{% endblock %}
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">OTH AI</a>
        <div>
            {% if 'user_id' in session %}
                <a href="/dashboard" class="btn btn-primary">لوحة التحكم</a>
                <a href="/logout" class="btn">تسجيل الخروج</a>
            {% else %}
                <a href="/login" class="btn">تسجيل الدخول</a>
                <a href="/register" class="btn btn-primary">إنشاء حساب</a>
            {% endif %}
        </div>
    </nav>

    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </main>

    <script>
        function copyCode(button) {
            const codeBlock = button.parentElement;
            const code = codeBlock.querySelector('code').innerText;
            
            navigator.clipboard.writeText(code)
                .then(() => {
                    button.textContent = 'تم النسخ!';
                    setTimeout(() => {
                        button.textContent = 'نسخ الكود';
                    }, 2000);
                });
        }
    </script>
    
    {% block extra_js %}{% endblock %}
</body>
</html>
'''

INDEX_TEMPLATE = '''
<div style="text-align: center; padding: 4rem 0;">
    <h1 style="font-size: 2.5rem; margin-bottom: 1.5rem;">مرحباً بك في OTH AI</h1>
    <p style="font-size: 1.25rem; margin-bottom: 2rem; color: var(--gray);">
        منصة الذكاء الاصطناعي المتقدم للدردشة الذكية وتحليل المحتوى
    </p>
    <div style="display: flex; justify-content: center; gap: 1rem;">
        <a href="/register" class="btn btn-primary" style="padding: 1rem 2rem;">ابدأ الآن</a>
        <a href="/login" class="btn" style="padding: 1rem 2rem;">تسجيل الدخول</a>
    </div>
</div>
'''

LOGIN_TEMPLATE = '''
<div style="max-width: 500px; margin: 0 auto; background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);">
    <h2 style="text-align: center; margin-bottom: 1.5rem;">تسجيل الدخول</h2>
    <form action="/login" method="POST">
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">البريد الإلكتروني</label>
            <input type="email" name="email" required style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">كلمة المرور</label>
            <input type="password" name="password" required style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <div style="margin-bottom: 1.5rem; display: flex; align-items: center;">
            <input type="checkbox" name="remember" id="remember" style="margin-left: 0.5rem;">
            <label for="remember">تذكرني</label>
        </div>
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.75rem;">تسجيل الدخول</button>
    </form>
    <div style="text-align: center; margin-top: 1.5rem;">
        ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
    </div>
</div>
'''

REGISTER_TEMPLATE = '''
<div style="max-width: 500px; margin: 0 auto; background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);">
    <h2 style="text-align: center; margin-bottom: 1.5rem;">إنشاء حساب جديد</h2>
    <form action="/register" method="POST">
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">الاسم الكامل</label>
            <input type="text" name="name" required minlength="3" style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">البريد الإلكتروني</label>
            <input type="email" name="email" required style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">كلمة المرور</label>
            <input type="password" name="password" required minlength="8" style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
            <small style="color: var(--gray);">يجب أن تكون 8 أحرف على الأقل</small>
        </div>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">تأكيد كلمة المرور</label>
            <input type="password" name="confirm_password" required style="width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.75rem;">إنشاء حساب</button>
    </form>
    <div style="text-align: center; margin-top: 1.5rem;">
        لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
    </div>
</div>
'''

DASHBOARD_TEMPLATE = '''
<div style="display: flex; min-height: calc(100vh - 120px);">
    <aside style="width: 250px; background: white; border-left: 1px solid #eee; padding: 1rem;">
        <div style="text-align: center; margin-bottom: 2rem;">
            <div style="width: 80px; height: 80px; background: var(--gray-light); border-radius: 50%; margin: 0 auto 1rem; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-user" style="font-size: 2rem; color: var(--gray);"></i>
            </div>
            <h3>{{ user_name }}</h3>
            <small style="color: var(--gray);">{{ user_email }}</small>
        </div>
        
        <nav>
            <ul style="list-style: none;">
                <li style="margin-bottom: 0.5rem;">
                    <a href="/dashboard" style="display: block; padding: 0.75rem; border-radius: 8px; text-decoration: none; color: var(--dark); background: var(--primary); color: white;">
                        <i class="fas fa-comments" style="margin-left: 0.5rem;"></i> الدردشة
                    </a>
                </li>
                <li style="margin-bottom: 0.5rem;">
                    <a href="/settings" style="display: block; padding: 0.75rem; border-radius: 8px; text-decoration: none; color: var(--dark);">
                        <i class="fas fa-cog" style="margin-left: 0.5rem;"></i> الإعدادات
                    </a>
                </li>
            </ul>
        </nav>
    </aside>
    
    <main style="flex: 1; padding: 2rem;">
        {% block dashboard_content %}{% endblock %}
    </main>
</div>
'''

CHAT_TEMPLATE = '''
<div style="display: flex; height: calc(100vh - 180px); background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);">
    <div style="flex: 1; display: flex; flex-direction: column;">
        <div id="chat-messages" style="flex: 1; padding: 1.5rem; overflow-y: auto;">
            {% for msg in conversation %}
                <div style="margin-bottom: 1.5rem; max-width: 80%; {% if msg.role == 'user' %}margin-left: auto; background-color: #f0f7ff;{% else %}margin-right: auto; background-color: #f8f9fa;{% endif %} padding: 1rem; border-radius: {% if msg.role == 'user' %}12px 12px 0 12px;{% else %}12px 12px 12px 0;{% endif %}">
                    <div style="line-height: 1.6;">
                        {{ msg.content|safe }}
                    </div>
                    <small style="color: #6c757d; display: block; text-align: {% if msg.role == 'user' %}left{% else %}right{% endif %}; margin-top: 0.5rem;">
                        {{ datetime.fromtimestamp(msg.timestamp).strftime('%Y-%m-%d %H:%M') }}
                    </small>
                </div>
            {% endfor %}
        </div>
        
        <div style="padding: 1rem; border-top: 1px solid #eee; display: flex; gap: 0.5rem;">
            <textarea id="message-input" placeholder="اكتب رسالتك هنا..." rows="2" style="flex: 1; padding: 1rem; border: 1px solid #ddd; border-radius: 8px; resize: none; min-height: 60px;"></textarea>
            <button id="send-btn" class="btn btn-primary" style="align-self: flex-end;">
                <i class="fas fa-paper-plane"></i>
            </button>
        </div>
    </div>
</div>

<script>
    document.addEventListener('DOMContentLoaded', function() {
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const chatMessages = document.getElementById('chat-messages');
        
        function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            
            // إضافة رسالة المستخدم إلى الواجهة
            const userMsgDiv = document.createElement('div');
            userMsgDiv.style.marginBottom = '1.5rem';
            userMsgDiv.style.maxWidth = '80%';
            userMsgDiv.style.marginLeft = 'auto';
            userMsgDiv.style.backgroundColor = '#f0f7ff';
            userMsgDiv.style.padding = '1rem';
            userMsgDiv.style.borderRadius = '12px 12px 0 12px';
            userMsgDiv.innerHTML = `
                <div style="line-height: 1.6;">${message}</div>
                <small style="color: #6c757d; display: block; text-align: left; margin-top: 0.5rem;">
                    ${new Date().toLocaleTimeString()}
                </small>
            `;
            chatMessages.appendChild(userMsgDiv);
            
            messageInput.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // إرسال الرسالة إلى الخادم
            fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    addMessage('حدث خطأ: ' + data.error, 'ai');
                } else {
                    addMessage(data.response, 'ai');
                }
            })
            .catch(error => {
                addMessage('حدث خطأ في الاتصال بالخادم', 'ai');
            });
        }
        
        function addMessage(content, role) {
            const msgDiv = document.createElement('div');
            msgDiv.style.marginBottom = '1.5rem';
            msgDiv.style.maxWidth = '80%';
            
            if (role === 'user') {
                msgDiv.style.marginLeft = 'auto';
                msgDiv.style.backgroundColor = '#f0f7ff';
                msgDiv.style.borderRadius = '12px 12px 0 12px';
            } else {
                msgDiv.style.marginRight = 'auto';
                msgDiv.style.backgroundColor = '#f8f9fa';
                msgDiv.style.borderRadius = '12px 12px 12px 0';
            }
            
            msgDiv.style.padding = '1rem';
            msgDiv.innerHTML = `
                <div style="line-height: 1.6;">${content}</div>
                <small style="color: #6c757d; display: block; text-align: ${role === 'user' ? 'left' : 'right'}; margin-top: 0.5rem;">
                    ${new Date().toLocaleTimeString()}
                </small>
            `;
            
            chatMessages.appendChild(msgDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        sendBtn.addEventListener('click', sendMessage);
    });
</script>
'''

SETTINGS_TEMPLATE = '''
<div style="background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);">
    <h2 style="margin-bottom: 1.5rem;">الإعدادات</h2>
    <form>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">الاسم</label>
            <input type="text" value="{{ user_name }}" style="width: 100%; max-width: 400px; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem;">البريد الإلكتروني</label>
            <input type="email" value="{{ user_email }}" style="width: 100%; max-width: 400px; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px;">
        </div>
        <button type="submit" class="btn btn-primary">حفظ التغييرات</button>
    </form>
</div>
'''

NOT_FOUND_TEMPLATE = '''
<div style="text-align: center; padding: 4rem 0;">
    <h1 style="font-size: 3rem; margin-bottom: 1rem;">404</h1>
    <p style="font-size: 1.25rem; margin-bottom: 2rem;">الصفحة التي تبحث عنها غير موجودة</p>
    <a href="/" class="btn btn-primary">العودة إلى الصفحة الرئيسية</a>
</div>
'''

# ==============================================
# مسارات الويب
# ==============================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember') == 'on'

        with db_lock:
            user = next((u for u in users_db.values() if u['email'] == email), None)
            if user and check_password(user['password'], password):
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['user_email'] = user['email']
                session.permanent = remember
                
                if user['id'] not in conversations_db:
                    save_conversation(user['id'], [{
                        'role': 'ai',
                        'content': 'مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟',
                        'timestamp': time.time()
                    }])
                
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if len(name) < 3:
            flash('الاسم يجب أن يكون 3 أحرف على الأقل', 'danger')
        elif len(password) < 8:
            flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'danger')
        elif password != confirm:
            flash('كلمتا المرور غير متطابقتين', 'danger')
        else:
            with db_lock:
                if any(u['email'] == email for u in users_db.values()):
                    flash('هذا البريد الإلكتروني مستخدم بالفعل', 'danger')
                else:
                    user_id = generate_user_id()
                    users_db[user_id] = {
                        'id': user_id,
                        'name': name,
                        'email': email,
                        'password': hash_password(password),
                        'created_at': time.time(),
                        'last_login': time.time()
                    }
                    
                    save_conversation(user_id, [{
                        'role': 'ai',
                        'content': 'مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟',
                        'timestamp': time.time()
                    }])
                    
                    flash('تم إنشاء الحساب بنجاح! يرجى تسجيل الدخول', 'success')
                    return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    conv = get_conversation(session['user_id'])
    return render_template('dashboard/index.html', 
                         user_name=session['user_name'],
                         user_email=session['user_email'],
                         conversation=conv['messages'])

@app.route('/chat')
@login_required
def chat():
    conv = get_conversation(session['user_id'])
    return render_template('dashboard/chat.html',
                         user_name=session['user_name'],
                         user_email=session['user_email'],
                         conversation=conv['messages'])

@app.route('/settings')
@login_required
def settings():
    return render_template('dashboard/settings.html',
                         user_name=session['user_name'],
                         user_email=session['user_email'])

@app.route('/api/chat', methods=['POST'])
@login_required
def chat_api():
    user_id = session['user_id']
    data = request.json
    message = data.get('message', '').strip()
    attachment = data.get('attachment')

    if not message and not attachment:
        return jsonify({'error': 'الرسالة لا يمكن أن تكون فارغة'}), 400

    conv = get_conversation(user_id)
    messages = conv['messages']

    user_msg = {
        'role': 'user',
        'content': message,
        'timestamp': time.time()
    }
    messages.append(user_msg)

    ai_response = None
    if attachment and attachment.get('type') == 'image':
        try:
            img_url = attachment['url']
            img_path = download_image(img_url)
            
            if img_path:
                img = genai.upload_file(img_path)
                response = model.generate_content(["حلل هذه الصورة بدقة:", img])
                ai_response = format_ai_response(response.text)
                
                if os.path.exists(img_path):
                    os.unlink(img_path)
        except Exception as e:
            logger.error(f"خطأ في معالجة الصورة: {str(e)}")
            ai_response = "⚠️ حدث خطأ أثناء معالجة الصورة"

    if not ai_response:
        try:
            context = "\n".join(
                f"{msg['role']}: {msg['content']}" 
                for msg in messages[-10:]
            )
            
            prompt = f"سياق المحادثة:\n{context}\n\nuser: {message}"
            response = model.generate_content(prompt)
            ai_response = format_ai_response(response.text)
        except Exception as e:
            logger.error(f"خطأ في نموذج الذكاء الاصطناعي: {str(e)}")
            ai_response = "⚠️ حدث خطأ أثناء معالجة طلبك"

    ai_msg = {
        'role': 'ai',
        'content': ai_response,
        'timestamp': time.time()
    }
    messages.append(ai_msg)

    save_conversation(user_id, messages)

    return jsonify({
        'response': ai_response,
        'conversation_id': user_id
    })

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# ==============================================
# تشغيل التطبيق
# ==============================================

if __name__ == '__main__':
    # بدء خيط تنظيف المحادثات القديمة
    cleaner = Thread(target=cleanup_old_conversations)
    cleaner.daemon = True
    cleaner.start()

    # إنشاء مستخدم افتراضي للاختبار
    with db_lock:
        if not users_db:
            user_id = generate_user_id()
            users_db[user_id] = {
                'id': user_id,
                'name': 'مستخدم تجريبي',
                'email': 'test@oth.ai',
                'password': hash_password('password123'),
                'created_at': time.time(),
                'last_login': time.time()
            }
            
            save_conversation(user_id, [{
                'role': 'ai',
                'content': 'مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟',
                'timestamp': time.time()
            }])

    app.run(debug=True)
