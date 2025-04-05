from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات والمفاتيح (تأكد من صحتها)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# ⚙️ تهيئة نموذج Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')  # التحديث للإصدار الصحيح
    logger.info("✅ تم تهيئة نموذج Gemini بنجاح")
except Exception as e:
    logger.error(f"❌ فشل تهيئة Gemini: {e}")
    raise

# 💾 تخزين المحادثات (30 دقيقة)
CONVERSATION_TIMEOUT = timedelta(minutes=30)
conversations = {}

# 🎨 واجهة الترحيب
def get_welcome_screen():
    return {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "generic",
                "elements": [{
                    "title": "مرحبًا بك في بوت الذكاء الاصطناعي! 🤖",
                    "image_url": "https://l.top4top.io/p_3056965410.png",
                    "subtitle": "يمكنك طرح أي سؤال وسأساعدك بالإجابة باستخدام Gemini 1.5 Flash",
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "🚀 ابدأ المحادثة",
                            "payload": "/start"
                        },
                        {
                            "type": "postback",
                            "title": "ℹ️ الأوامر",
                            "payload": "/help"
                        }
                    ]
                }]
            }
        }
    }

# 🎛 أزرار القائمة
def get_main_buttons():
    return [
        {"type": "postback", "title": "📖 المساعدة", "payload": "/help"},
        {"type": "postback", "title": "🔄 إعادة", "payload": "/restart"},
        {"type": "postback", "title": "ℹ️ عن البوت", "payload": "/about"}
    ]

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, buttons=False, welcome=False):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": get_welcome_screen() if welcome else {"text": text}
    }
    
    if buttons and not welcome:
        payload["message"] = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": get_main_buttons()
                }
            }
        }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"تم إرسال رسالة لـ {recipient_id}")
    except Exception as e:
        logger.error(f"فشل إرسال الرسالة: {e}")

# 🎚 معالجة الأوامر
def handle_command(sender_id, command):
    commands = {
        "/start": "مرحبًا! أنا بوت الذكاء الاصطناعي. اسألني أي شيء!\n\nاستخدم /help للمساعدة.",
        "/help": "📜 الأوامر:\n/start - بدء محادثة\n/help - هذه التعليمات\n/restart - بدء جديد\n/about - معلومات البوت",
        "/about": "🤖 البوت:\nالإصدار: 2.0\nالنموذج: Gemini 1.5 Flash\nالميزات: إجابات ذكية، دعم متعدد اللغات",
        "/restart": "تم إعادة الضبط. المحادثات تحذف بعد 30 دقيقة من عدم النشاط."
    }
    
    if command == "/restart" and sender_id in conversations:
        del conversations[sender_id]
    
    send_message(sender_id, commands[command], buttons=True)

# 🌐 الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            logger.info("تم التحقق من الويب هوك بنجاح")
            return request.args.get('hub.challenge')
        logger.error("توكن التحقق غير صحيح")
        return "Verification failed", 403
    
    try:
        data = request.get_json()
        logger.debug(f"البيانات الواردة: {data}")
        
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # تحديث وقت المحادثة
                conversations[sender_id] = {
                    "last_active": datetime.now(),
                    "expiry": datetime.now() + CONVERSATION_TIMEOUT
                }
                
                # معالجة الرسائل
                if 'postback' in event:
                    payload = event['postback'].get('payload')
                    if payload == "GET_STARTED":
                        handle_command(sender_id, "/start")
                    elif payload:
                        handle_command(sender_id, payload.lower())
                
                elif 'message' in event:
                    message = event['message']
                    if 'text' in message:
                        try:
                            response = model.generate_content(message['text'])
                            send_message(sender_id, response.text, buttons=True)
                        except Exception as e:
                            logger.error(f"خطأ في توليد الرد: {e}")
                            send_message(sender_id, "حدث خطأ في المعالجة", buttons=True)
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {e}")
        return jsonify({"status": "error"}), 500
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(debug=True)
