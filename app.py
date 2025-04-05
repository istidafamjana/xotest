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
import time

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

def get_user_id(sender_id):
    """إنشاء معرف فريد للمستخدم"""
    return hashlib.md5(sender_id.encode()).hexdigest()

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
                        "url": "https://yourwebsite.com",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "web_url",
                        "title": "📸 إنستجرام",
                        "url": "https://instagram.com/yourpage",
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
        "whitelisted_domains": ["https://yourdomain.com"],
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
        prompt = "حلل هذه الصورة بدقة:"
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
    if user_id in conversations:
        return "\n".join(conversations[user_id]["history"][-5:])
    return ""

def handle_new_user(sender_id, user_id):
    """معالجة المستخدم الجديد مع رسالة ترحيبية متكاملة"""
    # إرسال صورة الترحيب
    welcome_image_url = "https://example.com/welcome-bot-image.jpg"  # استبدل برابط صورتك
    send_message(sender_id, "", image_url=welcome_image_url)
    
    # إرسال رسالة الترحيب مع الأزرار
    welcome_msg = """
    🎉 أهلاً بك في بوت الذكاء الاصطناعي المتقدم!
    
    🤖 ما يمكنني فعله لك:
    • الإجابة على أسئلتك بذكاء
    • تحليل الصور ووصف محتواها
    • تذكر سياق المحادثة
    
    💡 اختر أحد الخيارات أدناه للبدء:
    """
    
    send_message(sender_id, welcome_msg, buttons=[
        {
            "type": "postback",
            "title": "🚀 ابدأ المحادثة",
            "payload": "GET_STARTED"
        },
        {
            "type": "postback",
            "title": "📚 شرح البوت",
            "payload": "INFO_CMD"
        },
        {
            "type": "web_url",
            "title": "📞 تواصل معنا",
            "url": "https://instagram.com/yourpage"  # أو رابط الاتصال الخاص بك
        }
    ])
    
    # بدء محادثة جديدة
    conversations[user_id] = {
        "history": ["بدأ المستخدم محادثة جديدة"],
        "last_active": time.time()
    }

def handle_command(sender_id, user_id, command):
    """معالجة الأوامر"""
    if command == "GET_STARTED":
        start_msg = "مرحبًا! يمكنك البدء بإرسال أي سؤال أو صورة وسأساعدك."
        send_message(sender_id, start_msg, buttons=[
            {
                "type": "web_url",
                "title": "🌐 زيارة الموقع",
                "url": "https://yourwebsite.com"
            },
            {
                "type": "web_url",
                "title": "📸 متابعة الإنستجرام",
                "url": "https://instagram.com/yourpage"
            }
        ])
        
    elif command == "INFO_CMD":
        info_msg = """
        ℹ️ معلومات عن البوت:
        
        الإصدار: 4.0
        التقنية: Gemini AI من جوجل
        الميزات:
        - فهم الأسئلة المعقدة
        - تحليل الصور المتقدم
        - دعم المحادثات الطويلة
        
        📅 آخر تحديث: 2024
        """
        send_message(sender_id, info_msg)
        
    elif command == "CONNECT_CMD":
        connect_msg = "يمكنك متابعتنا على:"
        send_message(sender_id, connect_msg, buttons=[
            {
                "type": "web_url",
                "title": "📸 إنستجرام",
                "url": "https://instagram.com/yourpage"
            },
            {
                "type": "web_url",
                "title": "🌐 الموقع الرسمي",
                "url": "https://yourwebsite.com"
            }
        ])

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
                
                # تنظيف المحادثات القديمة (أكثر من ساعة)
                for uid in list(conversations.keys()):
                    if current_time - conversations[uid]["last_active"] > 3600:
                        del conversations[uid]
                
                # معالجة Postback (أزرار القائمة)
                if 'postback' in event:
                    handle_command(sender_id, user_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # التحقق من مستخدم جديد
                    if user_id not in conversations:
                        handle_new_user(sender_id, user_id)
                        continue
                    
                    # تحديث وقت النشاط
                    conversations[user_id]["last_active"] = current_time
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                send_message(sender_id, "🔍 جاري تحليل الصورة...")
                                image_url = attachment['payload']['url']
                                image_path = download_image(image_url)
                                
                                if image_path:
                                    context = get_chat_context(user_id)
                                    analysis = analyze_image(image_path, context)
                                    
                                    if analysis:
                                        conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                                        send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                    else:
                                        send_message(sender_id, "⚠️ لم أتمكن من تحليل الصورة")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        # الأوامر النصية
                        if user_message.lower() in ['مساعدة', 'help']:
                            handle_command(sender_id, user_id, "HELP_CMD")
                        elif user_message.lower() in ['إعادة', 'restart']:
                            handle_command(sender_id, user_id, "RESTART_CMD")
                        elif user_message.lower() in ['تواصل', 'connect']:
                            handle_command(sender_id, user_id, "CONNECT_CMD")
                        elif user_message.lower() in ['موقع', 'web']:
                            send_message(sender_id, "🌐 يمكنك زيارة موقعنا:", buttons=[
                                {
                                    "type": "web_url",
                                    "title": "الموقع الرسمي",
                                    "url": "https://yourwebsite.com"
                                }
                            ])
                        elif user_message.lower() in ['شرح', 'info']:
                            handle_command(sender_id, user_id, "INFO_CMD")
                        else:
                            # معالجة الأسئلة مع السياق
                            try:
                                context = get_chat_context(user_id)
                                prompt = f"سياق المحادثة:\n{context}\n\nالسؤال الجديد: {user_message}" if context else user_message
                                
                                response = model.generate_content(prompt)
                                
                                conversations[user_id]["history"].append(f"المستخدم: {user_message}")
                                conversations[user_id]["history"].append(f"البوت: {response.text}")
                                
                                send_message(sender_id, response.text)
                                
                            except Exception as e:
                                logger.error(f"خطأ في الذكاء الاصطناعي: {str(e)}")
                                send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك")
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook AI Bot with Complete Features"

if __name__ == '__main__':
    setup_messenger_profile()
    app.run()
