from flask import Flask, request, jsonify
import requests
import os
import google.generativeai as genai
from datetime import datetime, timedelta

app = Flask(__name__)

# تحميل المتغيرات البيئية
PAGE_ACCESS_TOKEN = ("EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD")
VERIFY_TOKEN = ("d51ee4e3183dbbd9a27b7d2c1af8c655")
GEMINI_API_KEY = ("AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")

# تهيئة Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")  # تصحيح اسم الموديل

# قاموس لتخزين المحادثات مؤقتًا مع وقت الانتهاء
conversations = {}

# تنظيف المحادثات القديمة
def cleanup_old_conversations():
    current_time = datetime.now()
    expired_keys = [key for key, value in conversations.items() 
                   if 'expiry' in value and current_time > value['expiry']]
    for key in expired_keys:
        del conversations[key]

# إرسال رسالة إلى المستخدم
def send_message(recipient_id, text, buttons=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text} if not buttons else {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": buttons
                }
            }
        }
    }
    response = requests.post(url, json=payload)
    return response.json()

# أزرار القائمة الرئيسية
def main_buttons():
    return [
        {"type": "postback", "title": "ابدأ /start", "payload": "/start"},
        {"type": "postback", "title": "مساعدة /help", "payload": "/help"},
        {"type": "postback", "title": "إعادة البدء 🔁", "payload": "/restart"}
    ]

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "خطأ في التحقق", 403

    data = request.get_json()
    if not data:
        return "لا توجد بيانات", 400

    for entry in data.get("entry", []):
        for message_event in entry.get("messaging", []):
            sender_id = message_event.get("sender", {}).get("id")
            if not sender_id:
                continue
            
            # تنظيف المحادثات القديمة
            cleanup_old_conversations()
            
            # الحصول على الرسالة
            user_msg = ""
            if message_event.get("message", {}).get("text"):
                user_msg = message_event["message"]["text"]
            elif message_event.get("postback", {}).get("payload"):
                user_msg = message_event["postback"]["payload"]
            else:
                send_message(sender_id, "مرحبًا بك! استخدم الأزرار لبدء المحادثة.", main_buttons())
                continue

            # معالجة الأوامر الخاصة
            if user_msg.lower() == "/start":
                send_message(sender_id, "مرحبًا! يمكنك البدء في المحادثة معي الآن. أرسل لي أي سؤال وسأجيب باستخدام الذكاء الاصطناعي.", main_buttons())
            elif user_msg.lower() == "/help":
                send_message(sender_id, "أنا بوت ذكاء اصطناعي. يمكنك:\n- إرسال أي سؤال للحصول على إجابة\n- استخدام /restart لبدء محادثة جديدة\n- استخدام الأزرار للتنقل", main_buttons())
            elif user_msg.lower() == "/restart":
                if sender_id in conversations:
                    del conversations[sender_id]
                send_message(sender_id, "تم إعادة تعيين المحادثة. يمكنك البدء من جديد.", main_buttons())
            else:
                # تهيئة المحادثة إذا لم تكن موجودة
                if sender_id not in conversations:
                    conversations[sender_id] = {
                        'history': [],
                        'expiry': datetime.now() + timedelta(hours=1)
                    }
                
                try:
                    # إنشاء المحادثة مع التاريخ
                    chat = model.start_chat(history=conversations[sender_id]['history'])
                    response = chat.send_message(user_msg)
                    ai_text = response.text
                    
                    # تحديث التاريخ وتاريخ الانتهاء
                    conversations[sender_id]['history'].extend([
                        {'role': 'user', 'parts': [user_msg]},
                        {'role': 'model', 'parts': [ai_text]}
                    ])
                    conversations[sender_id]['expiry'] = datetime.now() + timedelta(hours=1)
                    
                    # إرسال الرد
                    send_message(sender_id, ai_text, main_buttons())
                except Exception as e:
                    send_message(sender_id, "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى.")
                    app.logger.error(f"Error: {str(e)}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(debug=True)
