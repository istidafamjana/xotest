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
import langid  # مكتبة لتحديد اللغة

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

def detect_language(text):
    """تحديد لغة النص"""
    try:
        lang, _ = langid.classify(text)
        return lang
    except:
        return 'ar'  # افتراضي العربية إذا لم يتم التعرف

def get_language_response(lang):
    """إعداد ردود بناءً على اللغة"""
    responses = {
        'ar': {
            'welcome': "🎉 أهلاً بك في بوت الذكاء الاصطناعي!",
            'help': "📚 الأوامر المتاحة:\n\n• إرسال أي سؤال → إجابة ذكية\n• إرسال صورة → تحليل المحتوى",
            'image_prompt': "📸 الرجاء إدخال وصف لما تريد معرفته عن هذه الصورة:",
            'analysis': "📸 نتيجة التحليل:",
            'error': "⚠️ حدث خطأ، يرجى المحاولة مرة أخرى",
            'restart': "🔄 تم إعادة ضبط المحادثة بنجاح!"
        },
        'en': {
            'welcome': "🎉 Welcome to AI Chatbot!",
            'help': "📚 Available commands:\n\n• Ask any question → Smart answer\n• Send image → Analyze content",
            'image_prompt': "📸 Please describe what you want to know about this image:",
            'analysis': "📸 Analysis result:",
            'error': "⚠️ An error occurred, please try again",
            'restart': "🔄 Conversation reset successfully!"
        },
        'fr': {
            'welcome': "🎉 Bienvenue sur le chatbot IA!",
            'help': "📚 Commandes disponibles:\n\n• Posez une question → Réponse intelligente\n• Envoyez une image → Analyser le contenu",
            'image_prompt': "📸 Veuillez décrire ce que vous voulez savoir sur cette image:",
            'analysis': "📸 Résultat d'analyse:",
            'error': "⚠️ Une erreur s'est produite, veuillez réessayer",
            'restart': "🔄 Conversation réinitialisée avec succès!"
        }
    }
    return responses.get(lang, responses['ar'])  # افتراضي العربية إذا لم تكن اللغة مدعومة

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

async def analyze_image_with_description(image_path, description, lang='ar'):
    """تحليل الصورة مع الوصف باستخدام Gemini"""
    try:
        img = genai.upload_file(image_path)
        
        # إعداد الطلب بناءً على اللغة
        if lang == 'ar':
            prompt = f"""
            قم بتحليل هذه الصورة بناءً على الطلب التالي: {description}
            
            قدم إجابة مفصلة تشمل:
            1. وصف دقيق للصورة
            2. تحليل العناصر الرئيسية
            3. أي نصوص موجودة
            4. إجابة محددة على طلب المستخدم
            """
        elif lang == 'en':
            prompt = f"""
            Analyze this image based on the following request: {description}
            
            Provide a detailed response including:
            1. Accurate image description
            2. Analysis of main elements
            3. Any existing texts
            4. Specific answer to user's request
            """
        else:
            prompt = description  # استخدام الوصف كما هو للغات الأخرى
            
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
            os.unlink(image_path)

async def generate_text_async(prompt, lang='ar'):
    """إنشاء نص باستخدام Gemini مع مراعاة اللغة"""
    try:
        # إضافة توجيه للغة إذا لزم الأمر
        if lang != 'en':
            prompt = f"الرجاء الإجابة باللغة {lang}\n{prompt}" if lang == 'ar' else f"Please respond in {lang}\n{prompt}"
        
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

async def handle_command(sender_id, command, lang='ar'):
    """معالجة الأوامر بناءً على اللغة"""
    responses = get_language_response(lang)
    
    if command == "GET_STARTED":
        await send_message_async(sender_id, responses['welcome'], quick_replies=[
            {
                "content_type": "text",
                "title": "📖 المساعدة" if lang == 'ar' else "📖 Help",
                "payload": "HELP_CMD"
            }
        ])
        
    elif command == "HELP_CMD":
        await send_message_async(sender_id, responses['help'])
        
    elif command == "RESTART_CMD":
        if sender_id in conversations:
            del conversations[sender_id]
        await send_message_async(sender_id, responses['restart'])

