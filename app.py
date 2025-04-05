from flask import Flask, request, jsonify
import httpx  # استبدال requests بـ httpx
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import asyncio
from threading import Thread
import time

app = Flask(__name__)

# 🔧 تهيئة التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 التوكنات
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
MY_INSTAGRAM = "https://www.instagram.com/your_username"

# ⚙️ تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 💾 تخزين المحادثات
conversations = {}

# 🎨 تصميم القوائم
def get_persistent_menu():
    return {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🏠 ابدأ /start",
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

# ✉️ إرسال الرسائل باستخدام httpx
async def send_message_async(recipient_id, text):
    url = f"https://graph.facebook.com/v17.0/me/messages"
    headers = {
        "Content-Type": "application/json"
    }
    params = {
        "access_token": PAGE_ACCESS_TOKEN
    }
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers=headers,
                params=params,
                json=payload
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"فشل الإرسال: {e}")
            return False

# 🖼️ معالجة الصور باستخدام httpx
async def analyze_image_async(image_url):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # تحميل الصورة
            image_response = await client.get(image_url)
            image_response.raise_for_status()
            
            # تحليل الصورة
            prompt = """حلل هذه الصورة:
1. صف المحتوى الرئيسي
2. اذكر 3 تفاصيل مهمة
3. اقترح حلولاً لأي مشاكل"""
            
            response = await asyncio.to_thread(
                model.generate_content,
                [prompt, image_response.content],
                generation_config={"temperature": 0.2, "max_output_tokens": 800}
            )
            return response.text
    except Exception as e:
        logger.error(f"خطأ في تحليل الصورة: {e}")
        return None

# 🌐 إعداد القائمة الدائمة
async def setup_menu_async():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                params=params,
                json=get_persistent_menu()
            )
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
    logger.info(f"بيانات الواردة: {data}")
    
    # تشغيل المعالجة في خيط منفصل
    Thread(target=process_webhook_data, args=(data,)).start()
    
    return jsonify({"status": "success"}), 200

def process_webhook_data(data):
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # تحديث وقت المحادثة
                conversations[sender_id] = datetime.now() + timedelta(hours=3)
                
                if 'message' in event:
                    message = event['message']
                    if 'text' in message:
                        asyncio.run(handle_text_async(sender_id, message['text']))
                    elif 'attachments' in message:
                        for att in message['attachments']:
                            if att['type'] == 'image':
                                asyncio.run(handle_image_async(sender_id, att['payload']['url']))
                
                elif 'postback' in event:
                    asyncio.run(handle_postback_async(sender_id, event['postback']['payload']))
    
    except Exception as e:
        logger.error(f"خطأ في معالجة البيانات: {e}")

async def handle_text_async(sender_id, text):
    text = text.strip().lower()
    
    if text.startswith('/'):
        await handle_command_async(sender_id, text)
    else:
        try:
            response = await asyncio.to_thread(
                model.generate_content,
                f"السؤال: {text}\n\nأجب بشكل مختصر ومنظم",
                generation_config={"temperature": 0.3, "max_output_tokens": 1000}
            )
            await send_message_async(sender_id, f"📝 الإجابة:\n\n{response.text}")
        except Exception as e:
            logger.error(f"خطأ في معالجة النص: {e}")
            await send_message_async(sender_id, "⚠️ حدث خطأ، يرجى المحاولة لاحقًا")

async def handle_image_async(sender_id, image_url):
    await send_message_async(sender_id, "⏳ جاري تحليل الصورة...")
    analysis = await analyze_image_async(image_url)
    
    if analysis:
        await send_message_async(sender_id, f"📸 نتائج التحليل:\n\n{analysis}")
    else:
        await send_message_async(sender_id, "⚠️ لم أستطع تحليل الصورة، يرجى إرسال صورة أوضح")

async def handle_command_async(sender_id, command):
    commands = {
        "/start": "🚀 مرحباً! أنا بوت الذكاء الاصطناعي. استخدم الأوامر:\n/help - للمساعدة\n/contact - للتواصل",
        "/help": "📚 الأوامر المتاحة:\n\n/start - بدء المحادثة\n/help - هذه التعليمات\n/contact - تواصل مع المطور",
        "/contact": f"📱 للتواصل مع المطور:\n\nInstagram: {MY_INSTAGRAM}"
    }
    
    if command in commands:
        await send_message_async(sender_id, commands[command])
    else:
        await send_message_async(sender_id, "⚠️ أمر غير معروف")

# تشغيل الإعدادات الأولية
asyncio.run(setup_menu_async())

if __name__ == '__main__':
    app.run(threaded=True)
