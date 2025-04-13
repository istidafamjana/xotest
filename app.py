import os
import uuid
import hashlib
import logging
import tempfile
import urllib.request
from datetime import datetime, timedelta
from threading import Lock
from flask import Flask, request, jsonify, redirect, url_for, session, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
import google.generativeai as genai
from PIL import Image
import io
import base64
import mimetypes

# تهيئة التطبيق
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-' + str(uuid.uuid4()))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'mp3', 'mp4', 'webp'}

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين البيانات
users = {}
conversations = {}
user_settings = {}
files_storage = {}
data_lock = Lock()

# ==============================================
# أنماط وتصميم الموقع (مستوحى من DeepSeek مع تحسينات)
# ==============================================

APP_STYLES = """
:root {
    --primary: #7C4DFF;
    --primary-dark: #5E35B1;
    --primary-light: #B388FF;
    --secondary: #FF4081;
    --dark: #263238;
    --light: #f5f7fa;
    --gray: #607D8B;
    --success: #4CAF50;
    --warning: #FFC107;
    --danger: #F44336;
    --code-bg: #282c34;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, sans-serif;
}

body {
    background-color: var(--light);
    color: var(--dark);
    line-height: 1.6;
}

a {
    text-decoration: none;
    color: var(--primary);
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 20px;
}

/* الشريط العلوي */
.navbar {
    background-color: white;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    padding: 15px 0;
    position: sticky;
    top: 0;
    z-index: 100;
}

.nav-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--primary);
    display: flex;
    align-items: center;
    gap: 10px;
}

.logo-icon {
    color: var(--secondary);
}

.nav-links {
    display: flex;
    gap: 20px;
    align-items: center;
}

.btn {
    display: inline-block;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.3s ease;
    text-align: center;
}

.btn-primary {
    background-color: var(--primary);
    color: white;
}

.btn-primary:hover {
    background-color: var(--primary-dark);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(124, 77, 255, 0.2);
}

.btn-outline {
    border: 1px solid var(--primary);
    color: var(--primary);
    background: transparent;
}

.btn-outline:hover {
    background-color: rgba(124, 77, 255, 0.1);
}

/* الصفحة الرئيسية */
.hero {
    padding: 80px 0;
    text-align: center;
    background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
}

.hero h1 {
    font-size: 3.5rem;
    margin-bottom: 20px;
    background: linear-gradient(90deg, var(--primary), var(--secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero p {
    font-size: 1.2rem;
    color: var(--gray);
    max-width: 700px;
    margin: 0 auto 40px;
}

.features {
    padding: 80px 0;
}

.features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 30px;
    margin-top: 40px;
}

.feature-card {
    background: white;
    border-radius: 12px;
    padding: 30px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.05);
    transition: all 0.3s ease;
}

.feature-card:hover {
    transform: translateY(-10px);
    box-shadow: 0 15px 30px rgba(0,0,0,0.1);
}

.feature-icon {
    font-size: 2.5rem;
    margin-bottom: 20px;
    color: var(--primary);
}

.feature-card h3 {
    margin-bottom: 15px;
    font-size: 1.3rem;
}

/* واجهة الدردشة */
.chat-container {
    display: grid;
    grid-template-columns: 300px 1fr;
    height: calc(100vh - 80px);
}

.sidebar {
    background: white;
    border-right: 1px solid #eee;
    padding: 20px;
    overflow-y: auto;
}

.chat-main {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.chat-header {
    padding: 20px;
    border-bottom: 1px solid #eee;
    background: white;
    display: flex;
    align-items: center;
    gap: 15px;
}

.chat-messages {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
    background-color: #f9f9f9;
}

.message {
    margin-bottom: 20px;
    max-width: 80%;
}

.user-message {
    margin-left: auto;
    background: var(--primary);
    color: white;
    padding: 15px;
    border-radius: 18px 18px 0 18px;
}

.bot-message {
    margin-right: auto;
    background: white;
    padding: 15px;
    border-radius: 18px 18px 18px 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.chat-input-container {
    padding: 20px;
    background: white;
    border-top: 1px solid #eee;
}

.chat-form {
    display: flex;
    gap: 10px;
}

#message-input {
    flex: 1;
    padding: 15px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 1rem;
}

#file-input {
    display: none;
}

.file-btn {
    padding: 15px;
    border: 1px dashed #ddd;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.3s ease;
}

.file-btn:hover {
    border-color: var(--primary);
    color: var(--primary);
}

.upload-preview {
    margin-top: 10px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.upload-item {
    position: relative;
    width: 100px;
    height: 100px;
    border-radius: 8px;
    overflow: hidden;
}

.upload-item img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.upload-item .remove-btn {
    position: absolute;
    top: 5px;
    right: 5px;
    background: var(--danger);
    color: white;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 12px;
}

/* كود البرمجة */
.code-block {
    background: var(--code-bg);
    border-radius: 8px;
    padding: 15px;
    margin: 15px 0;
    position: relative;
    overflow-x: auto;
}

.code-block pre {
    margin: 0;
    font-family: 'Courier New', Courier, monospace;
    color: #abb2bf;
    white-space: pre-wrap;
}

.copy-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: rgba(255,255,255,0.1);
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
    cursor: pointer;
    font-size: 12px;
    transition: all 0.3s ease;
}

.copy-btn:hover {
    background: rgba(255,255,255,0.2);
}

/* الصفحات الأخرى */
.auth-container {
    max-width: 500px;
    margin: 50px auto;
    padding: 40px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 5px 20px rgba(0,0,0,0.05);
}

.auth-title {
    text-align: center;
    margin-bottom: 30px;
    font-size: 1.8rem;
    color: var(--primary);
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 500;
}

.form-control {
    width: 100%;
    padding: 12px 15px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 1rem;
}

.form-control:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(124, 77, 255, 0.1);
}

.error-message {
    color: var(--danger);
    margin-top: 5px;
    font-size: 0.9rem;
}

/* التكيف مع الشاشات الصغيرة */
@media (max-width: 768px) {
    .chat-container {
        grid-template-columns: 1fr;
    }
    
    .sidebar {
        display: none;
    }
    
    .hero h1 {
        font-size: 2.5rem;
    }
}
"""

