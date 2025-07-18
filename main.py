import telebot
import os
import json
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
bot = telebot.TeleBot(BOT_TOKEN)

SESSION_FILE = "sessions.json"

# Load sessions
def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return json.load(f)
    return {}

def save_sessions(data):
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)

sessions = load_sessions()

# /start command
@bot.message_handler(commands=["start"])
def handle_start(message):
    bot.reply_to(message, (
        "👋 Welcome to Spotify Tracker Bot!\n\n"
        "Use this format to connect:\n"
        "/setcookie your_sp_dc_cookie_here\n\n"
        "Commands:\n"
        "/me → What you're listening to\n"
        "/friend → What your friends are listening to"
    ))

# /setcookie command
@bot.message_handler(commands=["setcookie"])
def handle_setcookie(message):
    user_id = str(message.from_user.id)
    parts = message.text.strip().split(" ")

    if len(parts) != 2:
        bot.reply_to(message, "❌ Format:\n/setcookie your_sp_dc_cookie_here")
        return

    sp_dc = parts[1]
    sessions[user_id] = {
        "sp_dc": sp_dc
    }
    save_sessions(sessions)

    bot.reply_to(message, "✅ Cookie saved! Now you can use /me or /friend.")

# /me command
@bot.message_handler(commands=["me"])
def handle_me(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please set your cookie using /setcookie")
        return

    sp_dc = sessions[user_id]["sp_dc"]
    headers = {
        "Cookie": f"sp_dc={sp_dc}"
    }

    try:
        response = requests.get(
            "https://guc3-spclient.spotify.com/now-playing-view/v1/view",
            headers=headers
        )

        if response.status_code != 200:
            bot.reply_to(message, f"⚠️ Failed to fetch now playing info.\nStatus: {response.status_code}")
            return

        data = response.json()
        if not data.get("track"):
            bot.reply_to(message, "ℹ️ You're not listening to anything right now.")
            return

        track = data["track"]
        artist = track["artist"]["name"]
        name = track["name"]
        url = track.get("uri", "").replace("spotify:track:", "https://open.spotify.com/track/")

        bot.reply_to(message, f"🎧 You're listening to:\n{name} — {artist}\n🔗 {url}")

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# /friend command
@bot.message_handler(commands=["friend"])
def handle_friend_activity(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please set your cookie using /setcookie")
        return

    sp_dc = sessions[user_id]["sp_dc"]
    headers = {
        "Cookie": f"sp_dc={sp_dc}"
    }

    try:
        response = requests.get(
            "https://guc3-spclient.spotify.com/presence-view/v1/buddylist",
            headers=headers
        )

        if response.status_code != 200:
            bot.reply_to(message, f"⚠️ Failed to fetch friends activity.\nStatus: {response.status_code}")
            return

        data = response.json()
        friends = data.get("friends", [])

        if not friends:
            bot.reply_to(message, "😕 None of your friends are currently listening to anything.")
            return

        reply = "🎧 Friends Listening Now:\n\n"
        for friend in friends:
            if "track" in friend and friend["track"] is not None:
                name = friend["user"]["name"]
                song = friend["track"]["track"]["name"]
                artist = friend["track"]["track"]["artist"]["name"]
                url = friend["track"]["track"]["uri"].replace("spotify:track:", "https://open.spotify.com/track/")
                reply += f"👤 {name} — {song} by {artist}\n🔗 {url}\n\n"

        bot.reply_to(message, reply.strip())

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# Start the bot
if __name__ == "__main__":
    print("🤖 Bot is running...")
    bot.polling(none_stop=True, interval=0, timeout=20)