async def handle_image(sender_id, image_url, lang='ar'):
    """معالجة الصور مع الطلب للوصف"""
    responses = get_language_response(lang)
    await send_message_async(sender_id, responses['image_prompt'])
    
    # تخزين رابط الصورة مؤقتًا في المحادثة
    if sender_id not in conversations:
        conversations[sender_id] = {
            'history': [],
            'expiry': datetime.now() + timedelta(hours=5),
            'pending_image': image_url,
            'lang': lang
        }
    else:
        conversations[sender_id]['pending_image'] = image_url
        conversations[sender_id]['expiry'] = datetime.now() + timedelta(hours=5)
        conversations[sender_id]['lang'] = lang

async def process_pending_image(sender_id, user_prompt):
    """معالجة الصورة المعلقة مع الطلب من المستخدم"""
    if sender_id in conversations and 'pending_image' in conversations[sender_id]:
        image_url = conversations[sender_id]['pending_image']
        lang = conversations[sender_id].get('lang', 'ar')
        responses = get_language_response(lang)
        
        del conversations[sender_id]['pending_image']
        
        image_path = await asyncio.get_event_loop().run_in_executor(
            executor,
            lambda: download_image(image_url)
        )
        
        if image_path:
            analysis = await analyze_image_with_description(image_path, user_prompt, lang)
            if analysis:
                await send_message_async(sender_id, f"{responses['analysis']}\n\n{analysis}")
            else:
                await send_message_async(sender_id, responses['error'])
        else:
            await send_message_async(sender_id, responses['error'])

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
                
                # تحديد لغة الرسالة
                lang = 'ar'  # افتراضي
                if 'message' in event and 'text' in event['message']:
                    lang = detect_language(event['message']['text'])
                
                # معالجة Postback (أزرار)
                if 'postback' in event:
                    await handle_command(sender_id, event['postback']['payload'], lang)
                    continue
                    
                # معالجة الرسائل
                if 'message' in event:
                    message = event['message']
                    
                    # معالجة الصور
                    if 'attachments' in message:
                        for attachment in message['attachments']:
                            if attachment['type'] == 'image':
                                await handle_image(sender_id, attachment['payload']['url'], lang)
                        continue
                    
                    # معالجة النصوص
                    if 'text' in message:
                        user_message = message['text'].strip()
                        
                        # التحقق من وجود صورة معلقة
                        if sender_id in conversations and 'pending_image' in conversations[sender_id]:
                            await process_pending_image(sender_id, user_message)
                            continue
                        
                        # الأوامر النصية
                        if user_message.lower() in ['ابدأ', 'بدء', 'start', 'commencer']:
                            await handle_command(sender_id, "GET_STARTED", lang)
                        elif user_message.lower() in ['مساعدة', 'مساعده', 'help', 'aide']:
                            await handle_command(sender_id, "HELP_CMD", lang)
                        elif user_message.lower() in ['اعادة', 'إعادة', 'restart', 'réinitialiser']:
                            await handle_command(sender_id, "RESTART_CMD", lang)
                        else:
                            # معالجة الأسئلة النصية مع الاحتفاظ بالسياق
                            try:
                                # إضافة سياق المحادثة إذا موجود
                                if sender_id in conversations:
                                    context = "\n".join(conversations[sender_id]['history'][-3:])
                                    user_message = f"{context}\n\n{user_message}"
                                
                                # الحصول على الإجابة من Gemini
                                response_text = await generate_text_async(user_message, lang)
                                
                                # تخزين المحادثة
                                if sender_id not in conversations:
                                    conversations[sender_id] = {
                                        'history': [],
                                        'expiry': datetime.now() + timedelta(hours=5),
                                        'lang': lang
                                    }
                                
                                conversations[sender_id]['history'].append(f"User: {message['text']}")
                                conversations[sender_id]['history'].append(f"Bot: {response_text}")
                                conversations[sender_id]['expiry'] = datetime.now() + timedelta(hours=5)
                                
                                # إرسال الإجابة
                                await send_message_async(sender_id, response_text)
                                
                            except Exception as e:
                                logger.error(f"AI Error: {str(e)}")
                                responses = get_language_response(lang)
                                await send_message_async(sender_id, responses['error'])
    
    except Exception as e:
        logger.error(f"Webhook Error: {str(e)}")

@app.route('/')
def home():
    return "Facebook Messenger AI Bot with Multi-Language Support!"

if __name__ == '__main__':
    app.run(threaded=True)
