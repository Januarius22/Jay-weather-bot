from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackContext,
    filters,
    JobQueue,
)
import requests
import json
from pathlib import Path
from datetime import time
import random
import asyncio
import os
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}


USERS_FILE = "users.json"

# Set your credentials
WEATHER_API_KEY = "57460d0a9c13405694614234252507"
TELEGRAM_BOT_TOKEN = "7949067008:AAFgTnK0MjKngM00qcd08oaJCjjjOfXLbyU"
ADMIN_CHAT_ID = 5075178708

user_locations = {}  # user_id: (lat, lon)
admin_message_mode = {}  # user_id: True or False
admin_broadcast_mode = {
    "active": False,
    "target_user": None  # could be user ID or None for broadcast-to-all
}
user_data = {}


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

#     return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username  # This could be None if the user has no username

    save_user(user_id, username)

    user_keyboard = [
        [KeyboardButton("🌤️ Weather by City"), KeyboardButton("📅 3-Day Forecast")],
        [KeyboardButton("🌡️ Temperature Alerts"), KeyboardButton("⏰ Daily Weather Update")],
        [KeyboardButton("📩 Contact Admin"), KeyboardButton("🌈 Fun Weather Quote")],
    ]

    admin_keyboard = [
        [KeyboardButton("📊 Users Count"), KeyboardButton("📢 Broadcast"), KeyboardButton("👥 All Users")]
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

import aiohttp

# Helper functions for weather API calls

import logging

async def fetch_weather(city: str):
    base_url = "http://api.weatherapi.com/v1/current.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": city,
        "aqi": "no"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(base_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print("WEATHER RESPONSE:", data)
                    logging.info(f"fetch_weather response for city '{city}': {data}")
                    if "error" not in data:
                        return data
                    else:
                        logging.warning(f"City '{city}' not found in weather API response: {data['error']}")
                        return None
                else:
                    logging.error(f"Failed to fetch weather for city '{city}', HTTP status: {resp.status}")
                    return None
        except Exception as e:
            logging.error(f"Exception during fetch_weather for city '{city}': {e}")
            return None

async def fetch_forecast(city: str):
    base_url = "http://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": WEATHER_API_KEY,
        "q": city,
        "days": 3,
        "aqi": "no",
        "alerts": "no"
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(base_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print("WEATHER RESPONSE:", data)
                    logging.info(f"fetch_forecast response for city '{city}': {data}")
                    if "error" not in data:
                        return data
                    else:
                        logging.warning(f"City '{city}' not found in forecast API response: {data['error']}")
                        return None
                else:
                    logging.error(f"Failed to fetch forecast for city '{city}', HTTP status: {resp.status}")
                    return None
        except Exception as e:
            logging.error(f"Exception during fetch_forecast for city '{city}': {e}")
            return None

# Fun weather quotes
WEATHER_QUOTES = [
    "Sunshine is the best medicine.",
    "Wherever you go, no matter what the weather, always bring your own sunshine.",
    "Some people feel the rain. Others just get wet.",
    "A change in the weather is sufficient to recreate the world and ourselves.",
    "There’s no such thing as bad weather, only inappropriate clothing.",
    "Rain is grace; rain is the sky descending to the earth.",
    "The best thing one can do when it’s raining is to let it rain.",
]

# User states for multi-step interactions
# user_data[user_id] = {"state": None, "temp_alert": {"min": None, "max": None}, "daily_update_time": None, ...}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    text_lower = text.lower()
    user = update.effective_user
    username = user.username if user.username else "N/A"
    save_user(user_id, username)

    # Initialize user_data entry if not exists
    if user_id not in user_data:
        user_data[user_id] = {
            "state": None,
            "temp_alert": {"min": None, "max": None},
            "daily_update_time": None,
            "last_city": None,
        }

    print(f"User sent: {text}")

    # Handle admin message mode
    if admin_message_mode.get(user_id):
        admin_message_mode[user_id] = False
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"📩 New message from user:\n\nUser ID: {user_id}\nUsername: @{username}\n\nMessage:\n{text}"
        )
        await update.message.reply_text("✅ Your message has been sent to the admin.")
        return

    # Handle "Contact Admin" text
    if "contact admin" in text_lower:
        admin_message_mode[user_id] = True
        await update.message.reply_text("✉️ Please type the message you want to send to the admin.")
        return

    # Admin commands
    if user_id == ADMIN_CHAT_ID:
        if text_lower == "📊 users count":
            total_users = get_user_count()
            await update.message.reply_text(f"👥 Total users: {total_users}")
            return
        elif text_lower == "📢 broadcast":
            admin_broadcast_mode["active"] = True
            admin_broadcast_mode["target_user"] = None
            await update.message.reply_text("📨 Type the message to broadcast to ALL users and this bd to userid_or_username : your message for specific user.")
            return
        elif text_lower == "👥 all users":
            await admin_allusers(update, context)
            return
        elif text_lower.startswith("bd to "):
            try:
                message_text = text[6:].strip()
                if ":" not in message_text:
                    await update.message.reply_text("❌ Invalid format. Use: bd to userid_or_username : your message")
                    return
                target_raw, msg = map(str.strip, message_text.split(":", 1))
                if target_raw.startswith("@"):
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
            # Reset broadcast mode after targeted send
            admin_broadcast_mode["active"] = False
            admin_broadcast_mode["target_user"] = None
            return
        if admin_broadcast_mode["active"]:
            message_to_send = text
            if admin_broadcast_mode["target_user"]:
                try:
                    await context.bot.send_message(chat_id=admin_broadcast_mode["target_user"], text=message_to_send)
                    await update.message.reply_text("✅ Message sent to selected user.")
                except Exception as e:
                    await update.message.reply_text(f"❌ Failed to send: {e}")
            else:
                users = load_users() or []
                for uid in users:
                    try:
                        await context.bot.send_message(chat_id=uid, text=message_to_send)
                    except:
                        continue
                await update.message.reply_text("✅ Broadcast sent to all users.")
            admin_broadcast_mode["active"] = False
            admin_broadcast_mode["target_user"] = None
            return

    # Handle user states for multi-step interactions
    state = user_data[user_id].get("state")

    if state == "awaiting_city_weather":
        city = text
        weather = await fetch_weather(city)
        if weather and "current" in weather and "condition" in weather["current"]:
            location = weather["location"]["name"]
            country = weather["location"]["country"]
            desc = weather["current"]["condition"]["text"]
            temp = weather["current"]["temp_c"]
            humidity = weather["current"]["humidity"]
            wind_speed = weather["current"]["wind_kph"]

            msg = (
                f"🌍 Weather in {location}, {country}:\n"
                f"{desc}\n"
                f"🌡️ Temperature: {temp}°C\n"
                f"💧 Humidity: {humidity}%\n"
                f"🌬️ Wind Speed: {wind_speed} km/h"
            )

            await update.message.reply_text(msg)
            user_data[user_id]["last_city"] = city
        else:
            await update.message.reply_text("❌ Could not find weather for that city. Please try again.")
        user_data[user_id]["state"] = None
        return

    if state == "awaiting_city_forecast":
        city = text
        forecast = await fetch_forecast(city)
        if forecast and "forecast" in forecast and "forecastday" in forecast["forecast"]:
            forecast_msg = f"📅 3-Day Forecast for {forecast['location']['name']}:\n"
            for day in forecast["forecast"]["forecastday"]:
                date = day["date"]
                condition = day["day"]["condition"]["text"]
                avg_temp = day["day"]["avgtemp_c"]
                forecast_msg += f"{date}: {condition}, Avg Temp: {avg_temp}°C\n"
            await update.message.reply_text(forecast_msg)
            user_data[user_id]["last_city"] = city
        else:
            await update.message.reply_text("❌ Could not find forecast for that city. Please try again.")
        user_data[user_id]["state"] = None
        return


    if state == "awaiting_temp_alert":
        # Expecting input like "min,max" e.g. "10,30"
        try:
            parts = text.split(",")
            if len(parts) != 2:
                raise ValueError
            min_temp = float(parts[0].strip())
            max_temp = float(parts[1].strip())
            user_data[user_id]["temp_alert"]["min"] = min_temp
            user_data[user_id]["temp_alert"]["max"] = max_temp
            await update.message.reply_text(f"✅ Temperature alert set: Min {min_temp}°C, Max {max_temp}°C")
        except:
            await update.message.reply_text("❌ Invalid format. Please send min and max temperature separated by a comma, e.g. 10,30")
        user_data[user_id]["state"] = None
        return

    if state == "awaiting_daily_update_time":
        # Expecting input like "HH:MM" 24-hour format
        try:
            parts = text.split(":")
            if len(parts) != 2:
                raise ValueError
            hour = int(parts[0].strip())
            minute = int(parts[1].strip())
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
            user_data[user_id]["daily_update_time"] = (hour, minute)
            # Schedule job for this user
            job_queue = context.job_queue
            # Remove existing job for user if any
            current_jobs = job_queue.get_jobs_by_name(str(user_id))
            for job in current_jobs:
                job.schedule_removal()
            job_queue.run_daily(
                daily_weather_update,
                time=time(hour=hour, minute=minute),
                name=str(user_id),
                data={"user_id": user_id, "context": context}
            )
            await update.message.reply_text(f"✅ Daily weather update scheduled at {hour:02d}:{minute:02d}")
        except:
            await update.message.reply_text("❌ Invalid time format. Please send time as HH:MM in 24-hour format.")
        user_data[user_id]["state"] = None
        return

    # Handle button presses
    if text == "🌤️ Weather by City":
        user_data[user_id]["state"] = "awaiting_city_weather"
        await update.message.reply_text("Please enter the city name to get current weather:")
        return

    if text == "📅 3-Day Forecast":
        user_data[user_id]["state"] = "awaiting_city_forecast"
        await update.message.reply_text("Please enter the city name to get 3-day forecast:")
        return

    if text == "🌡️ Temperature Alerts":
        user_data[user_id]["state"] = "awaiting_temp_alert"
        await update.message.reply_text("Please enter min and max temperature for alerts separated by a comma (e.g. 10,30):")
        return

    if text == "⏰ Daily Weather Update":
        user_data[user_id]["state"] = "awaiting_daily_update_time"
        await update.message.reply_text("Please enter the time for daily weather update in HH:MM (24-hour) format: TIME IS OF LONDON, UK")
        return

    if text == "🌈 Fun Weather Quote":
        quote = random.choice(WEATHER_QUOTES)
        await update.message.reply_text(f"🌈 Fun Weather Quote:\n{quote}")
        return

    # Final fallback: try to get weather by city if user sends a city name directly
    weather = await fetch_weather(text)
    if weather and "current" in weather and "condition" in weather["current"]:
        desc = weather["current"]["condition"]["text"].capitalize()
        temp = weather["current"]["temp_c"]
        humidity = weather["current"]["humidity"]
        wind_speed = weather["current"]["wind_kph"]
        msg = (f"Weather in {text}:\n"
               f"{desc}\n"
               f"Temperature: {temp}°C\n"
               f"Humidity: {humidity}%\n"
               f"Wind Speed: {wind_speed} km/h")
        await update.message.reply_text(msg)
        user_data[user_id]["last_city"] = text
        return

    # If none matched, send help message
    await update.message.reply_text("Sorry, I didn't understand that. Please use the buttons or type a city name.")

# Job callback for daily weather update
async def daily_weather_update(context: CallbackContext):
    job = context.job
    user_id = job.data["user_id"]
    user_ctx = job.data["context"]
    city = user_data.get(user_id, {}).get("last_city")
    if not city:
        await user_ctx.bot.send_message(chat_id=user_id, text="⏰ Daily update: Please set a city by using '🌤️ Weather by City' first.")
        return
    weather = await fetch_weather(city)
    if weather and "current" in weather and "condition" in weather["current"]:
        desc = weather["weather"][0]["description"].capitalize()
        temp = weather["main"]["temp"]
        humidity = weather["main"]["humidity"]
        wind_speed = weather["wind"]["speed"]
        msg = (f"⏰ Daily Weather Update for {city}:\n"
               f"{desc}\n"
               f"Temperature: {temp}°C\n"
               f"Humidity: {humidity}%\n"
               f"Wind Speed: {wind_speed} m/s")
        await user_ctx.bot.send_message(chat_id=user_id, text=msg)

# Function to check temperature alerts (can be scheduled periodically)
async def check_temperature_alerts(context: CallbackContext):
    users = list(user_data.keys())
    for user_id in users:
        alert = user_data[user_id].get("temp_alert")
        city = user_data[user_id].get("last_city")
        if alert and city and (alert["min"] is not None or alert["max"] is not None):
            weather = await fetch_weather(city)
            if weather and weather.get("main"):
                temp = weather["main"]["temp"]
                if (alert["min"] is not None and temp < alert["min"]) or (alert["max"] is not None and temp > alert["max"]):
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"🌡️ Temperature Alert for {city}!\nCurrent temperature: {temp}°C\nAlert range: {alert['min']}°C - {alert['max']}°C"
                        )
                    except:
                        pass



# Remaining functions unchanged...
# Please paste the rest of your unchanged helper functions and main() here if needed.

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

async def admin_allusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not Path(USERS_FILE).exists():
        await update.message.reply_text("❌ No users found.")
        return

    with open(USERS_FILE, "r") as f:
        users = json.load(f)

    if not users:
        await update.message.reply_text("❌ No users found.")
        return

    message_lines = ["\U0001F465 Users List:"]
    for user in users:
        uid = user.get("id", "N/A")
        username = user.get("username", "N/A")
        message_lines.append(f"ID: {uid}, Username: {username}")

    message = "\n".join(message_lines)
    # Telegram messages have a max length, so split if needed
    MAX_MESSAGE_LENGTH = 4000
    if len(message) > MAX_MESSAGE_LENGTH:
        # Split message into chunks
        chunks = [message[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(message), MAX_MESSAGE_LENGTH)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(message)

async def run_fastapi():
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

import threading

def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("allusers", admin_allusers))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # application.add_handler(MessageHandler(filters.LOCATION, handle_location))

    # ✅ JobQueue (Add this after all handlers are added)
    job_queue = application.job_queue
    # Schedule temperature alert checks every hour
    job_queue.run_repeating(check_temperature_alerts, interval=3600, first=10)

    def start_fastapi():
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)

    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    print("✅ Bot is running with FastAPI server...")
    application.run_polling()

if __name__ == "__main__":
    main()
