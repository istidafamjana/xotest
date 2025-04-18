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
import tempfile
import urllib.request

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
SECRET_KEY = os.getenv('SECRET_KEY', 'your_very_strong_secret_key_here')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your_gemini_api_key')
PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN', 'your_facebook_page_token')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', 'your_facebook_verify_token')

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
            """
        else:
            full_prompt = f"""
            Based on user request: {prompt}
            
            Analyze this image focusing on:
            1. Exactly what the user asked
            2. Relevant details
            3. Any additional useful information
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
    app.run(debug=True)
