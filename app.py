from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import logging
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import asyncio
from concurrent.futures import ThreadPoolExecutor
import langid
import requests
import os
import tempfile
import urllib.request

app = Flask(__name__, static_folder='static')

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
SECRET_KEY = "oth2024"
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات
conversations = {}
executor = ThreadPoolExecutor(max_workers=20)

# قاعدة بيانات المستخدمين
users_db = {
    "admin": {
        "password": generate_password_hash("admin123"),
        "name": "Admin User"
    }
}

def detect_language(text):
    """تحديد لغة النص"""
    try:
        lang, _ = langid.classify(text)
        return lang
    except:
        return 'ar'

async def generate_response(prompt, context=None, lang='ar'):
    """إنشاء رد باستخدام Gemini"""
    try:
        if context:
            prompt = f"{context}\n\n{prompt}" if lang == 'en' else f"{context}\n\n{prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2000
            ))
        )
        return response.text
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return None

async def analyze_image(image_url, prompt, lang='ar'):
    """تحليل الصورة باستخدام Gemini"""
    try:
        # تحميل الصورة
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(image_url, headers=headers)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            image_path = tmp_file.name

        # تحليل الصورة
        img = genai.upload_file(image_path)
        
        if lang == 'ar':
            full_prompt = f"""
            بناءً على طلب المستخدم: {prompt}
            
            قم بتحليل هذه الصورة مع التركيز على:
            1. ما طلبه المستخدم بالتحديد
            2. التفاصيل المتعلقة بالطلب
            3. أي معلومات إضافية مفيدة
            
            أجب باللغة العربية
            """
        else:
            full_prompt = f"""
            Based on user request: {prompt}
            
            Analyze this image focusing on:
            1. Exactly what the user asked
            2. Relevant details
            3. Any additional useful information
            
            Answer in English
            """
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([full_prompt, img])
        )
        
        return response.text
    except Exception as e:
        logger.error(f"Image analysis error: {str(e)}")
        return None
    finally:
        if 'image_path' in locals() and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except:
                pass

