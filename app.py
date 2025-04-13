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
import mimetypes
import json

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
import google.generativeai as genai
from PIL import Image
import io
import base64

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-oth-ia-advanced-v2')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('templates/auth', exist_ok=True)
os.makedirs('templates/admin', exist_ok=True)
os.makedirs('templates/errors', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('static/images', exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('OTH_IA_V2')

# Configuration
PAGE_ACCESS_TOKEN = os.environ.get('PAGE_ACCESS_TOKEN', 'EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD')
VERIFY_TOKEN = os.environ.get('VERIFY_TOKEN', 'd51ee4e3183dbbd9a27b7d2c1af8c655')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU')

# Initialize Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

# Data storage
conversations = {}
users = {}
user_settings = {}
notifications = {}
CONVERSATION_TIMEOUT = 24 * 60 * 60  # 24 hours in seconds
data_lock = Lock()

# Helper functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not users.get(session['username'], {}).get('is_admin', False):
            flash('Access denied. Admin only', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_response(text):
    if "```" in text:
        parts = text.split("```")
        formatted = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                lang = part.split('\n')[0].strip() if '\n' in part else ''
                code_content = part[len(lang):] if lang else part
                formatted.append(f'<div class="code-block"><pre><code class="{lang}">{code_content}</code></pre><button class="copy-btn" onclick="copyCode(this)">Copy Code</button></div>')
            else:
                formatted.append(part.replace("\n", "<br>"))
        return "".join(formatted)
    return text.replace("\n", "<br>")

def generate_avatar(name):
    colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8']
    color = colors[hash(name) % len(colors)]
    initials = ''.join([part[0].upper() for part in name.split()[:2]])
    if len(initials) < 2:
        initials = name[:2].upper()
    
    svg = f'''
    <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" rx="50" fill="{color}"/>
        <text x="50" y="60" font-family="Arial" font-size="40" fill="white" text-anchor="middle" dominant-baseline="middle">{initials}</text>
    </svg>
    '''
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"

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
                        "title": "🌐 Open Web",
                        "url": "https://your-app.vercel.app/chat",
                        "webview_height_ratio": "full",
                        "messenger_extensions": True
                    },
                    {
                        "type": "postback",
                        "title": "🆘 Help",
                        "payload": "HELP_CMD"
                    },
                    {
                        "type": "postback",
                        "title": "⚙️ Settings",
                        "payload": "SETTINGS_CMD"
                    },
                    {
                        "type": "postback",
                        "title": "🚪 Logout",
                        "payload": "LOGOUT_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://your-app.vercel.app"],
        "greeting": [
            {
                "locale": "default",
                "text": "Welcome to OTH IA! 💎\n\nI can help with any questions, analyze images and files."
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("Messenger profile setup successfully")
    except Exception as e:
        logger.error(f"Error setting up messenger profile: {str(e)}")

def download_file(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (OTH IA File Downloader)'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get('Content-Type', '')
            file_size = int(response.headers.get('Content-Length', 0))
            
            if file_size > app.config['MAX_CONTENT_LENGTH']:
                raise ValueError("File size exceeds limit")
                
            ext = mimetypes.guess_extension(content_type.split(';')[0]) or '.bin'
            filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            with open(filepath, 'wb') as f:
                f.write(response.read())
                
            return filepath, content_type
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return None, None

def analyze_file(filepath, content_type, context=None):
    try:
        if content_type.startswith('image/'):
            img = genai.upload_file(filepath)
            prompt = "Analyze this image in detail and provide a comprehensive description:"
            if context:
                prompt = f"Conversation context:\n{context}\n{prompt}"
            response = model.generate_content([prompt, img])
            return format_response(response.text)
        
        elif content_type == 'application/pdf':
            file = genai.upload_file(filepath)
            prompt = "Analyze this PDF file and summarize its contents:"
            if context:
                prompt = f"Conversation context:\n{context}\n{prompt}"
            response = model.generate_content([prompt, file])
            return format_response(response.text)
        
        elif content_type.startswith('text/'):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            prompt = "Analyze this text file and summarize its content:"
            if context:
                prompt = f"Conversation context:\n{context}\n{prompt}"
            response = model.generate_content([prompt, content])
            return format_response(response.text)
        
        else:
            return "⚠️ File type not supported for direct analysis."
            
    except Exception as e:
        logger.error(f"Error analyzing file: {str(e)}")
        return None
    finally:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)

def send_message(recipient_id, message_text, buttons=None, quick_replies=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    message_payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE"
    }
    
    if quick_replies:
        message_payload["message"] = {
            "text": message_text,
            "quick_replies": quick_replies
        }
    elif buttons:
        message_payload["message"] = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": message_text,
                    "buttons": buttons
                }
            }
        }
    else:
        message_payload["message"] = {"text": message_text}
    
    try:
        response = requests.post(url, json=message_payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return False

def handle_command(sender_id, user_id, command):
    if command == "GET_STARTED":
        welcome_msg = """
        Welcome to OTH IA! 💎

        I can help with:
        - Answering questions intelligently
        - Analyzing images and files
        - Assisting with programming
        - Explaining complex concepts

        Send your question or image now!
        """
        send_message(sender_id, welcome_msg, quick_replies=[
            {"content_type": "text", "title": "🆘 Help", "payload": "HELP_CMD"},
            {"content_type": "text", "title": "📷 Analyze Image", "payload": "UPLOAD_IMAGE"},
            {"content_type": "text", "title": "💬 New Chat", "payload": "NEW_CHAT"}
        ])
        
    elif command == "HELP_CMD":
        help_msg = """
        🆘 Help Center:

        • Ask any question
        • Send images/files for analysis
        • Use these commands:
        
        /new - Start new chat
        /help - Show this help
        /settings - Show settings
        """
        send_message(sender_id, help_msg)
        
    elif command == "SETTINGS_CMD":
        settings_msg = "⚙️ Chat Settings:\n\nAdjust your settings on our website"
        send_message(sender_id, settings_msg, buttons=[
            {
                "type": "web_url",
                "title": "Open Settings",
                "url": "https://your-app.vercel.app/settings",
                "webview_height_ratio": "full",
                "messenger_extensions": True
            }
        ])
        
    elif command == "LOGOUT_CMD":
        with data_lock:
            if user_id in conversations:
                del conversations[user_id]
        send_message(sender_id, "Logged out successfully. Come back anytime!")

def cleanup_old_conversations():
    current_time = time.time()
    with data_lock:
        for user_id in list(conversations.keys()):
            if current_time - conversations[user_id]["last_active"] > CONVERSATION_TIMEOUT:
                del conversations[user_id]
                logger.info(f"Cleaned up conversation for user {user_id}")

def add_notification(user_id, message, notification_type="info"):
    with data_lock:
        if user_id not in notifications:
            notifications[user_id] = []
        
        notifications[user_id].append({
            "id": str(uuid.uuid4()),
            "message": message,
            "type": notification_type,
            "timestamp": time.time(),
            "read": False
        })

def mark_notifications_read(user_id):
    with data_lock:
        if user_id in notifications:
            for note in notifications[user_id]:
                note['read'] = True

# Routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    features = [
        {"icon": "robot", "title": "Advanced AI", "desc": "Smart conversations with latest AI models"},
        {"icon": "code", "title": "Code Analysis", "desc": "Understand and analyze programming code"},
        {"icon": "image", "title": "Image Analysis", "desc": "Describe and analyze image content"},
        {"icon": "file-pdf", "title": "Document Analysis", "desc": "Read and summarize PDFs and texts"},
        {"icon": "mobile", "title": "Multi-platform", "desc": "Works on web and mobile apps"},
        {"icon": "shield", "title": "Secure & Private", "desc": "Your data is always protected"}
    ]
    
    return render_template('home.html', features=features)

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    username = session['username']
    
    cleanup_old_conversations()
    
    with data_lock:
        user_conversation = conversations.get(user_id, {})
        unread_notifications = sum(1 for note in notifications.get(user_id, []) if not note['read'])
    
    return render_template('dashboard.html',
                         username=username,
                         avatar=generate_avatar(username),
                         unread_notifications=unread_notifications,
                         last_active=datetime.fromtimestamp(user_conversation.get('last_active', time.time())) if user_conversation else None)

@app.route('/chat', methods=['GET', 'POST'])
@login_required
def chat():
    user_id = session['user_id']
    username = session['username']
    
    if request.method == 'POST':
        if 'file' in request.files:
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
                
                with data_lock:
                    context = "\n".join(conversations[user_id]["history"][-5:]) if user_id in conversations else None
                    conversations[user_id]["last_active"] = time.time()
                    conversations[user_id]["history"].append(f"User: Sent file {filename}")
                
                analysis = analyze_file(filepath, content_type, context)
                
                if analysis:
                    with data_lock:
                        conversations[user_id]["history"].append(f"Bot: {analysis[:500]}...")
                    return jsonify({"success": True, "reply": analysis})
                else:
                    return jsonify({"success": False, "error": "Failed to analyze file"})
        
        message = request.form.get('message', '').strip()
        if message:
            with data_lock:
                if user_id not in conversations:
                    conversations[user_id] = {
                        "history": ["New conversation started"],
                        "last_active": time.time()
                    }
                
                conversations[user_id]["last_active"] = time.time()
                conversations[user_id]["history"].append(f"User: {message}")
                
                context = "\n".join(conversations[user_id]["history"][-5:])
                prompt = f"{context}\n\nQuestion: {message}" if context else message
                
                try:
                    response = model.generate_content(prompt)
                    reply = format_response(response.text)
                    
                    conversations[user_id]["history"].append(f"Bot: {reply}")
                    
                    return jsonify({"success": True, "reply": reply})
                except Exception as e:
                    logger.error(f"AI model error: {str(e)}")
                    return jsonify({"success": False, "error": "Processing error"})
    
    with data_lock:
        conversation_history = conversations.get(user_id, {}).get("history", [])
    
    return render_template('chat.html',
                         username=username,
                         avatar=generate_avatar(username),
                         conversation_history=conversation_history)

@app.route('/new-chat', methods=['POST'])
@login_required
def new_chat():
    user_id = session['user_id']
    
    with data_lock:
        conversations[user_id] = {
            "history": ["New conversation started"],
            "last_active": time.time()
        }
    
    return jsonify({"success": True, "message": "Started new chat"})

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings_page():
    user_id = session['user_id']
    username = session['username']
    
    if request.method == 'POST':
        theme = request.form.get('theme', 'light')
        language = request.form.get('language', 'en')
        notifications_enabled = request.form.get('notifications', 'off') == 'on'
        
        with data_lock:
            if user_id not in user_settings:
                user_settings[user_id] = {}
            
            user_settings[user_id].update({
                'theme': theme,
                'language': language,
                'notifications': notifications_enabled,
                'updated_at': time.time()
            })
        
        flash('Settings updated successfully', 'success')
        return redirect(url_for('user_settings_page'))
    
    with data_lock:
        settings = user_settings.get(user_id, {
            'theme': 'light',
            'language': 'en',
            'notifications': True
        })
    
    return render_template('settings.html',
                         username=username,
                         avatar=generate_avatar(username),
                         settings=settings)

@app.route('/notifications')
@login_required
def user_notifications():
    user_id = session['user_id']
    
    with data_lock:
        user_notes = notifications.get(user_id, [])
        mark_notifications_read(user_id)
    
    return render_template('notifications.html',
                         username=username,
                         avatar=generate_avatar(username),
                         notifications=user_notes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        with data_lock:
            user = users.get(username)
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = username
                session['session_id'] = str(uuid.uuid4())
                session.permanent = True
                
                if user['id'] not in conversations:
                    conversations[user['id']] = {
                        "history": ["New conversation started"],
                        "last_active": time.time()
                    }
                else:
                    conversations[user['id']]["last_active"] = time.time()
                
                add_notification(user['id'], "Welcome back! How can we help you today?", "welcome")
                
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if len(username) < 4:
            flash('Username must be at least 4 characters', 'danger')
        elif len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
        elif password != confirm_password:
            flash('Passwords do not match', 'danger')
        else:
            with data_lock:
                if username in users:
                    flash('Username already exists', 'danger')
                else:
                    user_id = str(uuid.uuid4())
                    users[username] = {
                        'id': user_id,
                        'username': username,
                        'email': email,
                        'password': generate_password_hash(password),
                        'created_at': time.time(),
                        'is_admin': False,
                        'verified': False
                    }
                    
                    conversations[user_id] = {
                        "history": ["New conversation started"],
                        "last_active": time.time()
                    }
                    
                    add_notification(user_id, "Welcome to OTH IA! You can start asking questions now.", "welcome")
                    
                    flash('Account created successfully! Please login', 'success')
                    return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    user_id = session.get('user_id')
    with data_lock:
        if user_id in conversations:
            del conversations[user_id]
    
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    with data_lock:
        stats = {
            'total_users': len(users),
            'active_conversations': len(conversations),
            'notifications': sum(len(v) for v in notifications.values())
        }
        recent_users = sorted(users.values(), key=lambda x: x.get('created_at', 0), reverse=True)[:10]
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_users=recent_users)

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                user_id = hashlib.sha256(sender_id.encode()).hexdigest()
                current_time = time.time()
                
                cleanup_old_conversations()
                
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                if 'message' in event:
                    message = event['message']
                    
                    with data_lock:
                        if user_id not in conversations:
                            conversations[user_id] = {
                                "history": ["New conversation started"],
                                "last_active": current_time
                            }
                            handle_command(sender_id, user_id, "GET_STARTED")
                        
                        conversations[user_id]["last_active"] = current_time
                        
                        if 'attachments' in message:
                            for attachment in message['attachments']:
                                if attachment['type'] == 'image':
                                    send_message(sender_id, "⏳ Analyzing image...")
                                    image_url = attachment['payload']['url']
                                    image_path, content_type = download_file(image_url)
                                    
                                    if image_path:
                                        context = "\n".join(conversations[user_id]["history"][-5:])
                                        analysis = analyze_file(image_path, content_type, context)
                                        
                                        if analysis:
                                            conversations[user_id]["history"].append(f"Image: {analysis[:200]}...")
                                            send_message(sender_id, f"📸 Image Analysis:\n\n{analysis}")
                                        else:
                                            send_message(sender_id, "⚠️ Failed to analyze image")
                                elif attachment['type'] == 'file':
                                    send_message(sender_id, "⏳ Analyzing file...")
                                    file_url = attachment['payload']['url']
                                    file_path, content_type = download_file(file_url)
                                    
                                    if file_path:
                                        context = "\n".join(conversations[user_id]["history"][-5:])
                                        analysis = analyze_file(file_path, content_type, context)
                                        
                                        if analysis:
                                            conversations[user_id]["history"].append(f"File: {analysis[:200]}...")
                                            send_message(sender_id, f"📄 File Analysis:\n\n{analysis}")
                                        else:
                                            send_message(sender_id, "⚠️ Failed to analyze file")
                            continue
                        
                        if 'text' in message:
                            user_message = message['text'].strip()
                            
                            if user_message.lower() in ['help', '/help']:
                                handle_command(sender_id, user_id, "HELP_CMD")
                            elif user_message.lower() in ['new', '/new']:
                                conversations[user_id] = {
                                    "history": ["New conversation started"],
                                    "last_active": current_time
                                }
                                send_message(sender_id, "Started new chat. How can I help?")
                            elif user_message.lower() in ['settings', '/settings']:
                                handle_command(sender_id, user_id, "SETTINGS_CMD")
                            else:
                                try:
                                    context = "\n".join(conversations[user_id]["history"][-5:])
                                    prompt = f"{context}\n\nQuestion: {user_message}" if context else user_message
                                    
                                    response = model.generate_content(prompt)
                                    reply = response.text
                                    
                                    conversations[user_id]["history"].append(f"User: {user_message}")
                                    conversations[user_id]["history"].append(f"Bot: {reply}")
                                    
                                    send_message(sender_id, reply)
                                except Exception as e:
                                    logger.error(f"AI model error: {str(e)}")
                                    send_message(sender_id, "⚠️ Processing error, please try again")
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(e):
    return render_template('errors/500.html'), 500

# Background tasks
def periodic_tasks():
    while True:
        time.sleep(3600)
        cleanup_old_conversations()
        logger.info("Performed periodic cleanup")

# Vercel requirement
@app.route('/favicon.ico')
def favicon():
    return '', 204

if __name__ == '__main__':
    # Start background tasks
    Thread(target=periodic_tasks, daemon=True).start()
    
    # Setup messenger profile
    setup_messenger_profile()
    
    # Run the app
    app.run(threaded=True)
