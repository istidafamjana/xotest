from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
import time

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات المضمنة مباشرة
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
MY_INSTAGRAM = "https://www.instagram.com/mx.fo"  # استبدل برابطك

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 💾 تخزين المحادثات (3 ساعات)
CONVERSATION_TIMEOUT = timedelta(hours=3)
conversations = {}

# 🎨 تصميم القائمة الدائمة
def get_persistent_menu():
    return {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🚀 بدء /start",
                        "payload": "/start"
                    },
                    {
                        "type": "postback",
                        "title": "❓ مساعدة /help",
                        "payload": "/help"
                    },
                    {
                        "type": "web_url",
                        "title": "📱 تواصل /contact",
                        "url": MY_INSTAGRAM
                    }
                ]
            }
        ]
    }

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, quick_replies=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": quick_replies if quick_replies else []
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"فشل الإرسال: {e}")

# 🖼️ معالجة الصور المحسنة
def analyze_image(image_url):
    try:
        # تحميل الصورة مع تحسينات
        response = requests.get(image_url, timeout=20, 
                             headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code != 200:
            raise Exception(f"خطأ في تحميل الصورة: {response.status_code}")
        
        # تحقق من أن الملف صورة
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise Exception("الملف ليس صورة")
        
        # تحليل الصورة مع تعليمات محسنة
        prompt = """حلل هذه الصورة بدقة:
1. صف المحتوى الرئيسي
2. اذكر التفاصيل المهمة
3. ما هي المشاكل الواضحة؟
4. اقترح حلولاً عملية

الإجابة يجب أن تكون واضحة ومنظمة"""
        
        response = model.generate_content(
            [prompt, response.content],
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 1000
            }
        )
        return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {e}")
        return None

# 🌐 إعداد القائمة الدائمة
def setup_menu():
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
    logger.info(f"البيانات الواردة: {data}")
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # إنشاء/تحديث المحادثة
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
                        handle_text(sender_id, message['text'])
                    elif 'attachments' in message:
                        for att in message['attachments']:
                            if att['type'] == 'image':
                                handle_image(sender_id, att['payload']['url'])
                
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"خطأ في الويب هوك: {e}")
        return jsonify({"status": "error"}), 500
    
    return jsonify({"status": "success"}), 200

def handle_text(sender_id, text):
    text = text.strip().lower()
    
    # معالجة الأوامر
    if text.startswith('/'):
        handle_command(sender_id, text)
    else:
        try:
            # استخدام تاريخ المحادثة للسياق
            context = "\n".join([msg['content'] for msg in conversations[sender_id]["history"][-3:]])
            prompt = f"المحادثة السابقة:\n{context}\n\nالسؤال الجديد: {text}"
            
            response = model.generate_content(prompt)
            reply = response.text
            
            # حفظ المحادثة
            conversations[sender_id]["history"].append({
                "role": "user",
                "content": text,
                "timestamp": datetime.now()
            })
            conversations[sender_id]["history"].append({
                "role": "bot",
                "content": reply,
                "timestamp": datetime.now()
            })
            
            send_message(sender_id, reply)
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            send_message(sender_id, "حدث خطأ في معالجة سؤالك")

def handle_image(sender_id, image_url):
    try:
        send_message(sender_id, "🔍 جاري تحليل الصورة، يرجى الانتظار...")
        analysis = analyze_image(image_url)
        
        if analysis:
            # حفظ تحليل الصورة في التاريخ
            conversations[sender_id]["history"].append({
                "role": "image",
                "content": image_url,
                "analysis": analysis,
                "timestamp": datetime.now()
            })
            
            send_message(sender_id, f"📸 تحليل الصورة:\n\n{analysis}")
        else:
            send_message(sender_id, "⚠️ لم أستطع تحليل الصورة. يرجى التأكد من:\n1. وضوح الصورة\n2. أنها ليست كبيرة جدًا\n3. أنها تحتوي على محتوى قابل للتحليل")
    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        send_message(sender_id, "حدث خطأ غير متوقع في تحليل الصورة")

def handle_command(sender_id, command):
    command = command.lower()
    responses = {
        "/start": "مرحبًا بك! 👋\nأنا بوت الذكاء الاصطناعي الذي يمكنه:\n- الإجابة على أسئلتك\n- تحليل الصور\n- تذكر محادثاتك لمدة 3 ساعات\n\nاستخدم الأوامر في القائمة السفلية",
        "/help": "📚 كيفية الاستخدام:\n\n/start - بدء المحادثة\n/help - عرض هذه التعليمات\n/contact - للتواصل مع المطور\n\nيمكنك إرسال أي سؤال أو صورة للتحليل",
        "/contact": f"📱 يمكنك التواصل مع المطور عبر:\n\nInstagram: {MY_INSTAGRAM}\n\nسيتم الرد في أسرع وقت ممكن"
    }
    
    if command in responses:
        send_message(sender_id, responses[command])
    else:
        send_message(sender_id, "⚠️ أمر غير معروف. استخدم /help لرؤية الأوامر المتاحة")

# تنظيف المحادثات القديمة
def cleanup_old_conversations():
    while True:
        now = datetime.now()
        expired = [uid for uid, conv in conversations.items() if conv['expiry'] < now]
        for uid in expired:
            del conversations[uid]
        time.sleep(3600)  # تشغيل كل ساعة

# بدء خدمة التنظيف في خيط منفصل
Thread(target=cleanup_old_conversations, daemon=True).start()

# تشغيل الإعدادات الأولية
setup_menu()

if __name__ == '__main__':
    app.run(threaded=True)
