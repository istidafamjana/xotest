from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
import tempfile
import urllib.request
import os
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# تكوين السجلات
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح (يجب تخزينها في متغيرات البيئة)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات (لمدة 5 ساعات)
conversations = {}
executor = ThreadPoolExecutor(max_workers=10)

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

async def analyze_image_async(image_path, prompt_text=None):
    """تحليل الصورة باستخدام Gemini بشكل غير متزامن"""
    try:
        img = genai.upload_file(image_path)
        
        if not prompt_text:
            prompt_text = "قم بتحليل هذه الصورة وقدم وصفًا دقيقًا للمحتوى"
        
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content([prompt_text, img])
        )
        return response.text
    except Exception as e:
        logger.error(f"Error analyzing image: {str(e)}")
        return None
    finally:
        if image_path and os.path.exists(image_path):
            os.unlink(image_path)

async def generate_text_async(prompt):
    """إنشاء نص باستخدام Gemini بشكل غير متزامن"""
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: model.generate_content(prompt)
        )
        return response.text
    except Exception as e:
        logger.error(f"Error generating text: {str(e)}")
        return None

async def send_message_async(recipient_id, message_text, buttons=None, quick_replies=None):
    """إرسال رسالة بشكل غير متزامن"""
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    payload = {
        "recipient": {"id": recipient_id},
        "message": {}
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
    elif quick_replies:
        payload["message"] = {
            "text": message_text,
            "quick_replies": quick_replies
        }
    else:
        payload["message"] = {"text": message_text}

    try:
        await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: requests.post(url, json=payload).raise_for_status()
        )
        return True
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        return False

def get_main_menu():
    """القائمة الرئيسية"""
    return [
        {
            "type": "postback",
            "title": "🎓 التعليمات",
            "payload": "HELP_CMD"
        },
        {
            "type": "postback",
            "title": "🔄 إعادة البدء",
            "payload": "RESTART_CMD"
        }
    ]

async def handle_command(sender_id, command):
    """معالجة الأوامر بشكل غير متزامن"""
    if command == "GET_STARTED":
        welcome_msg = """
        🎉 أهلاً بك في بوت الذكاء الاصطناعي!
        
        ✨ يمكنك:
        - إرسال أي سؤال للحصول على إجابة ذكية
        - إرسال صورة لتحليل محتواها
        
        اختر أحد الخيارات:
        """
        await send_message_async(sender_id, welcome_msg, quick_replies=[
            {
                "content_type": "text",
                "title": "📖 التعليمات",
                "payload": "HELP_CMD"
            }
        ])
        
    elif command == "HELP_CMD":
        help_msg = """
        📚 الأوامر المتاحة:
        
        • إرسال أي سؤال → إجابة ذكية
        • إرسال صورة → تحليل المحتوى
        • "مساعدة" → عرض هذه التعليمات
        • "إعادة" → بدء محادثة جديدة
        """
        await send_message_async(sender_id, help_msg, buttons=get_main_menu())
        
    elif command == "RESTART_CMD":
        if sender_id in conversations:
            del conversations[sender_id]
        await send_message_async(sender_id, "🔄 تم إعادة ضبط المحادثة بنجاح!", buttons=get_main_menu())

async def handle_image(sender_id, image_url):
    """معالجة الصور بشكل غير متزامن"""
    # طلب من المستخدم إدخال ما يريده من الصورة
    await send_message_async(sender_id, "📸 الرجاء إدخال ما تريد معرفته عن هذه الصورة:")
    
    # تخزين رابط الصورة مؤقتًا في المحادثة
    if sender_id not in conversations:
        conversations[sender_id] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'pending_image': image_url
        }
    else:
        conversations[sender_id]['pending_image'] = image_url
        conversations[sender_id]['expiry'] = datetime.now() + timedelta(hours=5)

async def process_pending_image(sender_id, user_prompt):
    """معالجة الصورة المعلقة مع الطلب من المستخدم"""
    if sender_id in conversations and 'pending_image' in conversations[sender_id]:
        image_url = conversations[sender_id]['pending_image']
        del conversations[sender_id]['pending_image']
        
        image_path = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: download_image(image_url)
        )
        
        if image_path:
            analysis = await analyze_image_async(image_path, user_prompt)
            if analysis:
                await send_message_async(sender_id, f"📸 نتيجة التحليل:\n\n{analysis}")
            else:
                await send_message_async(sender_id, "⚠️ لم أتمكن من تحليل الصورة، يرجى المحاولة مرة أخرى")
        else:
            await send_message_async(sender_id, "⚠️ حدث خطأ في تحميل الصورة، يرجى إرسالها مرة أخرى")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """نقطة نهاية الويب هوك"""
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    # معالجة الأحداث بشكل غير متزامن
    asyncio.run(process_webhook_events(data))
    
    return jsonify({"status": "success"}), 200

async def process_webhook_events(data):
    """معالجة أحداث الويب هوك بشكل غير متزامن"""
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # تنظيف المحادثات القديمة
                now = datetime.now()
                if sender_id in conversations and conversations[sender_id]['expiry'] < now:
                    del conversations[sender_id]
                
                # معالجة Postback (أزرار)
                if 'postback' in event:
                    await handle_command(sender_id, event['postback']['payload'])
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                await handle_image(sender_id, attachment['payload']['url'])
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip().lower()
                        
                        # التحقق من وجود صورة معلقة
                        if sender_id in conversations and 'pending_image' in conversations[sender_id]:
                            await process_pending_image(sender_id, user_message)
                            continue
                        
                        # الأوامر النصية
                        if user_message in ['ابدأ', 'بدء', 'start']:
                            await handle_command(sender_id, "GET_STARTED")
                        elif user_message in ['مساعدة', 'مساعده', 'help']:
                            await handle_command(sender_id, "HELP_CMD")
                        elif user_message in ['اعادة', 'إعادة', 'restart']:
                            await handle_command(sender_id, "RESTART_CMD")
                        else:
                            # معالجة الأسئلة النصية مع الاحتفاظ بالسياق
                            try:
                                # إضافة سياق المحادثة إذا موجود
                                if sender_id in conversations:
                                    context = "\n".join(conversations[sender_id]['history'][-3:])
                                    user_message = f"السياق السابق:\n{context}\n\nالسؤال الجديد: {user_message}"
                                
                                # الحصول على الإجابة من Gemini
                                response_text = await generate_text_async(user_message)
                                
                                # تخزين المحادثة
                                if sender_id not in conversations:
                                    conversations[sender_id] = {
                                        'history': [],
                                        'expiry': datetime.now() + timedelta(hours=5)
                                    }
                                
                                conversations[sender_id]['history'].append(f"أنت: {message['text']}")
                                conversations[sender_id]['history'].append(f"البوت: {response_text}")
                                
                                # إرسال الإجابة
                                await send_message_async(sender_id, response_text, buttons=get_main_menu())
                                
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                await send_message_async(sender_id, "⚠️ حدث خطأ أثناء معالجة سؤالك، يرجى المحاولة لاحقاً")
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")

@app.route('/')
def home():
    return "Facebook Messenger AI Bot is Running with Async Support!"

if __name__ == '__main__':
    app.run()
