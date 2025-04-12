from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
import logging
import tempfile
import urllib.request
import os
import hashlib
import time
from threading import Lock

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات المؤقتة
conversations = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
user_locks = {}  # أقفال لكل مستخدم
global_lock = Lock()  # قفل عام

def get_user_id(sender_id):
    """إنشاء معرف فريد للمستخدم"""
    return hashlib.md5(sender_id.encode()).hexdigest()

def get_user_lock(user_id):
    """الحصول على قفل للمستخدم"""
    with global_lock:
        if user_id not in user_locks:
            user_locks[user_id] = Lock()
        return user_locks[user_id]

def setup_messenger_profile():
    """إعداد واجهة الماسنجر مع القائمة الدائمة والمظهر"""
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
                        "title": "🌐 الموقع الرسمي",
                        "url": "https://oth-ia.vercel.app",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "web_url",
                        "title": "📸 إنستجرام",
                        "url": "https://instagram.com/mx.fo",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "postback",
                        "title": "ℹ️ عن البوت",
                        "payload": "INFO_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://oth-ia.vercel.app"],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت الذكاء الاصطناعي! انقر على 'ابدأ' للتفاعل مع البوت"
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة الماسنجر بنجاح")
    except Exception as e:
        logger.error(f"خطأ في إعداد الواجهة: {str(e)}")

def download_image(url):
    """تحميل الصورة من الرابط المؤقت"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            return tmp_file.name
    except Exception as e:
        logger.error(f"خطأ في تحميل الصورة: {str(e)}")
        return None

def analyze_image(image_path, context=None):
    """تحليل الصورة مع السياق"""
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل هذه الصورة بدقة وأعط وصفاً تفصيلياً:\n"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None, image_url=None):
    """إرسال رسالة مع أزرار أو صورة"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {},
        "messaging_type": "RESPONSE"
    }

    if image_url:
        payload["message"] = {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True
                }
            }
        }
    elif buttons:
        payload["message"] = {
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
        payload["message"] = {"text": message_text}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def get_chat_context(user_id):
    """الحصول على سياق المحادثة (آخر 5 رسائل)"""
    with global_lock:
        if user_id in conversations:
            return "\n".join(conversations[user_id]["history"][-5:])
        return ""

def handle_new_user(sender_id, user_id):
    """معالجة المستخدم الجديد"""
    welcome_msg = """
    🎉 أهلاً بك في بوت الذكاء الاصطناعي المتقدم!
    
    🤖 ما يمكنني فعله لك:
    • الإجابة على أسئلتك بذكاء
    • تحليل الصور ووصف محتواها بدقة
    • تذكر سياق المحادثة لمدة 5 ساعات
    
    💡 يمكنك إرسال أي صورة وسأحللها لك بدقة
    """
    
    with global_lock:
        conversations[user_id] = {
            "history": ["بدأ المستخدم محادثة جديدة"],
            "last_active": time.time()
        }
    
    send_message(sender_id, welcome_msg)

def handle_command(sender_id, user_id, command):
    """معالجة الأوامر"""
    user_lock = get_user_lock(user_id)
    
    with user_lock:
        if command == "GET_STARTED":
            start_msg = "مرحباً بك! يمكنك إرسال:\n- أسئلة نصية\n- صور لتحليلها\nوسأرد عليك بأفضل إجابة"
            send_message(sender_id, start_msg)
            
        elif command == "INFO_CMD":
            info_msg = """
            ℹ️ معلومات عن البوت:
            
            الإصدار: 5.1
            التقنية: Gemini AI من جوجل
            ميزات تحليل الصور:
            - وصف دقيق لمحتوى الصورة
            - تحليل النصوص في الصور (إن وجدت)
            - فهم السياق العام
            
            📸 جرب إرسال صورة لتحصل على وصف مفصل
            """
            send_message(sender_id, info_msg)

def process_image_message(sender_id, user_id, image_url):
    """معالجة رسائل الصور بشكل منفصل"""
    user_lock = get_user_lock(user_id)
    
    with user_lock:
        send_message(sender_id, "🔍 جاري تحليل الصورة...")
        image_path = download_image(image_url)
        
        if image_path:
            context = get_chat_context(user_id)
            analysis = analyze_image(image_path, context)
            
            if analysis:
                with global_lock:
                    conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                    conversations[user_id]["last_active"] = time.time()
                
                response_msg = f"📸 تحليل الصورة:\n\n{analysis}\n\n✏️ يمكنك طرح أسئلة إضافية عن الصورة"
                send_message(sender_id, response_msg)
            else:
                send_message(sender_id, "⚠️ لم أتمكن من تحليل الصورة، يرجى المحاولة بصورة أخرى")

def process_text_message(sender_id, user_id, text):
    """معالجة الرسائل النصية"""
    user_lock = get_user_lock(user_id)
    
    with user_lock:
        if text.lower() in ['مساعدة', 'help']:
            handle_command(sender_id, user_id, "INFO_CMD")
        else:
            try:
                context = get_chat_context(user_id)
                prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {text}" if context else text
                
                response = model.generate_content(prompt)
                
                with global_lock:
                    conversations[user_id]["history"].append(f"المستخدم: {text}")
                    conversations[user_id]["history"].append(f"البوت: {response.text}")
                    conversations[user_id]["last_active"] = time.time()
                
                send_message(sender_id, response.text)
                
            except Exception as e:
                logger.error(f"خطأ في الذكاء الاصطناعي: {str(e)}")
                send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك، يرجى المحاولة لاحقاً")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
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
                user_id = get_user_id(sender_id)
                current_time = time.time()
                
                # تنظيف المحادثات القديمة (أكثر من 5 ساعات)
                with global_lock:
                    for uid in list(conversations.keys()):
                        if current_time - conversations[uid]["last_active"] > CONVERSATION_TIMEOUT:
                            del conversations[uid]
                            if uid in user_locks:
                                del user_locks[uid]
                
                # معالجة Postback (أزرار القائمة)
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # التحقق من مستخدم جديد
                    with global_lock:
                        if user_id not in conversations:
                            handle_new_user(sender_id, user_id)
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                process_image_message(sender_id, user_id, image_url)
                    
                    # معالجة النصوص
                    elif 'text' in message:
                        text = message['text'].strip()
                        if text:
                            process_text_message(sender_id, user_id, text)
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook AI Bot - Image Analysis & Text Processing"

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
