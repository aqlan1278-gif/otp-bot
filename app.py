# otp_bot.py - OTP Generator Bot
import os
import logging
import random
import time
import json
import sqlite3
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# قراءة التوكن من متغير البيئة (آمن)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUR_ID = 7869424638
ADMIN_IDS = [7869424638]

# المجموعات والقنوات
GROUP_ID = 1003684030974
CHANNEL_1_ID = 1003728817993
CHANNEL_2_ID = -1003985862829

GROUP_LINK = "https://t.me/myrqla_n"
CHANNEL_1_LINK = "https://t.me/myrqlan_7"
CHANNEL_2_LINK = "https://t.me/myrqla"

# إعدادات OTP
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 300
MAX_OTP_PER_USER = 3

# Webhook
RENDER_URL = os.environ.get("RENDER_URL", "https://otp-bot.onrender.com")
WEBHOOK_URL = f"{RENDER_URL}/webhook"

# قاعدة البيانات
DB_PATH = "/tmp/otp_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            phone_number TEXT,
            otp_code TEXT,
            created_at TEXT,
            expires_at TEXT,
            is_used INTEGER DEFAULT 0,
            sent_to_group INTEGER DEFAULT 0,
            sent_to_channel1 INTEGER DEFAULT 0,
            sent_to_channel2 INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def generate_otp(length=OTP_LENGTH):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

def save_otp_to_db(user_id, username, phone_number, otp_code):
    now = datetime.now()
    expires = datetime.fromtimestamp(time.time() + OTP_EXPIRY_SECONDS)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO otp_codes 
        (user_id, username, phone_number, otp_code, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, phone_number, otp_code, 
          now.strftime("%Y-%m-%d %H:%M:%S"),
          expires.strftime("%Y-%m-%d %H:%M:%S")))
    
    code_id = c.lastrowid
    conn.commit()
    conn.close()
    return code_id

