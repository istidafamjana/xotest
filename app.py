from flask import Flask, request
import requests
import os

app = Flask(__name__)

# استدعاء متغيرات البيئة
PAGE_ACCESS_TOKEN = os.getenv("EAAOeBunVPqoBO5CLPaCIKVr21FqLLQqZBZAi8AnGYqurjwSOEki2ZC2IgrVtYZAeJtZC5ZAgmOTCPNzpEOsJiGZCQ7fZAXO7FX0AO4B1GpUTyQajZBGNzZA8KH2IGzSB3VLmBeTxNFG4k7VRUY1Svp4ZCiJDaZBSzEuBecZATZBR0f2faXamwLvONJwmDmSD6Oahkp1bhxwU3egCKJ8zuoy7GbZCUEWXyjNxwZDZD")
VERIFY_TOKEN = os.getenv("d51ee4e3183dbbd9a27b7d2c1af8c655")

# تخزين بيانات اللاعبين
players = {}
waiting_players = []

# إنشاء لوحة XO جديدة
def create_board():
    return ["⬜️", "⬜️", "⬜️", "⬜️", "⬜️", "⬜️", "⬜️", "⬜️", "⬜️"]

# إرسال رسالة ماسنجر
def send_message(recipient_id, text, quick_replies=None):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {
            "text": text,
            "quick_replies": quick_replies
        } if quick_replies else {"text": text}
    }
    requests.post(url, json=payload)

# تنسيق لوحة XO باستخدام الرموز ✖️⭕️⬜️ بشكل أفضل
def format_board(board):
    return f"""
 {board[0]} | {board[1]} | {board[2]} 
---+---+---
 {board[3]} | {board[4]} | {board[5]} 
---+---+---
 {board[6]} | {board[7]} | {board[8]} 
"""

# تحقق Webhook مع فيسبوك
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "خطأ في التحقق", 403

    data = request.json
    for entry in data["entry"]:
        for message_event in entry["messaging"]:
            sender_id = message_event["sender"]["id"]
            if "message" in message_event:
                handle_message(sender_id, message_event["message"]["text"])
    return "تم الاستلام", 200

# إدارة الرسائل
def handle_message(sender_id, message_text):
    if sender_id not in players:
        if waiting_players:
            opponent = waiting_players.pop(0)
            players[sender_id] = {"opponent": opponent, "symbol": None, "board": create_board()}
            players[opponent] = {"opponent": sender_id, "symbol": None, "board": players[sender_id]["board"]}
            send_message(sender_id, "تم العثور على خصم! اختر ✖️ أو ⭕️ للبدء.", get_quick_replies())
            send_message(opponent, "تم العثور على خصم! اختر ✖️ أو ⭕️ للبدء.", get_quick_replies())
        else:
            waiting_players.append(sender_id)
            send_message(sender_id, "جاري البحث عن خصم...")

    else:
        if message_text not in ["✖️", "⭕️"]:
            send_message(sender_id, "⚠️ يرجى اختيار ✖️ أو ⭕️ فقط للبدء في اللعبة.")
        else:
            assign_symbol(sender_id, message_text)

# تعيين الرمز (✖️ أو ⭕️) لللاعب
def assign_symbol(sender_id, symbol):
    game_data = players[sender_id]
    if not game_data["symbol"]:
        game_data["symbol"] = symbol
        opponent = game_data["opponent"]
        players[opponent]["symbol"] = "⭕️" if symbol == "✖️" else "✖️"
        
        send_message(sender_id, f"لقد اخترت {symbol}.\n" + format_board(game_data["board"]))
        send_message(opponent, f"خصمك اختار {game_data['symbol']}. انتظر دورك.\n" + format_board(players[opponent]["board"]))
    else:
        send_message(sender_id, "⚠️ لقد اخترت رمزًا بالفعل.")

# إرسال أزرار الاختيارات
def get_quick_replies():
    return [
        {
            "content_type": "text",
            "title": "✖️",
            "payload": "✖️"
        },
        {
            "content_type": "text",
            "title": "⭕️",
            "payload": "⭕️"
        }
    ]

# تشغيل التطبيق على Vercel
if __name__ == "__main__":
    app.run()
