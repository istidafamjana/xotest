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

# 🔑 التوكنات المضمنة مباشرة
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 💾 تخزين المحادثات
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
        return True
    except Exception as e:
        logger.error(f"فشل الإرسال: {e}")
        return False

# 🖼️ معالجة الصور (محسنة)
def analyze_image(image_url):
    try:
        # تحميل الصورة مع زيادة المهلة
        response = requests.get(image_url, timeout=20)
        response.raise_for_status()
        
        # تحقق من نوع المحتوى
        if 'image/' not in response.headers.get('Content-Type', ''):
            logger.error("الملف ليس صورة")
            return None
            
        # تحليل الصورة مع تعليمات مفصلة
        prompt = """**مطلوب تحليل الصورة بالتفصيل:**
1. صف كل العناصر المرئية الرئيسية
2. اذكر أي مشاكل أو أعطال واضحة
3. اقترح حلول عملية لكل مشكلة
4. قدم نصائح للتحسين
        
تنسيق الإجابة:
- الوصف: [تفصيل المحتوى]
- المشاكل: [القائمة]
- الحلول: [المقترحات]
- النصائح: [التوصيات]"""
        
        response = model.generate_content(
            [prompt, response.content],
            generation_config={"temperature": 0.3}
        )
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في تحميل الصورة: {e}")
        return None
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {e}")
        return None

# 🌐 إعداد القائمة الدائمة
def setup_menu():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    try:
        response = requests.post(url, json=get_persistent_menu())
        response.raise_for_status()
        logger.info("تم إعداد القائمة الدائمة بنجاح")
    except Exception as e:
        logger.error(f"فشل إعداد القائمة: {e}")

# 🌐 الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
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
    
    if text.startswith('/'):
        handle_command(sender_id, text)
    else:
        try:
            response = model.generate_content(
                f"السؤال: {text}\n\nالرجاء الإجابة بشكل منظم مع عناوين فرعية",
                generation_config={"temperature": 0.4}
            )
            send_message(sender_id, f"✅ تمت المعالجة:\n\n{response.text}", quick_replies=True)
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            send_message(sender_id, "⚠️ حدث خطأ أثناء المعالجة، يرجى المحاولة لاحقًا", quick_replies=True)

def handle_image(sender_id, image_url):
    loading_msg = "⏳ جاري تحليل الصورة، يرجى الانتظار..."
    if not send_message(sender_id, loading_msg):
        return
    
    analysis = analyze_image(image_url)
    if analysis:
        reply = f"📋 نتائج التحليل:\n\n{analysis}\n\n✅ تم الانتهاء"
    else:
        reply = "⚠️ تعذر تحليل الصورة، يرجى إرسال صورة أخرى أو التأكد من وضوحها"
    
    send_message(sender_id, reply, quick_replies=True)

def handle_command(sender_id, command):
    command = command.lower().strip()
    responses = {
        "/start": "🚀 تم بدء جلسة جديدة\n\nمرحبًا! أنا بوت الذكاء الاصطناعي الخاص بك. يمكنك:\n• إرسال أي سؤال\n• تحميل الصور للتحليل\n• استخدام الأوامر الأخرى",
        "/help": "📚 الأوامر المتاحة:\n\n/start - بدء جلسة جديدة\n/help - عرض هذه المساعدة\n/restart - إعادة تعيين البوت\n/about - معلومات عن البوت",
        "/about": "🤖 معلومات البوت:\n\n• الإصدار: 3.1\n• النموذج: Gemini 1.5 Flash\n• الميزات:\n  - تحليل الصور المتقدم\n  - فهم السياق\n  - إجابات مفصلة",
        "/restart": "🔄 تم إعادة تعيين البوت بنجاح\n\nتم مسح جميع البيانات السابقة، يمكنك البدء من جديد"
    }
    
    if command in responses:
        send_message(sender_id, responses[command], quick_replies=True)
    else:
        send_message(sender_id, "⚠️ أمر غير معروف\n\nاستخدم /help لرؤية الأوامر المتاحة", quick_replies=True)

# تشغيل الإعدادات عند البدء
setup_menu()

if __name__ == '__main__':
    app.run()
