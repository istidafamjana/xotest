from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
import asyncio
from threading import Thread

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')  # أحدث إصدار

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
                        "title": "🏠 ابدأ /start",
                        "payload": "/start"
                    },
                    {
                        "type": "postback",
                        "title": "❓ مساعدة /help",
                        "payload": "/help"
                    },
                    {
                        "type": "postback",
                        "title": "🔄 إعادة /restart",
                        "payload": "/restart"
                    }
                ]
            }
        ]
    }

def get_quick_replies():
    return [
        {"content_type": "text", "title": "🔍 ابدأ", "payload": "/start"},
        {"content_type": "text", "title": "🆘 مساعدة", "payload": "/help"},
        {"content_type": "text", "title": "🔄 إعادة", "payload": "/restart"}
    ]

# ✉️ إرسال الرسائل (باستخدام الجلسات)
def send_message(recipient_id, text, quick_replies=False):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    # تقسيم الرسائل الطويلة
    max_length = 2000
    if len(text) > max_length:
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for part in parts:
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": part}
            }
            requests.post(url, json=payload)
            time.sleep(0.5)  # تجنب rate limiting
        return
    
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

# 🖼️ معالجة الصور (سريعة)
async def analyze_image_async(image_url):
    try:
        # تحميل الصورة بشكل غير متزامن
        response = await asyncio.to_thread(requests.get, image_url, timeout=15)
        response.raise_for_status()
        
        # نموذج التحليل السريع
        prompt = """حلل الصورة بسرعة وأجب بالنقاط:
1. الوصف المختصر (سطر واحد)
2. 3 مشاكل محتملة
3. 3 حلول مقترحة
        
الإجابة يجب أن تكون مختصرة وفي نقاط"""
        
        response = model.generate_content(
            [prompt, response.content],
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 500  # تقليل طول الإجابة
            }
        )
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {e}")
        return None

# 🚀 معالجة الأوامر السريعة
command_responses = {
    "/start": "✅ تم بدء الجلسة\n\nمرحبًا! أنا بوت الذكاء الاصطناعي. استخدم الأزرار للتحكم:",
    "/help": "📋 الأوامر السريعة:\n\n/start - بدء جديد\n/help - هذه التعليمات\n/restart - إعادة التعيين",
    "/restart": "🔄 تم إعادة التعيين\n\nتم مسح تاريخ المحادثة بنجاح",
    "/about": "🤖 معلومات البوت:\n\n• الإصدار: 3.2\n• النموذج: Gemini Flash\n• السرعة: فائقة"
}

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
                
                # معالجة الأحداث
                if 'message' in event:
                    message = event['message']
                    if 'text' in message:
                        handle_text_message(sender_id, message['text'])
                    elif 'attachments' in message:
                        Thread(target=handle_attachments, args=(sender_id, message['attachments'])).start()
                
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"خطأ: {e}")
    
    return jsonify({"status": "success"}), 200

def handle_text_message(sender_id, text):
    text = text.strip().lower()
    if text in command_responses:
        send_message(sender_id, command_responses[text], quick_replies=True)
    else:
        try:
            # إجابة سريعة مع تحسين الأداء
            response = model.generate_content(
                f"السؤال: {text}\n\nالرجاء الإجابة باختصار في نقاط",
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 800
                }
            )
            send_message(sender_id, f"📝 الإجابة:\n\n{response.text}", quick_replies=True)
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            send_message(sender_id, "⚠️ حدث خطأ، يرجى المحاولة لاحقًا", quick_replies=True)

def handle_attachments(sender_id, attachments):
    for att in attachments:
        if att['type'] == 'image':
            send_message(sender_id, "⏳ جاري تحليل الصورة بسرعة...")
            analysis = asyncio.run(analyze_image_async(att['payload']['url']))
            if analysis:
                send_message(sender_id, f"📸 نتيجة التحليل السريع:\n\n{analysis}", quick_replies=True)
            else:
                send_message(sender_id, "⚠️ لم أستطع تحليل الصورة، يرجى إرسال صورة أوضح", quick_replies=True)

def handle_postback(sender_id, payload):
    if payload in command_responses:
        send_message(sender_id, command_responses[payload], quick_replies=True)
    else:
        send_message(sender_id, "⚠️ أمر غير معروف", quick_replies=True)

# تشغيل الإعدادات
def setup():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json=get_persistent_menu())

setup()

if __name__ == '__main__':
    app.run(threaded=True)
