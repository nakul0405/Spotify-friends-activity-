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

# Temporary memory for OTP stage tracking
otp_state = {}

# /start command
@bot.message_handler(commands=["start"])
def handle_start(message):
    bot.reply_to(message, "👋 Welcome to Spotify Tracker Bot!\n\nUse:\n/login your@email.com\nThen reply with OTP\n\nCommands:\n/me → what you're playing\n/friend → friends' activity")

# /login <email>
@bot.message_handler(commands=["login"])
def handle_login(message):
    try:
        args = message.text.strip().split(" ")
        if len(args) != 2:
            bot.reply_to(message, "❌ Format:\n/login your@email.com")
            return

        email = args[1]
        user_id = str(message.from_user.id)

        bot.reply_to(message, "🔐 Opening Spotify... please wait.")

        # Set up headless browser
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=options)
        driver.get("https://accounts.spotify.com/en/login")
        time.sleep(3)

        # ✅ Corrected input selector
        driver.find_element(By.ID, "login-username").send_keys(email)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)

        if "check your email" in driver.page_source.lower():
            otp_state[user_id] = {
                "email": email,
                "driver": driver,
                "awaiting_otp": True,
                "timestamp": time.time()
            }
            bot.reply_to(message, "📩 OTP sent to your email.\n🔑 Please reply with the OTP code now (just the number).")
        else:
            driver.quit()
            bot.reply_to(message, "❌ Unexpected response from Spotify. Try again later.")

    except Exception as e:
        bot.reply_to(message, f"❌ Error during login: {str(e)}")

# /me command
@bot.message_handler(commands=["me"])
def handle_me(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please login first using /login <email>")
        return

    sp_dc = sessions[user_id]["sp_dc"]
    headers = { "Cookie": f"sp_dc={sp_dc}" }

    try:
        response = requests.get("https://guc3-spclient.spotify.com/now-playing-view/v1/view", headers=headers)

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

# /friend command
@bot.message_handler(commands=["friend"])
def handle_friend_activity(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please login first using /login <email>")
        return

    sp_dc = sessions[user_id]["sp_dc"]
    headers = { "Cookie": f"sp_dc={sp_dc}" }

    try:
        response = requests.get("https://guc3-spclient.spotify.com/presence-view/v1/buddylist", headers=headers)

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
            if "track" in friend and friend["track"]:
                name = friend["user"]["name"]
                song = friend["track"]["track"]["name"]
                artist = friend["track"]["track"]["artist"]["name"]
                url = friend["track"]["track"]["uri"].replace("spotify:track:", "https://open.spotify.com/track/")
                reply += f"👤 {name} — {song} by {artist}\n🔗 {url}\n\n"

        bot.reply_to(message, reply.strip())

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# OTP handler (auto-detects number reply)
@bot.message_handler(func=lambda m: True)
def handle_otp_input(message):
    user_id = str(message.from_user.id)

    if user_id not in otp_state or not otp_state[user_id]["awaiting_otp"]:
        return

    otp_code = message.text.strip()
    if not otp_code.isdigit():
        bot.reply_to(message, "❌ OTP should be numbers only.")
        return

    driver = otp_state[user_id]["driver"]

    try:
        driver.find_element(By.NAME, "code").send_keys(otp_code)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(6)

        cookies = driver.get_cookies()
        sp_dc = next((c["value"] for c in cookies if c["name"] == "sp_dc"), None)

        if not sp_dc:
            bot.reply_to(message, "❌ Invalid OTP or login failed.")
            driver.quit()
            del otp_state[user_id]
            return

        sessions[user_id] = {
            "email": otp_state[user_id]["email"],
            "sp_dc": sp_dc
        }
        save_sessions(sessions)

        bot.reply_to(message, "✅ Login successful! Use /me or /friend to track.")
        driver.quit()
        del otp_state[user_id]

    except Exception as e:
        bot.reply_to(message, f"❌ Error while submitting OTP: {str(e)}")
        driver.quit()
        del otp_state[user_id]

# Start the bot
if __name__ == "__main__":
    print("🤖 Bot is running...")
    bot.polling(none_stop=True, interval=0, timeout=20)

