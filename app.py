from flask import Flask, request
import requests
import os
import google.generativeai as genai

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.getenv("EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD")
VERIFY_TOKEN = os.getenv("d51ee4e3183dbbd9a27b7d2c1af8c655")
GEMINI_API_KEY = os.getenv("AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# قاموس لتخزين المحادثات مؤقتًا
conversations = {}

# إرسال رسالة نصية مع أزرار اختيارية
def send_message(recipient_id, text, buttons=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text
        }
    }

    if buttons:
        payload["message"] = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": buttons
                }
            }
        }

    requests.post(url, json=payload)

# توليد أزرار الأوامر
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

    data = request.json
    for entry in data.get("entry", []):
        for message_event in entry.get("messaging", []):
            sender_id = message_event["sender"]["id"]

            # الحصول على الرسالة المرسلة
            user_msg = ""
            if message_event.get("message", {}).get("text"):
                user_msg = message_event["message"]["text"]
            elif message_event.get("postback", {}).get("payload"):
                user_msg = message_event["postback"]["payload"]
            else:
                send_message(sender_id, "مرحبًا بك! استخدم الأزرار لبدء المحادثة.", main_buttons())
                continue

            # التفاعل مع الأوامر
            if user_msg == "/start":
                send_message(sender_id, "ابدأ المحادثة الآن! أرسل لي أي رسالة.", main_buttons())
            elif user_msg == "/help":
                send_message(sender_id, "اكتب لي أي سؤال، وسأجيب باستخدام الذكاء الاصطناعي. استخدم الأزرار للتنقل.", main_buttons())
            elif user_msg == "/restart":
                conversations[sender_id] = []  # مسح المحادثة السابقة
                send_message(sender_id, "تمت إعادة تعيين المحادثة. يمكنك البدء من جديد.", main_buttons())
            else:
                # التفاعل مع الذكاء الاصطناعي باستخدام Gemini
                if sender_id not in conversations:
                    conversations[sender_id] = []

                # إضافة الرسالة إلى المحادثة الحالية
                conversations[sender_id].append({'user': user_msg})

                # طلب الرد من Gemini AI
                ai_response = model.generate_content(user_msg)
                ai_text = ai_response.text

                # إضافة الرد من Gemini إلى المحادثة
                conversations[sender_id].append({'ai': ai_text})

                # إرسال الرد للمستخدم
                send_message(sender_id, ai_text, main_buttons())

    return "تم", 200
if __name__ == "__main__":
    app.run()
