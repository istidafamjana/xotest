from flask import Flask, request
import requests

app = Flask(__name__)

PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

players_queue = []
active_games = {}

board_template = lambda b: f"""{b[0]} | {b[1]} | {b[2]}
---+---+---
{b[3]} | {b[4]} | {b[5]}
---+---+---
{b[6]} | {b[7]} | {b[8]}
"""

def send_message(recipient_id, text):
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
        "access_token": PAGE_ACCESS_TOKEN
    }
    requests.post("https://graph.facebook.com/v16.0/me/messages", json=data)

def send_quick_reply(recipient_id, text):
    data = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": [
                {"content_type": "text", "title": "✖️", "payload": "XO_X"},
                {"content_type": "text", "title": "⭕️", "payload": "XO_O"},
                {"content_type": "text", "title": "تبديل لاعب", "payload": "CHANGE_PLAYER"},
                {"content_type": "text", "title": "اللعب مع AI", "payload": "PLAY_AI"}
            ]
        },
        "messaging_type": "RESPONSE",
        "access_token": PAGE_ACCESS_TOKEN
    }
    requests.post('https://graph.facebook.com/v16.0/me/messages', json=data)

def get_ai_reply(text):
    try:
        url = f"https://dev-pycodz-blackbox.pantheonsite.io/DEvZ44d/aii.php?text={text}"
        res = requests.get(url)
        return res.text if res.status_code == 200 else "حدث خطأ مع الذكاء الاصطناعي."
    except:
        return "خطأ في الاتصال بـ AI."

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Invalid verification token"
    elif request.method == "POST":
        data = request.json
        for entry in data["entry"]:
            for msg_event in entry["messaging"]:
                sender_id = msg_event["sender"]["id"]
                if "message" in msg_event:
                    message_text = msg_event["message"].get("text", "")
                    if message_text not in ["✖️", "⭕️"]:
                        send_message(sender_id, "الرجاء إرسال ✖️ أو ⭕️ فقط.")
                        send_quick_reply(sender_id, "اختر رمزًا للعب:")
                    else:
                        send_message(sender_id, f"تم تسجيل: {message_text}")
                elif "postback" in msg_event:
                    payload = msg_event["postback"]["payload"]
                    send_message(sender_id, f"تم اختيار: {payload}")
        return "ok"

if __name__ == "__main__":
    app.run()
