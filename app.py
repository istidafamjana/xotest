from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

app = Flask(__name__)

# التوكنات والمفاتيح (ضع قيمك هنا)
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"  # توكن صفحتك
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"  # توكن التحقق
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"  # مفتاح Gemini

# تهيئة نموذج Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# تخزين المحادثات
conversations = {}

# إنشاء واجهة الترحيب
def get_welcome_screen():
    return {
        "attachment": {
            "type": "template",
            "payload": {
                "template_type": "generic",
                "elements": [{
                    "title": "مرحبًا بك في بوت الذكاء الاصطناعي! 🤖",
                    "image_url": "https://l.top4top.io/p_3056965410.png",  # رابط صورة اختياري
                    "subtitle": "يمكنك طرح أي سؤال وسأساعدك بالإجابة باستخدام أحدث تقنيات الذكاء الاصطناعي",
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "بدء المحادثة 🚀",
                            "payload": "/start"
                        },
                        {
                            "type": "postback",
                            "title": "رؤية الأوامر ℹ️",
                            "payload": "/help"
                        },
                        {
                            "type": "web_url",
                            "title": "الدليل الكامل 📚",
                            "url": "https://example.com/guide"  # رابط دليل المستخدم
                        }
                    ]
                }]
            }
        }
    }

# أزرار القائمة الرئيسية
def get_main_buttons():
    return [
        {
            "type": "postback",
            "title": "تعليمات الاستخدام 📖",
            "payload": "/help"
        },
        {
            "type": "postback",
            "title": "إعادة البدء 🔄",
            "payload": "/restart"
        },
        {
            "type": "postback",
            "title": "معلومات البوت ℹ️",
            "payload": "/about"
        }
    ]

# إرسال رسالة مع الواجهة
def send_message(recipient_id, message_text, buttons=None, welcome=False):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    
    if welcome:
        payload = {
            "recipient": {"id": recipient_id},
            "message": get_welcome_screen()
        }
    else:
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message_text}
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
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending message: {str(e)}")

# معالجة الأوامر
def handle_command(sender_id, command):
    if command == "/start":
        send_message(sender_id, 
                    "مرحبًا بك! أنا بوت الذكاء الاصطناعي. يمكنك:\n"
                    "- طرح أي سؤال للحصول على إجابة ذكية\n"
                    "- استخدام /restart لبدء محادثة جديدة\n"
                    "- استخدام /help لرؤية الأوامر المتاحة",
                    get_main_buttons())
        
    elif command == "/help":
        help_text = "📋 الأوامر المتاحة:\n\n"
        help_text += "🔹 /start - بدء محادثة جديدة\n"
        help_text += "🔹 /help - عرض هذه التعليمات\n"
        help_text += "🔹 /restart - إعادة تعيين المحادثة\n"
        help_text += "🔹 /about - معلومات عن البوت\n\n"
        help_text += "يمكنك أيضًا كتابة أي سؤال مباشرة وسأجيبك فورًا!"
        send_message(sender_id, help_text, get_main_buttons())
        
    elif command == "/about":
        about_text = "🤖 معلومات البوت:\n\n"
        about_text += "الإصدار: 2.0\n"
        about_text += "التقنية: Gemini AI من جوجل\n"
        about_text += "الميزات:\n"
        about_text += "- فهم العميق للأسئلة\n"
        about_text += "- دعم المحادثات الطويلة\n"
        about_text += "- واجهة تفاعلية سهلة"
        send_message(sender_id, about_text, get_main_buttons())
        
    elif command == "/restart":
        if sender_id in conversations:
            del conversations[sender_id]
        send_message(sender_id, "تم إعادة ضبط المحادثة بنجاح. يمكنك البدء من جديد!", get_main_buttons())

# نقطة نهاية الويب هوك
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            return request.args.get('hub.challenge')
        return "Verification failed", 403
    
    data = request.get_json()
    
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event['sender']['id']
                
                # إرسال واجهة الترحيب عند أول تفاعل
                if 'postback' in event and event['postback'].get('title') == "Get Started":
                    send_message(sender_id, "", welcome=True)
                    continue
                    
                # تحديد نوع الرسالة
                if 'message' in event:
                    user_message = event['message'].get('text', '')
                elif 'postback' in event:
                    user_message = event['postback'].get('payload', '')
                else:
                    continue
                
                # معالجة الأوامر
                if user_message.lower() in ["/start", "/help", "/about", "/restart"]:
                    handle_command(sender_id, user_message.lower())
                else:
                    # معالجة الأسئلة العادية
                    if sender_id not in conversations:
                        send_message(sender_id, 
                                   "مرحبًا! أنا هنا لمساعدتك. يمكنك البدء بطرح سؤالك مباشرة، "
                                   "أو كتابة /help لرؤية الأوامر المتاحة.",
                                   get_main_buttons())
                        conversations[sender_id] = {
                            "history": [],
                            "expiry": datetime.now() + timedelta(hours=1)
                        }
                    
                    try:
                        response = model.generate_content(user_message)
                        send_message(sender_id, response.text, get_main_buttons())
                    except Exception as e:
                        print(f"AI Error: {str(e)}")
                        send_message(sender_id, 
                                   "عذرًا، حدث خطأ أثناء معالجة سؤالك. يرجى المحاولة مرة أخرى.",
                                   get_main_buttons())
    
    except Exception as e:
        print(f"Webhook Error: {str(e)}")
    
    return jsonify({"status": "success"}), 200
    
if __name__ == "__main__":
    app.run(debug=True)
