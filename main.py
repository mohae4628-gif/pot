import logging
import os
import asyncio
import threading
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify # تم تصحيح الاستدعاءات هنا
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. الإعدادات والمعرفات ---
TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")
ADMIN_ID = 5332562107 

PRIVATE_CHANNEL_ID = '-1003953368081' 
FREE_CHANNEL_URL = 'https://t.me/c/3907521588/1' 
REQUESTS_CHANNEL_ID = '-1003846832363' 
ARCHIVE_CHANNEL_ID = '-1003989339996'  
DATA_CHANNEL_ID = REQUESTS_CHANNEL_ID # توجيه بيانات سلة لنفس قناة الطلبات

PORT = int(os.environ.get('PORT', 8080))

URLS = {
    "spx_1m": "https://salla.sa/AZIZSPX/WzbWgKA",
    "spx_shop": "https://salla.sa/AZIZSPX",
    "spx_3m": "https://salla.sa/AZIZSPX/xvnbrQb",
    "spx_6m": "https://salla.sa/AZIZSPX/azdOBBK",
    "ind_1m": "https://salla.sa/AZIZSPX/EXKwOwZ",
    "whatsapp_support": "https://wa.me/+966554852681" 
}

# --- 2. إدارة قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('aziz_trading.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS subscribers 
                 (user_id INTEGER PRIMARY KEY, name TEXT, expiry_date TEXT, notified INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def add_subscriber(user_id, name, expiry_date):
    conn = sqlite3.connect('aziz_trading.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO subscribers (user_id, name, expiry_date, notified) VALUES (?, ?, ?, 0)", 
              (user_id, name, expiry_date))
    conn.commit()
    conn.close()

# --- 3. إعداد Flask وLogging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
app_flask = Flask(__name__)

# متغير عالمي لتخزين نسخة البوت لاستخدامها في الـ Webhook
application_instance = None

# --- 4. لوحة المفاتيح الرئيسية (نفس مصطلحاتك) ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 اشتراك تحليلات SPX الخاصة  ", url=URLS["spx_shop"])],
        [InlineKeyboardButton("📈     Aziz pro مؤشر      ", url=URLS["ind_1m"])],
        [InlineKeyboardButton("🆓      القناة المجانية        ", url=FREE_CHANNEL_URL)],
        [InlineKeyboardButton("✅     أرسل إثبات الدفع      ", callback_data='upload_proof')],
        [InlineKeyboardButton("💬       الدعم الفني        ", url=URLS["whatsapp_support"])]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- 5. المهام التلقائية (تنبيه + طرد) ---
async def daily_check_job(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('aziz_trading.db')
    c = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    threshold_48h = (datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M')
    c.execute("SELECT user_id, name, expiry_date FROM subscribers WHERE expiry_date <= ? AND notified = 0", (threshold_48h,))
    for user in c.fetchall():
        try:
            await context.bot.send_message(chat_id=user[0], text=f"⚠️ تذكير: اشتراكك ينتهي بتاريخ {user[2]}. يرجى التجديد لتجنب الخروج التلقائي.")
            c.execute("UPDATE subscribers SET notified = 1 WHERE user_id = ?", (user[0],))
        except: pass

    c.execute("SELECT user_id, name FROM subscribers WHERE expiry_date <= ?", (now_str,))
    for user in c.fetchall():
        uid, name = user[0], user[1]
        try:
            await context.bot.ban_chat_member(chat_id=PRIVATE_CHANNEL_ID, user_id=uid)
            await context.bot.unban_chat_member(chat_id=PRIVATE_CHANNEL_ID, user_id=uid)
            await context.bot.send_message(chat_id=uid, text="❌ انتهى اشتراكك وتمت إزالتك من القناة الخاصة. يسعدنا انضمامك إلينا مرة أخرى عند التجديد!")
            await context.bot.send_message(chat_id=ARCHIVE_CHANNEL_ID, text=f"🚫 **خروج تلقائي**\n👤 الاسم: {name}\n🆔 الآيدي: `{uid}`\n⚠️ السبب: انتهاء الاشتراك.")
            c.execute("DELETE FROM subscribers WHERE user_id = ?", (uid,))
        except: pass
        
    conn.commit()
    conn.close()

# --- 6. الأوامر والمعالجات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "🚀 مرحبًا بك في بوت AZIZ Trading\n\n"
        "📊 بوابتك إلى تداول أكثر احترافية وقرارات مبنية على تحليل دقيق لحركة السوق \n\n"
        "📈 اختر من الأزرار أدناه للوصول إلى خدماتنا وابدأ رحلتك الآن"
    )
    await update.message.reply_text(welcome_message, reply_markup=main_menu_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == 'back_to_main':
        context.user_data['waiting_for_proof'] = False
        await query.edit_message_text("الرئيسية 🏠\n 📈 ااختر من الأزرار أدناه للوصول إلى خدماتنا وابدأ رحلتك الآن :", reply_markup=main_menu_keyboard())

    elif data == 'menu_spx':
        keyboard = [
            [InlineKeyboardButton("شهر - 169 ريال", url=URLS["spx_1m"])],
            [InlineKeyboardButton("3 شهور - 399 ريال", url=URLS["spx_3m"])],
            [InlineKeyboardButton("✅ أرسل إثبات الدفع", callback_data='upload_proof')],
            [InlineKeyboardButton("🔙 العودة", callback_data='back_to_main')]
        ]
        await query.edit_message_text("باقات SPX 📊\nاختر المدة للدفع عبر سلة ثم أرسل الإثبات هنا:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == 'menu_indicators':
        keyboard = [
            [InlineKeyboardButton("📈 Aziz pro مؤشر ", url=URLS["ind_1m"])],
            [InlineKeyboardButton("✅ أرسل إثبات الدفع", callback_data='upload_proof')],
            [InlineKeyboardButton("🔙 العودة", callback_data='back_to_main')]
        ]
        await query.edit_message_text("المؤشرات الفنية 📈\nادفع عبر الرابط ثم أرسل الإثبات للمراجعة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == 'upload_proof':
        context.user_data['waiting_for_proof'] = True
        keyboard = [[InlineKeyboardButton("🔙 إلغاء والعودة للرئيسية", callback_data='back_to_main')]]
        await query.edit_message_text("بانتظار الإثبات ⏳\nمن فضلك أرسل الآن رقم الطلب هنا مباشرة:", reply_markup=InlineKeyboardMarkup(keyboard))
            
    elif data.startswith('approve_'):
        if query.from_user.id != ADMIN_ID: return
        parts = data.split('_')
        days, cust_id = int(parts[1]), int(parts[2])
        expiry_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
        duration_text = "شهر" if days == 30 else f"{days // 30} شهور"

        try:
            invite = await context.bot.create_chat_invite_link(chat_id=PRIVATE_CHANNEL_ID, member_limit=1)
            await context.bot.send_message(chat_id=cust_id, text=f"🎉 تم تفعيل اشتراكك بنجاح لمدة ({duration_text})!\nرابط القناة الخاصة:\n{invite.invite_link}\n\nينتهي اشتراكك في تاريخ: {expiry_date}")
            
            member = await context.bot.get_chat(cust_id)
            name = f"{member.first_name} {member.last_name or ''}"
            add_subscriber(cust_id, name, expiry_date)

            archive_msg = (f"👤 **مشترك جديد مؤكد**\n━━━━━━━━━━━━━━━\n"
                           f"📝 **الاسم:** {name}\n🆔 **الآيدي:** `{cust_id}`\n"
                           f"⏳ **مدة الاشتراك:** {duration_text}\n📅 **تاريخ الانتهاء:** `{expiry_date}`\n━━━━━━━━━━━━━━━")
            await context.bot.send_message(chat_id=ARCHIVE_CHANNEL_ID, text=archive_msg, parse_mode='Markdown')
            await query.edit_message_text(f"✅ تم قبول {name} بنجاح.")
        except Exception as e:
            await query.edit_message_text(f"⚠️ خطأ: {str(e)}")

    elif data.startswith('reject_'):
        if query.from_user.id != ADMIN_ID: return
        cust_id = int(data.split('_')[1])
        await context.bot.send_message(chat_id=cust_id, text="❌ نعتذر، لم يتم تأكيد الدفع. يرجى التواصل مع الدعم الفني.")
        await query.edit_message_text(f"❌ تم الرفض للآيدي {cust_id}.")

# --- 7. استقبال إشعارات سلة (Salla Webhook) ---
@app_flask.route('/webhook', methods=['POST'])
def salla_webhook():
    data = request.json
    if data and data.get('event') in ['subscription.created', 'subscription.charged', 'order.created']:
        customer = data['data'].get('customer', {})
        msg = f"💰 دفع جديد من سلة!\nالعميل: {customer.get('first_name')}\nالجوال: {customer.get('mobile')}"
        
        # إرسال الرسالة عبر البوت
        if application_instance:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(application_instance.bot.send_message(chat_id=ADMIN_ID, text=msg))
            
    return jsonify({'status': 'success'}), 200

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_proof'):
        user = update.effective_user
        admin_kb = [[InlineKeyboardButton("✅ قبول (30 يوم)", callback_data=f"approve_30_{user.id}")],
                    [InlineKeyboardButton("✅ قبول (90 يوم)", callback_data=f"approve_90_{user.id}")],
                    [InlineKeyboardButton("✅ قبول (180 يوم)", callback_data=f"approve_180_{user.id}")],
                    [InlineKeyboardButton("❌ رفض الطلب", callback_data=f"reject_{user.id}")]]
        
        caption = f"🔔 إثبات دفع جديد\n👤 العميل: {user.first_name}\n🆔 الآيدي: `{user.id}`"
        if update.message.photo:
            await context.bot.send_photo(chat_id=REQUESTS_CHANNEL_ID, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(admin_kb))
        else:
            await context.bot.send_message(chat_id=REQUESTS_CHANNEL_ID, text=f"{caption}\n📝 المحتوى: {update.message.text}", reply_markup=InlineKeyboardMarkup(admin_kb))
        
        await update.message.reply_text("⏳ تم إرسال إثباتك بنجاح. سيتم الرد عليك هنا فور مراجعة سلة للطلب.")
        context.user_data['waiting_for_proof'] = False

@app_flask.route('/')
def home(): return "Bot AZIZ Trading is Online"

# --- 8. تشغيل التطبيق ---
def main():
    global application_instance
    init_db()
    
    # تشغيل Flask في ثريد منفصل
    threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=PORT), daemon=True).start()
    
    application = Application.builder().token(TOKEN).build()
    application_instance = application # تخزين النسخة لاستخدامها في الـ Webhook
    
    # تفعيل نظام الجدولة إذا كان مثبتاً
    if application.job_queue:
        application.job_queue.run_repeating(daily_check_job, interval=3600, first=10)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🚀 البوت يعمل الآن بكامل المميزات...")
    application.run_polling()

if __name__ == '__main__':
    main()
