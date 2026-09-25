"""
Paltan Transactions Escrow Bot
Single-file build. Database + Keyboards + Handlers + Admin Commands + Startup Notify.
"""

import sqlite3
import telebot
from telebot import types

# ===================== HARDCODED CREDENTIALS =====================
BOT_TOKEN   = "8925443014:AAEB7ksbFqNkTS5r8UCsEtXyTjT27UDbiEc"
OWNER_ID_1  = 6871199191
OWNER_ID_2  = 2062068620
BOT_NAME    = "@PaltanTransactionsBot"
FEE_PERCENT = 4.0
DB_PATH     = "escrow.db"
# =================================================================

bot = telebot.TeleBot(BOT_TOKEN)


# ===================== DATABASE LAYER =====================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id     INTEGER PRIMARY KEY,
            username        TEXT,
            is_banned       INTEGER DEFAULT 0,
            is_admin        INTEGER DEFAULT 0,
            is_super_admin  INTEGER DEFAULT 0,
            credits         REAL DEFAULT 0.0,
            rank            INTEGER DEFAULT 0,
            total_deals     INTEGER DEFAULT 0,
            total_volume    REAL DEFAULT 0.0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id      TEXT UNIQUE,
            buyer_id      INTEGER,
            seller_id     INTEGER,
            amount        REAL,
            fee           REAL,
            net_release   REAL,
            status        TEXT DEFAULT 'pending',
            escrowed_by   INTEGER,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at  TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vouches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            deal_id     TEXT,
            message     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS global_stats (
            key    TEXT PRIMARY KEY,
            value  REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id    INTEGER,
            action      TEXT,
            details     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key    TEXT PRIMARY KEY,
            value  TEXT
        )
    """)

    c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_deals', 0)")
    c.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_volume', 0.0)")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_mode', '1')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_join', '')")
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def create_user(user_id, username):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()


def update_user(user_id, **kwargs):
    if not kwargs:
        return
    conn = get_db()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    conn.execute(f"UPDATE users SET {fields} WHERE telegram_id = ?", values)
    conn.commit()
    conn.close()


def get_all_users():
    conn = get_db()
    rows = conn.execute("SELECT telegram_id, username FROM users").fetchall()
    conn.close()
    return rows


def get_global_stats():
    conn = get_db()
    d = conn.execute("SELECT value FROM global_stats WHERE key = 'total_deals'").fetchone()
    v = conn.execute("SELECT value FROM global_stats WHERE key = 'total_volume'").fetchone()
    conn.close()
    return (d['value'] if d else 0, v['value'] if v else 0.0)


def update_global_stats(deals_delta=0, volume_delta=0.0):
    conn = get_db()
    conn.execute("UPDATE global_stats SET value = value + ? WHERE key = 'total_deals'", (deals_delta,))
    conn.execute("UPDATE global_stats SET value = value + ? WHERE key = 'total_volume'", (volume_delta,))
    conn.commit()
    conn.close()


def log_activity(admin_id, action, details=""):
    conn = get_db()
    conn.execute("INSERT INTO activity_log (admin_id, action, details) VALUES (?, ?, ?)",
                 (admin_id, action, details))
    conn.commit()
    conn.close()


def get_activity_log(limit=15):
    conn = get_db()
    rows = conn.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows


def get_setting(key):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else None


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_user_deals(user_id, limit=10, only_pending=False):
    conn = get_db()
    if only_pending:
        rows = conn.execute(
            "SELECT trade_id FROM deals WHERE (buyer_id = ? OR seller_id = ?) AND status = 'pending' ORDER BY id DESC LIMIT ?",
            (user_id, user_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT trade_id FROM deals WHERE buyer_id = ? OR seller_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, user_id, limit)
        ).fetchall()
    conn.close()
    return rows


def get_deal(trade_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM deals WHERE trade_id = ?", (trade_id,)).fetchone()
    conn.close()
    return row


def create_deal(trade_id, buyer_id, seller_id, amount, escrowed_by):
    fee = round(amount * (FEE_PERCENT / 100.0), 2)
    net_release = round(amount - fee, 2)
    conn = get_db()
    conn.execute("""
        INSERT INTO deals (trade_id, buyer_id, seller_id, amount, fee, net_release, status, escrowed_by)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (trade_id, buyer_id, seller_id, amount, fee, net_release, escrowed_by))
    conn.commit()
    conn.close()
    return fee, net_release