# ==============================================
# قوالب HTML
# ==============================================

def render_page(title, content, user=None):
    navbar = ""
    if user:
        navbar = f"""
        <div class="nav-links">
            <a href="/chat" class="btn btn-outline">الدردشة</a>
            <a href="/settings" class="btn btn-outline">الإعدادات</a>
            <a href="/logout" class="btn btn-primary">تسجيل الخروج</a>
        </div>
        """
    else:
        navbar = """
        <div class="nav-links">
            <a href="/login" class="btn btn-outline">تسجيل الدخول</a>
            <a href="/register" class="btn btn-primary">إنشاء حساب</a>
        </div>
        """
    
    return f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | OTH AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>{APP_STYLES}</style>
</head>
<body>
    <nav class="navbar">
        <div class="container nav-container">
            <a href="/" class="logo">
                <i class="fas fa-robot logo-icon"></i>
                <span>OTH AI</span>
            </a>
            {navbar}
        </div>
    </nav>
    
    {content}
    
    <script>
        // وظائف JavaScript العامة
        function copyCode(element) {{
            const code = element.parentElement.querySelector('pre').innerText;
            navigator.clipboard.writeText(code).then(() => {{
                element.textContent = 'تم النسخ!';
                setTimeout(() => {{
                    element.textContent = 'نسخ الكود';
                }}, 2000);
            }});
        }}
        
        // إدارة تحميل الملفات
        function handleFileUpload(event) {{
            const files = event.target.files;
            const previewContainer = document.getElementById('upload-preview');
            previewContainer.innerHTML = '';
            
            for (let i = 0; i < files.length; i++) {{
                const file = files[i];
                const reader = new FileReader();
                
                reader.onload = function(e) {{
                    const previewItem = document.createElement('div');
                    previewItem.className = 'upload-item';
                    
                    if (file.type.startsWith('image/')) {{
                        previewItem.innerHTML = `
                            <img src="${{e.target.result}}" alt="${{file.name}}">
                            <div class="remove-btn" onclick="this.parentElement.remove()">
                                <i class="fas fa-times"></i>
                            </div>
                        `;
                    }} else {{
                        previewItem.innerHTML = `
                            <div style="padding: 10px; text-align: center;">
                                <i class="fas fa-file" style="font-size: 2rem;"></i>
                                <p style="font-size: 0.8rem; margin-top: 5px;">${{file.name}}</p>
                                <div class="remove-btn" onclick="this.parentElement.parentElement.remove()">
                                    <i class="fas fa-times"></i>
                                </div>
                            </div>
                        `;
                    }}
                    
                    previewContainer.appendChild(previewItem);
                }};
                
                reader.readAsDataURL(file);
            }}
        }}
    </script>
