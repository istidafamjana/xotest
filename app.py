from flask import Flask, request, jsonify
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

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
SECRET_KEY = "your_very_secret_key_here_change_this"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
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
                'expiry': datetime.now() + timedelta(hours=5)
            }
        
        conversations[username]['history'].append(f"User: {text}")
        conversations[username]['history'].append(f"Bot: {response}")
        
        return jsonify({"response": response}), 200
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({"error": "حدث خطأ في الخادم"}), 500

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
        response = await generate_response(text, None, lang)
        
        if not response:
            response = "حدث خطأ أثناء توليد الرد"
        
        await send_facebook_message(sender_id, response)
        
    except Exception as e:
        logger.error(f"Facebook message error: {str(e)}")
        await send_facebook_message(sender_id, "حدث خطأ أثناء معالجة رسالتك")

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
    app.run(debug=True)
