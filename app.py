from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os

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

# تخزين المحادثات
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

def analyze_image(image_path):
    """تحليل الصورة باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        prompt = """
        حلل هذه الصورة بدقة وأجب بالعربية. اذكر:
        1. محتوى الصورة الرئيسي
        2. الألوان والعناصر البارزة
        3. إذا كان فيها نص اقرأه
        4. أي معلومات مفيدة يمكن استخلاصها
        """
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    """إرسال رسالة إلى المستخدم"""
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
    else:
        payload["message"] = {"text": message_text}

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
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
                
                # معالجة Postback
                if 'postback' in event:
                    payload = event['postback']['payload']
                    if payload == 'GET_STARTED':
                        send_message(sender_id, "مرحبًا بك! كيف يمكنني مساعدتك اليوم؟")
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                image_url = attachment['payload']['url']
                                image_path = download_image(image_url)
                                if image_path:
                                    analysis = analyze_image(image_path)
                                    if analysis:
                                        send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                                    else:
                                        send_message(sender_id, "⚠️ لم أستطع تحليل هذه الصورة، يرجى المحاولة بصورة أخرى")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text']
                        try:
                            response = model.generate_content(user_message)
                            send_message(sender_id, response.text)
                        except Exception as e:
                            logger.error(f"AI Error: {str(e)}")
                            send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك، يرجى المحاولة لاحقًا")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook Messenger AI Bot is Running!"

if __name__ == '__main__':
    app.run()
