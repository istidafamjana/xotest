from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import os
import uuid
import json
import time
from datetime import datetime
from threading import Lock
import requests
import tempfile
import urllib.request
from PIL import Image
import io
import base64
import logging

# إعدادات السجل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-123'  # تغيير هذا في الإنتاج
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 5  # 5 ساعات

# التوكنات المضمنة مباشرة (للتطوير فقط)
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
FB_PAGE_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
FB_VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين البيانات
users = {}
conversations = {}
db_lock = Lock()

## ====== تصميم الموقع ======
BASE_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Gemini AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {{
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --dark: #1e293b;
            --light: #f8fafc;
        }}
        body {{
            font-family: 'Tajawal', sans-serif;
            background-color: var(--light);
            color: var(--dark);
            transition: all 0.3s;
        }}
        body.dark {{
            background-color: #0f172a;
            color: #e2e8f0;
        }}
        .gradient-bg {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .glow {{
            animation: glow 2s infinite alternate;
        }}
        @keyframes glow {{
            from {{
                box-shadow: 0 0 5px rgba(99, 102, 241, 0.5);
            }}
            to {{
                box-shadow: 0 0 20px rgba(99, 102, 241, 0.8);
            }}
        }}
        .message-user {{
            background: var(--primary);
            color: white;
            border-radius: 1rem 1rem 0 1rem;
        }}
        .message-bot {{
            background: #e2e8f0;
            color: var(--dark);
            border-radius: 1rem 1rem 1rem 0;
        }}
        .dark .message-bot {{
            background: #334155;
            color: #e2e8f0;
        }}
        .file-upload {{
            display: none;
        }}
        .file-upload-label {{
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem 1rem;
            background-color: #e2e8f0;
            border-radius: 0.5rem;
            margin-left: 0.5rem;
        }}
        .file-upload-label:hover {{
            background-color: #cbd5e1;
        }}
    </style>
</head>
<body class="{dark_mode}">
    <!-- إضاءات خلفية -->
    <div class="fixed -z-10 inset-0 overflow-hidden">
        <div class="absolute top-0 left-1/4 w-32 h-32 rounded-full bg-purple-500 opacity-20 blur-3xl"></div>
        <div class="absolute bottom-0 right-1/4 w-64 h-64 rounded-full bg-indigo-500 opacity-20 blur-3xl"></div>
    </div>

    <div class="min-h-screen flex flex-col">
        <nav class="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md border-b border-gray-200 dark:border-slate-700">
            <div class="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center">
                <a href="/" class="flex items-center space-x-2">
                    <div class="w-8 h-8 gradient-bg rounded-full flex items-center justify-center text-white font-bold">G</div>
                    <span class="text-xl font-bold bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent">Gemini AI</span>
                </a>
                <div class="flex items-center space-x-4">
                    <button id="theme-toggle" class="p-2 rounded-full hover:bg-gray-200 dark:hover:bg-slate-700">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-gray-700 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                    </button>
                    {auth_buttons}
                </div>
            </div>
        </nav>

        <main class="flex-grow max-w-6xl mx-auto px-4 py-8 w-full">
            {flashes}
            {content}
        </main>

        <footer class="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md border-t border-gray-200 dark:border-slate-700 py-4">
            <div class="max-w-6xl mx-auto px-4 text-center text-sm text-gray-600 dark:text-gray-400">
                © {year} Gemini AI. جميع الحقوق محفوظة.
            </div>
        </footer>
    </div>

    <script>
        // تبديل الوضع الليلي
        const themeToggle = document.getElementById('theme-toggle');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const currentTheme = localStorage.getItem('theme') || (prefersDark ? 'dark' : 'light');
        
        if (currentTheme === 'dark') document.body.classList.add('dark');
        
        themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('dark');
            const theme = document.body.classList.contains('dark') ? 'dark' : 'light';
            localStorage.setItem('theme', theme);
        });

        // تأثيرات الإضاءة للعناصر
        document.querySelectorAll('.glow-on-hover').forEach(el => {
            el.addEventListener('mouseenter', () => {
                el.classList.add('glow');
            });
            el.addEventListener('mouseleave', () => {
                el.classList.remove('glow');
            });
        });
    </script>
    {additional_js}
