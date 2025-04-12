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

# إعدادات عامة
ALLOWED_IMAGE_DOMAINS = ['facebook.com', 'fbcdn.net', 'cdninstagram.com', 'whatsapp.net']
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات

# تخزين المحادثات
conversations = {}
user_locks = {}
global_lock = Lock()

# ========== الدوال المساعدة ========== #
def get_user_id(sender_id):
    return hashlib.md5(sender_id.encode()).hexdigest()

def get_user_lock(user_id):
    with global_lock:
        if user_id not in user_locks:
            user_locks[user_id] = Lock()
        return user_locks[user_id]

def is_valid_image_url(url):
    return any(domain in url for domain in ALLOWED_IMAGE_DOMAINS)

def download_image(url):
    try:
        if not is_valid_image_url(url):
            raise Exception("رابط الصورة غير مصرح به")
        
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status != 200:
                raise Exception(f"كود الاستجابة: {response.status}")
            
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                raise Exception(f"نوع الملف غير مدعوم: {content_type}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dat') as tmp_file:
                tmp_file.write(response.read())
                return tmp_file.name
                
    except Exception as e:
        logger.error(f"خطأ في تنزيل الصورة: {str(e)}")
        return None

def analyze_image(image_path, context=None):
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل الصورة بدقة مع ذكر التفاصيل المهمة:"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        
        response = model.generate_content([prompt, img])
        
        if not response.text:
            logger.error("رد فارغ من واجهة API")
            return "لم أتمكن من تحليل هذه الصورة"
            
        return response.text
    
    except Exception as e:
        logger.error(f"خطأ في التحليل: {str(e)}", exc_info=True)
        return None
    
    finally:
        try:
            if image_path and os.path.exists(image_path):
                os.unlink(image_path)
        except Exception as e:
            logger.error(f"خطأ في التنظيف: {str(e)}")

def send_message(recipient_id, text, buttons=None):
    try:
        time.sleep(0.3)  # تجنب حدود المعدل
        url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        
        payload = {
            "recipient": {"id": recipient_id},
            "messaging_type": "RESPONSE"
        }

        if buttons:
            payload["message"] = {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons
                    }
                }
            }
        else:
            payload["message"] = {"text": text}

        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
        
    except Exception as e:
        logger.error(f"فشل الإرسال: {str(e)}")
        return False

# ========== معالجة المحادثة ========== #
def process_image_message(sender_id, user_id, image_url):
    try:
        send_message(sender_id, "📥 جاري استلام الصورة...")
        image_path = download_image(image_url)
        
        if not image_path:
            raise Exception("فشل التنزيل")
        
        send_message(sender_id, "🔍 جاري التحليل، انتظر قليلاً...")
        context = "\n".join(conversations.get(user_id, {}).get("history", [])[-3:])
        analysis = analyze_image(image_path, context)
        
        if analysis:
            with global_lock:
                if user_id not in conversations:
                    conversations[user_id] = {"history": []}
                conversations[user_id]["history"].append(f"تحليل الصورة: {analysis[:300]}")
            
            send_message(sender_id, f"📸 النتيجة:\n\n{analysis}")
        else:
            send_message(sender_id, "⚠️ لم أتمكن من فهم الصورة")
            
    except Exception as e:
        logger.error(f"خطأ معالجة الصورة: {str(e)}")
        send_message(sender_id, "❌ حدث خطأ أثناء معالجة الصورة")

def handle_text_message(sender_id, user_id, text):
    try:
        context = "\n".join(conversations.get(user_id, {}).get("history", [])[-5:])
        prompt = f"السياق:\n{context}\n\nالسؤال: {text}" if context else text
        
        response = model.generate_content(prompt)
        
        with global_lock:
            if user_id not in conversations:
                conversations[user_id] = {"history": []}
            conversations[user_id]["history"].extend([f"المستخدم: {text}", f"البوت: {response.text}"])
        
        send_message(sender_id, response.text)
        
    except Exception as e:
        logger.error(f"خطاء الذكاء الاصطناعي: {str(e)}")
        send_message(sender_id, "⚠️ حدث خطأ في المعالجة")

# ========== الويب هوك ========== #
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge', '')
        return "Verification Failed", 403

    data = request.get_json()
    
    try:
        for entry in data['entry']:
            for event in entry['messaging']:
                sender_id = event['sender']['id']
                user_id = get_user_id(sender_id)
                
                with global_lock:
                    # تنظيف المحادثات القديمة
                    for uid in list(conversations.keys()):
                        if time.time() - conversations[uid].get('last_active', 0) > CONVERSATION_TIMEOUT:
                            del conversations[uid]
                            if uid in user_locks:
                                del user_locks[uid]
                    
                    # تحديث النشاط
                    if user_id not in conversations:
                        conversations[user_id] = {
                            "history": ["بدأ المحادثة"],
                            "last_active": time.time()
                        }
                    else:
                        conversations[user_id]["last_active"] = time.time()
                
                # معالجة الأحداث
                if event.get('postback'):
                    handle_command(sender_id, user_id, event['postback']['payload'])
                elif event.get('message'):
                    message = event['message']
                    if message.get('attachments'):
                        for att in message['attachments']:
                            if att['type'] == 'image':
                                process_image_message(sender_id, user_id, att['payload']['url'])
                    elif message.get('text'):
                        handle_text_message(sender_id, user_id, message['text'])
    
    except Exception as e:
        logger.error(f"خطأ الويب هوك: {str(e)}")
    
    return jsonify(success=True), 200

# ========== الإعدادات الأولية ========== #
def setup_messenger_profile():
    try:
        url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "get_started": {"payload": "GET_STARTED"},
            "persistent_menu": [{
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {"type": "web_url", "title": "🌐 الموقع", "url": "https://example.com"},
                    {"type": "postback", "title": "ℹ️ معلومات", "payload": "INFO_CMD"}
                ]
            }],
            "greeting": [{"locale": "default", "text": "مرحبًا! أنا بوت الذكاء الاصطناعي، كيف يمكنني مساعدتك؟"}]
        }
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        logger.error(f"خطأ الإعداد: {str(e)}")

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
