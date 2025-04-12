from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import time

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح (كما هي)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات (لمدة ساعة واحدة)
conversations = {}

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
    """تحليل الصورة باستخدام Gemini مع السياق"""
    try:
        img = genai.upload_file(image_path)
        
        prompt = """
        حلل هذه الصورة بدقة وأجب بالعربية:
        1. صف المحتوى الرئيسي
        2. اذكر التفاصيل المهمة
        3. اقرأ أي نص موجود
        4. قدم نصائح أو حلول إذا لزم الأمر
        """
        
        if context:
            prompt = f"بناءً على السياق التالي: {context}\n{prompt}"
            
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None, quick_replies=None):
    """إرسال رسالة مع خيارات متقدمة"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {}
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
    elif quick_replies:
        payload["message"] = {
            "text": message_text,
            "quick_replies": quick_replies
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

def get_main_menu():
    """القائمة الرئيسية مع كل الأزرار المطلوبة"""
    return [
        {
            "type": "postback",
            "title": "🎓 التعليمات",
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
            "url": "https://instagram.com/your_page"
        }
    ]

def handle_command(sender_id, command):
    """معالجة جميع الأوامر المطلوبة"""
    if command == "GET_STARTED":
        welcome_msg = """
        🎉 أهلاً بك في بوت الذكاء الاصطناعي!
        
        ✨ يمكنك:
        - إرسال أي سؤال للحصول على إجابة ذكية
        - إرسال صورة لتحليل محتواها
        - استخدام الأوامر أدناه
        
        اختر أحد الخيارات:
        """
        send_message(sender_id, welcome_msg, quick_replies=[
            {
                "content_type": "text",
                "title": "📖 التعليمات",
                "payload": "HELP_CMD"
            },
            {
                "content_type": "text",
                "title": "ℹ️ معلومات",
                "payload": "INFO_CMD"
            }
        ])
        
    elif command == "HELP_CMD":
        help_msg = """
        📚 الأوامر المتاحة:
        
        • إرسال أي سؤال → إجابة ذكية
        • إرسال صورة → تحليل المحتوى
        • "مساعدة" → عرض هذه التعليمات
        • "إعادة" → بدء محادثة جديدة
        • "معلومات" → عن البوت والمطور
        
        🛠️ الميزات الجديدة:
        - تحليل الصور المتقدم
        - دعم المحادثات الطويلة
        - واجهة تفاعلية سهلة
        """
        send_message(sender_id, help_msg, buttons=get_main_menu())
        
    elif command == "INFO_CMD":
        info_msg = """
        ℹ️ معلومات البوت:
        
        الإصدار: 3.1
        التقنية: Gemini 1.5 Flash
        المطور: [اسمك]
        
        📅 آخر تحديث: 2024
        """
        send_message(sender_id, info_msg, buttons=get_main_menu())
        
    elif command == "RESTART_CMD":
        if sender_id in conversations:
            del conversations[sender_id]
        send_message(sender_id, "🔄 تم إعادة ضبط المحادثة بنجاح!", buttons=get_main_menu())

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك مع جميع الميزات"""
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
                
                # تنظيف المحادثات القديمة
                now = datetime.now()
                if sender_id in conversations:
                    if conversations[sender_id]['expiry'] < now:
                        del conversations[sender_id]
                
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
                                send_message(sender_id, "🔍 جاري تحليل الصورة...")
                                
                                image_url = attachment['payload']['url']
                                image_path = download_image(image_url)
                                
                                if image_path:
                                    # استخدام سياق المحادثة إذا موجود
                                    context = conversations.get(sender_id, {}).get('context')
                                    analysis = analyze_image(image_path, context)
                                    
                                    if analysis:
                                        response_msg = f"📸 تحليل الصورة:\n\n{analysis}\n\n✏️ هل تريد شرحاً أكثر تفصيلاً؟"
                                        send_message(sender_id, response_msg, quick_replies=[
                                            {
                                                "content_type": "text",
                                                "title": "نعم، اشرح أكثر",
                                                "payload": "MORE_DETAILS"
                                            },
                                            {
                                                "content_type": "text",
                                                "title": "لا، شكراً",
                                                "payload": "NO_THANKS"
                                            }
                                        ])
                                    else:
                                        send_message(sender_id, "⚠️ لم أتمكن من تحليل الصورة، يرجى إرسال صورة أخرى")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip().lower()
                        
                        # الأوامر النصية
                        if user_message in ['ابدأ', 'بدء', 'start']:
                            handle_command(sender_id, "GET_STARTED")
                        elif user_message in ['مساعدة', 'مساعده', 'help']:
                            handle_command(sender_id, "HELP_CMD")
                        elif user_message in ['معلومات', 'عن البوت', 'info']:
                            handle_command(sender_id, "INFO_CMD")
                        elif user_message in ['اعادة', 'إعادة', 'restart']:
                            handle_command(sender_id, "RESTART_CMD")
                        else:
                            # معالجة الأسئلة النصية مع الاحتفاظ بالسياق
                            try:
                                # إعلام المستخدم أن البوت يعمل على الإجابة
                                send_message(sender_id, "🤔 جاري معالجة سؤالك...")
                                
                                # إضافة سياق المحادثة إذا موجود
                                if sender_id in conversations:
                                    context = "\n".join(conversations[sender_id]['history'][-3:])
                                    user_message = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {user_message}"
                                
                                # الحصول على الإجابة من Gemini
                                start_time = time.time()
                                response = model.generate_content(user_message)
                                processing_time = time.time() - start_time
                                
                                # تخزين المحادثة
                                if sender_id not in conversations:
                                    conversations[sender_id] = {
                                        'history': [],
                                        'expiry': datetime.now() + timedelta(hours=1)
                                    }
                                
                                conversations[sender_id]['history'].append(f"أنت: {message['text']}")
                                conversations[sender_id]['history'].append(f"البوت: {response.text}")
                                
                                # إرسال الإجابة مع وقت المعالجة
                                reply = f"{response.text}\n\n⏱️ وقت المعالجة: {processing_time:.2f} ثانية"
                                send_message(sender_id, reply, buttons=get_main_menu())
                                
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك، يرجى المحاولة لاحقاً")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook Messenger AI Bot is Running with All Features!"

if __name__ == '__main__':
    app.run()
