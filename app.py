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
PAGE_ACCESS_TOKEN = "YOUR_PAGE_ACCESS_TOKEN"
VERIFY_TOKEN = "YOUR_VERIFY_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات (تخزين آخر 20 رسالة لكل مستخدم)
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

async def analyze_image_with_prompt(image_path, user_prompt, lang='ar'):
    """تحليل الصورة بناءً على وصف المستخدم"""
    try:
        img = genai.upload_file(image_path)
        
        if lang == 'ar':
            prompt = f"""
            بناءً على طلب المستخدم: {user_prompt}
            
            قم بتحليل هذه الصورة مع التركيز على:
            1. ما طلبه المستخدم بالتحديد
            2. التفاصيل المتعلقة بالطلب
            3. أي معلومات إضافية مفيدة
            """
        else:
            prompt = f"""
            Based on user request: {user_prompt}
            
            Analyze this image focusing on:
            1. Exactly what the user asked
            2. Relevant details
            3. Any additional useful information
            """
            
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
    max_length = 1900
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

async def generate_response_async(prompt, context=None, lang='ar'):
    """إنشاء رد باستخدام السياق"""
    try:
        if context:
            if lang == 'ar':
                prompt = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {prompt}"
            else:
                prompt = f"Previous context:\n{context}\n\nNew question: {prompt}"
        
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

async def handle_image_request(sender_id, image_url, lang='ar'):
    """طلب وصف الصورة من المستخدم"""
    if lang == 'ar':
        message = "📸 لتحليل الصورة، الرجاء إرسال وصف لما تريد معرفته عنها:"
    else:
        message = "📸 To analyze the image, please describe what you want to know about it:"
    
    await send_message_async(sender_id, message)
    
    # تخزين معلومات الصورة مؤقتاً
    if sender_id not in conversations:
        conversations[sender_id] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'lang': lang,
            'pending_image': image_url
        }
    else:
        conversations[sender_id]['pending_image'] = image_url
        conversations[sender_id]['expiry'] = datetime.now() + timedelta(hours=5)

async def process_image_with_description(sender_id, description, lang='ar'):
    """معالجة الصورة بعد الحصول على الوصف"""
    if sender_id not in conversations or 'pending_image' not in conversations[sender_id]:
        return
    
    image_url = conversations[sender_id]['pending_image']
    del conversations[sender_id]['pending_image']
    
    await send_message_async(sender_id, "🔍 جاري تحليل الصورة..." if lang == 'ar' else "🔍 Analyzing image...")
    
    image_path = await download_image(image_url)
    if not image_path:
        await send_message_async(sender_id, "⚠️ تعذر تحميل الصورة" if lang == 'ar' else "⚠️ Failed to load image")
        return
    
    analysis = await analyze_image_with_prompt(image_path, description, lang)
    if analysis:
        # إضافة التحليل إلى سجل المحادثة
        conversations[sender_id]['history'].append(f"User image analysis request: {description}")
        conversations[sender_id]['history'].append(f"Image analysis: {analysis}")
        
        # تقليل السجل إذا تجاوز 20 رسالة (10 زوج من الرسائل)
        if len(conversations[sender_id]['history']) > 20:
            conversations[sender_id]['history'] = conversations[sender_id]['history'][-20:]
        
        await send_message_async(sender_id, analysis)
    else:
        await send_message_async(sender_id, "⚠️ تعذر تحليل الصورة" if lang == 'ar' else "⚠️ Failed to analyze image")

async def process_text_message(sender_id, message_text, lang='ar'):
    """معالجة الرسائل النصية"""
    # التحقق أولاً إذا كانت هناك صورة تنتظر وصفاً
    if sender_id in conversations and 'pending_image' in conversations[sender_id]:
        await process_image_with_description(sender_id, message_text, lang)
        return
    
    # معالجة الأوامر السريعة
    lower_msg = message_text.lower()
    if any(cmd in lower_msg for cmd in ['مساعدة', 'help']):
        help_msg = "أرسل صورة ثم اتبعها بوصف لما تريد معرفته، أو اكتب سؤالك مباشرة" if lang == 'ar' else "Send an image followed by your request, or type your question"
        await send_message_async(sender_id, help_msg)
        return
    
    if any(cmd in lower_msg for cmd in ['اعادة', 'reset']):
        if sender_id in conversations:
            del conversations[sender_id]
        await send_message_async(sender_id, "تم إعادة التشغيل" if lang == 'ar' else "Bot reset")
        return
    
    # معالجة الأسئلة العادية مع السياق
    context = None
    if sender_id in conversations and conversations[sender_id]['history']:
        context = "\n".join(conversations[sender_id]['history'][-10:])  # استخدام آخر 10 رسائل كسياق
    
    response = await generate_response_async(message_text, context, lang)
    if response:
        # تحديث سجل المحادثة
        if sender_id not in conversations:
            conversations[sender_id] = {
                'history': [],
                'expiry': datetime.now() + timedelta(hours=5),
                'lang': lang
            }
        
        conversations[sender_id]['history'].append(f"User: {message_text}")
        conversations[sender_id]['history'].append(f"Bot: {response}")
        
        # الحفاظ على آخر 20 رسالة كحد أقصى
        if len(conversations[sender_id]['history']) > 20:
            conversations[sender_id]['history'] = conversations[sender_id]['history'][-20:]
        
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
                now = datetime.now()
                if sender_id in conversations and conversations[sender_id]['expiry'] < now:
                    del conversations[sender_id]
                
                # تحديد اللغة
                lang = 'ar'
                if 'message' in event and 'text' in event['message']:
                    lang = detect_language(event['message']['text'])
                
                # معالجة الرسائل
                if 'message' in event:
                    if 'text' in event['message']:
                        await process_text_message(sender_id, event['message']['text'], lang)
                    elif 'attachments' in event['message']:
                        for attachment in event['message']['attachments']:
                            if attachment['type'] == 'image':
                                await handle_image_request(sender_id, attachment['payload']['url'], lang)
                                
            except Exception as e:
                logger.error(f"Event processing error: {str(e)}")

if __name__ == '__main__':
    app.run(threaded=True)
