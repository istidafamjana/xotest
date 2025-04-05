from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import json
import hashlib

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

# تخزين المحادثات
CONVERSATIONS_FILE = "conversations.json"

def load_conversations():
    try:
        if os.path.exists(CONVERSATIONS_FILE):
            with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading conversations: {str(e)}")
    return {}

def save_conversations(data):
    try:
        with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving conversations: {str(e)}")

def get_user_id(sender_id):
    """إنشاء معرف فريد للمستخدم"""
    return hashlib.md5(sender_id.encode()).hexdigest()

def setup_messenger_profile():
    """إعداد المظهر العام للبوت في فيسبوك"""
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "get_started": {
            "payload": "GET_STARTED"
        },
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "📚 التعليمات",
                        "payload": "HELP_CMD"
                    },
                    {
                        "type": "postback",
                        "title": "🔄 إعادة البدء",
                        "payload": "RESTART_CMD"
                    },
                    {
                        "type": "web_url",
                        "title": "📸 إنستجرام",
                        "url": "https://instagram.com/yourpage",
                        "webview_height_ratio": "full"
                    }
                ]
            }
        ],
        "whitelisted_domains": [
            "https://yourdomain.com"  # استبدل برابطك
        ]
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("تم إعداد واجهة فيسبوك بنجاح")
    except Exception as e:
        logger.error(f"Error setting up messenger profile: {str(e)}")

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
        logger.error(f"Error downloading image: {str(e)}")
        return None

def analyze_image(image_path, context=None):
    """تحليل الصورة باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل هذه الصورة بدقة:"
        if context:
            prompt = f"{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    """إرسال رسالة مع أزرار"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {},
        "messaging_type": "RESPONSE"
    }

    if buttons:
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
        logger.error(f"Error sending message: {str(e)}")
        return False

def get_chat_context(user_id):
    """الحصول على سياق المحادثة"""
    conversations = load_conversations()
    if user_id in conversations:
        return "\n".join(conversations[user_id]["history"][-5:])  # آخر 5 رسائل
    return ""

def handle_command(sender_id, user_id, command):
    """معالجة الأوامر"""
    conversations = load_conversations()
    
    if command == "GET_STARTED":
        welcome_msg = "مرحبًا بك! أنا بوت الذكاء الاصطناعي. كيف يمكنني مساعدتك اليوم؟"
        send_message(sender_id, welcome_msg, buttons=[
            {
                "type": "postback",
                "title": "🆘 المساعدة",
                "payload": "HELP_CMD"
            },
            {
                "type": "postback",
                "title": "ℹ️ معلومات",
                "payload": "INFO_CMD"
            }
        ])
        
        # بدء محادثة جديدة
        conversations[user_id] = {
            "history": ["بدأ المستخدم المحادثة"],
            "last_active": datetime.now().isoformat()
        }
        save_conversations(conversations)
        
    elif command == "HELP_CMD":
        help_msg = "📚 الأوامر المتاحة:\n\n• إرسال أي سؤال للحصول على إجابة\n• إرسال صورة لتحليلها\n• 'إعادة' لبدء محادثة جديدة"
        send_message(sender_id, help_msg)
        
    elif command == "INFO_CMD":
        info_msg = "🤖 معلومات البوت:\n\nالإصدار: 3.5\nالتقنية: Gemini AI\nالمطور: فريقك"
        send_message(sender_id, info_msg)
        
    elif command == "RESTART_CMD":
        if user_id in conversations:
            del conversations[user_id]
            save_conversations(conversations)
        send_message(sender_id, "تم إعادة ضبط المحادثة بنجاح!")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            setup_messenger_profile()  # إعداد الواجهة عند التحقق
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                user_id = get_user_id(sender_id)
                conversations = load_conversations()
                
                # تنظيف المحادثات القديمة (أكثر من 24 ساعة)
                for uid in list(conversations.keys()):
                    last_active = datetime.fromisoformat(conversations[uid]["last_active"])
                    if (datetime.now() - last_active) > timedelta(hours=24):
                        del conversations[uid]
                save_conversations(conversations)
                
                # معالجة Postback
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                send_message(sender_id, "جاري تحليل الصورة...")
                                image_url = attachment['payload']['url']
                                image_path = download_image(image_url)
                                
                                if image_path:
                                    context = get_chat_context(user_id)
                                    analysis = analyze_image(image_path, context)
                                    
                                    if analysis:
                                        # تحديث المحادثة
                                        if user_id not in conversations:
                                            conversations[user_id] = {
                                                "history": [],
                                                "last_active": datetime.now().isoformat()
                                            }
                                        
                                        conversations[user_id]["history"].append(f"صورة: {analysis[:100]}...")
                                        conversations[user_id]["last_active"] = datetime.now().isoformat()
                                        save_conversations(conversations)
                                        
                                        send_message(sender_id, f"📸 نتيجة التحليل:\n\n{analysis}")
                                    else:
                                        send_message(sender_id, "⚠️ لم أستطع تحليل الصورة")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        # الأوامر النصية
                        if user_message.lower() in ['مساعدة', 'help']:
                            handle_command(sender_id, user_id, "HELP_CMD")
                        elif user_message.lower() in ['إعادة', 'اعادة', 'restart']:
                            handle_command(sender_id, user_id, "RESTART_CMD")
                        elif user_message.lower() in ['معلومات', 'info']:
                            handle_command(sender_id, user_id, "INFO_CMD")
                        else:
                            # معالجة الأسئلة مع السياق
                            try:
                                context = get_chat_context(user_id)
                                prompt = f"{context}\n\nالسؤال الجديد: {user_message}" if context else user_message
                                
                                response = model.generate_content(prompt)
                                
                                # تحديث المحادثة
                                if user_id not in conversations:
                                    conversations[user_id] = {
                                        "history": [],
                                        "last_active": datetime.now().isoformat()
                                    }
                                
                                conversations[user_id]["history"].append(f"المستخدم: {user_message}")
                                conversations[user_id]["history"].append(f"البوت: {response.text}")
                                conversations[user_id]["last_active"] = datetime.now().isoformat()
                                save_conversations(conversations)
                                
                                send_message(sender_id, response.text)
                                
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook AI Bot with Persistent Menu and Memory"

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
