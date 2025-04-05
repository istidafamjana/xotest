from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
from threading import Thread
import time

app = Flask(__name__)

# 🔑 التوكنات (ضع قيمك هنا)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"  # توكن صفحتك
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"  # توكن التحقق
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"  # مفتاح Gemini

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# 💾 تخزين المحادثات (تنتهي بعد ساعة)
conversations = {}

# 🧹 تنظيف المحادثات المنتهية كل ساعة
def cleanup_conversations():
    while True:
        time.sleep(3600)  # تشغيل كل ساعة
        now = datetime.now()
        expired = [uid for uid, conv in conversations.items() if conv['expiry'] < now]
        for uid in expired:
            del conversations[uid]
        print(f"تم تنظيف {len(expired)} محادثة منتهية")

# 🚀 بدء خدمة التنظيف التلقائي
Thread(target=cleanup_conversations, daemon=True).start()

# 🎨 تصميم الأزرار
def get_main_buttons():
    return [
        {
            "type": "postback",
            "title": "🔍 ابدأ /start",
            "payload": "/start"
        },
        {
            "type": "postback",
            "title": "ℹ️ مساعدة /help",
            "payload": "/help"
        },
        {
            "type": "postback",
            "title": "🔄 إعادة /restart",
            "payload": "/restart"
        }
    ]

# ✉️ إرسال رسالة مع الأزرار
def send_message(recipient_id, text, buttons=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": get_main_buttons() if buttons else []
        }
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"فشل الإرسال: {e}")

# 🎛 معالجة الأوامر
def handle_command(sender_id, cmd):
    commands = {
        "/start": "مرحباً بك! 💡\nأنا بوت ذكاء اصطناعي يمكنك طرح أي سؤال.\n\nاستخدم /help لرؤية الأوامر.",
        "/help": "📚 الأوامر المتاحة:\n\n/start - بدء محادثة جديدة\n/help - عرض هذه التعليمات\n/restart - مسح تاريخ المحادثة",
        "/restart": "تم إعادة ضبط المحادثة. يمكنك البدء من جديد! 🆕"
    }
    
    if cmd == "/restart" and sender_id in conversations:
        del conversations[sender_id]
    
    send_message(sender_id, commands[cmd], buttons=True)

# 🤖 معالجة رسائل المستخدم
def handle_message(sender_id, message):
    # إنشاء محادثة جديدة إذا لزم الأمر
    if sender_id not in conversations:
        conversations[sender_id] = {
            "history": [],
            "expiry": datetime.now() + timedelta(hours=1)
        }
    
    # توليد الرد باستخدام Gemini
    try:
        response = model.generate_content(message)
        send_message(sender_id, response.text, buttons=True)
    except Exception as e:
        send_message(sender_id, "⚠️ حدث خطأ. يرجى المحاولة لاحقاً.", buttons=True)

# 🌐 نقطة نهاية الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "توكن التحقق غير صحيح", 403
    
    data = request.json
    for entry in data.get('entry', []):
        for event in entry.get('messaging', []):
            sender_id = event['sender']['id']
            message = event.get('message', {}).get('text') or event.get('postback', {}).get('payload')
            
            if not message:
                continue
                
            if message.lower() in ["/start", "/help", "/restart"]:
                handle_command(sender_id, message.lower())
            else:
                handle_message(sender_id, message)
    
    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
   app.run(debug=True)
