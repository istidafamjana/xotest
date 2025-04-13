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

app = Flask(__name__)
app.secret_key = 'your-secret-key-123'  # تغيير هذا في الإنتاج
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 5  # 5 ساعات

# التوكنات المضمنة مباشرة (للتطوير فقط)
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
FB_PAGE_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
FB_VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

# تهيئة نموذج Gemini 1.5 Flash
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

HOME_CONTENT = """
<div class="flex flex-col items-center justify-center py-12 text-center">
    <h1 class="text-4xl md:text-5xl font-bold mb-6 bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent">
        ذكاء اصطناعي متقدم للجميع
    </h1>
    <p class="text-lg text-gray-600 dark:text-gray-400 mb-8 max-w-2xl">
        تجربة محادثة ذكية وسريعة باستخدام Gemini 1.5 Flash
    </p>
    <div class="flex space-x-4">
        <a href="/chat" class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all glow-on-hover">
            ابدأ المحادثة الآن
        </a>
        {% if 'user_id' not in session %}
        <a href="/login" class="px-6 py-3 border border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 rounded-lg font-medium transition-all">
            تسجيل الدخول
        </a>
        {% endif %}
    </div>
</div>

<div class="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8">
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">محادثة فائقة السرعة</h3>
        <p class="text-gray-600 dark:text-gray-400">
            باستخدام Gemini 1.5 Flash للحصول على إجابات فورية
        </p>
    </div>
    
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">وضع ليلي مريح</h3>
        <p class="text-gray-600 dark:text-gray-400">
            تجربة تصفح مريحة للعين في جميع الأوقات
        </p>
    </div>
    
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">متعدد المنصات</h3>
        <p class="text-gray-600 dark:text-gray-400">
            تواصل عبر الموقع أو عبر مسنجر فيسبوك
        </p>
    </div>
</div>
"""

LOGIN_CONTENT = """
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h3 class="mb-0">تسجيل الدخول</h3>
            </div>
            <div class="card-body">
                <form method="POST" action="/login">
                    <div class="mb-3">
                        <label for="username" class="form-label">اسم المستخدم</label>
                        <input type="text" class="form-control" id="username" name="username" required>
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label">كلمة المرور</label>
                        <input type="password" class="form-control" id="password" name="password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-sign-in-alt"></i> تسجيل الدخول
                    </button>
                </form>
                <div class="mt-3 text-center">
                    <p>ليس لديك حساب؟ <a href="/register">سجل الآن</a></p>
                </div>
            </div>
        </div>
    </div>
</div>
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
            <button 
                type="submit" 
                class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all glow-on-hover"
            >
                إرسال
            </button>
        </form>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
            يدعم الموقع الدردشة عبر الويب وفيسبوك مسنجر
        </p>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatContainer = document.getElementById('chat-container');
    const newChatBtn = document.getElementById('new-chat');
    
    // إرسال رسالة
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = messageInput.value.trim();
        if (!message) return;
        
        // إضافة رسالة المستخدم
        addMessage('user', message);
        messageInput.value = '';
        
        try {
            // إرسال إلى الخادم
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
            addMessage('bot', 'عذرًا، حدث خطأ في معالجة طلبك. يرجى المحاولة لاحقًا.');
            console.error('Error:', error);
        }
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
    function addMessage(sender, text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `flex ${sender === 'user' ? 'justify-end' : 'justify-start'}`;
        
        messageDiv.innerHTML = `
            <div class="max-w-3/4 px-4 py-3 ${sender === 'user' ? 'message-user' : 'message-bot'}">
                ${text.replace(/\n/g, '<br>')}
            </div>
        `;
        
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
            f'<div class="max-w-3/4 px-4 py-3 {"message-user" if msg["sender"] == "user" else "message-bot"}">'
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
    
    if not message:
        return jsonify({'error': 'الرسالة فارغة'}), 400
    
    with db_lock:
        if user_id not in conversations:
            conversations[user_id] = []
        
        conversations[user_id].append({
            'sender': 'user',
            'text': message,
            'time': time.time()
        })
        
        try:
            # استخدام Gemini 1.5 Flash
            response = model.generate_content(message)
            reply = response.text
            
            conversations[user_id].append({
                'sender': 'bot',
                'text': reply,
                'time': time.time()
            })
            
            return jsonify({'reply': reply})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

## ====== دعم فيسبوك مسنجر ======
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # التحقق من التوكن
        if request.args.get('hub.verify_token') == FB_VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    # معالجة رسائل فيسبوك
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if event.get('message'):
                    message = event['message'].get('text', '')
                    if message:
                        handle_facebook_message(sender_id, message)
                
                elif event.get('postback'):
                    payload = event['postback']['payload']
                    if payload == 'GET_STARTED':
                        send_facebook_message(sender_id, "مرحبًا بك في بوت Gemini AI! اكتب رسالتك وسأساعدك.")
    except Exception as e:
        print(f"Error in webhook: {str(e)}")
    
    return jsonify({'status': 'ok'}), 200

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={FB_PAGE_TOKEN}"
    profile_data = {
        "get_started": {"payload": "GET_STARTED"},
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت Gemini AI الذكي!"
            }
        ]
    }
    try:
        response = requests.post(url, json=profile_data)
        response.raise_for_status()
        print("تم إعداد صفحة الماسنجر بنجاح")
    except Exception as e:
        print(f"خطأ في إعداد صفحة الماسنجر: {str(e)}")

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
        print(f"خطأ في إرسال رسالة فيسبوك: {str(e)}")
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
            # استخدام Gemini 1.5 Flash
            response = model.generate_content(message)
            reply = response.text
            
            conversations[sender_id].append({
                'sender': 'bot',
                'text': reply,
                'time': time.time()
            })
            
            send_facebook_message(sender_id, reply)
        except Exception as e:
            send_facebook_message(sender_id, "عذرًا، حدث خطأ في معالجة رسالتك.")
            print(f"Error handling FB message: {str(e)}")

## ====== تشغيل التطبيق ======
if __name__ == '__main__':
    app.run(debug=True)
