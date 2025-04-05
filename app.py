from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
from PIL import Image
import os

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"  # توكن صفحتك
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"  # توكن التحقق
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"  # مفتاح Gemini

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 💾 تخزين المحادثات (24 ساعة)
CONVERSATION_TIMEOUT = timedelta(hours=24)
conversations = {}

# 🎨 تصميم القوائم والأزرار
def get_persistent_menu():
    return {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🏠 القائمة الرئيسية",
                        "payload": "/start"
                    },
                    {
                        "type": "postback",
                        "title": "❓ المساعدة",
                        "payload": "/help"
                    },
                    {
                        "type": "postback",
                        "title": "🔄 إعادة البدء",
                        "payload": "/restart"
                    }
                ]
            }
        ]
    }

def get_main_buttons():
    return [
        {"type": "postback", "title": "📖 المساعدة", "payload": "/help"},
        {"type": "postback", "title": "🔄 إعادة", "payload": "/restart"},
        {"type": "postback", "title": "ℹ️ عن البوت", "payload": "/about"}
    ]

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, buttons=False, image_url=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    if image_url:
        payload = {
            "recipient": {"id": recipent_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": image_url, "is_reusable": True}
                }
            }
        }
    else:
        payload = {
            "recipient": {"id": recipent_id},
            "message": {"text": text}
        }
        
        if buttons:
            payload["message"]["quick_replies"] = get_main_buttons()
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"فشل الإرسال: {e}")

# 🖼️ معالجة الصور
def process_image(image_url):
    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        return None

# 🎚 معالجة الأوامر
def handle_command(sender_id, command):
    commands = {
        "/start": "مرحبًا بك! أنا بوت الذكاء الاصطناعي. يمكنك:\n- إرسال أي سؤال\n- إرسال صور لتحليلها\n- استخدام الأوامر أدناه",
        "/help": "📜 الأوامر:\n/start - بدء المحادثة\n/help - المساعدة\n/restart - بدء جديد\n/about - معلومات البوت",
        "/about": "🤖 البوت:\nالإصدار: 3.0\nالنموذج: Gemini 1.5 Flash\nيدعم النصوص والصور",
        "/restart": "تم إعادة ضبط المحادثة. يمكنك البدء من جديد!"
    }
    
    if command == "/restart" and sender_id in conversations:
        del conversations[sender_id]
    
    send_message(sender_id, commands[command], buttons=True)

# 🌐 إعداد القائمة الدائمة
@app.before_first_request
def setup_persistent_menu():
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
        return "Verification failed", 403
    
    data = request.get_json()
    logger.debug(f"البيانات الواردة: {data}")
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # تحديث/إنشاء محادثة
                if sender_id not in conversations:
                    conversations[sender_id] = {
                        "history": [],
                        "expiry": datetime.now() + CONVERSATION_TIMEOUT
                    }
                else:
                    conversations[sender_id]["expiry"] = datetime.now() + CONVERSATION_TIMEOUT
                
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    if 'text' in message:
                        handle_text_message(sender_id, message['text'])
                    
                    elif 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                handle_image_message(sender_id, attachment['payload']['url'])
                
                elif 'postback' in event:
                    handle_command(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {e}")
        return jsonify({"status": "error"}), 500
    
    return jsonify({"status": "success"}), 200

def handle_text_message(sender_id, text):
    if text.lower() in ["/start", "/help", "/about", "/restart"]:
        handle_command(sender_id, text.lower())
    else:
        try:
            # إضافة السياق من المحادثة السابقة
            context = "\n".join([msg['content'] for msg in conversations[sender_id]["history"]][-3:])
            prompt = f"المحادثة السابقة:\n{context}\n\nالسؤال الجديد: {text}"
            
            response = model.generate_content(prompt)
            reply = response.text
            
            # حفظ المحادثة
            conversations[sender_id]["history"].append({
                "type": "text",
                "content": text,
                "timestamp": datetime.now()
            })
            
            send_message(sender_id, reply, buttons=True)
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            send_message(sender_id, "حدث خطأ في معالجة سؤالك", buttons=True)

def handle_image_message(sender_id, image_url):
    try:
        img = process_image(image_url)
        if img:
            prompt = """الرجاء تحليل هذه الصورة وتقديم:
            1. وصف مفصل للمحتوى
            2. أي مشاكل محتملة
            3. حلول مقترحة
            4. نصائح ذات صلة"""
            
            response = model.generate_content([prompt, img])
            reply = "تحليل الصورة:\n" + response.text
            
            # حفظ المحادثة
            conversations[sender_id]["history"].append({
                "type": "image",
                "content": image_url,
                "analysis": reply,
                "timestamp": datetime.now()
            })
            
            send_message(sender_id, reply, buttons=True)
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        send_message(sender_id, "حدث خطأ في تحليل الصورة", buttons=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
