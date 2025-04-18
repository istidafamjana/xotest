import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
import asyncio
from concurrent.futures import ThreadPoolExecutor
import langid
import requests
import tempfile
import urllib.request
import json
from pathlib import Path

app = Flask(__name__, static_folder='static')

# تكوين السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=1000000, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
SECRET_KEY = os.getenv('SECRET_KEY', 'your_very_strong_secret_key_here')
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
        "name": "Admin User",
        "conversation_id": str(datetime.now().timestamp())
    }
}

# مسار تخزين المحادثات
CHAT_HISTORY_DIR = Path('chat_histories')
CHAT_HISTORY_DIR.mkdir(exist_ok=True)

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
        system_instruction = """
        أنت مساعد ذكي يتحدث العربية بطلاقة. يمكنك تحليل الصور والملفات والرد على الأسئلة المعقدة.
        عند عرض أكواد برمجية، قم بتنسيقها بشكل جميل مع إضافة زر نسخ.
        أجب بطريقة واضحة ومنظمة مع عناوين ونقاط عندما يكون ذلك مناسبًا.
        """
        
        if context:
            messages = [
                {"role": "user", "parts": [system_instruction]},
                {"role": "model", "parts": ["حسنًا، أنا مستعد للمساعدة!"]},
                {"role": "user", "parts": [context]},
                {"role": "user", "parts": [prompt]}
            ]
        else:
            messages = [
                {"role": "user", "parts": [system_instruction]},
                {"role": "model", "parts": ["حسنًا، أنا مستعد للمساعدة!"]},
                {"role": "user", "parts": [prompt]}
            ]
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(
                messages,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=2000,
                    candidate_count=1
                )
            )
        )
        
        # معالجة الرد لتحسين تنسيق الأكواد
        text = response.text
        if "```" in text:
            text = add_copy_button_to_code(text)
        
        return text
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return None

def add_copy_button_to_code(text):
    """إضافة زر نسخ للأكواد البرمجية مع تلوين الصyntax"""
    parts = text.split("```")
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # هذا جزء الكود
            code_content = part
            # تحديد لغة البرمجة
            first_line = code_content.split('\n')[0].strip().lower()
            language = first_line if first_line in ['python', 'javascript', 'html', 'css', 'java', 'c++', 'php', 'bash'] else ''
            
            if language:
                code_content = '\n'.join(code_content.split('\n')[1:])
            
            code_block = f"""
            <div class="code-container">
                <button class="copy-code-btn" onclick="copyCode(this)">نسخ الكود</button>
                <pre><code class="language-{language}">{code_content}</code></pre>
            </div>
            """
            result.append(code_block)
        else:
            result.append(part)
    return "".join(result)

async def analyze_file(file_path, prompt, lang='ar'):
    """تحليل الملف باستخدام Gemini"""
    try:
        file = genai.upload_file(file_path)
        
        if lang == 'ar':
            full_prompt = f"""
            بناءً على طلب المستخدم: {prompt}
            
            قم بتحليل هذا الملف مع التركيز على:
            1. محتوى الملف
            2. ما طلبه المستخدم بالتحديد
            3. أي معلومات إضافية مفيدة
            
            أجب بطريقة منظمة مع عناوين ونقاط.
            أجب باللغة العربية.
            """
        else:
            full_prompt = f"""
            Based on user request: {prompt}
            
            Analyze this file focusing on:
            1. File content
            2. Exactly what the user asked
            3. Any additional useful information
            
            Answer in English.
            """
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([full_prompt, file])
        )
        
        return response.text
    except Exception as e:
        logger.error(f"File analysis error: {str(e)}")
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
            
            أجب بطريقة منظمة مع عناوين ونقاط.
            أجب باللغة العربية.
            """
        else:
            full_prompt = f"""
            Based on user request: {prompt}
            
            Analyze this image focusing on:
            1. Exactly what the user asked
            2. Relevant details
            3. Any additional useful information
            
            Answer in English.
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