def complete_deal(trade_id):
    conn = get_db()
    conn.execute("UPDATE deals SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE trade_id = ?", (trade_id,))
    conn.commit()
    conn.close()


# ===================== KEYBOARD LAYER =====================
def btn(text, callback_data, style="primary"):
    # Telegram Bot API 7.0+ style: primary | success | danger
    return {"text": text, "callback_data": callback_data, "style": style}


def make_kb(rows):
    return {"inline_keyboard": rows}


def main_menu_kb(is_admin=False):
    rows = [
        [btn("✦ My status", "my_status", "primary")],
        [btn("★ My Deals Info", "my_deals", "primary")],
        [btn("➤ My Pending Deals", "my_pending", "primary")],
        [btn("✓ Escrow Global status", "global_status", "primary")],
    ]
    if is_admin:
        rows.append([btn("🛡 Admin Panel", "admin_panel", "danger")])
    return make_kb(rows)


def admin_panel_kb():
    return make_kb([
        [btn("📨 SEND VOUCH", "admin_send_vouch", "success"), btn("💼 MANAGE DEALS", "admin_manage_deals", "primary")],
        [btn("🏆 MANAGE RANKS", "admin_manage_ranks", "primary"), btn("👑 MANAGE SUPER ADMINS", "admin_manage_super_admins", "primary")],
        [btn("🛡 MANAGE ADMINS", "admin_manage_admins", "primary"), btn("👥 VIEW USERS", "admin_view_users", "primary")],
        [btn("🚫 BAN USER", "admin_ban_user", "danger"), btn("✅ UNBAN USER", "admin_unban_user", "danger")],
        [btn("📢 BROADCAST", "admin_broadcast", "primary"), btn("📊 API STATS", "admin_api_stats", "primary")],
        [btn("📝 ACTIVITY LOG", "admin_activity_log", "primary"), btn("💸 PRICING PLANS", "admin_pricing_plans", "primary")],
        [btn("🎟 REDEEM CODES", "admin_redeem_codes", "primary"), btn("➕ ADD CREDITS", "admin_add_credits", "success")],
        [btn("➖ DEDUCT CREDITS", "admin_deduct_credits", "danger"), btn("➕ ADD CREDITS ALL", "admin_add_credits_all", "success")],
        [btn("➖ DEDUCT ALL", "admin_deduct_all", "danger"), btn("🔗 FORCE JOIN", "admin_force_join", "primary")],
        [btn("⚙️ SETTINGS", "admin_settings", "primary"), btn("📜 DEAL HISTORY", "admin_sms_history", "primary")],
        [btn("📤 EXPORT DATA", "admin_export_script", "primary"), btn("🔒 PROTECT NUMBER", "admin_protect_number", "primary")],
        [btn("📋 PROTECTED LIST", "admin_protected_list", "primary"), btn("🎯 TRACK USER", "admin_track_number", "primary")],
        [btn("🔴 TOGGLE FREE MODE", "admin_toggle_free_mode", "danger")],
        [btn("🔄 REFRESH", "admin_refresh", "primary")],
    ])


# ===================== HELPERS =====================
def is_admin(user_id):
    if user_id in (OWNER_ID_1, OWNER_ID_2):
        return True
    user = get_user(user_id)
    if not user:
        return False
    return user['is_admin'] == 1 or user['is_super_admin'] == 1


def is_super_admin(user_id):
    if user_id in (OWNER_ID_1, OWNER_ID_2):
        return True
    user = get_user(user_id)
    return bool(user and user['is_super_admin'] == 1)


def safe_edit(call, text, kb=None):
    try:
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            parse_mode="HTML", reply_markup=kb
        )
    except Exception as e:
        print(f"edit failed: {e}")


# ===================== HANDLERS =====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    create_user(user_id, username)

    if user_id in (OWNER_ID_1, OWNER_ID_2):
        update_user(user_id, is_super_admin=1, is_admin=1)

    user = get_user(user_id)
    if user and user['is_banned']:
        bot.reply_to(message, "🚫 You are banned from using this bot.")
        return

    text = (
        f"<b>Welcome {username.upper()}!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 Escrow Bot for {BOT_NAME}\n"
        f"📊 Provided by {BOT_NAME}\n\n"
        "⚡ <b>This is Your Personal Dashboard:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Select the option below 📈\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML",
                     reply_markup=main_menu_kb(is_admin(user_id)))


