from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
import time
from threading import Thread

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
MY_INSTAGRAM = "https://www.instagram.com/your_username"  # استبدل برابطك

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
                        "url": MY_INSTAGRAM,
                        "webview_height_ratio": "full"
                    }
                ]
            }
        ]
    }

def get_quick_replies():
    return [
        {"content_type": "text", "title": "🔍 ابدأ", "payload": "/start"},
        {"content_type": "text", "title": "🆘 مساعدة", "payload": "/help"},
        {"content_type": "text", "title": "🔄 إعادة", "payload": "/restart"}
    ]

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, quick_replies=False):
    url = f"https://graph.facebook.com/v17.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    # تقسيم الرسائل الطويلة
    max_length = 1900  # أقل من 2000 للحماية
    if len(text) > max_length:
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for part in parts:
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": part}
            }
            try:
                response = requests.post(url, params=params, json=payload, timeout=10)
                response.raise_for_status()
                time.sleep(0.3)  # تجنب حظر الرسائل
            except Exception as e:
                logger.error(f"فشل إرسال جزء من الرسالة: {e}")
        return
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": get_quick_replies() if quick_replies else []
        }
    }
    
    try:
        response = requests.post(url, params=params, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"❌ فشل إرسال الرسالة: {e}")
        return False

# 🖼️ معالجة الصور
def analyze_image(image_url):
    try:
        logger.info(f"بدأ تحليل الصورة من الرابط: {image_url}")
        
        # تحميل الصورة مع تحسينات
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=20)
        response.raise_for_status()
        
        # التحقق من نوع الملف
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError("الملف ليس صورة")
        
        # تحليل الصورة مع تعليمات واضحة
        prompt = """حلل هذه الصورة بدقة:
1. صف المحتوى الرئيسي بجملة واحدة
2. اذكر 3 تفاصيل مهمة
3. ما هي المشاكل الواضحة؟
4. اقترح حلولاً عملية

الإجابة يجب أن تكون مختصرة وفي نقاط"""
        
        response = model.generate_content(
            [prompt, response.content],
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 800
            }
        )
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ خطأ في تحميل الصورة: {e}")
        return "⚠️ تعذر تحميل الصورة. يرجى التأكد من:\n- أن الرابط صحيح\n- أن الصورة ليست كبيرة جدًا\n- إعادة المحاولة لاحقًا"
    except Exception as e:
        logger.error(f"❌ خطأ في تحليل الصورة: {e}")
        return "⚠️ حدث خطأ غير متوقع أثناء التحليل. يرجى المحاولة بصور أخرى"

# 🌐 إعداد القائمة الدائمة
def setup_menu():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    try:
        response = requests.post(url, params=params, json=get_persistent_menu())
        response.raise_for_status()
        logger.info("✅ تم إعداد القائمة الدائمة بنجاح")
    except Exception as e:
        logger.error(f"❌ فشل إعداد القائمة: {e}")

# 🌐 الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            logger.info("✅ تم التحقق من الويب هوك بنجاح")
            return request.args.get('hub.challenge')
        logger.error("❌ توكن التحقق غير صحيح")
        return "Verification failed", 403
    
    data = request.get_json()
    if not data:
        logger.error("❌ لا توجد بيانات في الطلب")
        return jsonify({"status": "error", "message": "No data"}), 400
    
    logger.info(f"📩 بيانات واردة: {data}")
    
    # معالجة البيانات في خيط منفصل لضمان السرعة
    Thread(target=process_webhook_data, args=(data,)).start()
    
    return jsonify({"status": "success"}), 200

def process_webhook_data(data):
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                if not sender_id:
                    continue
                
                # تحديث وقت المحادثة
                conversations[sender_id] = {
                    "last_active": datetime.now(),
                    "expiry": datetime.now() + CONVERSATION_TIMEOUT
                }
                
                # معالجة أنواع الرسائل المختلفة
                if 'message' in event:
                    handle_message(sender_id, event['message'])
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة البيانات: {e}")

