from flask import Flask, request, jsonify
import requestsfrom flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# مفاتيح الوصول (يجب استبدالها بمفاتيحك)
PAGE_ACCESS_TOKEN = "YOUR_FACEBOOK_PAGE_ACCESS_TOKEN"
VERIFY_TOKEN = "YOUR_VERIFY_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# تهيئة نموذج Gemini المجاني
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات
conversations = {}

def download_image(url):
    """تحميل الصورة من الرابط المؤقت"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
        urllib.request.urlretrieve(url, tmp_file.name)
        return tmp_file.name

def analyze_image(image_path, prompt=None):
    """تحليل الصورة باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        
        if prompt:
            response = model.generate_content([prompt, img])
        else:
            response = model.generate_content([
                "حلل هذه الصورة بدقة وأجب بالعربية. اذكر:",
                "1. محتوى الصورة الرئيسي",
                "2. الألوان والعناصر البارزة",
                "3. إذا كان فيها نص اقرأه",
                "4. أي معلومات مفيدة يمكن استخلاصها",
                img
            ])
        
        os.unlink(image_path)
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        if os.path.exists(image_path):
            os.unlink(image_path)
        return None

def get_welcome_screen():
    """شاشة الترحيب مع الأزرار"""
    return {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "generic",
                "elements": [{
                    "title": "مرحبًا بك في بوت الذكاء الاصطناعي 🤖",
                    "image_url": "https://example.com/ai-bot.jpg",
                    "subtitle": "يمكنك إرسال أي نص أو صورة وسأساعدك في تحليلها",
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "بدء المحادثة 🚀",
                            "payload": "START_CMD"
                        },
                        {
                            "type": "postback",
                            "title": "المساعدة ℹ️",
                            "payload": "HELP_CMD"
                        }
                    ]
                }]
            }
        }
    }

def get_main_buttons():
    """الأزرار الرئيسية"""
    return [
        {
            "type": "postback",
            "title": "المساعدة 📖",
            "payload": "HELP_CMD"
        },
        {
            "type": "postback",
            "title": "إعادة البدء 🔄",
            "payload": "RESTART_CMD"
        },
        {
            "type": "web_url",
            "title": "تواصل معنا 📩",
            "url": "https://example.com/contact"
        }
    ]

def send_message(recipient_id, message_text, buttons=None, welcome=False):
    """إرسال رسالة إلى المستخدم"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    if welcome:
        payload = {
            "recipient": {"id": recipient_id},
            "message": get_welcome_screen()
        }
    else:
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
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
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")

def handle_command(sender_id, command):
    """معالجة الأوامر"""
    if command == "START_CMD":
        welcome_text = (
            "مرحبًا بك! 👋 أنا بوت الذكاء الاصطناعي. يمكنني:\n\n"
            "📝 - الإجابة على أسئلتك النصية\n"
            "🖼️ - تحليل الصور ووصف محتواها\n\n"
            "جرب إرسال سؤال أو صورة الآن!"
        )
        send_message(sender_id, welcome_text, get_main_buttons())
        
    elif command == "HELP_CMD":
        help_text = "📋 الأوامر المتاحة:\n\n"
        help_text += "🔹 بدء المحادثة - اضغط على زر 'بدء المحادثة'\n"
        help_text += "🔹 إعادة البدء - اضغط على زر 'إعادة البدء'\n"
        help_text += "🔹 المساعدة - اضغط على زر 'المساعدة'\n\n"
        help_text += "يمكنك أيضًا إرسال:\n- أي سؤال نصي\n- صورة لتحليلها"
        send_message(sender_id, help_text, get_main_buttons())
        
    elif command == "RESTART_CMD":
        if sender_id in conversations:
            del conversations[sender_id]
        send_message(sender_id, "تم إعادة ضبط المحادثة بنجاح!", get_main_buttons())

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
                
                # معالجة Postback (أزرار)
                if 'postback' in event:
                    handle_command(sender_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                try:
                                    image_path = download_image(image_url)
                                    analysis = analyze_image(image_path)
                                    if analysis:
                                        send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                    else:
                                        send_message(sender_id, "عذرًا، لم أستطع تحليل هذه الصورة")
                                except Exception as e:
                                    logger.error(f"Image processing error: {str(e)}")
                                    send_message(sender_id, "حدث خطأ أثناء معالجة الصورة")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text']
                        
                        # معالجة الأوامر النصية
                        if user_message.lower() in ['ابدأ', 'بدء', 'start']:
                            handle_command(sender_id, "START_CMD")
                        elif user_message.lower() in ['مساعدة', 'مساعدة', 'help']:
                            handle_command(sender_id, "HELP_CMD")
                        elif user_message.lower() in ['إعادة', 'اعادة', 'restart']:
                            handle_command(sender_id, "RESTART_CMD")
                        else:
                            # معالجة الأسئلة النصية
                            try:
                                response = model.generate_content(user_message)
                                send_message(sender_id, response.text, get_main_buttons())
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                send_message(sender_id, "عذرًا، حدث خطأ أثناء معالجة سؤالك")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook Messenger AI Bot is Running!"

if __name__ == '__main__':
    app.run()
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
from PIL import Image
import io

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# مفاتيح الوصول
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini المجاني
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # الإصدار المجاني

# تخزين المحادثات (تنتهي بعد ساعة)
conversations = {}

def download_image(url):
    """تحميل الصورة من الرابط المؤقت"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
        urllib.request.urlretrieve(url, tmp_file.name)
        return tmp_file.name

