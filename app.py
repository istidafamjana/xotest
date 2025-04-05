from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import os
from io import BytesIO
from PIL import Image  # لمعالجة الصور إذا لزم الأمر

app = Flask(__name__)

# 🔑 التوكنات (استبدلها بقيمك)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"  # توكن صفحتك
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"  # توكن التحقق
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"  # مفتاح Gemini

# ⚙️ تهيئة نموذج Gemini 1.5 Flash
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')  # النموذج المجاني

# 💾 تخزين المحادثات (30 دقيقة)
CONVERSATION_TIMEOUT = 30  # دقيقة
conversations = {}

# 🎨 تصميم الأزرار
def get_main_buttons():
    return [
        {"type": "postback", "title": "🔍 ابدأ", "payload": "/start"},
        {"type": "postback", "title": "ℹ️ مساعدة", "payload": "/help"},
        {"type": "postback", "title": "🔄 إعادة", "payload": "/restart"}
    ]

# ✉️ إرسال رسالة
def send_message(recipient_id, text, buttons=False):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": get_main_buttons() if buttons else []
        }
    }
    requests.post(url, json=payload)

# 🖼️ معالجة الصور من فيسبوك
def process_image(image_url):
    try:
        response = requests.get(image_url)
        img_data = BytesIO(response.content)
        return Image.open(img_data)
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

# 🤖 معالجة الرسائل (نصوص/صور)
def handle_message(sender_id, message, attachments=None):
    # تحديث وقت المحادثة
    conversations[sender_id] = {"expiry": datetime.now() + timedelta(minutes=CONVERSATION_TIMEOUT)}
    
    try:
        if attachments:  # إذا كانت هناك صور
            image_url = attachments[0]['payload']['url']
            image = process_image(image_url)
            
            if image:
                response = model.generate_content(["وصف هذه الصورة:", image])
                send_message(sender_id, response.text, buttons=True)
            else:
                send_message(sender_id, "⚠️ لم أستطع معالجة الصورة", buttons=True)
        else:  # إذا كانت رسالة نصية
            response = model.generate_content(message)
            send_message(sender_id, response.text, buttons=True)
    except Exception as e:
        send_message(sender_id, "⚠️ حدث خطأ في المعالجة", buttons=True)
        print(f"AI Error: {e}")

# 🌐 نقطة نهاية الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.json
    for entry in data.get('entry', []):
        for event in entry.get('messaging', []):
            sender_id = event['sender']['id']
            
            # تحديث وقت المحادثة
            conversations[sender_id] = {"expiry": datetime.now() + timedelta(minutes=CONVERSATION_TIMEOUT)}
            
            if 'message' in event:
                message = event['message']
                if 'text' in message:
                    handle_message(sender_id, message['text'])
                elif 'attachments' in message:
                    handle_message(sender_id, "لقد أرسلت صورة", message['attachments'])
    
    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(debug=True)
