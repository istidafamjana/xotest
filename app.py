from flask import Flask, request, jsonify
import requests
import google.generativeai as genai
from datetime import datetime, timedelta
import logging
from io import BytesIO
import asyncio
from threading import Thread
import time

app = Flask(__name__)

# 🔧 Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔑 Tokens and configuration
PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"
GEMINI_API_KEY = "AIzaSyA1TKhF1NQskLCqXR3O_cpISpTn9I8R-IU"
MY_INSTAGRAM = "https://www.instagram.com/your_username"  # Replace with your Instagram

# ⚙️ Initialize Gemini model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

# 💾 Conversation storage (3 hours timeout)
CONVERSATION_TIMEOUT = timedelta(hours=3)
conversations = {}

# 🎨 Menu design
def get_persistent_menu():
    return {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {
                        "type": "postback",
                        "title": "🏠 Start /start",
                        "payload": "/start"
                    },
                    {
                        "type": "postback",
                        "title": "❓ Help /help",
                        "payload": "/help"
                    },
                    {
                        "type": "web_url",
                        "title": "📱 Contact /contact",
                        "url": MY_INSTAGRAM,
                        "webview_height_ratio": "full"
                    }
                ]
            }
        ]
    }

def get_quick_replies():
    return [
        {"content_type": "text", "title": "🔍 Start", "payload": "/start"},
        {"content_type": "text", "title": "🆘 Help", "payload": "/help"},
        {"content_type": "text", "title": "🔄 Restart", "payload": "/restart"}
    ]

# ✉️ Message sending with improved error handling
def send_message(recipient_id, text, quick_replies=False):
    url = f"https://graph.facebook.com/v17.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    # Split long messages
    max_length = 1900  # Slightly below 2000 for safety
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
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Failed to send message part: {e}")
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
        logger.error(f"Failed to send message: {e}")
        return False

# 🖼️ Enhanced image analysis with better error handling
async def analyze_image_async(image_url):
    try:
        logger.info(f"Starting image analysis from URL: {image_url}")
        
        # Download image with improved headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = await asyncio.to_thread(
            requests.get, 
            image_url, 
            headers=headers, 
            timeout=20
        )
        response.raise_for_status()
        
        # Verify content type
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError("File is not an image")
        
        # Analyze with clear instructions
        prompt = """Analyze this image and provide:
1. Brief description (1 sentence)
2. 3 potential issues
3. 3 suggested solutions

Keep response concise and in bullet points"""
        
        response = model.generate_content(
            [prompt, response.content],
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 600  # Keep responses shorter
            }
        )
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"Image download error: {e}")
        return "⚠️ Couldn't download image. Please check:\n- URL is valid\n- Image isn't too large\n- Try again later"
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        return "⚠️ Unexpected error analyzing image. Please try another image."

# 🌐 Setup persistent menu
def setup_menu():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    try:
        response = requests.post(url, params=params, json=get_persistent_menu())
        response.raise_for_status()
        logger.info("✅ Persistent menu setup successfully")
    except Exception as e:
        logger.error(f"❌ Failed to setup menu: {e}")

# 🌐 Webhook endpoint
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        if verify_token == VERIFY_TOKEN:
            logger.info("✅ Webhook verified")
            return request.args.get('hub.challenge')
        logger.error("❌ Invalid verify token")
        return "Verification failed", 403
    
    data = request.get_json()
    if not data:
        logger.error("❌ Empty request data")
        return jsonify({"status": "error", "message": "No data"}), 400
    
    logger.info(f"📩 Received data: {data}")
    
    # Process in background thread
    Thread(target=process_webhook_data, args=(data,)).start()
    
    return jsonify({"status": "success"}), 200

def process_webhook_data(data):
    try:
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                if not sender_id:
                    continue
                
                # Update conversation timestamp
                conversations[sender_id] = {
                    "last_active": datetime.now(),
                    "expiry": datetime.now() + CONVERSATION_TIMEOUT
                }
                
                # Handle different message types
                if 'message' in event:
                    handle_message(sender_id, event['message'])
                elif 'postback' in event:
                    handle_postback(sender_id, event['postback']['payload'])
    
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}")

def handle_message(sender_id, message):
    if 'text' in message:
        handle_text(sender_id, message['text'])
    elif 'attachments' in message:
        for att in message['attachments']:
            if att['type'] == 'image':
                handle_image(sender_id, att['payload']['url'])

def handle_text(sender_id, text):
    text = text.strip()
    logger.info(f"📝 Processing text from {sender_id}: {text}")
    
    if text.lower().startswith('/'):
        handle_command(sender_id, text.lower())
    else:
        try:
            # Get conversation context
            context = ""
            if sender_id in conversations and "history" in conversations[sender_id]:
                context = "\n".join(
                    f"{msg['role']}: {msg['content']}" 
                    for msg in conversations[sender_id]["history"][-3:]
                )
            
            prompt = f"""Previous conversation:
{context}

New question: {text}

Please respond concisely with bullet points"""
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 800
                }
            )
            reply = response.text
            
            # Update conversation history
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
            logger.error(f"❌ Text processing error: {e}")
            send_message(sender_id, "⚠️ Error processing your request. Please try again.")

def handle_image(sender_id, image_url):
    logger.info(f"🖼️ Processing image from {sender_id}")
    send_message(sender_id, "🔍 Analyzing image, please wait...")
    
    analysis = asyncio.run(analyze_image_async(image_url))
    
    if analysis and not analysis.startswith("⚠️"):
        # Store analysis in conversation history
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
        
        send_message(sender_id, f"📊 Analysis results:\n\n{analysis}")
    else:
        send_message(sender_id, analysis if analysis else "⚠️ Couldn't analyze image. Please send a clearer image.")

def handle_command(sender_id, command):
    command_responses = {
        "/start": "🚀 Welcome! I'm your AI assistant. You can:\n- Ask me anything\n- Send images for analysis\n- Use the commands below",
        "/help": "📋 Available commands:\n\n/start - Start new chat\n/help - Show this help\n/contact - Contact developer\n/restart - Reset conversation",
        "/contact": f"📱 Contact the developer:\n\nInstagram: {MY_INSTAGRAM}\n\nI'll respond as soon as possible!",
        "/restart": "🔄 Conversation reset\n\nYour chat history has been cleared"
    }
    
    if command in command_responses:
        send_message(sender_id, command_responses[command])
    else:
        send_message(sender_id, "⚠️ Unknown command. Use /help to see available commands")

# Cleanup old conversations
def cleanup_old_conversations():
    while True:
        try:
            now = datetime.now()
            expired = [uid for uid, conv in conversations.items() 
                      if conv['expiry'] < now]
            
            for uid in expired:
                del conversations[uid]
                logger.info(f"🧹 Cleaned expired conversation for {uid}")
            
            time.sleep(3600)  # Run hourly
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
            time.sleep(60)

# Start cleanup thread
cleanup_thread = Thread(target=cleanup_old_conversations, daemon=True)
cleanup_thread.start()

# Initial setup
setup_menu()

if __name__ == '__main__':
    app.run(threaded=True)