</body>
</html>
    """

# الصفحة الرئيسية
HOME_PAGE = """
<section class="hero">
    <div class="container">
        <h1>منصة الذكاء الاصطناعي المتكاملة</h1>
        <p>تفاعل مع أحدث نماذج الذكاء الاصطناعي من جوجل، حلل الصور والملفات، واحصل على إجابات ذكية في مختلف المجالات</p>
        <div style="display: flex; gap: 15px; justify-content: center;">
            <a href="/register" class="btn btn-primary">ابدأ مجاناً</a>
            <a href="#features" class="btn btn-outline">المميزات</a>
        </div>
    </div>
</section>

<section class="features" id="features">
    <div class="container">
        <h2 style="text-align: center; margin-bottom: 20px; font-size: 2rem;">لماذا تختار OTH AI؟</h2>
        <p style="text-align: center; color: var(--gray); max-width: 700px; margin: 0 auto 40px;">
            منصة متكاملة تجمع بين أحدث تقنيات الذكاء الاصطناعي وسهولة الاستخدام
        </p>
        
        <div class="features-grid">
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-brain"></i>
                </div>
                <h3>ذكاء اصطناعي متقدم</h3>
                <p>تفاعل مع نموذج Gemini 1.5 Flash من جوجل، أحدث ما توصلت إليه تكنولوجيا الذكاء الاصطناعي</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-image"></i>
                </div>
                <h3>تحليل الصور والملفات</h3>
                <p>قم بتحميل الصور والملفات واحصل على تحليل مفصل لمحتوياتها باستخدام الذكاء الاصطناعي</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-code"></i>
                </div>
                <h3>تحليل الأكواد البرمجية</h3>
                <p>احصل على شرح وتحليل للأكواد البرمجية بجميع اللغات مع إمكانية نسخ النتائج بسهولة</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-comments"></i>
                </div>
                <h3>دردشة متعددة المنصات</h3>
                <p>تواصل مع البوت عبر الموقع أو عبر تطبيق فيسبوك ماسنجر بنفس الخصائص والمميزات</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-history"></i>
                </div>
                <h3>سجل المحادثات</h3>
                <p>احتفظ بسجل كامل لمحادثاتك ويمكنك الرجوع إليها في أي وقت</p>
            </div>
            
            <div class="feature-card">
                <div class="feature-icon">
                    <i class="fas fa-shield-alt"></i>
                </div>
                <h3>آمن وخاص</h3>
                <p>بياناتك محمية باستخدام أحدث تقنيات التشفير والحماية</p>
            </div>
        </div>
    </div>
