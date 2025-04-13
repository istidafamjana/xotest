# app.py
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import os
import uuid
import json
import time
from datetime import datetime
from threading import Lock
import random
import re

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 5  # 5 ساعات

# تهيئة نموذج Gemini
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-pro')

# تخزين البيانات (مؤقت - للتنمية فقط)
users = {}
conversations = {}
db_lock = Lock()

# ===== تصميم الموقع =====
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
        .neon-text {{
            text-shadow: 0 0 5px rgba(99, 102, 241, 0.8);
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
        تجربة محادثة ذكية وسريعة باستخدام أحدث تقنيات الذكاء الاصطناعي من جوجل
    </p>
    <div class="flex space-x-4">
        <a href="/chat" class="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all glow-on-hover">
            ابدأ المحادثة الآن
        </a>
        <a href="/about" class="px-6 py-3 border border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400 hover:bg-indigo-50 dark:hover:bg-slate-700 rounded-lg font-medium transition-all">
            تعرف أكثر
        </a>
    </div>
</div>

<div class="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8">
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">محادثة ذكية</h3>
        <p class="text-gray-600 dark:text-gray-400">
            تفاعل طبيعي مع ذكاء اصطناعي يفهم السياق ويتعلم من كل محادثة
        </p>
    </div>
    
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">وضع ليلي</h3>
        <p class="text-gray-600 dark:text-gray-400">
            تجربة مريحة للعين في كل الأوقات مع ميزة الوضع الليلي التلقائي
        </p>
    </div>
    
    <div class="bg-white/80 dark:bg-slate-800/80 p-6 rounded-xl shadow-sm backdrop-blur-sm border border-gray-200 dark:border-slate-700">
        <div class="w-12 h-12 gradient-bg rounded-lg flex items-center justify-center text-white mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
        </div>
        <h3 class="text-xl font-semibold mb-2">آمن وسريع</h3>
        <p class="text-gray-600 dark:text-gray-400">
            تشفير متقدم وسرعة فائقة مع بنية تحتية موزعة عالميًا
        </p>
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
            Gemini قد يقدم معلومات غير دقيقة أحيانًا
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

# ===== مسارات التطبيق =====
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
            # استخدام آخر 5 رسائل كسياق
            context = "\n".join(
                f"{msg['sender']}: {msg['text']}" 
                for msg in conversations[user_id][-5:]
            )
            
            response = model.generate_content(f"{context}\n\nassistant:")
            reply = response.text
            
            conversations[user_id].append({
                'sender': 'bot',
                'text': reply,
                'time': time.time()
            })
            
            return jsonify({'reply': reply})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

# ===== تكوين Vercel =====
# ===== تشغيل التطبيق =====
if __name__ == '__main__':
    app.run(debug=True)