def analyze_image(image_path, prompt=None):
    """تحليل الصورة باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        
        if prompt:
            response = model.generate_content([prompt, img])
        else:
            response = model.generate_content([
                "حلل هذه الصورة بدقة وأجب بالعربية. اذكر:",
                "1. محتوى الصورة الرئيسي",
                "2. الألوان والعناصر البارزة",
                "3. إذا كان فيها نص اقرأه",
                "4. أي معلومات مفيدة يمكن استخلاصها",
                img
            ])
        
        os.unlink(image_path)  # حذف الصورة بعد التحليل
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        os.unlink(image_path)
        return None

def get_welcome_screen():
    """شاشة الترحيب مع الأزرار"""
    return {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "generic",
                "elements": [{
                    "title": "مرحبًا بك في بوت الذكاء الاصطناعي المتقدم! 🤖",
                    "image_url": "https://example.com/ai-bot.jpg",
                    "subtitle": "يمكنك إرسال أي نص أو صورة وسأساعدك في تحليلها",
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "بدء المحادثة 🚀",
                            "payload": "/start"
                        },
                        {
                            "type": "postback",
                            "title": "معلومات ℹ️",
                            "payload": "/info"
                        },
                        {
                            "type": "web_url",
                            "title": "إنستجرام 📷",
                            "url": "https://instagram.com/yourpage"
                        }
                    ]
                }]
            }
        }
    }

def get_main_buttons():
    """الأزرار الرئيسية"""
    return [
        {
            "type": "postback",
            "title": "مساعدة 📖",
            "payload": "/help"
        },
        {
            "type": "postback",
            "title": "إعادة البدء 🔄",
            "payload": "/restart"
        },
        {
            "type": "postback",
            "title": "تواصل معنا 📩",
            "payload": "/contact"
        }
    ]

def send_message(recipient_id, message_text, buttons=None, welcome=False, image_url=None):
    """إرسال رسالة إلى المستخدم"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    if welcome:
        payload = {
            "recipient": {"id": recipient_id},
            "message": get_welcome_screen()
        }
    elif image_url:
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "url": image_url,
                        "is_reusable": True
                    }
                }
            }
        }
    else:
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
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
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"تم إرسال الرسالة إلى {recipient_id}")
    except Exception as e:
        logger.error(f"خطأ في إرسال الرسالة: {str(e)}")

