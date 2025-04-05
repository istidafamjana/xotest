from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
import time
from threading import Thread
import os

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات (يُفضل استخدام متغيرات البيئة في الإنتاج)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
MY_INSTAGRAM = "https://www.instagram.com/your_username"  # استبدل برابطك

# ⚙️ تهيئة نموذج Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ تم تهيئة نموذج Gemini بنجاح")
except Exception as e:
    logger.error(f"❌ فشل تهيئة Gemini: {e}")
    raise

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

# ✉️ إرسال الرسائل
def send_message(recipient_id, text, quick_replies=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    # إذا كانت الرسالة طويلة، نقسمها لأجزاء
    max_length = 2000
    if len(text) > max_length:
        parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
        for part in parts:
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": part}
            }
            try:
                requests.post(url, json=payload, timeout=10)
                time.sleep(0.3)  # تجنب rate limiting
            except Exception as e:
                logger.error(f"فشل إرسال جزء من الرسالة: {e}")
        return
    
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
        return True
    except Exception as e:
        logger.error(f"❌ فشل إرسال الرسالة: {e}")
        return False

# 🖼️ معالجة الصور المحسنة
def analyze_image(image_url):
    try:
        logger.info(f"بدء تحليل الصورة من الرابط: {image_url}")
        
        # تحميل الصورة مع تحسينات
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=20)
        response.raise_for_status()
        
        # التحقق من نوع الملف
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            raise ValueError(f"الملف ليس صورة (النوع: {content_type})")
        
        # تحليل الصورة مع تعليمات محسنة
        prompt = """**مطلوب تحليل الصورة بدقة:**
1. صف المحتوى الرئيسي بجملة واحدة
2. اذكر 3 تفاصيل مهمة
3. ما هي المشاكل الواضحة؟ (إن وجدت)
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
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"
    try:
        response = requests.post(url, json=get_persistent_menu())
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
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                if not sender_id:
                    continue
                
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
                        handle_text_message(sender_id, message['text'])
                    elif 'attachments' in message:
                        for att in message['attachments']:
                            if att['type'] == 'image':
                                handle_image_message(sender_id, att['payload']['url'])
                
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة الويب هوك: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "success"}), 200

def handle_text_message(sender_id, text):
    text = text.strip()
    logger.info(f"📝 معالجة نص من {sender_id}: {text}")
    
    if text.lower().startswith('/'):
        handle_command(sender_id, text.lower())
    else:
        try:
            # استخدام تاريخ المحادثة للسياق
            context = "\n".join(
                f"{msg['role']}: {msg['content']}" 
                for msg in conversations[sender_id]["history"][-3:]
            )
            
            prompt = f"""المحادثة السابقة:
{context}

السؤال الجديد: {text}

الرجاء الإجابة بشكل واضح ومنظم مع مراعاة السياق السابق"""
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 1000
                }
            )
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
            logger.error(f"❌ خطأ في معالجة النص: {e}")
            send_message(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة لاحقًا")

def handle_image_message(sender_id, image_url):
    logger.info(f"🖼️ معالجة صورة من {sender_id}")
    
    # إرسال رسالة الانتظار
    send_message(sender_id, "🔍 جاري تحليل الصورة، يرجى الانتظار...")
    
    analysis = analyze_image(image_url)
    
    if analysis and not analysis.startswith("⚠️"):
        # حفظ تحليل الصورة في التاريخ
        conversations[sender_id]["history"].append({
            "role": "image",
            "content": image_url,
            "analysis": analysis,
            "timestamp": datetime.now()
        })
        
        send_message(sender_id, f"📊 نتائج التحليل:\n\n{analysis}")
    else:
        send_message(sender_id, analysis if analysis else "⚠️ تعذر تحليل الصورة. يرجى إرسال صورة أخرى")

def handle_postback(sender_id, payload):
    logger.info(f"🔄 معالجة postback من {sender_id}: {payload}")
    
    commands = {
        "/start": "مرحبًا بك! 👋\nأنا بوت الذكاء الاصطناعي الذي يمكنه:\n✔ الإجابة على أسئلتك\n✔ تحليل الصور\n✔ تذكر محادثتك لمدة 3 ساعات\n\nاستخدم الأوامر في القائمة السفلية ⬇",
        "/help": "📚 كيفية الاستخدام:\n\n/start - بدء المحادثة\n/help - عرض التعليمات\n/contact - للتواصل مع المطور\n\nيمكنك إرسال:\n- أي سؤال للحصول على إجابة\n- صورة لتحليل محتواها",
        "/contact": f"📱 للتواصل مع المطور:\n\nInstagram: {MY_INSTAGRAM}\n\nسيتم الرد في أسرع وقت ممكن ⏳"
    }
    
    if payload in commands:
        send_message(sender_id, commands[payload])
    else:
        send_message(sender_id, "⚠️ أمر غير معروف. استخدم /help لرؤية الأوامر المتاحة")

# تنظيف المحادثات القديمة
def cleanup_old_conversations():
    while True:
        try:
            now = datetime.now()
            expired = [uid for uid, conv in conversations.items() if conv['expiry'] < now]
            
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
    app.run(threaded=True)
