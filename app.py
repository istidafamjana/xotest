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
executor = ThreadPoolExecutor(max_workers=20)  # زيادة عدد العمال لتحسين الأداء

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

async def send_message_async(recipient_id, message_text):
    """إرسال رسالة بشكل غير متزامن مع دعم الردود الطويلة"""
    max_length = 2000  # الحد الأقصى لطول الرسالة في فيسبوك
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
                lambda: requests.post(url, json=payload, timeout=5)
            )
        except Exception as e:
            logger.error(f"Error sending message chunk: {str(e)}")

async def generate_response_async(prompt, lang='ar'):
    """إنشاء رد سريع باستخدام Gemini مع تحسينات الأداء"""
    try:
        start_time = time.time()
        
        # إضافة توجيه للسرعة والدقة
        prompt = f"الرجاء الإجابة بسرعة وبدقة: {prompt}" if lang == 'ar' else f"Please respond quickly and accurately: {prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # تقليل العشوائية للإجابات السريعة
                max_output_tokens=4000  # زيادة الحد للردود الطويلة
            ))
        )
        
        logger.info(f"Generation time: {time.time() - start_time:.2f} seconds")
        return response.text
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return None

async def handle_new_user(sender_id):
    """معالجة المستخدم الجديد مع إرسال رسالة ترحيبية"""
    if sender_id not in conversations:
        conversations[sender_id] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'lang': 'ar',
            'is_new': True
        }
        await send_message_async(sender_id, WELCOME_MESSAGE)
        
        # إرسال رسالة متابعة بعد 5 ثواني
        await asyncio.sleep(5)
        await send_message_async(sender_id, "💡 لا تتردد في البدء بإرسال سؤالك الأول أو صورة لتحليلها!")
    else:
        conversations[sender_id]['is_new'] = False

async def process_message(sender_id, message_text, lang='ar'):
    """معالجة الرسائل بكفاءة"""
    try:
        # معالجة سريعة للأوامر القصيرة
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
        
        # توليد الرد بسرعة
        response_text = await generate_response_async(message_text, lang)
        
        if response_text:
            # تخزين المحادثة
            if sender_id not in conversations:
                conversations[sender_id] = {
                    'history': [],
                    'expiry': datetime.now() + timedelta(hours=5),
                    'lang': lang
                }
            
            conversations[sender_id]['history'].append(message_text)
            conversations[sender_id]['history'] = conversations[sender_id]['history'][-3:]  # الاحتفاظ بآخر 3 رسائل فقط
            
            # إرسال الرد مع تقسيمه إذا كان طويلاً
            await send_message_async(sender_id, response_text)
            
    except Exception as e:
        logger.error(f"Message processing error: {str(e)}")
        await send_message_async(sender_id, "⚠️ حدث خطأ أثناء معالجة طلبك، يرجى المحاولة لاحقاً")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    # معالجة الأحداث بشكل غير متزامن
    asyncio.run(process_events(data))
    return jsonify({"status": "success"}), 200

async def process_events(data):
    """معالجة أحداث الويب هوك بكفاءة"""
    if not data.get('entry'):
        return

    for entry in data['entry']:
        for event in entry.get('messaging', []):
            try:
                sender_id = event['sender']['id']
                
                # تنظيف المحادثات القديمة
                if sender_id in conversations and conversations[sender_id]['expiry'] < datetime.now():
                    del conversations[sender_id]
                
                # معالجة المستخدم الجديد
                await handle_new_user(sender_id)
                
                # تحديد اللغة
                lang = 'ar'
                if 'message' in event and 'text' in event['message']:
                    lang = detect_language(event['message']['text'])
                
                # معالجة الرسائل
                if 'message' in event:
                    if 'text' in event['message']:
                        await process_message(sender_id, event['message']['text'], lang)
                    elif 'attachments' in event['message']:
                        for attachment in event['message']['attachments']:
                            if attachment['type'] == 'image':
                                await send_message_async(sender_id, "📸 جاري معالجة الصورة...")
                                # هنا يمكنك إضافة معالجة الصورة
                                
            except Exception as e:
                logger.error(f"Event processing error: {str(e)}")

if __name__ == '__main__':
    app.run(threaded=True)