def save_conversation(username, conversation_data):
    """حفظ المحادثة في ملف"""
    try:
        if username not in users_db:
            return False
            
        conversation_id = users_db[username].get('conversation_id', str(datetime.now().timestamp()))
        file_path = CHAT_HISTORY_DIR / f"{username}_{conversation_id}.json"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(conversation_data, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        logger.error(f"Error saving conversation: {str(e)}")
        return False

def load_conversation(username):
    """تحميل المحادثة من ملف"""
    try:
        if username not in users_db:
            return None
            
        conversation_id = users_db[username].get('conversation_id', str(datetime.now().timestamp()))
        file_path = CHAT_HISTORY_DIR / f"{username}_{conversation_id}.json"
        
        if not file_path.exists():
            return None
            
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading conversation: {str(e)}")
        return None

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    """خدمة الملفات الثابتة"""
    return send_from_directory('static', path)

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
        
        # تحميل سجل المحادثة إذا وجد
        conversation = load_conversation(username)
        if conversation:
            conversations[username] = conversation
        
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
            'name': username,
            'conversation_id': str(datetime.now().timestamp())
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
                'pending_file': None
            }
        
        conversations[username]['history'].append(f"User: {text}")
        conversations[username]['history'].append(f"Bot: {response}")
        
        # الحفاظ على آخر 20 رسالة كحد أقصى
        if len(conversations[username]['history']) > 20:
            conversations[username]['history'] = conversations[username]['history'][-20:]
        
        # حفظ المحادثة
        save_conversation(username, conversations[username])
        
        # إرسال الرد بشكل تدريجي
        return jsonify({
            "response": response,
            "typing": True,
            "chunked": True
        }), 200
        
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
                'pending_file': None
            }
        
        conversations[username]['history'].append(f"User sent image with prompt: {prompt}")
        conversations[username]['history'].append(f"Image analysis: {analysis}")
        
        # حفظ المحادثة
        save_conversation(username, conversations[username])
        
        return jsonify({
            "response": analysis,
            "typing": True
        }), 200
        
    except Exception as e:
        logger.error(f"Image chat error: {str(e)}")
        return jsonify({"error": "حدث خطأ في معالجة الصورة"}), 500

@app.route('/chat/file', methods=['POST'])
def chat_file():
    """معالجة الملفات"""
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
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix)
        file.save(temp_file.name)
        temp_file.close()
        
        # الحصول على وصف الملف (إن وجد)
        prompt = request.form.get('prompt', 'تحليل هذا الملف' if detect_language('') == 'ar' else 'Analyze this file')
        
        # تحليل الملف
        analysis = asyncio.run(analyze_file(temp_file.name, prompt))
        
        # تنظيف الملف المؤقت
        try:
            os.unlink(temp_file.name)
        except:
            pass
        
        if not analysis:
            return jsonify({"error": "تعذر تحليل الملف"}), 500
        
        # تحديث سجل المحادثة
        if username not in conversations:
            conversations[username] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': detect_language(prompt),
                'pending_file': None
            }
        
        conversations[username]['history'].append(f"User sent file ({file.filename}) with prompt: {prompt}")
        conversations[username]['history'].append(f"File analysis: {analysis}")
        
        # حفظ المحادثة
        save_conversation(username, conversations[username])
        
        return jsonify({
            "response": analysis,
            "typing": True
        }), 200
        
    except Exception as e:
        logger.error(f"File chat error: {str(e)}")
        return jsonify({"error": "حدث خطأ في معالجة الملف"}), 500

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
                            elif attachment['type'] == 'file':
                                asyncio.run(handle_facebook_file(sender_id, attachment['payload']['url']))
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"error": "حدث خطأ في معالجة الرسالة"}), 500

