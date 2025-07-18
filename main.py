import telebot
import os
import json
import time
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# Get bot token from Zeabur env vars
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
bot = telebot.TeleBot(BOT_TOKEN)

SESSION_FILE = "sessions.json"

# Load user sessions from file
def load_sessions():
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            return json.load(f)
    return {}

# Save sessions to file
def save_sessions(data):
    with open(SESSION_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Load into memory
sessions = load_sessions()

# /start command
@bot.message_handler(commands=["start"])
def handle_start(message):
    bot.reply_to(message, "👋 Welcome to Spotify Tracker Bot!\n\nUse:\n/login your@email.com yourpassword\nThen:\n/me → What you're playing\n/friend → What your friends are listening to")

# /login <email> <password> command
@bot.message_handler(commands=["login"])
def handle_login(message):
    try:
        args = message.text.strip().split(" ")
        if len(args) != 3:
            bot.reply_to(message, "❌ Format:\n/login your@email.com yourpassword")
            return

        email = args[1]
        password = args[2]

        bot.reply_to(message, "🔐 Logging in to Spotify... please wait 10-15 sec.")

        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=options)
        driver.get("https://accounts.spotify.com/en/login")
        time.sleep(3)

        # Wait for username input
        time.sleep(2)
        driver.find_element(By.NAME, "username").send_keys(email)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()


        cookies = driver.get_cookies()
        sp_dc = None
        for cookie in cookies:
            if cookie['name'] == 'sp_dc':
                sp_dc = cookie['value']
                break

        driver.quit()

        if not sp_dc:
            bot.reply_to(message, "❌ Login failed. Could not find sp_dc cookie.")
            return

        user_id = str(message.from_user.id)
        sessions[user_id] = {
            "email": email,
            "password": password,
            "sp_dc": sp_dc
        }
        save_sessions(sessions)

        bot.reply_to(message, "✅ Login successful. Session saved!")
    
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# /me command – Show user's currently playing song
@bot.message_handler(commands=["me"])
def handle_me(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please login first using /login <email> <password>")
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

        bot.reply_to(message, f"🎧 You're listening to:\n{name} — {artist}\n{url}")

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# /friend command – Show friends' current activity
@bot.message_handler(commands=["friend"])
def handle_friend_activity(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please login first using /login <email> <password>")
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
      
# Start polling the bot (runs forever)
if __name__ == "__main__":
    print("🤖 Bot is running...")
    bot.polling(none_stop=True, interval=0, timeout=20)
