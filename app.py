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
import time  # إضافة مكتبة time

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

# رسالة الترحيب المخصصة
WELCOME_MESSAGE = """
🌟 مرحباً بك في بوت الذكاء الاصطناعي المتقدم!

🎯 يمكنك الاستفادة من الميزات التالية:
- تحليل الصور بدقة عالية
- إجابة على أسئلتك بذكاء
- دعم متعدد اللغات

🔍 جرب إرسال:
- سؤال لتحصل على إجابة ذكية
- صورة لتحليل محتواها
- كلمة "مساعدة" لعرض الأوامر

نحن هنا لمساعدتك على مدار الساعة! 😊
"""

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
            prompt = """
            قم بتحليل هذه الصورة بدقة وأجب بالعربية:
            1. صف المحتوى الرئيسي
            2. اذكر التفاصيل المهمة
            3. اقرأ أي نص موجود
            4. قدم نصائح أو حلول إذا لزم الأمر
            """
        else:
            prompt = """
            Analyze this image in detail and respond in English:
            1. Describe the main content
            2. Mention important details
            3. Read any existing text
            4. Provide advice or solutions if needed
            """
            
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([prompt, img])
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
    """إرسال رسالة بشكل غير متزامن مع دعم الردود الطويلة"""
    max_length = 2000
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
                lambda: requests.post(url, json=payload, timeout=10)
            )
        except Exception as e:
            logger.error(f"Error sending message chunk: {str(e)}")

async def generate_response_async(prompt, lang='ar'):
    """إنشاء رد سريع باستخدام Gemini"""
    try:
        start_time = time.time()
        
        if lang == 'ar':
            prompt = f"الرجاء الإجابة بسرعة وبدقة بالعربية: {prompt}"
        else:
            prompt = f"Please respond quickly and accurately in English: {prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=4000
            ))
        )
        
        logger.info(f"Generation time: {time.time() - start_time:.2f} seconds")
        return response.text
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return None

async def handle_new_user(sender_id):
    """معالجة المستخدم الجديد"""
    if sender_id not in conversations:
        conversations[sender_id] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'lang': 'ar',
            'is_new': True
        }
        await send_message_async(sender_id, WELCOME_MESSAGE)
        await asyncio.sleep(5)
        await send_message_async(sender_id, "💡 لا تتردد في البدء بإرسال سؤالك الأول أو صورة لتحليلها!")

async def process_image_message(sender_id, image_url, lang='ar'):
    """معالجة رسائل الصور"""
    try:
        await send_message_async(sender_id, "🔍 جاري تحليل الصورة، الرجاء الانتظار...")
        
        image_path = await download_image(image_url)
        if not image_path:
            await send_message_async(sender_id, "⚠️ تعذر تحميل الصورة، يرجى إعادة المحاولة")
            return
        
        analysis = await analyze_image(image_path, lang)
        if analysis:
            await send_message_async(sender_id, f"📸 نتيجة تحليل الصورة:\n\n{analysis}")
        else:
            await send_message_async(sender_id, "⚠️ تعذر تحليل الصورة، يرجى إرسال صورة أخرى")
    except Exception as e:
        logger.error(f"Image processing error: {str(e)}")
        await send_message_async(sender_id, "⚠️ حدث خطأ أثناء معالجة الصورة")

async def process_text_message(sender_id, message_text, lang='ar'):
    """معالجة الرسائل النصية"""
    try:
        lower_msg = message_text.lower()
        
        if any(cmd in lower_msg for cmd in ['مساعدة', 'مساعده', 'help', 'aide']):
            help_msg = "📚 الأوامر المتاحة:\n\n• إرسال سؤال → إجابة ذكية\n• إرسال صورة → تحليل المحتوى\n• 'اعادة' → بدء محادثة جديدة"
            await send_message_async(sender_id, help_msg)
            return
        
        if any(cmd in lower_msg for cmd in ['اعادة', 'إعادة', 'restart', 'réinitialiser']):
            if sender_id in conversations:
                del conversations[sender_id]
            await send_message_async(sender_id, "🔄 تم إعادة ضبط المحادثة بنجاح!")
            return
        
        response_text = await generate_response_async(message_text, lang)
        
        if response_text:
            if sender_id not in conversations:
                conversations[sender_id] = {
                    'history': [],
                    'expiry': datetime.now() + timedelta(hours=5),
                    'lang': lang
                }
            
            conversations[sender_id]['history'].append(message_text)
            conversations[sender_id]['history'] = conversations[sender_id]['history'][-3:]
            
            await send_message_async(sender_id, response_text)
            
    except Exception as e:
        logger.error(f"Message processing error: {str(e)}")
        await send_message_async(sender_id, "⚠️ حدث خطأ أثناء معالجة طلبك")

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
                
                if sender_id in conversations and conversations[sender_id]['expiry'] < datetime.now():
                    del conversations[sender_id]
                
                await handle_new_user(sender_id)
                
                lang = 'ar'
                if 'message' in event and 'text' in event['message']:
                    lang = detect_language(event['message']['text'])
                
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
