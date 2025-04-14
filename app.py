from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import langid
import time

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

# تخزين المحادثات
conversations = {}
executor = ThreadPoolExecutor(max_workers=20)

def detect_language(text):
    """تحديد لغة النص"""
    try:
        lang, _ = langid.classify(text)
        return lang
    except:
        return 'ar'

async def download_image(url):
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

async def analyze_image(image_path, lang='ar'):
    """تحليل الصورة باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        
        if lang == 'ar':
            prompt = "حلل هذه الصورة بدقة مع التركيز على التفاصيل المهمة"
        else:
            prompt = "Analyze this image in detail focusing on important elements"
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([prompt, img], generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=3000
            ))
        )
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except:
                pass

async def send_message_async(recipient_id, message_text):
    """إرسال رسالة بشكل غير متزامن"""
    max_length = 1900  # هامش أمان أقل من الحد الأقصى لفيسبوك
    chunks = [message_text[i:i+max_length] for i in range(0, len(message_text), max_length)]
    
    for chunk in chunks:
        url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": chunk}
        }
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                executor,
                lambda: requests.post(url, json=payload, timeout=7)
            )
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")

async def generate_response_async(prompt, lang='ar'):
    """إنشاء رد سريع باستخدام Gemini"""
    try:
        if lang == 'ar':
            prompt = f"أجب باختصار ودقة: {prompt}"
        else:
            prompt = f"Respond concisely and accurately: {prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2000
            ))
        )
        return response.text
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return None

async def process_image_message(sender_id, image_url, lang='ar'):
    """معالجة رسائل الصور"""
    image_path = await download_image(image_url)
    if not image_path:
        await send_message_async(sender_id, "⚠️ حدث خطأ في تحميل الصورة" if lang == 'ar' else "⚠️ Error loading image")
        return
    
    analysis = await analyze_image(image_path, lang)
    if analysis:
        await send_message_async(sender_id, analysis)
    else:
        await send_message_async(sender_id, "⚠️ تعذر تحليل الصورة" if lang == 'ar' else "⚠️ Couldn't analyze image")

async def process_text_message(sender_id, message_text, lang='ar'):
    """معالجة الرسائل النصية"""
    lower_msg = message_text.lower()
    
    # معالجة الأوامر السريعة
    if any(cmd in lower_msg for cmd in ['مساعدة', 'help']):
        help_msg = "أرسل صورة لتحليلها أو اكتب سؤالك" if lang == 'ar' else "Send an image or type your question"
        await send_message_async(sender_id, help_msg)
        return
    
    if any(cmd in lower_msg for cmd in ['اعادة', 'reset']):
        if sender_id in conversations:
            del conversations[sender_id]
        await send_message_async(sender_id, "تم إعادة التشغيل" if lang == 'ar' else "Bot reset")
        return
    
    # معالجة الأسئلة العادية
    response = await generate_response_async(message_text, lang)
    if response:
        await send_message_async(sender_id, response)
    else:
        await send_message_async(sender_id, "⚠️ حدث خطأ" if lang == 'ar' else "⚠️ An error occurred")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    asyncio.run(process_events(data))
    return jsonify({"status": "success"}), 200

async def process_events(data):
    """معالجة أحداث الويب هوك"""
    if not data.get('entry'):
        return

    for entry in data['entry']:
        for event in entry.get('messaging', []):
            try:
                sender_id = event['sender']['id']
                
                # تنظيف المحادثات القديمة
                if sender_id in conversations and conversations[sender_id]['expiry'] < datetime.now():
                    del conversations[sender_id]
                
                # تحديد اللغة
                lang = 'ar'
                if 'message' in event and 'text' in event['message']:
                    lang = detect_language(event['message']['text'])
                
                # بدء المحادثة إذا كانت جديدة
                if sender_id not in conversations:
                    conversations[sender_id] = {
                        'history': [],
                        'expiry': datetime.now() + timedelta(hours=5),
                        'lang': lang
                    }
                
                # معالجة الرسائل
                if 'message' in event:
                    if 'text' in event['message']:
                        await process_text_message(sender_id, event['message']['text'], lang)
                    elif 'attachments' in event['message']:
                        for attachment in event['message']['attachments']:
                            if attachment['type'] == 'image':
                                await process_image_message(sender_id, attachment['payload']['url'], lang)
                                
            except Exception as e:
                logger.error(f"Event processing error: {str(e)}")

if __name__ == '__main__':
    app.run(threaded=True)
