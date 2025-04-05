from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import json
import hashlib

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

# تخزين المحادثات في ملف (بدلاً من الذاكرة)
CONVERSATIONS_FILE = "conversations.json"

def load_conversations():
    try:
        if os.path.exists(CONVERSATIONS_FILE):
            with open(CONVERSATIONS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading conversations: {str(e)}")
    return {}

def save_conversations(conversations):
    try:
        with open(CONVERSATIONS_FILE, 'w') as f:
            json.dump(conversations, f)
    except Exception as e:
        logger.error(f"Error saving conversations: {str(e)}")

def get_user_id(event):
    """إنشاء معرف فريد للمستخدم بناءً على sender_id"""
    sender_id = event['sender']['id']
    return hashlib.md5(sender_id.encode()).hexdigest()

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

def analyze_image(image_path, context=None):
    """تحليل الصورة باستخدام Gemini مع السياق"""
    try:
        img = genai.upload_file(image_path)
        
        prompt = "حلل هذه الصورة بدقة وأجب بالعربية مع ذكر التفاصيل المهمة:"
        if context:
            prompt = f"{context}\n{prompt}"
            
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

def send_message(recipient_id, message_text, buttons=None):
    """إرسال رسالة مع أزرار تظهر في فيسبوك"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {},
        "messaging_type": "RESPONSE"
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
        return True
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return False

def setup_persistent_menu():
    """إعداد القائمة الدائمة لفيسبوك (تظهر في واجهة فيسبوك الرئيسية)"""
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    
    menu_items = [
        {
            "locale": "default",
            "composer_input_disabled": False,
            "call_to_actions": [
                {
                    "type": "postback",
                    "title": "🎓 التعليمات",
                    "payload": "HELP_CMD"
                },
                {
                    "type": "postback",
                    "title": "🔄 إعادة البدء",
                    "payload": "RESTART_CMD"
                },
                {
                    "type": "web_url",
                    "title": "📸 إنستجرام",
                    "url": "https://instagram.com/your_page",
                    "webview_height_ratio": "full"
                }
            ]
        }
    ]
    
    try:
        response = requests.post(url, json={"persistent_menu": menu_items})
        response.raise_for_status()
        logger.info("تم إعداد القائمة الدائمة بنجاح")
    except Exception as e:
        logger.error(f"Error setting up persistent menu: {str(e)}")

def handle_command(user_id, command, event):
    """معالجة الأوامر مع الاحتفاظ بالمحادثة"""
    conversations = load_conversations()
    
    if command == "GET_STARTED":
        welcome_msg = "🎉 أهلاً بك في بوت الذكاء الاصطناعي!\n\n✨ يمكنك إرسال أي سؤال أو صورة وسأساعدك"
        send_message(event['sender']['id'], welcome_msg)
        
        # بدء محادثة جديدة
        conversations[user_id] = {
            "history": [],
            "created_at": datetime.now().isoformat()
        }
        save_conversations(conversations)
        
    elif command == "HELP_CMD":
        help_msg = """
        📚 الأوامر المتاحة:
        
        • إرسال أي سؤال → إجابة ذكية
        • إرسال صورة → تحليل المحتوى
        • "إعادة" → بدء محادثة جديدة
        """
        send_message(event['sender']['id'], help_msg)
        
    elif command == "RESTART_CMD":
        if user_id in conversations:
            del conversations[user_id]
            save_conversations(conversations)
        send_message(event['sender']['id'], "🔄 تم إعادة ضبط المحادثة بنجاح!")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            # عند التحقق لأول مرة، إعداد القائمة الدائمة
            setup_persistent_menu()
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                user_id = get_user_id(event)
                conversations = load_conversations()
                
                # معالجة Postback (أزرار القائمة الدائمة)
                if 'postback' in event:
                    handle_command(user_id, event['postback']['payload'], event)
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                send_message(event['sender']['id'], "🔍 جاري تحليل الصورة...")
                                
                                image_url = attachment['payload']['url']
                                image_path = download_image(image_url)
                                
                                if image_path:
                                    # استخدام سياق المحادثة إذا موجود
                                    context = "\n".join(conversations.get(user_id, {}).get("history", [])[-3:])
                                    analysis = analyze_image(image_path, context)
                                    
                                    if analysis:
                                        # حفظ المحادثة
                                        if user_id not in conversations:
                                            conversations[user_id] = {
                                                "history": [],
                                                "created_at": datetime.now().isoformat()
                                            }
                                        
                                        conversations[user_id]["history"].append(f"صورة: {analysis}")
                                        save_conversations(conversations)
                                        
                                        send_message(event['sender']['id'], f"📸 تحليل الصورة:\n\n{analysis}")
                                    else:
                                        send_message(event['sender']['id'], "⚠️ لم أتمكن من تحليل الصورة")
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        # الأوامر النصية
                        if user_message.lower() in ['مساعدة', 'مساعده', 'help']:
                            handle_command(user_id, "HELP_CMD", event)
                        elif user_message.lower() in ['اعادة', 'إعادة', 'restart']:
                            handle_command(user_id, "RESTART_CMD", event)
                        else:
                            # معالجة الأسئلة النصية مع الاحتفاظ بالسياق
                            try:
                                # تحميل المحادثة الحالية
                                if user_id not in conversations:
                                    conversations[user_id] = {
                                        "history": [],
                                        "created_at": datetime.now().isoformat()
                                    }
                                
                                # إضافة السياق إذا كان هناك محادثة سابقة
                                context = ""
                                if conversations[user_id]["history"]:
                                    context = "\n".join(conversations[user_id]["history"][-3:])
                                    prompt = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {user_message}"
                                else:
                                    prompt = user_message
                                
                                # الحصول على الإجابة
                                response = model.generate_content(prompt)
                                
                                # حفظ المحادثة
                                conversations[user_id]["history"].append(f"أنت: {user_message}")
                                conversations[user_id]["history"].append(f"البوت: {response.text}")
                                save_conversations(conversations)
                                
                                # إرسال الإجابة
                                send_message(event['sender']['id'], response.text)
                                
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                send_message(event['sender']['id'], "⚠️ حدث خطأ أثناء معالجة سؤالك")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200

@app.route('/')
def home():
    return "Facebook AI Bot with Persistent Menu and Memory"

if __name__ == '__main__':
    # عند التشغيل، إعداد القائمة الدائمة
    setup_persistent_menu()
    app.run()
