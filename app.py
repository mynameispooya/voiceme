import os
import requests
import threading  # <--- کتابخانه جدید برای پردازش موازی
from flask import Flask, request
import google.generativeai as genai

app = Flask(__name__)

# --- تنظیمات Koyeb ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --- پرامپت‌ها ---
PROMPT_TRANSCRIBE = """
Listen explicitly to the audio. 
It contains a mix of English and Persian.
Transcribe exactly what is said. 
Write Persian parts in Persian script, and English parts in English.
Do NOT translate yet.
"""

PROMPT_CORRECT = """
You are a friendly English teacher.
Task:
1. Translate any Persian parts to English.
2. Correct the grammar of the entire sentence.
3. Rewrite the final sentence in simple English (Level A1/A2).
Output Format: English: [Sentence]\nPersian Meaning: [Translation]
"""

# --- توابع کمکی ---
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
    except: pass

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(f"{TELEGRAM_API_URL}/editMessageText", json=payload)
    except: pass

def get_file_path(file_id):
    try:
        res = requests.post(f"{TELEGRAM_API_URL}/getFile", json={"file_id": file_id}).json()
        return res["result"]["file_path"] if res.get("ok") else None
    except: return None

# --- تابع اصلی پردازش (در پس‌زمینه اجرا می‌شود) ---
def process_audio_background(chat_id, file_id, msg_id_to_edit):
    try:
        # تنظیم جمینای
        if not GEMINI_API_KEY:
            send_message(chat_id, "❌ خطا: کلید جمینای تنظیم نشده است.")
            return

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # دانلود فایل
        fpath = get_file_path(file_id)
        if not fpath:
            edit_message(chat_id, msg_id_to_edit, "❌ خطا در دانلود فایل.")
            return

        audio = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fpath}").content
        
        # ارسال به جمینای
        res = model.generate_content([PROMPT_TRANSCRIBE, {"mime_type": "audio/ogg", "data": audio}])
        
        # نمایش نتیجه
        kb = {"inline_keyboard": [[{"text": "Correct 🇬🇧", "callback_data": "do_correct"}]]}
        edit_message(chat_id, msg_id_to_edit, f"📝 <b>متن خام:</b>\n\n{res.text}", reply_markup=kb)

    except Exception as e:
        edit_message(chat_id, msg_id_to_edit, f"❌ خطا: {e}")

# --- تابع پردازش دکمه (در پس‌زمینه) ---
def process_callback_background(chat_id, msg_id, original_text):
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        res = model.generate_content(f"{PROMPT_CORRECT}\nInput: {original_text}")
        edit_message(chat_id, msg_id, f"📝 {original_text}\n\n🎓 {res.text}")
    except Exception as e:
        send_message(chat_id, f"❌ خطا در تصحیح: {e}")

# --- روت‌ها ---
@app.route('/')
def home():
    return "✅ VoxMind Bot is Running (Async Mode)!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data: return "ok"

        # 1. مدیریت دکمه
        if 'callback_query' in data:
            cb = data['callback_query']
            chat_id = cb['message']['chat']['id']
            msg_id = cb['message']['message_id']
            
            # سریع به تلگرام می‌گوییم "باشه، فهمیدم" تا لودینگ دکمه قطع شود
            requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": cb['id'], "text": "⏳ در حال بررسی..."})

            if cb['data'] == "do_correct":
                try:
                    original_text = cb['message']['text'].split("\n\n")[1]
                except:
                    original_text = "متن یافت نشد."
                
                # اجرای پردازش در نخ جداگانه (بدون معطلی)
                thread = threading.Thread(target=process_callback_background, args=(chat_id, msg_id, original_text))
                thread.start()
            
            return "ok"

        # 2. مدیریت پیام
        if 'message' in data:
            msg = data['message']
            chat_id = msg['chat']['id']

            if 'text' in msg and msg['text'] == "/start":
                send_message(chat_id, "👋 سلام! سیستم پرسرعت فعال شد.\nویس بفرستید.")

            elif 'voice' in msg:
                # اول یک پیام انتظار می‌فرستیم که کاربر بفهمد ربات زنده است
                wait = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": "⏳ شنیدم، صبر کنید..."}).json()
                msg_id = wait['result']['message_id']
                
                # حالا پردازش اصلی را به یک "کارگر" دیگر (Thread) می‌سپاریم
                # و خودمان سریع به تلگرام "ok" می‌دهیم تا ارتباط قطع نشود.
                thread = threading.Thread(target=process_audio_background, args=(chat_id, msg['voice']['file_id'], msg_id))
                thread.start()

    except Exception as e:
        print(f"Error: {e}")
    
    # نکته حیاتی: همیشه بلافاصله "ok" برمی‌گردانیم
    return "ok"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
