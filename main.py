import telebot
import os
import json
import time
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

        wait = WebDriverWait(driver, 15)

        # ✅ Enter email
        email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Email or username"]')))
        email_input.send_keys(email)

        # ✅ Click login button
        login_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-testid="login-button"]')))
        login_button.click()

        # Wait for OTP prompt (optional)
        time.sleep(3)

        print(driver.page_source)

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

# /me command – Show user's currently playing song
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

        # Headless browser
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=options)
        driver.get("https://accounts.spotify.com/en/login")

        wait = WebDriverWait(driver, 15)

        # Step 1: email
        email_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Email or username"]')))
        email_input.send_keys(email)

        # Step 2: login button
        login_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="login-button"]')))
        login_btn.click()

        # Step 3: check for "Check your email" screen
        wait.until(lambda d: "check your email" in d.page_source.lower())

        # Save state
        otp_state[user_id] = {
            "email": email,
            "driver": driver,
            "awaiting_otp": True,
            "timestamp": time.time()
        }

        bot.reply_to(message, "📩 OTP sent to your email.\nSend the OTP directly without any command.")

    except Exception as e:
        bot.reply_to(message, f"❌ Error during login: {str(e)}")

# /friend command – Show friends' current activity
@bot.message_handler(commands=["friend"])
def handle_friend_activity(message):
    user_id = str(message.from_user.id)

    if user_id not in sessions:
        bot.reply_to(message, "❌ Please login first using /login <email>")
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

# OTP input handler
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
        sp_dc = None
        for cookie in cookies:
            if cookie["name"] == "sp_dc":
                sp_dc = cookie["value"]
                break

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

        bot.reply_to(message, "✅ Login successful! You can now use /me or /friend.")
        driver.quit()
        del otp_state[user_id]

    except Exception as e:
        bot.reply_to(message, f"❌ Error while submitting OTP: {str(e)}")
        driver.quit()
        del otp_state[user_id]

# Start polling
if __name__ == "__main__":
    print("🤖 Bot is running...")
    bot.polling(none_stop=True, interval=0, timeout=20)
