from flask import Flask, request
import requests

app = Flask(__name__)

PAGE_ACCESS_TOKEN = "EAAOeBunVPqoBO3yB2OJoUmYa7IdbtKdLXvoGZB3vNvieMDgF5by5MJve0ZA9ZB8cZAAsBwtYZBd1ZAlMWDt92wDvoPrqinPZA6KqYUpiH5TYZA6mndF84V7mVTKs5NKj3V8YhKUREBtketxyeh0ZCJiWYRPIebHxsG9jLiAi9KmZCCwxy8rRwhqdXZAhvDqoZAs15zVNytZBEHfwSXIpPJ8h1I9UOfjeXiXdTuJOwGDkZD"
VERIFY_TOKEN = "d51ee4e3183dbbd9a27b7d2c1af8c655"

waiting_users = []
games = {}

def send_message(recipient_id, message_text):
    url = 'https://graph.facebook.com/v16.0/me/messages'
    headers = {'Content-Type': 'application/json'}
    data = {
        'recipient': {'id': recipient_id},
        'message': {'text': message_text},
        'messaging_type': 'RESPONSE',
        'access_token': PAGE_ACCESS_TOKEN
    }
    requests.post(url, headers=headers, json=data)

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        token_sent = request.args.get("hub.verify_token")
        return request.args.get("hub.challenge") if token_sent == VERIFY_TOKEN else 'Invalid verification token'
    
    if request.method == 'POST':
        data = request.get_json()
        for entry in data.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event["sender"]["id"]
                if "message" in messaging_event:
                    handle_message(sender_id, messaging_event["message"].get("text", ""))
        return "ok", 200

def handle_message(sender_id, message_text):
    if sender_id in games:
        opponent_id = games[sender_id]
        send_message(opponent_id, f"خصمك يقول: {message_text}")
    else:
        if sender_id not in waiting_users:
            waiting_users.append(sender_id)
            send_message(sender_id, "تم تسجيلك. نبحث عن خصم...")
        if len(waiting_users) >= 2:
            player1 = waiting_users.pop(0)
            player2 = waiting_users.pop(0)
            games[player1] = player2
            games[player2] = player1
            send_message(player1, "تم العثور على خصم! ابدأ اللعب الآن.")
            send_message(player2, "تم العثور على خصم! ابدأ اللعب الآن.")

if __name__ == "__main__":
    app.run()