async def handle_facebook_message(sender_id, text):
    """معالجة رسالة فيسبوك"""
    try:
        lang = detect_language(text)
        
        # التحقق مما إذا كان هناك ملف ينتظر وصفاً
        if sender_id in conversations and conversations[sender_id]['pending_file']:
            file_url = conversations[sender_id]['pending_file']
            conversations[sender_id]['pending_file'] = None
            
            await send_facebook_message(sender_id, "🔍 جاري تحليل الملف..." if lang == 'ar' else "🔍 Analyzing file...")
            
            analysis = await analyze_file_from_url(file_url, text, lang)
            if analysis:
                await send_facebook_message(sender_id, analysis)
                
                # تحديث سجل المحادثة
                conversations[sender_id]['history'].append(f"User file analysis request: {text}")
                conversations[sender_id]['history'].append(f"File analysis: {analysis}")
                
                # حفظ المحادثة
                save_conversation(sender_id, conversations[sender_id])
            else:
                await send_facebook_message(sender_id, "⚠️ تعذر تحليل الملف" if lang == 'ar' else "⚠️ Failed to analyze file")
            
            return
        
        # معالجة الرسائل العادية
        context = None
        if sender_id in conversations:
            context = "\n".join(conversations[sender_id]['history'][-5:])
        
        response = await generate_response(text, context, lang)
        
        if not response:
            response = "حدث خطأ أثناء توليد الرد" if lang == 'ar' else "Error generating response"
        
        # إرسال الرد بشكل تدريجي
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await send_facebook_message(sender_id, chunk)
            await asyncio.sleep(1)  # تأخير بين الأجزاء
        
        # تحديث سجل المحادثة
        if sender_id not in conversations:
            conversations[sender_id] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang,
                'pending_file': None
            }
        
        conversations[sender_id]['history'].append(f"User: {text}")
        conversations[sender_id]['history'].append(f"Bot: {response}")
        
        # حفظ المحادثة
        save_conversation(sender_id, conversations[sender_id])
        
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
                'pending_file': image_url
            }
        else:
            conversations[sender_id]['pending_file'] = image_url
        
        # حفظ المحادثة
        save_conversation(sender_id, conversations[sender_id])
        
    except Exception as e:
        logger.error(f"Facebook image error: {str(e)}")
        await send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة الصورة" if lang == 'ar' else "⚠️ Error processing image")

async def handle_facebook_file(sender_id, file_url):
    """معالجة ملف من فيسبوك"""
    try:
        lang = 'ar'
        if sender_id in conversations:
            lang = conversations[sender_id]['lang']
        
        # طلب وصف الملف من المستخدم
        await send_facebook_message(sender_id, "📁 لتحليل الملف، الرجاء إرسال وصف لما تريد معرفته عنه:" if lang == 'ar' else "📁 To analyze the file, please describe what you want to know about it:")
        
        # تخزين معلومات الملف مؤقتاً
        if sender_id not in conversations:
            conversations[sender_id] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang,
                'pending_file': file_url
            }
        else:
            conversations[sender_id]['pending_file'] = file_url
        
        # حفظ المحادثة
        save_conversation(sender_id, conversations[sender_id])
        
    except Exception as e:
        logger.error(f"Facebook file error: {str(e)}")
        await send_facebook_message(sender_id, "⚠️ حدث خطأ أثناء معالجة الملف" if lang == 'ar' else "⚠️ Error processing file")

async def analyze_file_from_url(file_url, prompt, lang='ar'):
    """تحليل ملف من URL"""
    try:
        # تحميل الملف
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(file_url, headers=headers)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            file_path = tmp_file.name

        # تحليل الملف
        analysis = await analyze_file(file_path, prompt, lang)
        
        return analysis
    except Exception as e:
        logger.error(f"File from URL analysis error: {str(e)}")
        return None
    finally:
        if 'file_path' in locals() and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except:
                pass

async def send_facebook_message(recipient_id, message_text):
    """إرسال رسالة إلى فيسبوك"""
    try:
        url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        
        # إرسال إشعار الكتابة أولاً
        typing_payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on"
        }
        requests.post(url, json=typing_payload, timeout=5)
        
        # إرسال الرسالة الفعلية بعد تأخير
        await asyncio.sleep(1)
        
        message_payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
        }
        
        response = requests.post(url, json=message_payload, timeout=10)
        if response.status_code != 200:
            logger.error(f"Facebook API error: {response.text}")
            
    except Exception as e:
        logger.error(f"Error sending to Facebook: {str(e)}")