def log_action(user_id, username, action, details=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        INSERT INTO usage_log (user_id, username, action, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, action, details, 
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.commit()
    conn.close()

def get_active_otp_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        SELECT COUNT(*) FROM otp_codes 
        WHERE user_id = ? AND is_used = 0 AND expires_at > ?
    ''', (user_id, now))
    
    count = c.fetchone()[0]
    conn.close()
    return count

def update_otp_field(code_id, field, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f'UPDATE otp_codes SET {field} = ? WHERE id = ?', (value, code_id))
    conn.commit()
    conn.close()

# تطبيق Flask
app = Flask(__name__)

# تطبيق تيليغرام
application = Application.builder().token(BOT_TOKEN).build()

# ========== أوامر البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_msg = f"""
🎯 *OTP Generator Bot*
مرحباً {user.first_name}!

أنا بوت توليد أكواد OTP للاختبارات الأمنية.

*الأوامر المتاحة:*
/start - عرض هذه الرسالة
/otp +963XXXXXXXX - توليد OTP
/my_otps - عرض أكوادك النشطة
/help - المساعدة

*مثال:* `/otp 963XXXXXXXX`
    """
    
    keyboard = [
        [InlineKeyboardButton("📢 الجروب", url=GROUP_LINK),
         InlineKeyboardButton("📡 القناة 1", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("📡 القناة 2", url=CHANNEL_2_LINK),
         InlineKeyboardButton("👤 المطور", url=f"tg://user?id={YOUR_ID}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📘 *مساعدة البوت*

*الأمر:* `/otp +963XXXXXXXX`
*الوظيفة:* توليد كود OTP لرقم الهاتف
*مثال:* `/otp 963712345678`

*ملاحظات:*
• كود OTP يتكون من 6 أرقام
• صلاحية الكود: 5 دقائق
• أقصى 3 أكواد نشطة لكل مستخدم
• الأكواد تُنشر تلقائياً في الجروب والقنوات
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def generate_otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("⚠️ يرجى إدخال رقم الهاتف. مثال: `/otp 963712345678`", parse_mode='Markdown')
        return
    
    phone = context.args[0].strip().replace("+", "").replace(" ", "").replace("-", "")
    
    if not phone.isdigit() or len(phone) < 7:
        await update.message.reply_text("⚠️ رقم الهاتف غير صالح.", parse_mode='Markdown')
        return
    
    active_count = get_active_otp_count(user_id)
    if active_count >= MAX_OTP_PER_USER:
        await update.message.reply_text(f"⚠️ لديك {MAX_OTP_PER_USER} أكواد نشطة بالفعل.", parse_mode='Markdown')
        return
    
    otp_code = generate_otp()
    code_id = save_otp_to_db(user_id, username, phone, otp_code)
    
    user_msg = f"""
✅ *تم توليد الكود بنجاح!*

📱 *الرقم:* `{phone}`
🔐 *الكود:* `{otp_code}`
⏰ *الصالحية:* 5 دقائق
🆔 *#{code_id}*

• تم النشر في:
  📢 @myrqla_n
  📡 @myrqlan_7
  📡 @myrqla
"""
    
    await update.message.reply_text(user_msg, parse_mode='Markdown')
    
    # إرسال للجروب والقنوات
    otp_message = f"""
🔐 *OTP Code Generated*

📱 `{phone}`
🔑 `{otp_code}`
⏰ 5 دقائق
👤 {username}
"""
    
    keyboard = [[InlineKeyboardButton("👤 المالك", url=f"tg://user?id={YOUR_ID}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.send_message(chat_id=GROUP_ID, text=otp_message, parse_mode='Markdown', reply_markup=reply_markup)
        update_otp_field(code_id, 'sent_to_group', 1)
    except Exception as e:
        print(f"جروب: {e}")
    
    try:
        await context.bot.send_message(chat_id=CHANNEL_1_ID, text=otp_message, parse_mode='Markdown')
        update_otp_field(code_id, 'sent_to_channel1', 1)
    except Exception as e:
        print(f"قناة 1: {e}")
    
    try:
        await context.bot.send_message(chat_id=CHANNEL_2_ID, text=otp_message, parse_mode='Markdown')
        update_otp_field(code_id, 'sent_to_channel2', 1)
    except Exception as e:
        print(f"قناة 2: {e}")
    
    log_action(user_id, username, "generate_otp", f"Phone: {phone}, OTP: {otp_code}")

async def my_otps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''SELECT id, phone_number, otp_code, created_at, expires_at 
                 FROM otp_codes WHERE user_id = ? AND is_used = 0 AND expires_at > ?
                 ORDER BY created_at DESC''', (user_id, now))
    
    codes = c.fetchall()
    conn.close()
    
    if not codes:
        await update.message.reply_text("📭 لا يوجد أكواد نشطة.", parse_mode='Markdown')
        return
    
    msg = "📋 *أكوادك النشطة:*\n\n"
    for code in codes:
        code_id, phone, otp, created, expires = code
        msg += f"#{code_id} 📱 `{phone}` 🔑 `{otp}`\n🕐 {expires}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ أمر غير معروف. استخدم /help")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM otp_codes')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM otp_codes WHERE is_used = 1')
    used = c.fetchone()[0]
    c.execute('SELECT COUNT(DISTINCT user_id) FROM otp_codes')
    users = c.fetchone()[0]
    
    conn.close()
    
    msg = f"📊 *الإحصائيات:*\n• إجمالي الأكواد: {total}\n• مستخدمة: {used}\n• المستخدمون: {users}\n• الحالة: 🟢 يعمل"
    await update.message.reply_text(msg, parse_mode='Markdown')

# ========== صفحات Flask ==========

@app.route('/')
def index():
    return '''
    <html>
    <head><style>
        body { font-family: Arial; text-align: center; margin-top: 100px; 
               background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
        .card { background: white; color: #333; max-width: 500px; margin: auto;
                padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        .status { color: #22c55e; font-size: 24px; }
    </style></head>
    <body>
        <div class="card">
            <div class="status">🟢</div>
            <h1>🤖 OTP Generator Bot</h1>
            <p>البوت يعمل بنجاح!</p>
            <p>📱 أرسل /start للبوت على تيليغرام</p>
        </div>
    </body>
    </html>
    '''

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.process_update(update))
    loop.close()
    return 'OK', 200

@app.route('/health')
def health():
    return {"status": "ok", "bot": "running"}, 200

def init_bot():
    init_db()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("otp", generate_otp_command))
    application.add_handler(CommandHandler("my_otps", my_otps))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(application.bot.delete_webhook(drop_pending_updates=True))
        loop.run_until_complete(application.bot.set_webhook(url=WEBHOOK_URL))
        print(f"✅ Webhook: {WEBHOOK_URL}")
    except Exception as e:
        print(f"❌ Webhook error: {e}")
    loop.close()

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN غير موجود! أضفه في Environment Variables على Render")
    else:
        init_bot()
        port = int(os.environ.get("PORT", 10000))
        app.run(host="0.0.0.0", port=port)
