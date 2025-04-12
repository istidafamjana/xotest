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
conversation_lock = Lock()  # قفل لإدارة الوصول إلى المحادثات

class UserSession:
    """فئة لإدارة جلسة المستخدم"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.history = []
        self.last_active = time.time()
        self.lock = Lock()  # قفل خاص بكل مستخدم
        
    def add_message(self, role, message):
        with self.lock:
            self.history.append(f"{role}: {message}")
            self.last_active = time.time()
            
    def get_context(self, max_messages=5):
        with self.lock:
            return "\n".join(self.history[-max_messages:])

def get_user_session(sender_id):
    """الحصول على جلسة المستخدم أو إنشاء جديدة"""
    user_id = hashlib.md5(sender_id.encode()).hexdigest()
    
    with conversation_lock:
        if user_id not in conversations:
            conversations[user_id] = UserSession(user_id)
            logger.info(f"جلسة جديدة للمستخدم: {user_id}")
            
        # تنظيف الجلسات القديمة
        for uid in list(conversations.keys()):
            if time.time() - conversations[uid].last_active > CONVERSATION_TIMEOUT:
                del conversations[uid]
                logger.info(f"تم حذف الجلسة المنتهية للمستخدم: {uid}")
                
        return conversations[user_id]

# ... [بقية الدوال مثل setup_messenger_profile, download_image, analyze_image] ...

def send_message(recipient_id, message_text, buttons=None):
    """إرسال رسالة مع أزرار"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text} if not buttons else {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": message_text,
                    "buttons": buttons
                }
            }
        },
        "messaging_type": "RESPONSE"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")
        return False

def handle_new_user(sender_id, session):
    """معالجة المستخدم الجديد"""
    welcome_msg = """
    🎉 أهلاً بك في بوت الذكاء الاصطناعي المتقدم!
    🤖 يمكنك البدء بإرسال رسالتك الآن...
    """
    send_message(sender_id, welcome_msg)
    session.add_message("النظام", "بدأ المستخدم محادثة جديدة")

def process_user_message(sender_id, message):
    """معالجة رسالة المستخدم بشكل تسلسلي"""
    session = get_user_session(sender_id)
    
    # معالجة الصور
    if 'attachments' in message:
        for attachment in message['attachments']:
            if attachment['type'] == 'image':
                send_message(sender_id, "🔍 جاري تحليل الصورة...")
                image_url = attachment['payload']['url']
                image_path = download_image(image_url)
                
                if image_path:
                    context = session.get_context()
                    analysis = analyze_image(image_path, context)
                    
                    if analysis:
                        session.add_message("الصورة", analysis[:200])
                        send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                    else:
                        send_message(sender_id, "⚠️ لم أتمكن من تحليل الصورة")
        return
    
    # معالجة النصوص
    if 'text' in message:
        user_message = message['text'].strip()
        session.add_message("المستخدم", user_message)
        
        try:
            context = session.get_context()
            prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {user_message}" if context else user_message
            response = model.generate_content(prompt)
            
            session.add_message("البوت", response.text)
            send_message(sender_id, response.text)
            
        except Exception as e:
            logger.error(f"خطأ في الذكاء الاصطناعي: {str(e)}")
            send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                if 'postback' in event:
                    session = get_user_session(sender_id)
                    handle_command(sender_id, session, event['postback']['payload'])
                elif 'message' in event:
                    message = event['message']
                    session = get_user_session(sender_id)
                    
                    if len(session.history) == 0:  # مستخدم جديد
                        handle_new_user(sender_id, session)
                    
                    process_user_message(sender_id, message)
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    setup_messenger_profile()
    app.run(threaded=False)