@bot.callback_query_handler(func=lambda call: True)
def cb_router(call):
    user_id = call.from_user.id
    data = call.data

    user = get_user(user_id)
    if not user or user['is_banned']:
        bot.answer_callback_query(call.id, "You are banned.")
        return

    # -------- USER SIDE --------
    if data == "my_status":
        rank = user['rank'] if user['rank'] > 0 else "Unranked"
        text = (
            f"✅ <b>{user['username'].upper()} Deal status!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Rank ➤ #{rank}\n"
            f"🔥 Active deals ➤ 0\n"
            f"✅ Total Escrow's ➤ {user['total_deals']}\n"
            "⚡ <b>Total Volume :</b>\n"
            "⚡ ➤ 0 TON\n"
            "💎 ➤ 0 USDT\n"
            f"💲 ➤ {user['total_volume']:.2f} ₹\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Escrow Bot for {BOT_NAME}\n"
            f"✅ Provided by {BOT_NAME} !"
        )
        safe_edit(call, text, main_menu_kb(is_admin(user_id)))

    elif data == "my_deals":
        deals = get_user_deals(user_id)
        if not deals:
            bot.answer_callback_query(call.id, "No deals found.")
            return
        rows = [[btn(d['trade_id'], f"deal_info_{d['trade_id']}", "primary")] for d in deals]
        rows.append([btn("➤ Back", "back_main", "primary")])
        safe_edit(call,
                  "❤ <b>All deals info !</b>\n"
                  "━━━━━━━━━━━━━━━━━━━━\n"
                  "Select the deal below for info :",
                  make_kb(rows))

    elif data == "my_pending":
        deals = get_user_deals(user_id, only_pending=True)
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
        safe_edit(call, text, main_menu_kb(is_admin(user_id)))

    elif data == "back_main":
        safe_edit(call,
                  "⚡ <b>Main Menu</b>\nSelect an option below:",
                  main_menu_kb(is_admin(user_id)))

    elif data.startswith("deal_info_"):
        trade_id = data.replace("deal_info_", "")
        deal = get_deal(trade_id)
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
                f"📝 Status: {deal['status']}\n"
                f"⏰ Expected Time: -\n"
                f"📍 T/C: -\n\n"
                f"👤 Escrowed By: @{user['username']}"
            )
            safe_edit(call, text,
                      make_kb([[btn("➤ Back", "my_deals", "primary")]]))

    # -------- ADMIN SIDE --------
    elif data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "Access Denied.")
            return
        safe_edit(call,
                  "🛡 <b>Admin Control Panel</b>\n"
                  "━━━━━━━━━━━━━━━━━━━━\n"
                  "Select an option:",
                  admin_panel_kb())

    elif data.startswith("admin_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "Access Denied.")
            return
        log_activity(user_id, data)
        handle_admin_action(call, user_id, data)

    else:
        bot.answer_callback_query(call.id, "Unknown action.")


def handle_admin_action(call, user_id, data):
    if data == "admin_refresh":
        safe_edit(call, "🛡 <b>Admin Control Panel</b>\nRefreshed.", admin_panel_kb())
        return

    if data == "admin_view_users":
        rows = get_all_users()
        text = "👥 <b>Registered Users:</b>\n\n"
        for u in rows[:30]:
            text += f"• @{u['username']} — <code>{u['telegram_id']}</code>\n"
        if len(rows) > 30:
            text += f"\n... and {len(rows) - 30} more."
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_activity_log":
        logs = get_activity_log()
        text = "📝 <b>Recent Activity Log:</b>\n\n"
        for l in logs:
            text += f"• <code>{l['admin_id']}</code> → {l['action']}\n"
        if not logs:
            text += "No activity yet."
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_api_stats":
        conn_users = len(get_all_users())
        d, v = get_global_stats()
        text = (
            "📊 <b>API Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• Users: {conn_users}\n"
            f"• Deals: {int(d)}\n"
            f"• Volume: ₹{v:.2f}\n"
            f"• Status: ✅ Active\n"
            f"• Uptime: 100%"
        )
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_pricing_plans":
        free = get_setting('free_mode')
        text = (
            "💸 <b>Pricing Plans</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• Current Fee: <b>{FEE_PERCENT}%</b>\n"
            f"• Free Mode: {'🟢 ON' if free == '1' else '🔴 OFF'}\n\n"
            "Fee change karne ke liye bot.py me FEE_PERCENT edit karke redeploy kar."
        )
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_toggle_free_mode":
        cur = get_setting('free_mode')
        new_val = '0' if cur == '1' else '1'
        set_setting('free_mode', new_val)
        safe_edit(call,
                  f"⚙️ Free Mode is now {'🟢 ON' if new_val == '1' else '🔴 OFF'}.",
                  admin_panel_kb())
        return

    if data == "admin_settings":
        fj = get_setting('force_join') or "(not set)"
        free = get_setting('free_mode')
        text = (
            "⚙️ <b>Bot Settings</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• Bot Name: {BOT_NAME}\n"
            f"• Owner 1: <code>{OWNER_ID_1}</code>\n"
            f"• Owner 2: <code>{OWNER_ID_2}</code>\n"
            f"• Fee: {FEE_PERCENT}%\n"
            f"• Free Mode: {'🟢' if free == '1' else '🔴'}\n"
            f"• Force Join: {fj}"
        )
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_sms_history":
        conn = get_db()
        rows = conn.execute("SELECT trade_id, amount, status FROM deals ORDER BY id DESC LIMIT 15").fetchall()
        conn.close()
        text = "📜 <b>Recent Deals:</b>\n\n"
        for r in rows:
            text += f"• <code>{r['trade_id']}</code> — ₹{r['amount']} [{r['status']}]\n"
        if not rows:
            text += "No deals yet."
        safe_edit(call, text, admin_panel_kb())
        return

    if data == "admin_export_script":
        conn = get_db()
        rows = conn.execute("SELECT * FROM deals").fetchall()
        conn.close()
        if not rows:
            bot.answer_callback_query(call.id, "No deals to export.")
            return
        csv_lines = ["trade_id,buyer_id,seller_id,amount,fee,net_release,status"]
        for r in rows:
            csv_lines.append(f"{r['trade_id']},{r['buyer_id']},{r['seller_id']},{r['amount']},{r['fee']},{r['net_release']},{r['status']}")
        csv_data = "\n".join(csv_lines)
        bot.send_message(call.message.chat.id, f"<pre>{csv_data[:3800]}</pre>", parse_mode="HTML")
        bot.answer_callback_query(call.id, "Exported.")
        return

    # Simple ack for buttons needing reply-based input
    ack_map = {
        "admin_send_vouch": "Vouch send karne ke liye user ko reply karke /sendvouch likh.",
        "admin_manage_deals": "Deal management: /newdeal <buyer_id> <seller_id> <amount> use kar.",
        "admin_manage_ranks": "Rank management: /setrank <user_id> <rank> use kar.",
        "admin_manage_super_admins": "Super admin add: /addsuper <user_id> | remove: /rmsuper <user_id>",
        "admin_manage_admins": "Admin add: /addadmin <user_id> | remove: /rmadmin <user_id>",
        "admin_ban_user": "Reply to a user's message with /ban.",
        "admin_unban_user": "Reply to a user's message with /unban.",
        "admin_broadcast": "Send /broadcast <message> to notify all users.",
        "admin_redeem_codes": "Redeem code: /gencode <amount> | /redeem <code>",
        "admin_add_credits": "Reply to a user with /addcredits <amount>.",
        "admin_deduct_credits": "Reply to a user with /deductcredits <amount>.",
        "admin_add_credits_all": "Send /addall <amount> to credit everyone.",
        "admin_deduct_all": "Send /deductall <amount> to debit everyone.",
        "admin_force_join": "Send /setforcejoin <@channel> to set force-join channel.",
        "admin_protect_number": "Send /protect <user_id> to protect a user.",
        "admin_protected_list": "Protected list: /protectedlist",
        "admin_track_number": "Send /track <user_id> to view user details.",
    }
    bot.answer_callback_query(call.id, ack_map.get(data, "Action triggered."))


# ===================== ADMIN TEXT COMMANDS =====================
@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message with /ban.")
        return
    target = message.reply_to_message.from_user.id
    update_user(target, is_banned=1)
    log_activity(message.from_user.id, "ban", str(target))
    bot.reply_to(message, f"🚫 User <code>{target}</code> banned.", parse_mode="HTML")


@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message with /unban.")
        return
    target = message.reply_to_message.from_user.id
    update_user(target, is_banned=0)
    log_activity(message.from_user.id, "unban", str(target))
    bot.reply_to(message, f"✅ User <code>{target}</code> unbanned.", parse_mode="HTML")


@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/broadcast", "", 1).strip()
    if not text:
        bot.reply_to(message, "Usage: /broadcast <message>")
        return
    users = get_all_users()
    ok, fail = 0, 0
    for u in users:
        try:
            bot.send_message(u['telegram_id'], text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
    log_activity(message.from_user.id, "broadcast", f"ok={ok} fail={fail}")
    bot.reply_to(message, f"📢 Broadcast: ✅ {ok} | ❌ {fail}")


@bot.message_handler(commands=['addcredits'])
def cmd_addcredits(message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message with /addcredits <amount>.")
        return
    try:
        amount = float(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /addcredits <amount>")
        return
    target = message.reply_to_message.from_user.id
    u = get_user(target)
    if u:
        update_user(target, credits=u['credits'] + amount)
        bot.reply_to(message, f"➕ Added {amount} credits to <code>{target}</code>.", parse_mode="HTML")


@bot.message_handler(commands=['deductcredits'])
def cmd_deductcredits(message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, "Reply to a user's message with /deductcredits <amount>.")
        return
    try:
        amount = float(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /deductcredits <amount>")
        return
    target = message.reply_to_message.from_user.id
    u = get_user(target)
    if u:
        update_user(target, credits=max(0.0, u['credits'] - amount))
        bot.reply_to(message, f"➖ Deducted {amount} credits from <code>{target}</code>.", parse_mode="HTML")


@bot.message_handler(commands=['addall'])
def cmd_addall(message):
    if not is_super_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /addall <amount>")
        return
    conn = get_db()
    conn.execute("UPDATE users SET credits = credits + ?", (amount,))
    conn.commit()
    conn.close()
    log_activity(message.from_user.id, "addall", str(amount))
    bot.reply_to(message, f"➕ Added {amount} credits to everyone.")


@bot.message_handler(commands=['deductall'])
def cmd_deductall(message):
    if not is_super_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /deductall <amount>")
        return
    conn = get_db()
    conn.execute("UPDATE users SET credits = MAX(0, credits - ?)", (amount,))
    conn.commit()
    conn.close()
    log_activity(message.from_user.id, "deductall", str(amount))
    bot.reply_to(message, f"➖ Deducted {amount} credits from everyone.")


@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(message):
    if not is_super_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /addadmin <user_id>")
        return
    create_user(uid, "admin")
    update_user(uid, is_admin=1)
    log_activity(message.from_user.id, "addadmin", str(uid))
    bot.reply_to(message, f"🛡 User <code>{uid}</code> is now admin.", parse_mode="HTML")


@bot.message_handler(commands=['rmadmin'])
def cmd_rmadmin(message):
    if not is_super_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /rmadmin <user_id>")
        return
    update_user(uid, is_admin=0)
    log_activity(message.from_user.id, "rmadmin", str(uid))
    bot.reply_to(message, f"User <code>{uid}</code> removed from admins.", parse_mode="HTML")


@bot.message_handler(commands=['addsuper'])
def cmd_addsuper(message):
    if message.from_user.id not in (OWNER_ID_1, OWNER_ID_2):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /addsuper <user_id>")
        return
    create_user(uid, "super")
    update_user(uid, is_super_admin=1, is_admin=1)
    log_activity(message.from_user.id, "addsuper", str(uid))
    bot.reply_to(message, f"👑 User <code>{uid}</code> is now Super Admin.", parse_mode="HTML")


@bot.message_handler(commands=['rmsuper'])
def cmd_rmsuper(message):
    if message.from_user.id not in (OWNER_ID_1, OWNER_ID_2):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /rmsuper <user_id>")
        return
    update_user(uid, is_super_admin=0)
    log_activity(message.from_user.id, "rmsuper", str(uid))
    bot.reply_to(message, f"User <code>{uid}</code> removed from super admins.", parse_mode="HTML")


@bot.message_handler(commands=['setrank'])
def cmd_setrank(message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
        rank = int(message.text.split()[2])
    except Exception:
        bot.reply_to(message, "Usage: /setrank <user_id> <rank>")
        return
    update_user(uid, rank=rank)
    log_activity(message.from_user.id, "setrank", f"{uid}->{rank}")
    bot.reply_to(message, f"🏆 Rank #{rank} set for <code>{uid}</code>.", parse_mode="HTML")


@bot.message_handler(commands=['newdeal'])
def cmd_newdeal(message):
    if not is_admin(message.from_user.id):
        return
    try:
        parts = message.text.split()
        buyer = int(parts[1])
        seller = int(parts[2])
        amount = float(parts[3])
        trade_id = f"DL-PALTAN-{int(__import__('time').time())}"
    except Exception:
        bot.reply_to(message, "Usage: /newdeal <buyer_id> <seller_id> <amount>")
        return
    fee, net = create_deal(trade_id, buyer, seller, amount, message.from_user.id)
    update_global_stats(1, amount)
    log_activity(message.from_user.id, "newdeal", trade_id)
    bot.reply_to(
        message,
        f"✅ Deal created: <code>{trade_id}</code>\n"
        f"Amount: ₹{amount:.2f} | Fee: ₹{fee:.2f} | Net: ₹{net:.2f}",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['completedeal'])
def cmd_completedeal(message):
    if not is_admin(message.from_user.id):
        return
    try:
        trade_id = message.text.split()[1]
    except Exception:
        bot.reply_to(message, "Usage: /completedeal <trade_id>")
        return
    complete_deal(trade_id)
    log_activity(message.from_user.id, "completedeal", trade_id)
    bot.reply_to(message, f"✅ Deal <code>{trade_id}</code> completed.", parse_mode="HTML")


@bot.message_handler(commands=['track'])
def cmd_track(message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /track <user_id>")
        return
    u = get_user(uid)
    if not u:
        bot.reply_to(message, "User not found.")
        return
    text = (
        f"🎯 <b>User Track</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• ID: <code>{u['telegram_id']}</code>\n"
        f"• Username: @{u['username']}\n"
        f"• Banned: {'Yes' if u['is_banned'] else 'No'}\n"
        f"• Admin: {'Yes' if u['is_admin'] else 'No'}\n"
        f"• Super Admin: {'Yes' if u['is_super_admin'] else 'No'}\n"
        f"• Credits: {u['credits']}\n"
        f"• Rank: {u['rank']}\n"
        f"• Deals: {u['total_deals']}\n"
        f"• Volume: ₹{u['total_volume']:.2f}"
    )
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(commands=['setforcejoin'])
def cmd_setforcejoin(message):
    if not is_super_admin(message.from_user.id):
        return
    try:
        channel = message.text.split()[1]
    except Exception:
        bot.reply_to(message, "Usage: /setforcejoin @channel")
        return
    set_setting('force_join', channel)
    log_activity(message.from_user.id, "setforcejoin", channel)
    bot.reply_to(message, f"🔗 Force join set to {channel}")


@bot.message_handler(commands=['protect'])
def cmd_protect(message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except Exception:
        bot.reply_to(message, "Usage: /protect <user_id>")
        return
    set_setting(f'protected_{uid}', '1')
    bot.reply_to(message, f"🔒 User <code>{uid}</code> protected.", parse_mode="HTML")


@bot.message_handler(commands=['protectedlist'])
def cmd_protectedlist(message):
    if not is_admin(message.from_user.id):
        return
    conn = get_db()
    rows = conn.execute("SELECT key FROM settings WHERE key LIKE 'protected_%'").fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No protected users.")
        return
    text = "📋 <b>Protected Users:</b>\n\n"
    for r in rows:
        text += f"• <code>{r['key'].replace('protected_', '')}</code>\n"
    bot.reply_to(message, text, parse_mode="HTML")


@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    if not is_admin(message.from_user.id):
        return
    d, v = get_global_stats()
    users = len(get_all_users())
    bot.reply_to(
        message,
        f"📊 Users: {users} | Deals: {int(d)} | Volume: ₹{v:.2f}",
        parse_mode="HTML"
    )


# ===================== STARTUP NOTIFICATION =====================
def notify_owners_startup():
    msg = (
        "🤖 <b>Paltan Transactions Bot is ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Bot: {BOT_NAME}\n"
        "🔹 Status: 🟢 Active\n"
        "🔹 Database: ✅ Connected\n"
        "🔹 Admin Panel: ✅ Ready\n"
        "🔹 Fee: " + str(FEE_PERCENT) + "%\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Use /start to open the dashboard."
    )
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try:
            bot.send_message(oid, msg, parse_mode="HTML")
        except Exception as e:
            print(f"[startup notify] owner {oid}: {e}")


# ===================== ENTRY =====================
def main():
    init_db()
    print("✅ Database ready.")
    notify_owners_startup()
    print("🤖 Bot polling...")
    bot.infinity_polling()


if __name__ == "__main__":
    main()