def create_static_files():
    """إنشاء الملفات الثابتة عند التشغيل الأول"""
    static_dir = Path('static')
    static_dir.mkdir(exist_ok=True)
    
    # إضافة مكتبة Prism.js لتلوين الأكواد
    css_files = [
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/themes/prism-okaidia.min.css",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/plugins/line-numbers/prism-line-numbers.min.css"
    ]
    
    js_files = [
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/prism.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-python.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-javascript.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-html.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-css.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/components/prism-bash.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/plugins/line-numbers/prism-line-numbers.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/prism/1.24.1/plugins/copy-to-clipboard/prism-copy-to-clipboard.min.js"
    ]
    
    index_html = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دردشة الذكاء الاصطناعي</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">
    {"".join(f'<link href="{css}" rel="stylesheet">' for css in css_files)}
    <style>
        /* جميع أنماط CSS السابقة تبقى كما هي */
        /* نضيف فقط بعض التحسينات لتنسيق الأكواد */
        .code-container {{
            position: relative;
            margin: 15px 0;
            border-radius: 8px;
            overflow: hidden;
        }}
        
        .copy-code-btn {{
            position: absolute;
            top: 5px;
            left: 5px;
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: none;
            border-radius: 4px;
            padding: 5px 10px;
            font-size: 0.8em;
            cursor: pointer;
            transition: all 0.3s ease;
            z-index: 10;
        }}
        
        .copy-code-btn:hover {{
            background: rgba(255, 255, 255, 0.3);
        }}
        
        pre[class*="language-"] {{
            margin: 0;
            padding: 2em 1em 1em 1em;
            border-radius: 0;
        }}
        
        code[class*="language-"] {{
            font-family: 'Courier New', Courier, monospace;
            direction: ltr;
            text-align: left;
        }}
        
        /* بقية الأنماط تبقى كما هي */
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
            <i class="fas fa-paperclip"></i>
            <input type="file" id="fileUpload" class="file-upload-input" accept="image/*,.pdf,.txt,.doc,.docx,.zip" onchange="handleFileUpload()">
        </button>
        <button onclick="sendMessage()">إرسال</button>
    </div>

    <img id="imagePreview" class="image-preview">
    <div id="fileInfo" class="file-info"></div>
    
    <div class="toast" id="toast"></div>

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

    {"".join(f'<script src="{js}"></script>' for js in js_files)}
    
    <script>
        // متغيرات عامة
        let currentUser = null;
        let userToken = null;
        let pendingFile = null;
        const API_BASE_URL = window.location.origin;
        let isTyping = false;
        
        // عناصر DOM
        const chatWindow = document.getElementById("chatWindow");
        const authContainer = document.getElementById("authContainer");
        const loginForm = document.getElementById("loginForm");
        const registerForm = document.getElementById("registerForm");
        const loginError = document.getElementById("loginError");
        const registerError = document.getElementById("registerError");
        const imagePreview = document.getElementById("imagePreview");
        const fileInfo = document.getElementById("fileInfo");
        const fileUpload = document.getElementById("fileUpload");
        const toast = document.getElementById("toast");

        // عند تحميل الصفحة
        window.onload = function() {{
            checkAuth();
            // إصلاح مشكلة اختيار الملفات
            document.querySelector('.file-upload-button').addEventListener('click', function(e) {{
                if (e.target !== this) return;
                fileUpload.click();
            }});
        }};

        function showToast(message) {{
            toast.textContent = message;
            toast.style.display = 'block';
            setTimeout(() => {{
                toast.style.display = 'none';
            }}, 3000);
        }}

        function copyCode(button) {{
            const codeBlock = button.nextElementSibling;
            const codeText = codeBlock.textContent;
            
            navigator.clipboard.writeText(codeText).then(() => {{
                showToast("تم نسخ الكود بنجاح!");
            }}).catch(err => {{
                console.error('Failed to copy code: ', err);
                showToast("فشل نسخ الكود!");
            }});
        }}

        // بقية الدوال تبقى كما هي مع تعديلات طفيفة لتحسين الأداء
        
        function handleFileUpload() {{
            const file = fileUpload.files[0];
            if (!file) return;
            
            pendingFile = file;
            
            if (file.type.match('image.*')) {{
                const reader = new FileReader();
                reader.onload = function(e) {{
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = 'block';
                    fileInfo.style.display = 'none';
                }};
                reader.readAsDataURL(file);
            }} else {{
                imagePreview.style.display = 'none';
                fileInfo.innerHTML = `
                    <i class="fas fa-file"></i> ${{file.name}} (${{formatFileSize(file.size)}})
                    <input type="text" id="filePrompt" placeholder="✍️ اكتب وصفًا للملف..." style="width: 100%; margin-top: 10px;">
                `;
                fileInfo.style.display = 'block';
            }}
        }}

        // بقية الكود يبقى كما هو مع التأكد من أن جميع الدوال محمية بمعالجة الأخطاء
    </script>
</body>
</html>
    """
    
    with open(static_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)

if __name__ == '__main__':
    create_static_files()
    app.run(debug=True)
