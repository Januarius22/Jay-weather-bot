from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    JobQueue,
)
import requests
import json
from pathlib import Path
from datetime import time
import random
import asyncio

USERS_FILE = "users.json"

# Set your credentials
WEATHER_API_KEY = "ef68327cb4c2420881c02338252307"
TELEGRAM_BOT_TOKEN = "7949067008:AAFgTnK0MjKngM00qcd08oaJCjjjOfXLbyU"
ADMIN_CHAT_ID = 5075178708

user_locations = {}  # user_id: (lat, lon)
admin_message_mode = {}  # user_id: True or False
admin_broadcast_mode = {
    "active": False,
    "target_user": None  # could be user ID or None for broadcast-to-all
}
user_data = {}



WEATHER_QUOTES = [
    "After rain comes sunshine.",
    "Wherever you go, no matter what the weather, always bring your own sunshine.",
    "Sunshine is delicious, rain is refreshing, wind braces us up.",
    "There’s no such thing as bad weather, only different kinds of good weather."
]

import os
import json
from pathlib import Path
import re



LOCATION_FILE = "user_locations.json"

def save_user_location(user_id, latitude, longitude):
    try:
        if Path(LOCATION_FILE).exists():
            with open(LOCATION_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {}

        data[str(user_id)] = {
            "latitude": latitude,
            "longitude": longitude
        }

        with open(LOCATION_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving location: {e}")

def load_user_locations():
    if not os.path.exists("locations.json"):
        with open("locations.json", "w") as f:
            json.dump({}, f)

    with open("locations.json", "r") as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def save_user(user_id, username):
    if not Path(USERS_FILE).exists():
        with open(USERS_FILE, "w") as f:
            json.dump([], f)

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    # Convert old int-only entries to dicts
    users = [
        {"id": u, "username": None} if isinstance(u, int) else u
        for u in users
    ]

    # Check if user already exists
    existing = next((u for u in users if u["id"] == user_id), None)

    if not existing:
        users.append({"id": user_id, "username": username})
    else:
        existing["username"] = username  # Update username if it changed

    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)




def get_user_count():
    if not Path(USERS_FILE).exists():
        return 0
    with open(USERS_FILE, "r") as f:
        user_ids = json.load(f)
    return len(user_ids)

def load_users():
    if not Path(USERS_FILE).exists():
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

MESSAGES_FILE = "messages.json"

def save_message(user_id, text):
    if not Path(MESSAGES_FILE).exists():
        with open(MESSAGES_FILE, "w") as f:
            json.dump([], f)
    with open(MESSAGES_FILE, "r") as f:
        messages = json.load(f)
    messages.append({"user_id": user_id, "text": text})
    with open(MESSAGES_FILE, "w") as f:
        json.dump(messages, f)

def load_messages():
    if not Path(MESSAGES_FILE).exists():
        return []
    with open(MESSAGES_FILE, "r") as f:
        return json.load(f)

def get_all_messages():
    if not Path(MESSAGES_FILE).exists() or os.path.getsize(MESSAGES_FILE) == 0:
        return []  # Return empty list if file doesn't exist or is empty

    with open(MESSAGES_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []  # In case file is not valid JSON

def get_forecast(lat, lon):
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={lat},{lon}&days=3&aqi=no&alerts=no"
    response = requests.get(url)
    data = response.json()
    if "error" in data:
        return None
    forecast_data = data["forecast"]["forecastday"]
    lines = [f"📍 *{data['location']['name']}, {data['location']['country']}* - 3 Day Forecast:"]
    for day in forecast_data:
        date = day["date"]
        condition = day["day"]["condition"]["text"].lower()
        max_temp = day["day"]["maxtemp_c"]
        min_temp = day["day"]["mintemp_c"]
        rain = day["day"]["daily_chance_of_rain"]
        lines.append(f"📅 {date}\n🌤️ {condition}\n🌡️ {min_temp}°C - {max_temp}°C\n🌧️ Chance of Rain: {rain}%\n")
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username  # This could be None if the user has no username

    save_user(user_id, username)

    user_keyboard = [
        [KeyboardButton("🌤️ Weather by City"), KeyboardButton("📍 Share Location", request_location=True)],
        [KeyboardButton("📅 3-Day Forecast"), KeyboardButton("🌡️ Temperature Alerts")],
        [KeyboardButton("📩 Contact Admin"), KeyboardButton("⏰ Daily Weather Update")],
        [KeyboardButton("🌈 Fun Weather Quote")]
    ]

    admin_keyboard = [
        [KeyboardButton("📊 Users Count"), KeyboardButton("📢 Broadcast")],
        [KeyboardButton("💬 View Messages")]
    ]

    # reply_markup = ReplyKeyboardMarkup(admin_keyboard if user_id == ADMIN_CHAT_ID else user_keyboard, resize_keyboard=True)
    # await update.message.reply_text("👋 Welcome to Jay's Weather Bot!", reply_markup=reply_markup)

    if user_id == ADMIN_CHAT_ID:
        user_keyboard.extend(admin_keyboard)

    reply_markup = ReplyKeyboardMarkup(user_keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Welcome to Jay's Weather Bot!\n\nUse the buttons below to get started.",
        reply_markup=reply_markup
    )

def get_weather_by_city(city):
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}&aqi=no"
    try:
        response = requests.get(url)
        data = response.json()
        if "error" in data:
            return None
        location = data["location"]["name"]
        country = data["location"]["country"]
        temp = data["current"]["temp_c"]
        condition = data["current"]["condition"]["text"]
        humidity = data["current"]["humidity"]
        wind_kph = data["current"]["wind_kph"]

        return (
            f"📍 *{location}, {country}*\n"
            f"🌡️ Temperature: {temp}°C\n"
            f"🌥️ Condition: {condition}\n"
            f"💧 Humidity: {humidity}%\n"
            f"💨 Wind: {wind_kph} kph"
        )

    except:
        return None

async def broadcast(context: ContextTypes.DEFAULT_TYPE, message: str, targets=None):
    try:
        if not Path(USERS_FILE).exists():
            return

        with open(USERS_FILE, "r") as f:
            user_ids = json.load(f)

        for uid in (targets if targets else user_ids):
            try:
                await context.bot.send_message(chat_id=uid, text=message)
            except Exception as e:
                print(f"Failed to send to {uid}: {e}")

    except Exception as e:
        print(f"Broadcast error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    # user_name = update.effective_user.full_name
    text = update.message.text.strip().lower()
    user = update.effective_user
    global ADMIN_CHAT_ID  
    # user_id = user.id
    username = user.username if user.username else "N/A"
    save_user(user_id, username)


    print(f"User sent: {text}")
    # 🟩 Priority 1: Handle message after user selects "Contact Admin"
    # ✅ Check if user is replying to "Contact Admin"
    if admin_message_mode.get(user_id):
        admin_message_mode[user_id] = False  # reset
        ADMIN_CHAT_ID = 5075178708  # Your Telegram ID
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📩 New message from user:\n\nUser ID: {user_id}\nUsername: @{username}\n\nMessage:\n{text}"
        )
        await update.message.reply_text("✅ Your message has been sent to the admin.")
        return

    # 🔁 Your normal weather logic goes here
    if "contact admin" in text.lower():
        admin_message_mode[user_id] = True
        await update.message.reply_text("✉️ Please type the message you want to send to the admin.")
        return


    # 🟩 Priority 3: Admin-only commands
    if user_id == ADMIN_CHAT_ID:
        if text.lower() == "📊 users count":
            total_users = get_user_count()  
            await update.message.reply_text(f"👥 Total users: {total_users}")
            return

        elif text.lower() == "📢 broadcast":
            admin_broadcast_mode["active"] = True
            admin_broadcast_mode["target_user"] = None  # default: send to all
            await update.message.reply_text("📨 Type the message to broadcast to ALL users and this bd to userid_or_username : your message for specific user.")
            return


        elif text.lower().startswith("bd to "):
            try:
                message_text = text[6:].strip()  # Removes "bd to "
                if ":" not in message_text:
                    await update.message.reply_text("❌ Invalid format. Use: bd to userid_or_username : your message")
                    return

                target_raw, msg = map(str.strip, message_text.split(":", 1))

                # Check if it's an ID (digits) or username (@something)
                if target_raw.startswith("@"):
                    # Search username in user_data
                    target_username = target_raw[1:].lower()
                    target_id = None
                    for uid, data in user_data.items():
                        if data.get("username", "").lower() == target_username:
                            target_id = uid
                            break
                    if not target_id:
                        await update.message.reply_text("❌ Username not found or user hasn't interacted with bot.")
                        return
                else:
                    target_id = int(target_raw)

                await context.bot.send_message(chat_id=target_id, text=msg)
                await update.message.reply_text(f"✅ Message sent to {target_raw}")
            except Exception as e:
                print("Broadcast error:", e)
                await update.message.reply_text("❌ Failed to send. Check your format or user ID.")
            return


        if admin_broadcast_mode["active"]:
            message_to_send = text
            if admin_broadcast_mode["target_user"]:
                # Send to specific user
                try:
                    await context.bot.send_message(chat_id=admin_broadcast_mode["target_user"], text=message_to_send)
                    await update.message.reply_text("✅ Message sent to selected user.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Failed to send: {e}")
            else:
                # Broadcast to all users
                users = load_users() or []
                for uid in users:
                    try:
                        await context.bot.send_message(chat_id=uid, text=message_to_send)
                    except:
                        continue
                await update.message.reply_text("✅ Broadcast sent to all users.")

            # ✅ Reset mode after sending
            admin_broadcast_mode["active"] = False
            admin_broadcast_mode["target_user"] = None
            return

        elif text.lower() == "💬 view messages":
            messages = get_all_messages()
            if messages:
                reply = "\n\n".join([f"🧾 {m}" for m in messages])
                await update.message.reply_text(reply)
            else:
                await update.message.reply_text("📭 No messages yet.")
            return

    # 🟩 Priority 4: Weather features
    if text.lower() == "🌤️ weather by city":
        await update.message.reply_text("🏖️ Enter city name:")
        return

    elif text.lower() == "🌡️ temperature alerts":
        all_locations = load_user_locations()
        if str(user_id) in all_locations:
            lat = all_locations[str(user_id)]["latitude"]
            lon = all_locations[str(user_id)]["longitude"]
            await send_alert(update, context, lat, lon)
        else:
            await update.message.reply_text("📍 Please share your location first.")
        return


    elif text.lower() == "📅 3-day forecast":
        all_locations = load_user_locations()
        if str(user_id) in all_locations:
            lat = all_locations[str(user_id)]["latitude"]
            lon = all_locations[str(user_id)]["longitude"]
            forecast = get_forecast(lat, lon)
            await update.message.reply_text(forecast, parse_mode="Markdown")
        else:
            await update.message.reply_text("📍 Please share your location first.")
        return


    elif text.lower() == "⏰ daily weather update":
        all_locations = load_user_locations()  # Load from file
        if str(user_id) in all_locations:  # Keys are strings in JSON
            context.chat_data["daily_update"] = True
            await update.message.reply_text("✅ You'll receive daily updates!")
        else:
            await update.message.reply_text("📍 Please share your location first.")
        return


    elif text.lower() == "🌈 fun weather quote":
        quote = random.choice(WEATHER_QUOTES)
        await update.message.reply_text(f"🌦️ *Fun Weather Quote:*\n\n_{quote}_", parse_mode="Markdown")
        return

    # 🟩 Priority 5: Final fallback – Try to get weather by city
    weather = get_weather_by_city(text)
    if weather:
        await update.message.reply_text(weather, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ City not found. Try again or use a button.")


# Remaining functions unchanged...
# Please paste the rest of your unchanged helper functions and main() here if needed.


def get_weather_by_coords(lat, lon):
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={lat},{lon}&aqi=no"
    response = requests.get(url)
    data = response.json()
    if "error" in data:
        return None
    return data

def format_weather(data):
    location = data["location"]["name"]
    country = data["location"]["country"]
    temp = data["current"]["temp_c"]
    condition = data["current"]["condition"]["text"]
    humidity = data["current"]["humidity"]
    wind_kph = data["current"]["wind_kph"]

    return (
        f"🌍 *{location}, {country}*\n"
        f"🌡️ Temperature: {temp}°C\n"
        f"🌤️ Condition: {condition}\n"
        f"💧 Humidity: {humidity}%\n"
        f"🌬️ Wind: {wind_kph} kph"
    )




async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.message.from_user
        user_id = user.id
        username = user.username  # Can be None

        # Save user ID and username
        save_user(user_id, username)

        location = update.message.location
        save_user_location(user_id, location.latitude, location.longitude)

        await update.message.reply_text("✅ Location saved! You can now access local weather features.")

    except Exception as e:
        print(f"Error in handle_location: {e}")
        await update.message.reply_text("❌ An error occurred while processing your location. Please try again.")


async def send_alert(update, context, lat, lon):
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={lat},{lon}&days=1&aqi=no&alerts=no"
    response = requests.get(url)
    data = response.json()
    if "error" in data:
        await update.message.reply_text("❌ Could not fetch forecast.")
        return

    day = data["forecast"]["forecastday"][0]["day"]
    max_temp = day["maxtemp_c"]
    rain_chance = day["daily_chance_of_rain"]

    if max_temp > 35:
        await update.message.reply_text(f"🌡️ Heat Alert: Max temp today is {max_temp}°C. Stay hydrated!")
    elif int(rain_chance) > 60:
        await update.message.reply_text(f"🌧️ Rain Alert: {rain_chance}% chance of rain. Carry an umbrella!")

async def scheduled_weather_update(context: ContextTypes.DEFAULT_TYPE):
    for user_id, (lat, lon) in user_locations.items():
        chat_data = context.chat_data.get(user_id)
        if chat_data and chat_data.get("daily_update"):
            forecast = get_forecast(lat, lon)
            if forecast:
                try:
                    await context.bot.send_message(chat_id=user_id, text=forecast, parse_mode="Markdown")
                except:
                    continue

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    message = ' '.join(context.args)
    if not message:
        await update.message.reply_text("❗ Usage: /broadcast <your message>")
        return

    if not Path(USERS_FILE).exists():
        await update.message.reply_text("❌ No users to send message to.")
        return

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    success, failed = 0, 0
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=f"\U0001F4E3 Broadcast:\n{message}")
            success += 1
        except:
            failed += 1

    await update.message.reply_text(f"✅ Sent to {success} users. ❌ Failed: {failed}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if Path(USERS_FILE).exists():
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
        total = len(users)
    else:
        total = 0

    await update.message.reply_text(f"\U0001F4CA Total users: {total}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))




    # ✅ JobQueue (Add this after all handlers are added)
    job_queue = app.job_queue
    job_queue.run_daily(scheduled_weather_update, time=time(hour=6, minute=30))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
