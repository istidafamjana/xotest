from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات المضمنة مباشرة (للتجربة فقط)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 💾 تخزين المحادثات (24 ساعة)
conversations = {}

# 🎨 تصميم القوائم
def get_persistent_menu():
    return {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🏠 ابدأ",
                        "payload": "/start"
                    },
                    {
                        "type": "postback",
                        "title": "❓ مساعدة",
                        "payload": "/help"
                    },
                    {
                        "type": "postback",
                        "title": "🔄 إعادة",
                        "payload": "/restart"
                    }
                ]
            }
        ]
    }

def get_quick_replies():
    return [
        {"content_type": "text", "title": "🆘 مساعدة", "payload": "/help"},
        {"content_type": "text", "title": "🔄 إعادة", "payload": "/restart"},
        {"content_type": "text", "title": "ℹ️ معلومات", "payload": "/about"}
    ]

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, quick_replies=False):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": get_quick_replies() if quick_replies else []
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"فشل الإرسال: {e}")

# 🖼️ معالجة الصور
def analyze_image(image_url):
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        
        prompt = """حلل هذه الصورة وقدم:
        1. وصف مفصل للمحتوى
        2. المشاكل المحتملة
        3. الحلول المقترحة
        4. نصائح عملية"""
        
        response = model.generate_content([prompt, response.content])
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {e}")
        return None

# 🌐 إعداد القائمة الدائمة
def setup_menu():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json=get_persistent_menu())

# 🌐 الويب هوك
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "توكن التحقق غير صحيح", 403
    
    data = request.get_json()
    logger.info(f"بيانات الواردة: {data}")
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # تحديث وقت المحادثة
                conversations[sender_id] = datetime.now() + timedelta(hours=24)
                
                if 'message' in event:
                    message = event['message']
                    
                    if 'text' in message:
                        handle_text(sender_id, message['text'])
                    elif 'attachments' in message:
                        for att in message['attachments']:
                            if att['type'] == 'image':
                                handle_image(sender_id, att['payload']['url'])
                
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"خطأ: {e}")
        return jsonify({"status": "error"}), 500
    
    return jsonify({"status": "success"}), 200

def handle_text(sender_id, text):
    text = text.strip().lower()
    
    if text in ['/start', '/help', '/restart', '/about']:
        handle_command(sender_id, text)
    else:
        try:
            response = model.generate_content(f"المستخدم يسأل: {text}\n\nأجب بشكل مفصل ومنظم:")
            send_message(sender_id, response.text, quick_replies=True)
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            send_message(sender_id, "حدث خطأ في المعالجة", quick_replies=True)

def handle_image(sender_id, image_url):
    try:
        analysis = analyze_image(image_url)
        if analysis:
            reply = "📊 تحليل الصورة:\n\n" + analysis
            send_message(sender_id, reply, quick_replies=True)
        else:
            send_message(sender_id, "⚠️ لم أستطع تحليل الصورة", quick_replies=True)
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        send_message(sender_id, "حدث خطأ في تحليل الصورة", quick_replies=True)

def handle_postback(sender_id, payload):
    commands = {
        "/start": "مرحبًا! أنا بوت الذكاء الاصطناعي. يمكنك:\n- إرسال أي سؤال\n- إرسال صور لتحليلها\n- استخدام الأوامر أدناه",
        "/help": "🔍 الأوامر المتاحة:\n\n/start - بدء المحادثة\n/help - عرض المساعدة\n/restart - إعادة التعيين\n/about - معلومات البوت",
        "/about": "🤖 معلومات البوت:\n\nالإصدار: 3.0\nالنموذج: Gemini 1.5 Flash\nالميزات: يدعم النصوص والصور",
        "/restart": "تم إعادة ضبط المحادثة. يمكنك البدء من جديد!"
    }
    
    if payload in commands:
        send_message(sender_id, commands[payload], quick_replies=True)
    else:
        send_message(sender_id, "أمر غير معروف", quick_replies=True)

# تشغيل الإعدادات عند البدء
setup_menu()

if __name__ == '__main__':
    app.run()