def create_token(username):
    """إنشاء توكن JWT"""
    payload = {
        'sub': username,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=5)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    """التحقق من صحة التوكن"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload['sub']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return send_from_directory('static', 'index.html')

@app.route('/auth/login', methods=['POST'])
def login():
    """تسجيل الدخول"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"error": "يجب إدخال اسم المستخدم وكلمة المرور"}), 400
        
        user = users_db.get(username)
        if not user or not check_password_hash(user['password'], password):
            return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401
        
        token = create_token(username)
        return jsonify({
            "token": token,
            "username": username,
            "name": user['name']
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500

@app.route('/auth/register', methods=['POST'])
def register():
    """إنشاء حساب جديد"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"error": "يجب إدخال اسم المستخدم وكلمة المرور"}), 400
        
        if username in users_db:
            return jsonify({"error": "اسم المستخدم موجود بالفعل"}), 400
        
        users_db[username] = {
            'password': generate_password_hash(password),
            'name': username
        }
        
        token = create_token(username)
        return jsonify({
            "token": token,
            "username": username,
            "name": username
        }), 200
        
    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500

@app.route('/chat', methods=['GET'])
def chat():
    """الدردشة مع الذكاء الاصطناعي"""
    try:
        # التحقق من التوكن
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({"error": "التوكن مطلوب"}), 401
        
        token = token.split(' ')[1]
        username = verify_token(token)
        if not username:
            return jsonify({"error": "توكن غير صالح أو منتهي الصلاحية"}), 401
        
        # الحصول على النص
        text = request.args.get('text')
        if not text:
            return jsonify({"error": "النص مطلوب"}), 400
        
        # توليد الرد
        lang = detect_language(text)
        context = None
        
        if username in conversations:
            context = "\n".join(conversations[username]['history'][-5:])
        
        response = asyncio.run(generate_response(text, context, lang))
        if not response:
            return jsonify({"error": "حدث خطأ أثناء توليد الرد"}), 500
        
        # تحديث سجل المحادثة
        if username not in conversations:
            conversations[username] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang,
                'pending_image': None
            }
        
        conversations[username]['history'].append(f"User: {text}")
        conversations[username]['history'].append(f"Bot: {response}")
        
        # الحفاظ على آخر 20 رسالة كحد أقصى
        if len(conversations[username]['history']) > 20:
            conversations[username]['history'] = conversations[username]['history'][-20:]
        
        return jsonify({"response": response}), 200
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500

@app.route('/chat/image', methods=['POST'])
def chat_image():
    """معالجة الصور"""
    try:
        # التحقق من التوكن
        token = request.headers.get('Authorization')
        if not token or not token.startswith('Bearer '):
            return jsonify({"error": "التوكن مطلوب"}), 401
        
        token = token.split(' ')[1]
        username = verify_token(token)
        if not username:
            return jsonify({"error": "توكن غير صالح أو منتهي الصلاحية"}), 401
        
        if 'file' not in request.files:
            return jsonify({"error": "لم يتم توفير ملف"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "لم يتم اختيار ملف"}), 400
        
        # حفظ الملف مؤقتاً
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        file.save(temp_file.name)
        temp_file.close()
        
        # الحصول على وصف الصورة (إن وجد)
        prompt = request.form.get('prompt', 'وصف هذه الصورة' if detect_language('') == 'ar' else 'Describe this image')
        
        # تحليل الصورة
        analysis = asyncio.run(analyze_image(temp_file.name, prompt))
        
        # تنظيف الملف المؤقت
        try:
            os.unlink(temp_file.name)
        except:
            pass
        
        if not analysis:
            return jsonify({"error": "تعذر تحليل الصورة"}), 500
        
        # تحديث سجل المحادثة
        if username not in conversations:
            conversations[username] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': detect_language(prompt),
                'pending_image': None
            }
        
        conversations[username]['history'].append(f"User sent image with prompt: {prompt}")
        conversations[username]['history'].append(f"Image analysis: {analysis}")
        
        return jsonify({"response": analysis}), 200
        
    except Exception as e:
        logger.error(f"Image chat error: {str(e)}")
        return jsonify({"error": "حدث خطأ في معالجة الصورة"}), 500

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """ويب هوك فيسبوك"""
    if request.method == 'GET':
        # التحقق من التوكن
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        return "Verification failed", 403
    
    # معالجة الرسائل
    try:
        data = request.get_json()
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                if 'message' in event:
                    sender_id = event['sender']['id']
                    message = event['message']
                    
                    if 'text' in message:
                        asyncio.run(handle_facebook_message(sender_id, message['text']))
                    elif 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                asyncio.run(handle_facebook_image(sender_id, attachment['payload']['url']))
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"error": "حدث خطأ في معالجة الرسالة"}), 500

async def handle_facebook_message(sender_id, text):
    """معالجة رسالة فيسبوك"""
    try:
        lang = detect_language(text)
        
        # التحقق مما إذا كانت هناك صورة تنتظر وصفاً
        if sender_id in conversations and conversations[sender_id]['pending_image']:
            image_url = conversations[sender_id]['pending_image']
            conversations[sender_id]['pending_image'] = None
            
            await send_facebook_message(sender_id, "🔍 جاري تحليل الصورة..." if lang == 'ar' else "🔍 Analyzing image...")
            
            analysis = await analyze_image(image_url, text, lang)
            if analysis:
                await send_facebook_message(sender_id, analysis)
                
                # تحديث سجل المحادثة
                conversations[sender_id]['history'].append(f"User image analysis request: {text}")
                conversations[sender_id]['history'].append(f"Image analysis: {analysis}")
            else:
                await send_facebook_message(sender_id, "⚠️ تعذر تحليل الصورة" if lang == 'ar' else "⚠️ Failed to analyze image")
            
            return
        
        # معالجة الرسائل العادية
        context = None
        if sender_id in conversations:
            context = "\n".join(conversations[sender_id]['history'][-5:])
        
        response = await generate_response(text, context, lang)
        
        if not response:
            response = "حدث خطأ أثناء توليد الرد" if lang == 'ar' else "Error generating response"
        
        await send_facebook_message(sender_id, response)
        
        # تحديث سجل المحادثة
        if sender_id not in conversations:
            conversations[sender_id] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang,
                'pending_image': None
            }
        
        conversations[sender_id]['history'].append(f"User: {text}")
        conversations[sender_id]['history'].append(f"Bot: {response}")
        
    except Exception as e:
        logger.error(f"Facebook message error: {str(e)}")
        await send_facebook_message(sender_id, "حدث خطأ أثناء معالجة رسالتك")

async def handle_facebook_image(sender_id, image_url):
    """معالجة صورة من فيسبوك"""
    try:
        lang = 'ar'
        if sender_id in conversations:
            lang = conversations[sender_id]['lang']
        
        # طلب وصف الصورة من المستخدم
        await send_facebook_message(sender_id, "📸 لتحليل الصورة، الرجاء إرسال وصف لما تريد معرفته عنها:" if lang == 'ar' else "📸 To analyze the image, please describe what you want to know about it:")
        
        # تخزين معلومات الصورة مؤقتاً
        if sender_id not in conversations:
            conversations[sender_id] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang,
                'pending_image': image_url
            }
        else:
            conversations[sender_id]['pending_image'] = image_url
        
    except Exception as e:
        logger.error(f"Facebook image error: {str(e)}")
        await send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة الصورة" if lang == 'ar' else "⚠️ Error processing image")

async def send_facebook_message(recipient_id, message_text):
    """إرسال رسالة إلى فيسبوك"""
    try:
        url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
        }
        
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Facebook API error: {response.text}")
            
    except Exception as e:
        logger.error(f"Error sending to Facebook: {str(e)}")

if __name__ == '__main__':
    # إنشاء مجلد static إذا لم يكن موجوداً
    if not os.path.exists('static'):
        os.makedirs('static')
    
    # حفظ ملف HTML في مجلد static
    html_content = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دردشة الذكاء الاصطناعي</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        body {
            margin: 0;
            font-family: 'Tajawal', sans-serif;
            background-color: #1e1e2f;
            color: #e0e0e0;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: linear-gradient(45deg, #6a11cb, #2575fc);
            color: white;
            padding: 15px;
            text-align: center;
            font-size: 1.8em;
            font-weight: 700;
            border-radius: 0 0 20px 20px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            position: relative;
        }
        
        .menu-button {
            position: absolute;
            top: 5px;
            left: 10px;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            padding: 5px 20px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.5s ease;
        }
        
        .menu-button:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: scale(1.1);
        }
        
        .logout-button {
            position: absolute;
            top: 5px;
            right: 10px;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            padding: 5px 15px;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.3s ease;
        }
        
        .logout-button:hover {
            background: rgba(255, 0, 0, 0.2);
        }
        
        .overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 2;
        }
        
        .sidebar {
            display: none;
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #2a2a40;
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            z-index: 3;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            animation: slideIn 0.3s ease-in-out;
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translate(-50%, -60%);
            }
            to {
                opacity: 1;
                transform: translate(-50%, -50%);
            }
        }
        
        .sidebar button {
            background: linear-gradient(45deg, #6a11cb, #2575fc);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 12px;
            margin: 10px 0;
            cursor: pointer;
            width: 200px;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        
        .sidebar button:hover {
            transform: translateY(-3px);
            box-shadow: 0 4px 10px rgba(106, 17, 203, 0.5);
        }
        
        .sidebar button i {
            margin-left: 10px;
            font-size: 1.2em;
        }
        
        .chat-window {
            flex: 1;
            background: #25253d;
            margin: 10px;
            border-radius: 15px;
            overflow-y: auto;
            padding: 15px;
            display: flex;
            flex-direction: column;
            box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
        }
        
        .user-message, .bot-message {
            padding: 12px 16px;
            margin: 10px;
            border-radius: 15px;
            max-width: 70%;
            word-wrap: break-word;
            position: relative;
            animation: fadeIn 0.5s ease-in-out;
            display: inline-block;
        }
        
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .user-message {
            background: linear-gradient(45deg, #2575fc, #6a11cb);
            color: white;
            margin-left: auto;
            text-align: right;
            box-shadow: 0 4px 10px rgba(37, 117, 252, 0.3);
        }
        
        .bot-message {
            background: #3a3a5d;
            color: #e0e0e0;
            margin-right: auto;
            text-align: left;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
        }
        
        .input-area {
            display: flex;
            margin: 10px;
            border-radius: 15px;
            background: #2a2a40;
            padding: 10px;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
        }
        
        .input-area input {
            flex: 1;
            padding: 12px;
            border-radius: 12px;
            border: none;
            outline: none;
            background: #3a3a5d;
            color: #e0e0e0;
            font-size: 1em;
        }
        
        .input-area button {
            background: linear-gradient(45deg, #6a11cb, #2575fc);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 12px 20px;
            margin-right: 30px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        
        .input-area button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(106, 17, 203, 0.5);
        }
        
        .file-upload-button {
            background: linear-gradient(45deg, #6a11cb, #2575fc);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 12px 15px;
            margin-left: 10px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        
        .file-upload-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(106, 17, 203, 0.5);
        }
        
        .file-upload-input {
            display: none;
        }
        
        .typing-indicator {
            font-size: 1.5em;
            color: #6a11cb;
            margin: 10px;
        }
        
        .auth-container {
            display: none;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background: linear-gradient(45deg, #1e1e2f, #25253d);
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            z-index: 10;
        }
        
        .auth-form {
            background: #2a2a40;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
            width: 90%;
            max-width: 400px;
            text-align: center;
        }
        
        .auth-form h2 {
            color: white;
            margin-bottom: 20px;
        }
        
        .auth-form input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border-radius: 8px;
            border: none;
            background: #3a3a5d;
            color: white;
            font-size: 1em;
        }
        
        .auth-form button {
            width: 100%;
            padding: 12px;
            margin-top: 20px;
            background: linear-gradient(45deg, #6a11cb, #2575fc);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        
        .auth-form button:hover {
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(106, 17, 203, 0.4);
        }
        
        .switch-auth {
            margin-top: 15px;
            color: #aaa;
            cursor: pointer;
        }
        
        .switch-auth:hover {
            color: #fff;
            text-decoration: underline;
        }
        
        .error-message {
            color: #ff6b6b;
            margin-top: 10px;
            display: none;
        }
        
        .image-preview {
            max-width: 200px;
            max-height: 200px;
            margin: 10px;
            border-radius: 10px;
            display: none;
        }
    </style>
</head>
<body>
    <!-- واجهة الدردشة -->
    <div class="header">
        OTH-GPT
        <button class="menu-button" onclick="toggleMenu()">☰ </button>
        <button class="logout-button" onclick="logout()">تسجيل الخروج</button>
    </div>

    <div class="overlay" id="overlay" onclick="toggleMenu()"></div>

    <div class="sidebar" id="sidebar">
        <button onclick="window.open('https://youtube.com/@l7aj.1m?si=rCZmOnGPqoY6q8zY')"><i class="fab fa-youtube"></i> يوتيوب</button>
        <button onclick="window.open('https://www.instagram.com/mx.fo/profilecard/?igsh=NG9qbXJucHVlYjkz')"><i class="fab fa-instagram"></i> إنستجرام</button>
        <button onclick="window.open('https://t.me/l7l7aj')"><i class="fab fa-telegram"></i> تليجرام</button>
        <button onclick="window.open('https://t.me/OTH_GPT_WORM_bot')"><i class="fab fa-telegram"></i> بوت تليجرام</button>
        <button onclick="clearChat()">مسح الدردشة</button>
        <button class="close-button" onclick="toggleMenu()">إغلاق</button>
    </div>

    <div class="chat-window" id="chatWindow"></div>

    <div class="input-area">
        <input type="text" id="userInput" placeholder="⌨️ اكتب رسالتك..." onkeypress="handleKeyPress(event)">
        <button class="file-upload-button">
            <i class="fas fa-image"></i>
            <input type="file" id="fileUpload" class="file-upload-input" accept="image/*" onchange="handleImageUpload()">
        </button>
        <button onclick="sendMessage()">إرسال</button>
    </div>

    <img id="imagePreview" class="image-preview">

    <!-- صفحة تسجيل الدخول -->
    <div class="auth-container" id="authContainer">
        <div class="auth-form" id="loginForm">
            <h2>تسجيل الدخول</h2>
            <input type="text" id="loginUsername" placeholder="اسم المستخدم">
            <input type="password" id="loginPassword" placeholder="كلمة المرور">
            <button onclick="login()">تسجيل الدخول</button>
            <div class="switch-auth" onclick="showRegisterForm()">ليس لديك حساب؟ سجل الآن</div>
            <div class="error-message" id="loginError"></div>
        </div>

        <div class="auth-form" id="registerForm" style="display: none;">
            <h2>إنشاء حساب جديد</h2>
            <input type="text" id="registerUsername" placeholder="اسم المستخدم">
            <input type="password" id="registerPassword" placeholder="كلمة المرور">
            <input type="password" id="registerConfirmPassword" placeholder="تأكيد كلمة المرور">
            <button onclick="register()">إنشاء حساب</button>
            <div class="switch-auth" onclick="showLoginForm()">لديك حساب بالفعل؟ سجل الدخول</div>
            <div class="error-message" id="registerError"></div>
        </div>
    </div>

    <script>
        // متغيرات عامة
        let currentUser = null;
        let userToken = null;
        let pendingImage = null;
        const API_BASE_URL = window.location.origin;
        
        // عناصر DOM
        const chatWindow = document.getElementById("chatWindow");
        const authContainer = document.getElementById("authContainer");
        const loginForm = document.getElementById("loginForm");
        const registerForm = document.getElementById("registerForm");
        const loginError = document.getElementById("loginError");
        const registerError = document.getElementById("registerError");
        const imagePreview = document.getElementById("imagePreview");
        const fileUpload = document.getElementById("fileUpload");

        // عند تحميل الصفحة
        window.onload = function() {
            checkAuth();
        };

        function checkAuth() {
            const savedUser = localStorage.getItem('ai_chat_user');
            const savedToken = localStorage.getItem('ai_chat_token');
            
            if (savedUser && savedToken) {
                currentUser = savedUser;
                userToken = savedToken;
                showChatInterface();
            } else {
                showAuthContainer();
            }
        }

        function showChatInterface() {
            authContainer.style.display = 'none';
            loadChatHistory();
        }

        function showAuthContainer() {
            authContainer.style.display = 'flex';
            showLoginForm();
        }

        function showLoginForm() {
            loginForm.style.display = 'block';
            registerForm.style.display = 'none';
            loginError.style.display = 'none';
            document.getElementById("loginUsername").value = '';
            document.getElementById("loginPassword").value = '';
        }

        function showRegisterForm() {
            loginForm.style.display = 'none';
            registerForm.style.display = 'block';
            registerError.style.display = 'none';
            document.getElementById("registerUsername").value = '';
            document.getElementById("registerPassword").value = '';
            document.getElementById("registerConfirmPassword").value = '';
        }

        async function login() {
            const username = document.getElementById("loginUsername").value.trim();
            const password = document.getElementById("loginPassword").value.trim();
            
            if (!username || !password) {
                showError(loginError, "الرجاء إدخال اسم المستخدم وكلمة المرور");
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/auth/login`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: username,
                        password: password
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    currentUser = data.username;
                    userToken = data.token;
                    localStorage.setItem('ai_chat_user', data.username);
                    localStorage.setItem('ai_chat_token', data.token);
                    showChatInterface();
                } else {
                    showError(loginError, data.error || "حدث خطأ أثناء تسجيل الدخول");
                }
            } catch (error) {
                showError(loginError, "تعذر الاتصال بالخادم");
                console.error("Login error:", error);
            }
        }

        async function register() {
            const username = document.getElementById("registerUsername").value.trim();
            const password = document.getElementById("registerPassword").value.trim();
            const confirmPassword = document.getElementById("registerConfirmPassword").value.trim();
            
            if (!username || !password || !confirmPassword) {
                showError(registerError, "الرجاء ملء جميع الحقول");
                return;
            }
            
            if (password !== confirmPassword) {
                showError(registerError, "كلمة المرور غير متطابقة");
                return;
            }
            
            try {
                const response = await fetch(`${API_BASE_URL}/auth/register`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: username,
                        password: password
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    currentUser = data.username;
                    userToken = data.token;
                    localStorage.setItem('ai_chat_user', data.username);
                    localStorage.setItem('ai_chat_token', data.token);
                    showChatInterface();
                } else {
                    showError(registerError, data.error || "حدث خطأ أثناء إنشاء الحساب");
                }
            } catch (error) {
                showError(registerError, "تعذر الاتصال بالخادم");
                console.error("Register error:", error);
            }
        }

        function logout() {
            currentUser = null;
            userToken = null;
            pendingImage = null;
            localStorage.removeItem('ai_chat_user');
            localStorage.removeItem('ai_chat_token');
            showAuthContainer();
            clearChat();
        }

        function showError(element, message) {
            element.textContent = message;
            element.style.display = 'block';
        }

        function handleImageUpload() {
            const file = fileUpload.files[0];
            if (!file) return;
            
            if (!file.type.match('image.*')) {
                alert("الرجاء اختيار ملف صورة فقط");
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                imagePreview.src = e.target.result;
                imagePreview.style.display = 'block';
                pendingImage = file;
            };
            reader.readAsDataURL(file);
        }

        async function sendMessage() {
            const userInput = document.getElementById("userInput");
            const messageText = userInput.value.trim();
            
            // إذا كانت هناك صورة معلقة
            if (pendingImage) {
                await sendImageWithPrompt(messageText || "وصف هذه الصورة");
                userInput.value = "";
                return;
            }
            
            if (!messageText) return;
            
            addMessage(messageText, "user-message");
            userInput.value = "";
            
            addTypingIndicator();
            
            try {
                const response = await fetch(`${API_BASE_URL}/chat?text=${encodeURIComponent(messageText)}`, {
                    headers: {
                        'Authorization': `Bearer ${userToken}`,
                        'User-ID': currentUser
                    }
                });
                
                if (!response.ok) {
                    throw new Error(await response.text());
                }
                
                const data = await response.json();
                removeTypingIndicator();
                addMessage(data.response, "bot-message");
                saveChatHistory();
                
            } catch (error) {
                removeTypingIndicator();
                addMessage("تعذر جلب الرد من الخادم", "bot-message");
                console.error("Error sending message:", error);
            }
        }

        async function sendImageWithPrompt(prompt) {
            if (!pendingImage) return;
            
            const formData = new FormData();
            formData.append('file', pendingImage);
            formData.append('prompt', prompt);
            
            addMessage(`صورة: ${prompt}`, "user-message");
            imagePreview.style.display = 'none';
            pendingImage = null;
            fileUpload.value = "";
            
            addTypingIndicator();
            
            try {
                const response = await fetch(`${API_BASE_URL}/chat/image`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${userToken}`,
                        'User-ID': currentUser
                    },
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error(await response.text());
                }
                
                const data = await response.json();
                removeTypingIndicator();
                addMessage(data.response, "bot-message");
                saveChatHistory();
                
            } catch (error) {
                removeTypingIndicator();
                addMessage("تعذر تحليل الصورة", "bot-message");
                console.error("Error sending image:", error);
            }
        }

        function addMessage(text, className) {
            const messageDiv = document.createElement("div");
            messageDiv.className = className;
            messageDiv.textContent = text;
            chatWindow.appendChild(messageDiv);
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }

        function addTypingIndicator() {
            const typingDiv = document.createElement("div");
            typingDiv.className = "typing-indicator";
            typingDiv.textContent = "...";
            chatWindow.appendChild(typingDiv);
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }

        function removeTypingIndicator() {
            const typingDiv = document.querySelector(".typing-indicator");
            if (typingDiv) {
                typingDiv.remove();
            }
        }

        function clearChat() {
            chatWindow.innerHTML = "";
            if (currentUser) {
                localStorage.removeItem(`ai_chat_history_${currentUser}`);
            }
        }

        function saveChatHistory() {
            if (currentUser) {
                const messages = chatWindow.innerHTML;
                localStorage.setItem(`ai_chat_history_${currentUser}`, messages);
            }
        }

        function loadChatHistory() {
            if (currentUser) {
                const savedMessages = localStorage.getItem(`ai_chat_history_${currentUser}`);
                if (savedMessages) {
                    chatWindow.innerHTML = savedMessages;
                    chatWindow.scrollTop = chatWindow.scrollHeight;
                }
            }
        }

        function toggleMenu() {
            const overlay = document.getElementById("overlay");
            const sidebar = document.getElementById("sidebar");
            
            if (overlay.style.display === "block") {
                overlay.style.display = "none";
                sidebar.style.display = "none";
            } else {
                overlay.style.display = "block";
                sidebar.style.display = "block";
            }
        }

        function handleKeyPress(event) {
            if (event.key === "Enter") {
                sendMessage();
            }
        }
    </script>
</body>
</html>
    """
    
    with open('static/index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
