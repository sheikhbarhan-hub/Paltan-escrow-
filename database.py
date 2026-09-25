import os
import telebot
from dotenv import load_dotenv
from database import init_db, get_user, create_user, update_user, get_global_stats, update_global_stats, get_db
from keyboards import main_menu_keyboard, admin_panel_keyboard

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID_1 = int(os.getenv("OWNER_ID_1"))
OWNER_ID_2 = int(os.getenv("OWNER_ID_2"))
BOT_NAME = os.getenv("BOT_NAME", "@PaltanTransactionsBot")
FEE_PERCENT = float(os.getenv("FEE_PERCENT", 4.0))

bot = telebot.TeleBot(BOT_TOKEN)

def is_admin(user_id):
    user = get_user(user_id)
    if not user:
        return False
    return user['is_admin'] == 1 or user['is_super_admin'] == 1 or user_id in [OWNER_ID_1, OWNER_ID_2]

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    create_user(user_id, username)
    
    if user_id in [OWNER_ID_1, OWNER_ID_2]:
        update_user(user_id, is_super_admin=1, is_admin=1)
    
    user = get_user(user_id)
    if user['is_banned']:
        bot.reply_to(message, "🚫 You are banned from using this bot.")
        return
    
    text = (
        f"<b>Welcome {username.upper()}!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💬 Escrow Bot for " + BOT_NAME + "\n"
        "📊 Provided by " + BOT_NAME + "\n\n"
        "⚡ <b>This is Your Personal Dashboard:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Select the option below 📈\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=main_menu_keyboard(is_admin(user_id)))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    user = get_user(user_id)
    
    if not user or user['is_banned']:
        bot.answer_callback_query(call.id, "You are banned.")
        return

    if data == "my_status":
        deals = user['total_deals']
        volume = user['total_volume']
        rank = user['rank'] if user['rank'] > 0 else "Unranked"
        text = (
            f"✅ <b>{user['username'].upper()} Deal status!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Rank ➤ #{rank}\n"
            f"🔥 Active deals ➤ 0\n"
            f"✅ Total Escrow's ➤ {deals}\n"
            "⚡ <b>Total Volume :</b>\n"
            f"⚡ ➤ 0 TON\n"
            f"💎 ➤ 0 USDT\n"
            f"💲 ➤ {volume:.2f} ₹\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Escrow Bot for {BOT_NAME}\n"
            f"✅ Provided by {BOT_NAME} !"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(is_admin(user_id)))
    
    elif data == "my_deals":
        conn = get_db()
        deals = conn.execute("SELECT trade_id FROM deals WHERE buyer_id = ? OR seller_id = ? ORDER BY id DESC LIMIT 10", (user_id, user_id)).fetchall()
        conn.close()
        
        if not deals:
            bot.answer_callback_query(call.id, "No deals found.")
            return
        
        rows = [[{"text": d['trade_id'], "callback_data": f"deal_info_{d['trade_id']}"}] for d in deals]
        rows.append([{"text": "➤ Back", "callback_data": "back_main"}])
        bot.edit_message_text("❤ <b>All deals info !</b>\n━━━━━━━━━━━━━━━━━━━━\nSelect the deal below for info :", 
                             call.message.chat.id, call.message.message_id, parse_mode="HTML", 
                             reply_markup={"inline_keyboard": rows})

    elif data == "my_pending":
        conn = get_db()
        deals = conn.execute("SELECT trade_id FROM deals WHERE (buyer_id = ? OR seller_id = ?) AND status = 'pending'", (user_id, user_id)).fetchall()
        conn.close()
        if not deals:
            bot.answer_callback_query(call.id, "Koi pending deal nahi hai.")
        else:
            bot.answer_callback_query(call.id, f"You have {len(deals)} pending deals.")

    elif data == "global_status":
        deals, volume = get_global_stats()
        text = (
            "🚀 <b>Escrow Global Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 Total Deals: {int(deals)}\n\n"
            "📈 <b>Total Volume:</b>\n"
            "⚡ - 0 TON\n"
            "💎 - 0 USDT\n"
            f"💲 - {volume:.2f} ₹\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Escrow Bot for {BOT_NAME}\n"
            f"✅ Provided by {BOT_NAME}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(is_admin(user_id)))

    elif data == "back_main":
        text = "⚡ <b>Main Menu</b>\nSelect an option below:"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=main_menu_keyboard(is_admin(user_id)))

    elif data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "Access Denied.")
            return
        bot.edit_message_text("🛡 <b>Admin Control Panel</b>\nSelect an option:", 
                             call.message.chat.id, call.message.message_id, parse_mode="HTML", 
                             reply_markup=admin_panel_keyboard())

    elif data.startswith("deal_info_"):
        trade_id = data.replace("deal_info_", "")
        conn = get_db()
        deal = conn.execute("SELECT * FROM deals WHERE trade_id = ?", (trade_id,)).fetchone()
        conn.close()
        if deal:
            text = (
                f"💎 <b>Deal Details: {deal['trade_id']}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💎 Deal Amount: ₹{deal['amount']:.2f}\n"
                f"📤 Fee: {FEE_PERCENT}% — ₹{deal['fee']:.2f}\n"
                f"📤 Net Release: ₹{deal['net_release']:.2f}\n"
                f"📊 Trade ID: {deal['trade_id']}\n\n"
                f"👤 Buyer: {deal['buyer_id']}\n"
                f"👤 Seller: {deal['seller_id']}\n"
                f"📝 Detail: {deal['status']}\n"
                f"⏰ Expected Time: -\n"
                f"📍 T/C: -\n\n"
                f"👤 Escrowed By: @{user['username']}"
            )
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", 
                                 reply_markup={"inline_keyboard": [[{"text": "➤ Back", "callback_data": "my_deals"}]]})

    else:
        bot.answer_callback_query(call.id, "Feature coming soon.")

def main():
    init_db()
    print("Bot is running...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