def handle_command(sender_id, command):
    """معالجة الأوامر النصية"""
    if command == "/start":
        welcome_text = (
            "مرحبًا بك! 👋 أنا بوت الذكاء الاصطناعي المتقدم. يمكنني:\n\n"
            "📝 - الإجابة على أسئلتك النصية\n"
            "🖼️ - تحليل الصور ووصف محتواها\n"
            "🔍 - مساعدتك في حل المشكلات\n\n"
            "جرب إرسال سؤال أو صورة الآن!"
        )
        send_message(sender_id, welcome_text, get_main_buttons())
        
    elif command == "/help":
        help_text = "📋 الأوامر المتاحة:\n\n"
        help_text += "🔹 /start - بدء محادثة جديدة\n"
        help_text += "🔹 /help - عرض التعليمات\n"
        help_text += "🔹 /restart - إعادة تعيين المحادثة\n"
        help_text += "🔹 /info - معلومات عن البوت\n"
        help_text += "🔹 /contact - تواصل معنا\n\n"
        help_text += "يمكنك أيضًا إرسال:\n"
        help_text += "- أي سؤال نصي للحصول على إجابة\n"
        help_text += "- صورة لتحليل محتواها"
        send_message(sender_id, help_text, get_main_buttons())
        
    elif command == "/info":
        about_text = "🤖 معلومات البوت:\n\n"
        about_text += "الإصدار: 2.5\n"
        about_text += "التقنية: Gemini 1.5 Flash (مجاني)\n"
        about_text += "الميزات:\n"
        about_text += "- فهم النصوص بذكاء\n"
        about_text += "- تحليل الصور المتقدم\n"
        about_text += "- دعم المحادثات الطويلة\n"
        about_text += "- واجهة تفاعلية سهلة"
        send_message(sender_id, about_text, get_main_buttons())
        
    elif command == "/contact":
        contact_text = "📩 تواصل معنا:\n\n"
        contact_text += "للأسئلة أو الدعم الفني:\n"
        contact_text += "📧 البريد: support@example.com\n"
        contact_text += "📱 إنستجرام: @yourpage\n"
        contact_text += "🌐 الموقع: example.com"
        send_message(sender_id, contact_text, get_main_buttons())
        
    elif command == "/restart":
        if sender_id in conversations:
            del conversations[sender_id]
        send_message(sender_id, "تم إعادة ضبط المحادثة بنجاح. يمكنك البدء من جديد!", get_main_buttons())

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "فشل التحقق", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # إرسال شاشة الترحيب عند أول تفاعل
                if 'postback' in event and event['postback'].get('title') == "Get Started":
                    send_message(sender_id, "", welcome=True)
                    continue
                    
                # معالجة الأوامر النصية
                if 'postback' in event:
                    handle_command(sender_id, event['postback'].get('payload', ''))
                    continue
                    
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة المرفقات (الصور)
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                try:
                                    image_path = download_image(image_url)
                                    analysis = analyze_image(image_path)
                                    if analysis:
                                        send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                    else:
                                        send_message(sender_id, "عذرًا، لم أستطع تحليل هذه الصورة. يرجى إرسال صورة أخرى.")
                                except Exception as e:
                                    logger.error(f"خطأ في معالجة الصورة: {str(e)}")
                                    send_message(sender_id, "حدث خطأ أثناء معالجة الصورة. يرجى المحاولة مرة أخرى.")
                        continue
                    
                    # معالجة الرسائل النصية
                    if 'text' in message:
                        user_message = message['text']
                        
                        if user_message.lower().startswith(('/start', '/help', '/info', '/contact', '/restart')):
                            handle_command(sender_id, user_message.lower())
                        else:
                            try:
                                # إضافة سياق المحادثة
                                if sender_id not in conversations:
                                    conversations[sender_id] = {
                                        "history": [],
                                        "expiry": datetime.now() + timedelta(hours=1)
                                    }
                                
                                # إرسال رسالة توضح أن البوت يعمل على الإجابة
                                send_message(sender_id, "🔍 جاري معالجة طلبك...")
                                
                                # الحصول على الإجابة من Gemini
                                response = model.generate_content(
                                    user_message,
                                    generation_config={
                                        "max_output_tokens": 2000,
                                        "temperature": 0.7
                                    }
                                )
                                
                                # إرسال الإجابة مع الأزرار
                                send_message(sender_id, response.text, get_main_buttons())
                                
                            except Exception as e:
                                logger.error(f"خطأ في الذكاء الاصطناعي: {str(e)}")
                                send_message(sender_id, "عذرًا، حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة مرة أخرى.", get_main_buttons())
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {str(e)}")
    
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run()