</body>
</html>
"""

CHAT_CONTENT = """
<div class="flex flex-col h-full">
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-2xl font-bold text-indigo-600 dark:text-indigo-400">محادثة Gemini</h1>
        <button id="new-chat" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm transition-all">
            محادثة جديدة
        </button>
    </div>
    
    <div id="chat-container" class="flex-grow space-y-4 mb-6 overflow-y-auto max-h-[70vh] p-2">
        {messages}
    </div>
    
    <div class="sticky bottom-0 bg-white/80 dark:bg-slate-800/80 backdrop-blur-md pt-4 pb-2">
        <form id="chat-form" class="flex space-x-2">
            <input 
                type="text" 
                id="message-input" 
                placeholder="اكتب رسالتك هنا..." 
                class="flex-grow px-4 py-3 rounded-lg border border-gray-300 dark:border-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white dark:bg-slate-800 text-gray-800 dark:text-gray-200"
                autocomplete="off"
            >
            <label for="file-upload" class="file-upload-label">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </label>
            <input type="file" id="file-upload" class="file-upload" accept="image/*">
            <button 
                type="submit" 
                class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all glow-on-hover"
            >
                إرسال
            </button>
        </form>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
            يدعم الموقع الدردشة النصية ومعالجة الصور
        </p>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatContainer = document.getElementById('chat-container');
    const newChatBtn = document.getElementById('new-chat');
    const fileUpload = document.getElementById('file-upload');
    
    // إرسال رسالة
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = messageInput.value.trim();
        const file = fileUpload.files[0];
        
        if (!message && !file) return;
        
        // إضافة رسالة المستخدم
        if (message) {
            addMessage('user', message);
        }
        
        if (file) {
            // معالجة الصورة
            const reader = new FileReader();
            reader.onload = async (e) => {
                addMessage('user', '[صورة مرفوعة]', e.target.result);
                
                try {
                    // إرسال الصورة إلى الخادم
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ 
                            message: message || 'حلل هذه الصورة',
                            image: e.target.result 
                        })
                    });
                    
                    const data = await response.json();
                    if (data.reply) {
                        addMessage('bot', data.reply);
                    } else {
                        throw new Error(data.error || 'حدث خطأ غير متوقع');
                    }
                } catch (error) {
                    addMessage('bot', 'عذرًا، حدث خطأ في معالجة الصورة.');
                    console.error('Error:', error);
                }
            };
            reader.readAsDataURL(file);
        } else {
            // إرسال نص فقط
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message })
                });
                
                const data = await response.json();
                if (data.reply) {
                    addMessage('bot', data.reply);
                } else {
                    throw new Error(data.error || 'حدث خطأ غير متوقع');
                }
            } catch (error) {
                addMessage('bot', 'عذرًا، حدث خطأ في معالجة طلبك.');
                console.error('Error:', error);
            }
        }
        
        messageInput.value = '';
        fileUpload.value = '';
    });
    
    // محادثة جديدة
    newChatBtn.addEventListener('click', () => {
        if (confirm('هل تريد بدء محادثة جديدة؟ سيتم مسح سجل المحادثة الحالي.')) {
            fetch('/api/new_chat', { method: 'POST' })
                .then(() => location.reload())
                .catch(err => console.error(err));
        }
    });
    
    // إضافة رسالة إلى الواجهة
    function addMessage(sender, text, image = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `flex ${sender === 'user' ? 'justify-end' : 'justify-start'}`;
        
        if (image) {
            messageDiv.innerHTML = `
                <div class="max-w-3/4 px-4 py-3 ${sender === 'user' ? 'message-user' : 'message-bot'}">
                    <img src="${image}" class="max-w-full h-auto rounded-lg mb-2" alt="الصورة المرفوعة">
                    ${text ? `<p>${text}</p>` : ''}
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="max-w-3/4 px-4 py-3 ${sender === 'user' ? 'message-user' : 'message-bot'}">
                    ${text.replace(/\n/g, '<br>')}
                </div>
            `;
        }
        
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
});
</script>
"""

## ====== مسارات الموقع ======
@app.route('/')
def home():
    dark_mode = 'dark' if request.cookies.get('theme') == 'dark' else ''
    
    auth_buttons = """
    <div class="flex space-x-2">
        <a href="/login" class="px-4 py-2 text-indigo-600 dark:text-indigo-400 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg transition-all">
            تسجيل الدخول
        </a>
        <a href="/register" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-all">
            إنشاء حساب
        </a>
    </div>
    """ if 'user_id' not in session else """
    <a href="/chat" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-all">
        الدردشة
    </a>
    """
    
    flashes = ''
    if '_flashes' in session:
        flashes = '<div class="mb-6 space-y-2">' + \
                  ''.join(f'<div class="px-4 py-3 rounded-lg bg-{cat}-100 text-{cat}-800 dark:bg-{cat}-900 dark:text-{cat}-200">{msg}</div>' 
                          for cat, msg in session['_flashes']) + \
                  '</div>'
        session.pop('_flashes')
    
    return render_template_string(
        BASE_HTML.format(
            title="الرئيسية",
            dark_mode=dark_mode,
            auth_buttons=auth_buttons,
            content=HOME_CONTENT,
            flashes=flashes,
            year=datetime.now().year,
            additional_js=""
        )
    )

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        flash('يجب تسجيل الدخول أولاً', 'danger')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    with db_lock:
        if user_id not in conversations:
            conversations[user_id] = []
        
        messages_html = '\n'.join(
            f'<div class="flex {"justify-end" if msg["sender"] == "user" else "justify-start"}">'
            f'<div class="max-w-3/4 px-4 py-3 {"message-user" if msg["sender"] == "user" else "message-bot'}">'
            f'{msg["text"].replace("\n", "<br>")}'
            f'</div></div>'
            for msg in conversations[user_id]
        )
    
    dark_mode = 'dark' if request.cookies.get('theme') == 'dark' else ''
    return render_template_string(
        BASE_HTML.format(
            title="الدردشة",
            dark_mode=dark_mode,
            auth_buttons='<a href="/logout" class="text-indigo-600 dark:text-indigo-400 hover:underline">تسجيل الخروج</a>',
            content=CHAT_CONTENT.format(messages=messages_html),
            flashes='',
            year=datetime.now().year,
            additional_js=""
        )
    )

@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مسموح'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    message = data.get('message', '').strip()
    image_data = data.get('image', None)
    
    if not message and not image_data:
        return jsonify({'error': 'الرسالة فارغة'}), 400
    
    with db_lock:
        if user_id not in conversations:
            conversations[user_id] = []
        
        if message:
            conversations[user_id].append({
                'sender': 'user',
                'text': message,
                'time': time.time()
            })
        
        try:
            # معالجة الصور إذا وجدت
            image_parts = []
            if image_data:
                img = Image.open(io.BytesIO(base64.b64decode(image_data.split(',')[1])))
                img = img.convert('RGB')
                img.thumbnail((800, 800))
                
                # تحويل الصورة إلى تنسيق مناسب لـ Gemini
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                image_parts.append({
                    'mime_type': 'image/jpeg',
                    'data': img_str
                })
            
            # إرسال الطلب إلى Gemini
            if image_parts:
                if message:
                    response = model.generate_content([message, *image_parts])
                else:
                    response = model.generate_content(image_parts)
            else:
                response = model.generate_content(message)
            
            reply = response.text
            
            conversations[user_id].append({
                'sender': 'bot',
                'text': reply,
                'time': time.time()
            })
            
            return jsonify({'reply': reply})
        except Exception as e:
            logger.error(f"Error in chat API: {str(e)}")
            return jsonify({'error': 'حدث خطأ في معالجة طلبك'}), 500

## ====== دعم فيسبوك مع معالجة الصور ======
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == FB_VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if event.get('message'):
                    message = event['message']
                    
                    # معالجة الصور من فيسبوك
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                send_facebook_message(sender_id, "⏳ جاري تحليل الصورة...")
                                
                                try:
                                    # تحميل الصورة
                                    headers = {'User-Agent': 'Mozilla/5.0'}
                                    req = urllib.request.Request(image_url, headers=headers)
                                    with urllib.request.urlopen(req) as response:
                                        img = Image.open(io.BytesIO(response.read()))
                                    
                                    # معالجة الصورة
                                    img = img.convert('RGB')
                                    img.thumbnail((800, 800))
                                    
                                    # تحويل الصورة إلى تنسيق مناسب لـ Gemini
                                    buffered = io.BytesIO()
                                    img.save(buffered, format="JPEG")
                                    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
                                    
                                    # تحليل الصورة باستخدام Gemini
                                    response = model.generate_content({
                                        'mime_type': 'image/jpeg',
                                        'data': img_str
                                    })
                                    
                                    reply = f"📸 تحليل الصورة:\n\n{response.text}"
                                    send_facebook_message(sender_id, reply)
                                except Exception as e:
                                    logger.error(f"Error analyzing Facebook image: {str(e)}")
                                    send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء تحليل الصورة")
                                return jsonify({'status': 'ok'}), 200
                    
                    # معالجة الرسائل النصية
                    if 'text' in message:
                        text = message['text'].strip()
                        handle_facebook_message(sender_id, text)
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({'status': 'ok'}), 200

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={FB_PAGE_TOKEN}"
    profile_data = {
        "get_started": {"payload": "GET_STARTED"},
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت Gemini AI الذكي! يمكنك إرسال النصوص أو الصور وسأساعدك في تحليلها."
            }
        ],
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "مساعدة",
                        "payload": "HELP"
                    }
                ]
            }
        ]
    }
    try:
        response = requests.post(url, json=profile_data)
        response.raise_for_status()
        logger.info("تم إعداد صفحة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد صفحة الماسنجر: {str(e)}")

def send_facebook_message(recipient_id, message):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={FB_PAGE_TOKEN}"
    message_data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message}
    }
    try:
        response = requests.post(url, json=message_data)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال رسالة فيسبوك: {str(e)}")
        return False

def handle_facebook_message(sender_id, message):
    with db_lock:
        if sender_id not in conversations:
            conversations[sender_id] = []
        
        conversations[sender_id].append({
            'sender': 'user',
            'text': message,
            'time': time.time()
        })
        
        try:
            response = model.generate_content(message)
            reply = response.text
            
            conversations[sender_id].append({
                'sender': 'bot',
                'text': reply,
                'time': time.time()
            })
            
            send_facebook_message(sender_id, reply)
        except Exception as e:
            logger.error(f"Error handling FB message: {str(e)}")
            send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة رسالتك")

## ====== مسارات إضافية ======
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with db_lock:
            user = users.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                flash('تم تسجيل الدخول بنجاح!', 'success')
                return redirect(url_for('chat'))
            else:
                flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'danger')
    
    dark_mode = 'dark' if request.cookies.get('theme') == 'dark' else ''
    return render_template_string(
        BASE_HTML.format(
            title="تسجيل الدخول",
            dark_mode=dark_mode,
            auth_buttons='',
            content=LOGIN_CONTENT,
            flashes='',
            year=datetime.now().year,
            additional_js=""
        )
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if len(username) < 4:
            flash('اسم المستخدم يجب أن يكون 4 أحرف على الأقل', 'danger')
        elif len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        elif username in users:
            flash('اسم المستخدم موجود بالفعل', 'danger')
        else:
            user_id = str(uuid.uuid4())
            users[username] = {
                'id': user_id,
                'username': username,
                'password': generate_password_hash(password),
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            session['user_id'] = user_id
            session['username'] = username
            flash('تم إنشاء الحساب بنجاح!', 'success')
            return redirect(url_for('chat'))
    
    dark_mode = 'dark' if request.cookies.get('theme') == 'dark' else ''
    return render_template_string(
        BASE_HTML.format(
            title="إنشاء حساب",
            dark_mode=dark_mode,
            auth_buttons='',
            content=REGISTER_CONTENT,
            flashes='',
            year=datetime.now().year,
            additional_js=""
        )
    )

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('home'))

@app.route('/api/new_chat', methods=['POST'])
def new_chat():
    if 'user_id' not in session:
        return jsonify({'error': 'غير مسموح'}), 401
    
    user_id = session['user_id']
    with db_lock:
        conversations[user_id] = []
    
    return jsonify({'status': 'success'})

## ====== تشغيل التطبيق ======
if __name__ == '__main__':
    app.run(debug=True)