def handle_message(sender_id, message):
    if 'text' in message:
        handle_text(sender_id, message['text'])
    elif 'attachments' in message:
        for att in message['attachments']:
            if att['type'] == 'image':
                handle_image(sender_id, att['payload']['url'])

def handle_text(sender_id, text):
    text = text.strip()
    logger.info(f"📝 معالجة نص من {sender_id}: {text}")
    
    if text.lower().startswith('/'):
        handle_command(sender_id, text.lower())
    else:
        try:
            # استخدام سياق المحادثة السابقة
            context = ""
            if sender_id in conversations and "history" in conversations[sender_id]:
                context = "\n".join(
                    f"{msg['role']}: {msg['content']}" 
                    for msg in conversations[sender_id]["history"][-3:]
                )
            
            prompt = f"""المحادثة السابقة:
{context}

السؤال الجديد: {text}

الرجاء الإجابة بشكل واضح ومنظم"""
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 1000
                }
            )
            reply = response.text
            
            # حفظ المحادثة في التاريخ
            if sender_id not in conversations:
                conversations[sender_id] = {
                    "history": [],
                    "expiry": datetime.now() + CONVERSATION_TIMEOUT
                }
            
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
            logger.error(f"❌ خطأ في معالجة النص: {e}")
            send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة لاحقًا")

def handle_image(sender_id, image_url):
    logger.info(f"🖼️ معالجة صورة من {sender_id}")
    send_message(sender_id, "🔍 جاري تحليل الصورة، يرجى الانتظار...")
    
    analysis = analyze_image(image_url)
    
    if analysis and not analysis.startswith("⚠️"):
        # حفظ تحليل الصورة في التاريخ
        if sender_id not in conversations:
            conversations[sender_id] = {
                "history": [],
                "expiry": datetime.now() + CONVERSATION_TIMEOUT
            }
        
        conversations[sender_id]["history"].append({
            "role": "image",
            "content": image_url,
            "analysis": analysis,
            "timestamp": datetime.now()
        })
        
        send_message(sender_id, f"📊 نتائج التحليل:\n\n{analysis}")
    else:
        send_message(sender_id, analysis if analysis else "⚠️ تعذر تحليل الصورة. يرجى إرسال صورة أوضح")

def handle_command(sender_id, command):
    command_responses = {
        "/start": "🚀 مرحباً! أنا بوت الذكاء الاصطناعي. يمكنك:\n- إرسال أي سؤال\n- تحليل الصور\n- استخدام الأوامر أدناه",
        "/help": "📚 الأوامر المتاحة:\n\n/start - بدء المحادثة\n/help - هذه التعليمات\n/contact - للتواصل مع المطور\n/restart - إعادة تعيين المحادثة",
        "/contact": f"📱 للتواصل مع المطور:\n\nInstagram: {MY_INSTAGRAM}\n\nسيتم الرد في أسرع وقت ممكن",
        "/restart": "🔄 تم إعادة تعيين المحادثة\n\nتم مسح تاريخ المحادثة بنجاح"
    }
    
    if command in command_responses:
        send_message(sender_id, command_responses[command])
    else:
        send_message(sender_id, "⚠️ أمر غير معروف. استخدم /help لرؤية الأوامر المتاحة")

# تنظيف المحادثات القديمة
def cleanup_old_conversations():
    while True:
        try:
            now = datetime.now()
            expired = [uid for uid, conv in conversations.items() 
                      if conv['expiry'] < now]
            
            for uid in expired:
                del conversations[uid]
                logger.info(f"🧹 تم تنظيف محادثة المستخدم {uid}")
            
            time.sleep(3600)  # تشغيل كل ساعة
        except Exception as e:
            logger.error(f"❌ خطأ في خدمة التنظيف: {e}")
            time.sleep(60)

# بدء خدمة التنظيف في خيط منفصل
cleanup_thread = Thread(target=cleanup_old_conversations, daemon=True)
cleanup_thread.start()

# تشغيل الإعدادات الأولية
setup_menu()

if __name__ == '__main__':
    app.run(debug=True)
