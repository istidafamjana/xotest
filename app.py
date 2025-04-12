from flask import Flask, request, jsonify, render_template
import requests
import google.generativeai as genai
import logging
import tempfile
import urllib.request
import os
import hashlib
import time
from threading import Lock

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات المؤقتة
conversations = {}
CONVERSATION_TIMEOUT = 5 * 60 * 60  # 5 ساعات بالثواني
conversations_lock = Lock()

def get_user_id(sender_id):
    return hashlib.md5(sender_id.encode()).hexdigest()

def setup_messenger_profile():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "get_started": {"payload": "GET_STARTED"},
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "web_url",
                        "title": "🌐 الانتقال للويب",
                        "url": "https://yourdomain.com/chat",
                        "webview_height_ratio": "full"
                    },
                    {
                        "type": "postback",
                        "title": "🆘 المساعدة",
                        "payload": "HELP_CMD"
                    }
                ]
            }
        ],
        "whitelisted_domains": ["https://yourdomain.com"],
        "greeting": [
            {
                "locale": "default",
                "text": "مرحبًا بك في بوت DeepSeek العربي! 💎"
            }
        ]
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error setting up profile: {str(e)}")

def download_image(url):
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

def analyze_image(image_path, context=None):
    try:
        img = genai.upload_file(image_path)
        prompt = "حلل هذه الصورة بدقة وقدم وصفاً شاملاً:"
        if context:
            prompt = f"سياق المحادثة:\n{context}\n{prompt}"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text} if not buttons else {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": message_text,
                    "buttons": buttons
                }
            }
        },
        "messaging_type": "RESPONSE"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")

def handle_message(sender_id, message):
    user_id = get_user_id(sender_id)
    
    with conversations_lock:
        if user_id not in conversations:
            conversations[user_id] = {
                "history": [],
                "last_active": time.time()
            }
            send_message(sender_id, "مرحباً بك في بوت DeepSeek العربي! 💎\n\nيمكنك إرسال أي سؤال أو صورة وسأساعدك.")

        conversations[user_id]["last_active"] = time.time()

        if 'attachments' in message:
            for attachment in message['attachments']:
                if attachment['type'] == 'image':
                    send_message(sender_id, "⏳ جاري تحليل الصورة...")
                    image_url = attachment['payload']['url']
                    image_path = download_image(image_url)
                    
                    if image_path:
                        context = "\n".join(conversations[user_id]["history"][-5:])
                        analysis = analyze_image(image_path, context)
                        
                        if analysis:
                            conversations[user_id]["history"].append(f"صورة: {analysis[:200]}...")
                            send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
                        else:
                            send_message(sender_id, "⚠️ تعذر تحليل الصورة")

        elif 'text' in message:
            user_message = message['text'].strip()
            
            if user_message.lower() in ['مساعدة', 'help']:
                send_message(sender_id, "🆘 مركز المساعدة:\n\n• اكتب سؤالك مباشرة\n• أرسل صورة لتحليلها\n• /new لبدء محادثة جديدة")
            else:
                try:
                    context = "\n".join(conversations[user_id]["history"][-5:])
                    prompt = f"{context}\n\nالسؤال: {user_message}" if context else user_message
                    
                    response = model.generate_content(prompt)
                    reply = response.text
                    
                    conversations[user_id]["history"].append(f"المستخدم: {user_message}")
                    conversations[user_id]["history"].append(f"البوت: {reply}")
                    
                    send_message(sender_id, reply)
                except Exception as e:
                    logger.error(f"AI Error: {str(e)}")
                    send_message(sender_id, "⚠️ حدث خطأ أثناء المعالجة، يرجى المحاولة لاحقاً")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            setup_messenger_profile()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                if 'message' in event:
                    handle_message(event['sender']['id'], event['message'])
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
    
    return jsonify({"status": "ok"}), 200

# روابط الموقع
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    setup_messenger_profile()
    app.run(threaded=True)
