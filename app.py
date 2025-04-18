from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging
import jwt
import os
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import tempfile
import urllib.request
import asyncio
from concurrent.futures import ThreadPoolExecutor
import langid

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
SECRET_KEY = "your_very_secret_key_here"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات (تخزين آخر 20 رسالة لكل مستخدم)
conversations = {}
executor = ThreadPoolExecutor(max_workers=20)

# قاعدة بيانات المستخدمين (في بيئة حقيقية استخدم قاعدة بيانات حقيقية)
users = {
    "admin": {
        "password": generate_password_hash("admin123"),
        "name": "Admin User"
    },
    "user1": {
        "password": generate_password_hash("password1"),
        "name": "User One"
    }
}

def detect_language(text):
    """تحديد لغة النص"""
    try:
        lang, _ = langid.classify(text)
        return lang
    except:
        return 'ar'

async def download_image(url):
    """تحميل الصورة من الرابط المؤقت"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            return tmp_file.name
    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
        return None

async def analyze_image_with_prompt(image_path, user_prompt, lang='ar'):
    """تحليل الصورة بناءً على وصف المستخدم"""
    try:
        img = genai.upload_file(image_path)
        
        if lang == 'ar':
            prompt = f"""
            بناءً على طلب المستخدم: {user_prompt}
            
            قم بتحليل هذه الصورة مع التركيز على:
            1. ما طلبه المستخدم بالتحديد
            2. التفاصيل المتعلقة بالطلب
            3. أي معلومات إضافية مفيدة
            """
        else:
            prompt = f"""
            Based on user request: {user_prompt}
            
            Analyze this image focusing on:
            1. Exactly what the user asked
            2. Relevant details
            3. Any additional useful information
            """
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([prompt, img], generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=3000
            ))
        )
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except:
                pass

async def generate_response_async(prompt, context=None, lang='ar'):
    """إنشاء رد باستخدام السياق"""
    try:
        if context:
            if lang == 'ar':
                prompt = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {prompt}"
            else:
                prompt = f"Previous context:\n{context}\n\nNew question: {prompt}"
        
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

@app.route('/auth', methods=['POST'])
def authenticate():
    """نقطة نهاية المصادقة"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "اسم المستخدم وكلمة المرور مطلوبان"}), 400
    
    user = users.get(username)
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"error": "اسم المستخدم أو كلمة المرور غير صحيحة"}), 401
    
    token = create_token(username)
    return jsonify({"token": token, "username": username, "name": user['name']})

@app.route('/chat', methods=['GET'])
def chat():
    """نقطة نهاية الدردشة النصية"""
    token = request.headers.get('Authorization')
    user_id = request.headers.get('User-ID')
    
    if not token or not token.startswith('Bearer '):
        return jsonify({"error": "التوكن مطلوب"}), 401
    
    token = token.split(' ')[1]
    username = verify_token(token)
    
    if not username or username != user_id:
        return jsonify({"error": "توكن غير صالح أو منتهي الصلاحية"}), 401
    
    text = request.args.get('text', '')
    if not text:
        return jsonify({"error": "النص مطلوب"}), 400
    
    # تنظيف المحادثات القديمة
    now = datetime.now()
    if username in conversations and conversations[username]['expiry'] < now:
        del conversations[username]
    
    # تحديد اللغة
    lang = detect_language(text)
    
    # معالجة الأسئلة العادية مع السياق
    context = None
    if username in conversations and conversations[username]['history']:
        context = "\n".join(conversations[username]['history'][-10:])  # استخدام آخر 10 رسائل كسياق
    
    response = asyncio.run(generate_response_async(text, context, lang))
    if not response:
        return jsonify({"error": "حدث خطأ أثناء توليد الرد"}), 500
    
    # تحديث سجل المحادثة
    if username not in conversations:
        conversations[username] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'lang': lang
        }
    
    conversations[username]['history'].append(f"User: {text}")
    conversations[username]['history'].append(f"Bot: {response}")
    
    # الحفاظ على آخر 20 رسالة كحد أقصى
    if len(conversations[username]['history']) > 20:
        conversations[username]['history'] = conversations[username]['history'][-20:]
    
    return jsonify({"response": response})

@app.route('/chat/img', methods=['POST'])
def chat_image():
    """نقطة نهاية معالجة الصور"""
    token = request.headers.get('Authorization')
    user_id = request.headers.get('User-ID')
    
    if not token or not token.startswith('Bearer '):
        return jsonify({"error": "التوكن مطلوب"}), 401
    
    token = token.split(' ')[1]
    username = verify_token(token)
    
    if not username or username != user_id:
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
    
    # تحليل الصورة
    prompt = request.form.get('prompt', 'وصف هذه الصورة')
    lang = detect_language(prompt) if prompt else 'ar'
    
    analysis = asyncio.run(analyze_image_with_prompt(temp_file.name, prompt, lang))
    
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
            'lang': lang
        }
    
    conversations[username]['history'].append(f"User image analysis request: {prompt}")
    conversations[username]['history'].append(f"Image analysis: {analysis}")
    
    # الحفاظ على آخر 20 رسالة كحد أقصى
    if len(conversations[username]['history']) > 20:
        conversations[username]['history'] = conversations[username]['history'][-20:]
    
    return jsonify({"response": analysis})

@app.route('/chat/file', methods=['POST'])
def chat_file():
    """نقطة نهاية معالجة الملفات"""
    token = request.headers.get('Authorization')
    user_id = request.headers.get('User-ID')
    
    if not token or not token.startswith('Bearer '):
        return jsonify({"error": "التوكن مطلوب"}), 401
    
    token = token.split(' ')[1]
    username = verify_token(token)
    
    if not username or username != user_id:
        return jsonify({"error": "توكن غير صالح أو منتهي الصلاحية"}), 401
    
    if 'file' not in request.files:
        return jsonify({"error": "لم يتم توفير ملف"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "لم يتم اختيار ملف"}), 400
    
    # هنا يمكنك معالجة الملف حسب نوعه
    # في هذا المثال سنقوم فقط بإرجاع معلومات عن الملف
    file_info = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(file.read())
    }
    
    # في تطبيق حقيقي، يمكنك تحليل محتوى الملف هنا
    response_text = f"تم استلام الملف: {file_info['filename']} (حجم: {file_info['size']} بايت)"
    
    # تحديث سجل المحادثة
    if username not in conversations:
        conversations[username] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'lang': 'ar'
        }
    
    conversations[username]['history'].append(f"User uploaded file: {file_info['filename']}")
    conversations[username]['history'].append(f"Bot response: {response_text}")
    
    return jsonify({"response": response_text})

if __name__ == '__main__':
    app.run(threaded=True)