</section>
"""

# صفحة الدردشة
CHAT_PAGE = """
<div class="chat-container">
    <div class="sidebar">
        <h3 style="margin-bottom: 20px;">المحادثات الحديثة</h3>
        <div id="conversation-list" style="display: flex; flex-direction: column; gap: 10px;">
            <!-- سيتم ملء قائمة المحادثات بواسطة JavaScript -->
        </div>
    </div>
    
    <div class="chat-main">
        <div class="chat-header">
            <div style="width: 40px; height: 40px; background: var(--primary); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-robot"></i>
            </div>
            <h3>مساعد OTH AI</h3>
        </div>
        
        <div class="chat-messages" id="chat-messages">
            <!-- سيتم ملء المحادثة بواسطة JavaScript -->
        </div>
        
        <div class="chat-input-container">
            <div class="upload-preview" id="upload-preview"></div>
            <form class="chat-form" id="chat-form">
                <label for="file-input" class="file-btn">
                    <i class="fas fa-paperclip"></i>
                </label>
                <input type="file" id="file-input" multiple style="display: none;" onchange="handleFileUpload(event)">
                <input type="text" id="message-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
                <button type="submit" class="btn btn-primary">إرسال</button>
            </form>
        </div>
    </div>
</div>

<script>
    // تحميل المحادثة عند بدء الصفحة
    document.addEventListener('DOMContentLoaded', function() {{
        loadConversation();
        setupEventListeners();
    }});
    
    // تحميل المحادثة
    function loadConversation() {{
        fetch('/api/conversation')
            .then(response => response.json())
            .then(data => {{
                if (data.history && data.history.length > 0) {{
                    data.history.forEach(item => {{
                        if (item.startsWith('User:')) {{
                            addMessage(item.replace('User:', '').trim(), true);
                        }} else if (item.startsWith('Bot:')) {{
                            addMessage(item.replace('Bot:', '').trim(), false);
                        }}
                    }});
                }} else {{
                    addMessage('مرحباً بك في OTH AI! كيف يمكنني مساعدتك اليوم؟', false);
                }}
            }});
    }}
    
    // إعداد مستمعي الأحداث
    function setupEventListeners() {{
        const chatForm = document.getElementById('chat-form');
        const messageInput = document.getElementById('message-input');
        const fileInput = document.getElementById('file-input');
        
        chatForm.addEventListener('submit', function(e) {{
            e.preventDefault();
            sendMessage();
        }});
        
        messageInput.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});
    }}
    
    // إرسال الرسالة
    function sendMessage() {{
        const messageInput = document.getElementById('message-input');
        const fileInput = document.getElementById('file-input');
        const message = messageInput.value.trim();
        const files = fileInput.files;
        
        if (!message && files.length === 0) return;
        
        // عرض رسالة المستخدم
        if (message) {{
            addMessage(message, true);
        }}
        
        // عرض معاينة الملفات
        if (files.length > 0) {{
            Array.from(files).forEach(file => {{
                addMessage(`تم تحميل الملف: ${{file.name}}`, true);
            }});
        }}
        
        // إرسال البيانات إلى الخادم
        const formData = new FormData();
        formData.append('message', message);
        
        for (let i = 0; i < files.length; i++) {{
            formData.append('files', files[i]);
        }}
        
        fetch('/chat', {{
            method: 'POST',
            body: formData
        }})
        .then(response => response.json())
        .then(data => {{
            if (data.error) {{
                addMessage('حدث خطأ: ' + data.error, false);
            }} else {{
                addMessage(data.response, false);
            }}
            
            // مسح حق الإدخال ومعاينة الملفات
            messageInput.value = '';
            fileInput.value = '';
            document.getElementById('upload-preview').innerHTML = '';
        }})
        .catch(error => {{
            addMessage('حدث خطأ في الاتصال بالخادم', false);
        }});
    }}
    
    // إضافة رسالة إلى الدردشة
    function addMessage(text, isUser) {{
        const chatMessages = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${{isUser ? 'user-message' : 'bot-message'}}`;
        
        // معالجة الكود البرمجي
        if (!isUser && text.includes('```')) {{
            const parts = text.split('```');
            let formattedText = '';
            
            for (let i = 0; i < parts.length; i++) {{
                if (i % 2 === 1) {{
                    // كود برمجي
                    const codeContent = parts[i].replace(/^[^\n]*\n/, ''); // إزالة لغة البرمجة إذا وجدت
                    formattedText += `
                        <div class="code-block">
                            <pre>${{codeContent}}</pre>
                            <button class="copy-btn" onclick="copyCode(this)">نسخ الكود</button>
                        </div>
                    `;
                }} else {{
                    // نص عادي
                    formattedText += parts[i].replace(/\n/g, '<br>');
                }}
            }}
            
            messageDiv.innerHTML = formattedText;
        }} else {{
            messageDiv.textContent = text;
        }}
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }}
</script>
"""

# ==============================================
# دوال المساعدة
# ==============================================

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file):
    try:
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return filepath
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")
        return None

def analyze_content(text=None, files=None):
    try:
        if files and len(files) > 0:
            # تحليل الملفات
            file = files[0]
            filepath = save_uploaded_file(file)
            
            if not filepath:
                return "حدث خطأ أثناء معالجة الملف"
            
            # تحديد نوع الملف
            content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
            
            if content_type.startswith('image/'):
                # تحليل الصور
                img = genai.upload_file(filepath)
                prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً:"
                if text:
                    prompt = f"بناء على طلب المستخدم: '{text}'\n{prompt}"
                
                response = model.generate_content([prompt, img])
                result = response.text
            elif content_type == 'application/pdf':
                # تحليل ملفات PDF
                file_content = genai.upload_file(filepath)
                prompt = "حلل هذا الملف وقدم ملخصاً لمحتواه:"
                if text:
                    prompt = f"بناء على طلب المستخدم: '{text}'\n{prompt}"
                
                response = model.generate_content([prompt, file_content])
                result = response.text
            else:
                # محاولة قراءة الملف النصي
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    prompt = "حلل هذا الملف النصي:"
                    if text:
                        prompt = f"بناء على طلب المستخدم: '{text}'\n{prompt}"
                    
                    response = model.generate_content([prompt, content])
                    result = response.text
                except:
                    result = "يمكنني تحليل الصور وملفات PDF والنصوص فقط"
            
            # حذف الملف بعد التحليل
            try:
                os.remove(filepath)
            except:
                pass
            
            return result
        else:
            # تحليل النص العادي
            response = model.generate_content(text)
            return response.text
    except Exception as e:
        logger.error(f"AI Error: {str(e)}")
        return "عذرًا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا."

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "web_url",
                        "title": "🌐 الانتقال للويب",
                        "url": "https://your-app.vercel.app/chat",
                        "webview_height_ratio": "full",
                        "messenger_extensions": True
                    },
                    {
                        "type": "postback",
                        "title": "🆘 المساعدة",
                        "payload": "HELP_CMD"
                    },
                    {
                        "type": "postback",
                        "title": "🚪 تسجيل الخروج",
                        "payload": "LOGOUT_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://your-app.vercel.app"],
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

def handle_messenger_command(sender_id, command):
    if command == "GET_STARTED":
        welcome_msg = """
        مرحباً بك في OTH AI! 💎
        
        يمكنك إرسال:
        - أي سؤال لتحصل على إجابة ذكية
        - صورة لتحليل محتواها
        - ملف PDF أو نصي لتحليله
        
        جرب الآن بإرسال سؤالك الأول!
        """
        send_messenger_message(sender_id, welcome_msg)
    elif command == "HELP_CMD":
        help_msg = """
        🆘 مركز المساعدة:
        
        • اكتب سؤالك مباشرة
        • أرسل صورة لتحليلها
        • أرسل ملف PDF أو نصي لتحليله
        • استخدم /new لبدء محادثة جديدة
        """
        send_messenger_message(sender_id, help_msg)
    elif command == "LOGOUT_CMD":
        send_messenger_message(sender_id, "تم تسجيل الخروج بنجاح. يمكنك العودة في أي وقت!")

# ==============================================
# مسارات التطبيق
# ==============================================

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_page("الرئيسية", HOME_PAGE)

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
    
    login_content = """
    <div class="auth-container">
        <h2 class="auth-title">تسجيل الدخول</h2>
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="username">اسم المستخدم</label>
                <input type="text" id="username" name="username" class="form-control" required>
            </div>
            <div class="form-group">
                <label for="password">كلمة المرور</label>
                <input type="password" id="password" name="password" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">تسجيل الدخول</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            ليس لديك حساب؟ <a href="/register">إنشاء حساب جديد</a>
        </div>
    </div>
    """
    
    if error:
        login_content = login_content.replace('</h2>', f'</h2><div class="error-message">{error}</div>')
    
    return render_page("تسجيل الدخول", login_content)

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
    
    register_content = """
    <div class="auth-container">
        <h2 class="auth-title">إنشاء حساب جديد</h2>
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
            <button type="submit" class="btn btn-primary" style="width: 100%;">إنشاء حساب</button>
        </form>
        <div style="text-align: center; margin-top: 20px;">
            لديك حساب بالفعل؟ <a href="/login">تسجيل الدخول</a>
        </div>
    </div>
    """
    
    if error:
        register_content = register_content.replace('</h2>', f'</h2><div class="error-message">{error}</div>')
    
    return render_page("إنشاء حساب", register_content)

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    if request.method == 'POST':
        user_id = session['user_id']
        message = request.form.get('message', '').strip()
        files = request.files.getlist('files')
        
        if not message and not files:
            return jsonify({"error": "الرجاء إدخال رسالة أو تحميل ملف"}), 400
        
        with data_lock:
            if user_id not in conversations:
                conversations[user_id] = {
                    "history": ["بدأ المستخدم محادثة جديدة"],
                    "last_active": datetime.now()
                }
            
            if message:
                conversations[user_id]["history"].append(f"User: {message}")
            
            if files:
                for file in files:
                    if file and allowed_file(file.filename):
                        conversations[user_id]["history"].append(f"User: أرسل ملف {file.filename}")
            
            conversations[user_id]["last_active"] = datetime.now()
            
            try:
                response = analyze_content(message, files)
                conversations[user_id]["history"].append(f"Bot: {response}")
                
                return jsonify({"response": response})
            except Exception as e:
                logger.error(f"Error in chat: {str(e)}")
                return jsonify({"error": "حدث خطأ أثناء معالجة طلبك"}), 500
    
    return render_page("الدردشة", CHAT_PAGE, user=session.get('username'))

@app.route('/api/conversation')
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
                    
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                send_messenger_message(sender_id, "⏳ جاري تحليل الصورة...")
                                image_url = attachment['payload']['url']
                                
                                try:
                                    headers = {'User-Agent': 'Mozilla/5.0'}
                                    req = urllib.request.Request(image_url, headers=headers)
                                    with urllib.request.urlopen(req) as response:
                                        img_data = response.read()
                                    
                                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                                        tmp_file.write(img_data)
                                        tmp_file_path = tmp_file.name
                                    
                                    img = genai.upload_file(tmp_file_path)
                                    prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً:"
                                    response = model.generate_content([prompt, img])
                                    send_messenger_message(sender_id, f"📸 تحليل الصورة:\n\n{response.text}")
                                    
                                    os.unlink(tmp_file_path)
                                except Exception as e:
                                    send_messenger_message(sender_id, "⚠️ تعذر تحليل الصورة")
                                    logger.error(f"Error analyzing image: {str(e)}")
                    
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        if user_message.lower() in ['مساعدة', 'help']:
                            handle_messenger_command(sender_id, "HELP_CMD")
                        elif user_message.lower() in ['/new', 'جديد']:
                            send_messenger_message(sender_id, "تم بدء محادثة جديدة. كيف يمكنني مساعدتك؟")
                        else:
                            response = analyze_content(user_message)
                            send_messenger_message(sender_id, response)
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    # إنشاء مستخدم مسؤول افتراضي إذا لم يكن موجوداً
    with data_lock:
        if "admin" not in users:
            users["admin"] = {
                "id": str(uuid.uuid4()),
                "username": "admin",
                "password": generate_password_hash("admin123"),
                "created_at": datetime.now()
            }
            conversations[users["admin"]["id"]] = {
                "history": ["بدأ المستخدم محادثة جديدة"],
                "last_active": datetime.now()
            }
    
    setup_messenger_profile()
    app.run()
