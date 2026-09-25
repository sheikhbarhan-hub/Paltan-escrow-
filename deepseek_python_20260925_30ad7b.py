"""
Paltan Transactions Escrow Bot — Advanced Escrow Mediator
Buyer ↔ Seller ↔ Admin Mediator. Colored buttons. Fee auto-cut. Deal chat, dispute, vouch.
"""

import asyncio
import random
import sqlite3
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
)

# ===================== CREDENTIALS =====================
BOT_TOKEN  = "8925443014:AAEB7ksbFqNkTS5r8UCsEtXyTjT27UDbiEc"
OWNER_ID_1 = 6871199191
OWNER_ID_2 = 2062068620
BOT_NAME   = "@PaltanTransactionsBot"
DEFAULT_FEE = 15.0   # %
DB_PATH    = "escrow.db"
# ======================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---- colored button support ----
HAS_STYLE = False
try:
    _t = InlineKeyboardButton(text="t", callback_data="t", style="success")
    HAS_STYLE = getattr(_t, "style", None) is not None
except Exception:
    HAS_STYLE = False


class ChatRelay(StatesGroup):
    waiting_message = State()


# ===================== DATABASE =====================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    c = db(); cur = c.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0,
            total_deals INTEGER DEFAULT 0,
            completed_deals INTEGER DEFAULT 0,
            disputed_deals INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0.0,
            rating REAL DEFAULT 0.0,
            vouch_count INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            buyer_id INTEGER,
            seller_id INTEGER,
            mediator_id INTEGER,
            amount REAL,
            fee REAL,
            net_release REAL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            buyer_confirmed INTEGER DEFAULT 0,
            seller_confirmed INTEGER DEFAULT 0,
            payment_received_at TIMESTAMP,
            delivered_at TIMESTAMP,
            completed_at TIMESTAMP,
            cancel_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deal_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            sender_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            actor_id INTEGER,
            action TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vouches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            from_id INTEGER,
            to_id INTEGER,
            rating INTEGER,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
    """)

    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fee_percent', ?)", (str(DEFAULT_FEE),))
    c.commit(); c.close()


# ================ USERS ================
def get_user(uid):
    c = db(); r = c.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)).fetchone(); c.close(); return r


def create_user(uid, username):
    c = db()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (uid, username))
    c.commit(); c.close()


def update_user(uid, **kw):
    if not kw: return
    c = db()
    f = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE users SET {f} WHERE telegram_id=?", list(kw.values()) + [uid])
    c.commit(); c.close()


def all_users():
    c = db(); r = c.execute("SELECT telegram_id, username FROM users").fetchall(); c.close(); return r


# ================ DEALS ================
def new_trade_id():
    return f"ESC-{random.randint(100000, 999999)}"


def create_deal(trade_id, buyer_id, seller_id, amount, description):
    fee_pct = get_fee()
    fee = round(amount * fee_pct / 100.0, 2)
    net = round(amount - fee, 2)
    c = db()
    c.execute("""INSERT INTO deals
                 (trade_id, buyer_id, seller_id, mediator_id, amount, fee, net_release, description, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
              (trade_id, buyer_id, seller_id, OWNER_ID_1, amount, fee, net, description))
    c.commit(); c.close()
    return fee, net


def get_deal(tid):
    c = db(); r = c.execute("SELECT * FROM deals WHERE trade_id=?", (tid,)).fetchone(); c.close(); return r


def update_deal(tid, **kw):
    if not kw: return
    c = db()
    f = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE deals SET {f} WHERE trade_id=?", list(kw.values()) + [tid])
    c.commit(); c.close()


def user_deals(uid, limit=15):
    c = db()
    r = c.execute("""SELECT trade_id, status, amount FROM deals
                     WHERE buyer_id=? OR seller_id=?
                     ORDER BY id DESC LIMIT ?""", (uid, uid, limit)).fetchall()
    c.close(); return r


def all_deals(limit=30, status=None):
    c = db()
    if status:
        r = c.execute("SELECT * FROM deals WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
    else:
        r = c.execute("SELECT * FROM deals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close(); return r


def log_event(tid, actor_id, action, notes=""):
    c = db()
    c.execute("INSERT INTO deal_events (trade_id, actor_id, action, notes) VALUES (?, ?, ?, ?)",
              (tid, actor_id, action, notes))
    c.commit(); c.close()


def get_events(tid, limit=20):
    c = db()
    r = c.execute("SELECT * FROM deal_events WHERE trade_id=? ORDER BY id DESC LIMIT ?", (tid, limit)).fetchall()
    c.close(); return r


def add_deal_msg(tid, sender_id, content):
    c = db()
    c.execute("INSERT INTO deal_messages (trade_id, sender_id, content) VALUES (?, ?, ?)", (tid, sender_id, content))
    c.commit(); c.close()


def get_deal_msgs(tid, limit=15):
    c = db()
    r = c.execute("SELECT * FROM deal_messages WHERE trade_id=? ORDER BY id DESC LIMIT ?", (tid, limit)).fetchall()
    c.close(); return r


# ================ MISC ================
def get_fee():
    c = db(); r = c.execute("SELECT value FROM settings WHERE key='fee_percent'").fetchone(); c.close()
    try: return float(r['value']) if r else DEFAULT_FEE
    except: return DEFAULT_FEE


def set_fee(p):
    c = db(); c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('fee_percent', ?)", (str(p),)); c.commit(); c.close()


def gstats():
    c = db()
    d = c.execute("SELECT COUNT(*) AS n FROM deals").fetchone()
    comp = c.execute("SELECT COUNT(*) AS n FROM deals WHERE status='completed'").fetchone()
    vol = c.execute("SELECT COALESCE(SUM(amount),0) AS v FROM deals WHERE status='completed'").fetchone()
    us = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    c.close()
    return {
        "deals": d['n'] if d else 0,
        "completed": comp['n'] if comp else 0,
        "volume": vol['v'] if vol else 0.0,
        "users": us['n'] if us else 0,
    }


def log_act(admin_id, action, details=""):
    c = db()
    c.execute("INSERT INTO activity_log (admin_id, action, details) VALUES (?, ?, ?)", (admin_id, action, details))
    c.commit(); c.close()


def get_logs(limit=15):
    c = db()
    r = c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close(); return r


def add_vouch(tid, from_id, to_id, rating, comment):
    c = db()
    c.execute("INSERT INTO vouches (trade_id, from_id, to_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
              (tid, from_id, to_id, rating, comment))
    c.commit(); c.close()
    # recompute rating
    rr = db().execute("SELECT AVG(rating) AS a, COUNT(*) AS n FROM vouches WHERE to_id=?", (to_id,)).fetchone()
    if rr and rr['n']:
        update_user(to_id, rating=round(rr['a'], 2), vouch_count=rr['n'])


# ===================== HELPERS =====================
def is_admin(uid):
    if uid in (OWNER_ID_1, OWNER_ID_2): return True
    u = get_user(uid)
    return bool(u and (u['is_admin'] == 1 or u['is_super_admin'] == 1))


def is_super(uid):
    if uid in (OWNER_ID_1, OWNER_ID_2): return True
    u = get_user(uid)
    return bool(u and u['is_super_admin'] == 1)


def KB(text, data, style="primary"):
    if HAS_STYLE:
        try:
            return InlineKeyboardButton(text=text, callback_data=data, style=style)
        except Exception:
            pass
    return InlineKeyboardButton(text=text, callback_data=data)


async def show(call: CallbackQuery, text: str, kb=None):
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        try:
            await call.message.delete()
        except Exception:
            pass
        try:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e2:
            print(f"[show] {e2}")


def status_emoji(s):
    return {
        "pending": "🟡 Pending",
        "awaiting_payment": "💳 Awaiting Payment",
        "payment_received": "✅ Payment Held",
        "delivering": "🚚 Delivering",
        "delivered": "📦 Delivered",
        "completed": "🏁 Completed",
        "disputed": "⚠️ Disputed",
        "cancelled": "❌ Cancelled",
    }.get(s, s)


# ===================== KEYBOARDS =====================
def main_menu(admin=False):
    rows = [
        [KB("💼 New Deal", "new_deal", "success")],
        [KB("📂 My Deals", "my_deals", "primary")],
        [KB("👤 My Profile", "profile", "primary")],
        [KB("📊 Global Stats", "global_stats", "primary")],
        [KB("📖 Help", "help", "primary")],
    ]
    if admin:
        rows.append([KB("🛡 Admin Panel", "admin_panel", "danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [KB("📊 STATS", "adm_stats", "primary"), KB("👥 USERS", "adm_users", "primary")],
        [KB("💼 ACTIVE DEALS", "adm_active", "primary"), KB("📜 ALL DEALS", "adm_all_deals", "primary")],
        [KB("🚫 BAN USER", "adm_ban", "danger"), KB("✅ UNBAN USER", "adm_unban", "success")],
        [KB("📢 BROADCAST", "adm_broadcast", "primary"), KB("📝 ACTIVITY LOG", "adm_logs", "primary")],
        [KB("🎯 TRACK USER", "adm_track", "primary"), KB("💸 SET FEE", "adm_setfee", "primary")],
        [KB("📤 EXPORT DEALS", "adm_export", "primary"), KB("📜 DISPUTES", "adm_disputes", "primary")],
        [KB("⚙️ SETTINGS", "adm_settings", "primary")],
        [KB("🔄 REFRESH", "adm_refresh", "primary")],
        [KB("⬅ Back to Main", "back_main", "primary")],
    ])


def deal_actions_kb(deal, uid):
    """Buttons relevant to the deal + current user role."""
    rows = []
    tid = deal['trade_id']
    status = deal['status']
    is_buyer = (uid == deal['buyer_id'])
    is_seller = (uid == deal['seller_id'])
    adm = is_admin(uid)

    if status == "pending":
        if is_buyer and not deal['buyer_confirmed']:
            rows.append([KB("✅ Confirm as Buyer", f"conf_buyer_{tid}", "success")])
        if is_seller and not deal['seller_confirmed']:
            rows.append([KB("✅ Confirm as Seller", f"conf_seller_{tid}", "success")])
        if (is_buyer or is_seller) and deal['buyer_confirmed'] and deal['seller_confirmed']:
            rows.append([KB("💳 Proceed to Payment", f"proceed_pay_{tid}", "primary")])

    if status == "awaiting_payment":
        if is_buyer:
            rows.append([KB("💰 I Have Sent Payment", f"paid_{tid}", "success")])
        if adm:
            rows.append([KB("✅ Confirm Payment Received", f"adm_payrecv_{tid}", "success")])

    if status == "payment_received":
        if is_seller:
            rows.append([KB("🚚 I Am Delivering", f"delivering_{tid}", "primary")])
            rows.append([KB("📦 Mark Delivered", f"delivered_{tid}", "success")])

    if status == "delivering":
        if is_seller:
            rows.append([KB("📦 Mark Delivered", f"delivered_{tid}", "success")])
        if is_buyer:
            rows.append([KB("✅ Confirm Received", f"received_{tid}", "success")])

    if status == "delivered":
        if is_buyer:
            rows.append([KB("✅ Confirm Received", f"received_{tid}", "success")])

    rows.append([KB("💬 Message Other Party", f"msg_{tid}", "primary")])
    rows.append([KB("📜 Chat Log", f"chatlog_{tid}", "primary")])
    rows.append([KB("📜 Deal Timeline", f"timeline_{tid}", "primary")])

    if status not in ("completed", "cancelled"):
        rows.append([KB("⚠️ Raise Dispute", f"dispute_{tid}", "danger")])

    if adm:
        rows.append([KB("🏁 Force Release", f"adm_release_{tid}", "success")])
        rows.append([KB("❌ Cancel Deal", f"adm_cancel_{tid}", "danger")])

    rows.append([KB("⬅ Back", "my_deals", "primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ===================== RENDERERS =====================
def deal_text(deal):
    return (
        f"💼 <b>Deal: {deal['trade_id']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Status: {status_emoji(deal['status'])}\n\n"
        f"💰 Amount: ₹{deal['amount']:.2f}\n"
        f"💸 Fee ({get_fee()}%): ₹{deal['fee']:.2f}\n"
        f"🎁 Net to Seller: ₹{deal['net_release']:.2f}\n\n"
        f"👤 Buyer: <code>{deal['buyer_id']}</code>\n"
        f"👤 Seller: <code>{deal['seller_id']}</code>\n"
        f"🛡 Mediator: <code>{deal['mediator_id']}</code>\n\n"
        f"📝 Description:\n{deal['description'] or '-'}\n\n"
        f"✅ Buyer Confirmed: {'Yes' if deal['buyer_confirmed'] else 'No'}\n"
        f"✅ Seller Confirmed: {'Yes' if deal['seller_confirmed'] else 'No'}\n"
        f"🕓 Created: {deal['created_at']}"
    )


def user_profile_text(u):
    return (
        f"👤 <b>Profile: @{u['username']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{u['telegram_id']}</code>\n"
        f"📅 Joined: {u['joined_at']}\n\n"
        f"💼 Total Deals: {u['total_deals']}\n"
        f"🏁 Completed: {u['completed_deals']}\n"
        f"⚠️ Disputes: {u['disputed_deals']}\n"
        f"💰 Volume: ₹{u['total_volume']:.2f}\n"
        f"⭐ Rating: {u['rating']:.2f} ({u['vouch_count']} vouches)\n"
        f"🚫 Banned: {'Yes' if u['is_banned'] else 'No'}"
    )


# ===================== COMMANDS =====================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    try:
        uid = m.from_user.id
        username = m.from_user.username or "Unknown"
        create_user(uid, username)
        if uid in (OWNER_ID_1, OWNER_ID_2):
            update_user(uid, is_super_admin=1, is_admin=1)
        u = get_user(uid)
        if u and u['is_banned']:
            await m.reply("🚫 You are banned from using this bot.")
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
        await m.answer(text, parse_mode="HTML", reply_markup=main_menu(is_admin(uid)))
    except Exception as e:
        print(f"[start] {e}")
        await m.reply(f"⚠️ Error: {e}")


@dp.message(Command("help"))
async def cmd_help(m: Message):
    text = (
        "📖 <b>Paltan Escrow — Help</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>USER COMMANDS</b>\n"
        "/start — Open dashboard\n"
        "/newdeal &lt;amount&gt; &lt;description&gt; — Start a new deal\n"
        "/mydeals — List your deals\n"
        "/deal &lt;trade_id&gt; — View deal details\n"
        "/confirm &lt;trade_id&gt; — Confirm your side\n"
        "/paid &lt;trade_id&gt; — Buyer: I've sent payment\n"
        "/delivering &lt;trade_id&gt; — Seller: started delivering\n"
        "/delivered &lt;trade_id&gt; — Seller: delivered\n"
        "/received &lt;trade_id&gt; — Buyer: received, release funds\n"
        "/dispute &lt;trade_id&gt; — Raise a dispute\n"
        "/msg &lt;trade_id&gt; &lt;text&gt; — Message other party\n"
        "/vouch &lt;trade_id&gt; &lt;1-5&gt; &lt;comment&gt; — Leave a vouch\n"
        "/profile — Your profile\n"
        "/stats — Global bot statistics\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>ADMIN COMMANDS</b>\n"
        "/admin — Open admin panel\n"
        "/viewusers — List all users\n"
        "/viewdeals — List all deals\n"
        "/dealinfo &lt;trade_id&gt; — Deal details\n"
        "/release &lt;trade_id&gt; — Force release funds\n"
        "/canceldeal &lt;trade_id&gt; [reason]\n"
        "/ban &lt;user_id&gt; (or reply)\n"
        "/unban &lt;user_id&gt; (or reply)\n"
        "/broadcast &lt;msg&gt;\n"
        "/track &lt;user_id&gt;\n"
        "/setfee &lt;percent&gt;\n"
        "/addadmin &lt;id&gt; | /rmadmin &lt;id&gt;\n"
        "/addsuper &lt;id&gt; | /rmsuper &lt;id&gt;\n"
        "/logs | /export | /stats"
    )
    await m.reply(text, parse_mode="HTML")


@dp.message(Command("newdeal"))
async def cmd_newdeal(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 3:
            await m.reply("Usage: /newdeal <amount> <seller_id> <description>\n"
                          "Example: /newdeal 500 123456789 iPhone 13 sale")
            return
        amount = float(parts[1])
        rest = parts[2].split(maxsplit=1)
        if len(rest) < 2:
            await m.reply("Usage: /newdeal <amount> <seller_id> <description>")
            return
        seller_id = int(rest[0])
        desc = rest[1]
        buyer_id = m.from_user.id
        if seller_id == buyer_id:
            await m.reply("You can't be both buyer and seller.")
            return
        create_user(seller_id, "seller")
        tid = new_trade_id()
        fee, net = create_deal(tid, buyer_id, seller_id, amount, desc)
        update_user(buyer_id, total_deals=(get_user(buyer_id)['total_deals'] or 0) + 1)
        update_user(seller_id, total_deals=(get_user(seller_id)['total_deals'] or 0) + 1)
        log_event(tid, buyer_id, "created", f"amount={amount}")

        # notify buyer
        await m.reply(
            f"✅ <b>Deal Created: {tid}</b>\n"
            f"Amount: ₹{amount:.2f} | Fee: ₹{fee:.2f} | Net: ₹{net:.2f}\n"
            f"Seller: <code>{seller_id}</code>\n"
            f"Use /deal {tid} for details.",
            parse_mode="HTML"
        )
        # notify seller
        try:
            await bot.send_message(
                seller_id,
                f"🔔 <b>New Deal Request</b>\n"
                f"Trade ID: <code>{tid}</code>\n"
                f"Buyer: <code>{buyer_id}</code>\n"
                f"Amount: ₹{amount:.2f}\n"
                f"Description: {desc}\n\n"
                f"Use /deal {tid} to view and confirm.",
                parse_mode="HTML"
            )
        except Exception:
            pass
        # notify owners
        for oid in (OWNER_ID_1, OWNER_ID_2):
            try:
                await bot.send_message(oid,
                    f"🆕 <b>New Deal Created</b>\n"
                    f"Trade ID: <code>{tid}</code>\nBuyer: <code>{buyer_id}</code>\nSeller: <code>{seller_id}</code>\nAmount: ₹{amount:.2f}",
                    parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        await m.reply(f"⚠️ Error: {e}")


@dp.message(Command("mydeals"))
async def cmd_mydeals(m: Message):
    rows = user_deals(m.from_user.id)
    if not rows:
        await m.reply("No deals yet. Start with /newdeal.")
        return
    text = "📂 <b>Your Deals:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for r in rows:
        text += f"• <code>{r['trade_id']}</code> — ₹{r['amount']:.2f} [{status_emoji(r['status'])}]\n"
    await m.reply(text, parse_mode="HTML")


@dp.message(Command("deal"))
async def cmd_deal(m: Message):
    try:
        tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /deal <trade_id>")
        return
    d = get_deal(tid)
    if not d:
        await m.reply("Deal not found.")
        return
    uid = m.from_user.id
    if uid not in (d['buyer_id'], d['seller_id']) and not is_admin(uid):
        await m.reply("You're not part of this deal.")
        return
    await m.reply(deal_text(d), parse_mode="HTML", reply_markup=deal_actions_kb(d, uid))


@dp.message(Command("confirm"))
async def cmd_confirm(m: Message):
    try: tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /confirm <trade_id>"); return
    d = get_deal(tid)
    if not d:
        await m.reply("Deal not found."); return
    uid = m.from_user.id
    if uid == d['buyer_id']:
        update_deal(tid, buyer_confirmed=1)
        log_event(tid, uid, "buyer_confirmed")
        await m.reply("✅ You confirmed as buyer.")
    elif uid == d['seller_id']:
        update_deal(tid, seller_confirmed=1)
        log_event(tid, uid, "seller_confirmed")
        await m.reply("✅ You confirmed as seller.")
    else:
        await m.reply("You're not part of this deal."); return
    d = get_deal(tid)
    if d['buyer_confirmed'] and d['seller_confirmed']:
        update_deal(tid, status="awaiting_payment")
        log_event(tid, uid, "both_confirmed")
        await m.reply(f"🎯 Both parties confirmed. Buyer should send ₹{d['amount']:.2f} to the mediator.")


@dp.message(Command("paid"))
async def cmd_paid(m: Message):
    try: tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /paid <trade_id>"); return
    d = get_deal(tid)
    if not d or m.from_user.id != d['buyer_id']:
        await m.reply("Invalid."); return
    update_deal(tid, status="awaiting_payment")  # already expected
    log_event(tid, m.from_user.id, "buyer_paid")
    await m.reply("✅ Marked as paid. Waiting for mediator confirmation.")
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try:
            await bot.send_message(oid,
                f"💰 <b>Buyer Claims Payment Sent</b>\nTrade: <code>{tid}</code>\nFrom: <code>{m.from_user.id}</code>",
                parse_mode="HTML")
        except Exception: pass


@dp.message(Command("delivering"))
async def cmd_delivering(m: Message):
    try: tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /delivering <trade_id>"); return
    d = get_deal(tid)
    if not d or m.from_user.id != d['seller_id']:
        await m.reply("Invalid."); return
    update_deal(tid, status="delivering")
    log_event(tid, m.from_user.id, "seller_delivering")
    await m.reply("🚚 Seller delivering.")


@dp.message(Command("delivered"))
async def cmd_delivered(m: Message):
    try: tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /delivered <trade_id>"); return
    d = get_deal(tid)
    if not d or m.from_user.id != d['seller_id']:
        await m.reply("Invalid."); return
    update_deal(tid, status="delivered", delivered_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log_event(tid, m.from_user.id, "seller_delivered")
    await m.reply("📦 Marked as delivered. Waiting for buyer confirmation.")
    try:
        await bot.send_message(d['buyer_id'], f"📦 <b>Seller marked Deal {tid} as delivered.</b>\nUse /received {tid} to confirm.", parse_mode="HTML")
    except Exception: pass


@dp.message(Command("received"))
async def cmd_received(m: Message):
    try: tid = m.text.split()[1]
    except Exception:
        await m.reply("Usage: /received <trade_id>"); return
    d = get_deal(tid)
    if not d or m.from_user.id != d['buyer_id']:
        await m.reply("Invalid."); return
    update_deal(tid, status="completed", completed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log_event(tid, m.from_user.id, "buyer_received_release")
    # stats
    bu = get_user(d['buyer_id']); se = get_user(d['seller_id'])
    if bu: update_user(d['buyer_id'], completed_deals=(bu['completed_deals'] or 0) + 1,
                       total_volume=(bu['total_volume'] or 0) + d['amount'])
    if se: update_user(d['seller_id'], completed_deals=(se['completed_deals'] or 0) + 1,
                       total_volume=(se['total_volume'] or 0) + d['amount'])
    await m.reply(f"🏁 Deal {tid} completed. Mediator will release ₹{d['net_release']:.2f} to seller.")
    try:
        await bot.send_message(d['seller_id'], f"🏁 <b>Deal {tid} completed!</b> Net release: ₹{d['net_release']:.2f}", parse_mode="HTML")
    except Exception: pass
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try:
            await bot.send_message(oid,
                f"🏁 <b>Deal Completed</b>\n<code>{tid}</code>\nNet: ₹{d['net_release']:.2f}",
                parse_mode="HTML")
        except Exception: pass


@dp.message(Command("dispute"))
async def cmd_dispute(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        tid = parts[1]
    except Exception:
        await m.reply("Usage: /dispute <trade_id> [reason]"); return
    d = get_deal(tid)
    if not d or m.from_user.id not in (d['buyer_id'], d['seller_id']):
        await m.reply("Invalid."); return
    reason = parts[2] if len(parts) > 2 else "(no reason)"
    update_deal(tid, status="disputed", cancel_reason=reason)
    log_event(tid, m.from_user.id, "dispute", reason)
    u = get_user(m.from_user.id)
    if u: update_user(m.from_user.id, disputed_deals=(u['disputed_deals'] or 0) + 1)
    await m.reply(f"⚠️ Dispute raised on {tid}. Mediator will review.")
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try:
            await bot.send_message(oid,
                f"⚠️ <b>Dispute Raised</b>\nDeal: <code>{tid}</code>\nBy: <code>{m.from_user.id}</code>\nReason: {reason}",
                parse_mode="HTML")
        except Exception: pass


@dp.message(Command("msg"))
async def cmd_msg(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        tid = parts[1]; text = parts[2]
    except Exception:
        await m.reply("Usage: /msg <trade_id> <text>"); return
    d = get_deal(tid)
    if not d:
        await m.reply("Deal not found."); return
    uid = m.from_user.id
    if uid == d['buyer_id']:
        other = d['seller_id']
    elif uid == d['seller_id']:
        other = d['buyer_id']
    else:
        await m.reply("Not part of this deal."); return
    add_deal_msg(tid, uid, text)
    log_event(tid, uid, "msg_sent")
    try:
        await bot.send_message(other, f"💬 <b>Deal {tid}</b>\nFrom: <code>{uid}</code>\n\n{text}", parse_mode="HTML")
        await m.reply("✅ Message sent.")
    except Exception as e:
        await m.reply(f"⚠️ Failed to deliver: {e}")


@dp.message(Command("vouch"))
async def cmd_vouch(m: Message):
    try:
        parts = m.text.split(maxsplit=3)
        tid = parts[1]; rating = int(parts[2]); comment = parts[3]
    except Exception:
        await m.reply("Usage: /vouch <trade_id> <1-5> <comment>"); return
    d = get_deal(tid)
    if not d or m.from_user.id not in (d['buyer_id'], d['seller_id']):
        await m.reply("Invalid."); return
    if d['status'] != "completed":
        await m.reply("Deal not completed yet."); return
    other = d['seller_id'] if m.from_user.id == d['buyer_id'] else d['buyer_id']
    add_vouch(tid, m.from_user.id, other, rating, comment)
    await m.reply(f"⭐ Vouch submitted for <code>{other}</code>.", parse_mode="HTML")


@dp.message(Command("profile"))
async def cmd_profile(m: Message):
    u = get_user(m.from_user.id)
    if not u:
        await m.reply("Use /start first."); return
    await m.reply(user_profile_text(u), parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    s = gstats()
    t = (f"📊 <b>Global Escrow Stats</b>\n━━━━━━━━━━━━━━━━━━━━\n"
         f"👥 Users: {s['users']}\n💼 Total Deals: {s['deals']}\n"
         f"🏁 Completed: {s['completed']}\n💰 Volume: ₹{s['volume']:.2f}\n"
         f"💸 Current Fee: {get_fee()}%")
    await m.reply(t, parse_mode="HTML")


# ===================== ADMIN COMMANDS =====================
@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if not is_admin(m.from_user.id): return
    await m.reply("🛡 <b>Admin Control Panel</b>\nSelect an option:", parse_mode="HTML", reply_markup=admin_menu())


@dp.message(Command("viewusers"))
async def cmd_vu(m: Message):
    if not is_admin(m.from_user.id): return
    rows = all_users()
    t = "👥 <b>Users:</b>\n"
    for u in rows[:40]:
        t += f"• @{u['username']} — <code>{u['telegram_id']}</code>\n"
    if len(rows) > 40: t += f"...and {len(rows)-40} more."
    await m.reply(t, parse_mode="HTML")


@dp.message(Command("viewdeals"))
async def cmd_vd(m: Message):
    if not is_admin(m.from_user.id): return
    rows = all_deals(limit=30)
    if not rows: await m.reply("No deals."); return
    t = "💼 <b>Recent Deals:</b>\n"
    for d in rows:
        t += f"• <code>{d['trade_id']}</code> — ₹{d['amount']:.2f} [{status_emoji(d['status'])}]\n"
    await m.reply(t, parse_mode="HTML")


@dp.message(Command("dealinfo"))
async def cmd_di(m: Message):
    if not is_admin(m.from_user.id): return
    try: tid = m.text.split()[1]
    except Exception: await m.reply("Usage: /dealinfo <trade_id>"); return
    d = get_deal(tid)
    if not d: await m.reply("Not found."); return
    await m.reply(deal_text(d), parse_mode="HTML")


@dp.message(Command("release"))
async def cmd_rel(m: Message):
    if not is_admin(m.from_user.id): return
    try: tid = m.text.split()[1]
    except Exception: await m.reply("Usage: /release <trade_id>"); return
    d = get_deal(tid)
    if not d: await m.reply("Not found."); return
    update_deal(tid, status="completed", completed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log_event(tid, m.from_user.id, "admin_release")
    log_act(m.from_user.id, "release", tid)
    await m.reply(f"🏁 Released {tid}.")
    for pid in (d['buyer_id'], d['seller_id']):
        try: await bot.send_message(pid, f"🏁 Deal {tid} has been released by admin.")
        except Exception: pass


@dp.message(Command("canceldeal"))
async def cmd_cncl(m: Message):
    if not is_admin(m.from_user.id): return
    try:
        parts = m.text.split(maxsplit=2)
        tid = parts[1]; reason = parts[2] if len(parts) > 2 else "admin cancel"
    except Exception:
        await m.reply("Usage: /canceldeal <trade_id> [reason]"); return
    update_deal(tid, status="cancelled", cancel_reason=reason)
    log_event(tid, m.from_user.id, "admin_cancel", reason)
    log_act(m.from_user.id, "cancel", tid)
    await m.reply(f"❌ Cancelled {tid}.")


@dp.message(Command("ban"))
async def cmd_ban(m: Message):
    if not is_admin(m.from_user.id): return
    uid = None
    if m.reply_to_message:
        uid = m.reply_to_message.from_user.id
    else:
        try: uid = int(m.text.split()[1])
        except Exception: await m.reply("Usage: /ban <user_id> or reply."); return
    update_user(uid, is_banned=1)
    log_act(m.from_user.id, "ban", str(uid))
    await m.reply(f"🚫 Banned <code>{uid}</code>.", parse_mode="HTML")


@dp.message(Command("unban"))
async def cmd_unban(m: Message):
    if not is_admin(m.from_user.id): return
    uid = None
    if m.reply_to_message:
        uid = m.reply_to_message.from_user.id
    else:
        try: uid = int(m.text.split()[1])
        except Exception: await m.reply("Usage: /unban <user_id> or reply."); return
    update_user(uid, is_banned=0)
    log_act(m.from_user.id, "unban", str(uid))
    await m.reply(f"✅ Unbanned <code>{uid}</code>.", parse_mode="HTML")


@dp.message(Command("broadcast"))
async def cmd_bc(m: Message):
    if not is_admin(m.from_user.id): return
    text = m.text.replace("/broadcast", "", 1).strip()
    if not text: await m.reply("Usage: /broadcast <msg>"); return
    ok = fail = 0
    for u in all_users():
        try:
            await bot.send_message(u['telegram_id'], text, parse_mode="HTML"); ok += 1
        except Exception: fail += 1
    log_act(m.from_user.id, "broadcast", f"ok={ok} fail={fail}")
    await m.reply(f"📢 Broadcast: ✅ {ok} | ❌ {fail}")


@dp.message(Command("track"))
async def cmd_tr(m: Message):
    if not is_admin(m.from_user.id): return
    try: uid = int(m.text.split()[1])
    except Exception: await m.reply("Usage: /track <user_id>"); return
    u = get_user(uid)
    if not u: await m.reply("Not found."); return
    await m.reply(user_profile_text(u), parse_mode="HTML")


@dp.message(Command("setfee"))
async def cmd_sf(m: Message):
    if not is_admin(m.from_user.id): return
    try: p = float(m.text.split()[1])
    except Exception: await m.reply("Usage: /setfee <percent>"); return
    set_fee(p); log_act(m.from_user.id, "setfee", str(p))
    await m.reply(f"💸 Fee set to {p}%.")


@dp.message(Command("addadmin"))
async def cmd_aa(m: Message):
    if not is_super(m.from_user.id): return
    try: uid = int(m.text.split()[1])
    except Exception: await m.reply("Usage: /addadmin <id>"); return
    create_user(uid, "admin"); update_user(uid, is_admin=1)
    log_act(m.from_user.id, "addadmin", str(uid))
    await m.reply(f"🛡 <code>{uid}</code> is now admin.", parse_mode="HTML")


@dp.message(Command("rmadmin"))
async def cmd_ra(m: Message):
    if not is_super(m.from_user.id): return
    try: uid = int(m.text.split()[1])
    except Exception: await m.reply("Usage: /rmadmin <id>"); return
    update_user(uid, is_admin=0)
    log_act(m.from_user.id, "rmadmin", str(uid))
    await m.reply(f"Removed <code>{uid}</code>.", parse_mode="HTML")


@dp.message(Command("addsuper"))
async def cmd_as(m: Message):
    if m.from_user.id not in (OWNER_ID_1, OWNER_ID_2): return
    try: uid = int(m.text.split()[1])
    except Exception: await m.reply("Usage: /addsuper <id>"); return
    create_user(uid, "super"); update_user(uid, is_super_admin=1, is_admin=1)
    log_act(m.from_user.id, "addsuper", str(uid))
    await m.reply(f"👑 <code>{uid}</code> is now Super Admin.", parse_mode="HTML")


@dp.message(Command("rmsuper"))
async def cmd_rs(m: Message):
    if m.from_user.id not in (OWNER_ID_1, OWNER_ID_2): return
    try: uid = int(m.text.split()[1])
    except Exception: await m.reply("Usage: /rmsuper <id>"); return
    update_user(uid, is_super_admin=0)
    log_act(m.from_user.id, "rmsuper", str(uid))
    await m.reply(f"Removed <code>{uid}</code>.", parse_mode="HTML")


@dp.message(Command("logs"))
async def cmd_logs(m: Message):
    if not is_admin(m.from_user.id): return
    rows = get_logs()
    t = "📝 <b>Activity Log:</b>\n\n"
    for l in rows:
        t += f"• <code>{l['admin_id']}</code> → {l['action']} ({l['details']})\n"
    await m.reply(t, parse_mode="HTML")


@dp.message(Command("export"))
async def cmd_export(m: Message):
    if not is_admin(m.from_user.id): return
    rows = all_deals(limit=500)
    if not rows: await m.reply("No deals."); return
    lines = ["trade_id,buyer,seller,amount,fee,net,status,created"]
    for d in rows:
        lines.append(f"{d['trade_id']},{d['buyer_id']},{d['seller_id']},{d['amount']},{d['fee']},{d['net_release']},{d['status']},{d['created_at']}")
    data = "\n".join(lines)[:3800]
    await m.reply(f"<pre>{data}</pre>", parse_mode="HTML")


# ===================== CALLBACKS =====================
@dp.callback_query()
async def on_cb(call: CallbackQuery, state: FSMContext):
    try:
        uid = call.from_user.id
        data = call.data
        u = get_user(uid)
        if not u or u['is_banned']:
            await call.answer("You are banned.", show_alert=True); return

        # ---------- MAIN MENU ----------
        if data == "new_deal":
            await call.answer("Use /newdeal <amount> <seller_id> <description>", show_alert=True)
            return

        if data == "my_deals":
            rows = user_deals(uid)
            if not rows:
                await call.answer("No deals yet.", show_alert=True); return
            btns = [[KB(f"{r['trade_id']} | ₹{r['amount']:.0f} | {status_emoji(r['status'])}", f"open_{r['trade_id']}", "primary")] for r in rows]
            btns.append([KB("⬅ Back", "back_main", "primary")])
            await show(call, "📂 <b>Your Deals:</b>", InlineKeyboardMarkup(inline_keyboard=btns))
            await call.answer(); return

        if data == "profile":
            await show(call, user_profile_text(u), InlineKeyboardMarkup(inline_keyboard=[[KB("⬅ Back", "back_main", "primary")]]))
            await call.answer(); return

        if data == "global_stats":
            s = gstats()
            t = (f"📊 <b>Global Escrow Stats</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                 f"👥 Users: {s['users']}\n💼 Total Deals: {s['deals']}\n"
                 f"🏁 Completed: {s['completed']}\n💰 Volume: ₹{s['volume']:.2f}\n"
                 f"💸 Fee: {get_fee()}%")
            await show(call, t, InlineKeyboardMarkup(inline_keyboard=[[KB("⬅ Back", "back_main", "primary")]]))
            await call.answer(); return

        if data == "help":
            t = ("📖 <b>Commands</b>\n"
                 "/newdeal <amount> <seller_id> <description>\n"
                 "/mydeals\n/deal <trade_id>\n/confirm <trade_id>\n"
                 "/paid /delivering /delivered /received /dispute\n"
                 "/msg <trade_id> <text>\n/vouch <trade_id> 1-5 <comment>\n"
                 "/profile /stats /help")
            await show(call, t, InlineKeyboardMarkup(inline_keyboard=[[KB("⬅ Back", "back_main", "primary")]]))
            await call.answer(); return

        if data == "back_main":
            await show(call, "⚡ <b>Main Menu</b>\nSelect an option:", main_menu(is_admin(uid)))
            await call.answer(); return

        # ---------- OPEN DEAL ----------
        if data.startswith("open_"):
            tid = data.replace("open_", "")
            d = get_deal(tid)
            if not d: await call.answer("Not found.", show_alert=True); return
            await show(call, deal_text(d), deal_actions_kb(d, uid))
            await call.answer(); return

        # ---------- DEAL ACTIONS ----------
        if data.startswith("conf_buyer_"):
            tid = data.replace("conf_buyer_", "")
            d = get_deal(tid)
            if not d or uid != d['buyer_id']: await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, buyer_confirmed=1); log_event(tid, uid, "buyer_confirmed")
            await call.answer("✅ Confirmed as buyer.")
            d = get_deal(tid)
            if d['buyer_confirmed'] and d['seller_confirmed']:
                update_deal(tid, status="awaiting_payment")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("conf_seller_"):
            tid = data.replace("conf_seller_", "")
            d = get_deal(tid)
            if not d or uid != d['seller_id']: await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, seller_confirmed=1); log_event(tid, uid, "seller_confirmed")
            await call.answer("✅ Confirmed as seller.")
            d = get_deal(tid)
            if d['buyer_confirmed'] and d['seller_confirmed']:
                update_deal(tid, status="awaiting_payment")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("proceed_pay_"):
            tid = data.replace("proceed_pay_", "")
            d = get_deal(tid)
            if not d: await call.answer("Not found.", show_alert=True); return
            update_deal(tid, status="awaiting_payment")
            await call.answer("💳 Buyer please send payment to mediator.")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("paid_"):
            tid = data.replace("paid_", "")
            d = get_deal(tid)
            if not d or uid != d['buyer_id']: await call.answer("Invalid.", show_alert=True); return
            log_event(tid, uid, "buyer_paid")
            await call.answer("✅ Mediator notified.")
            for oid in (OWNER_ID_1, OWNER_ID_2):
                try: await bot.send_message(oid, f"💰 Buyer claims payment for <code>{tid}</code>", parse_mode="HTML")
                except Exception: pass
            return

        if data.startswith("delivering_"):
            tid = data.replace("delivering_", "")
            d = get_deal(tid)
            if not d or uid != d['seller_id']: await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, status="delivering"); log_event(tid, uid, "seller_delivering")
            await call.answer("🚚 Marked delivering.")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("delivered_"):
            tid = data.replace("delivered_", "")
            d = get_deal(tid)
            if not d or uid != d['seller_id']: await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, status="delivered", delivered_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            log_event(tid, uid, "seller_delivered")
            try:
                await bot.send_message(d['buyer_id'], f"📦 <b>Seller marked {tid} delivered.</b> Use /received {tid} to confirm.", parse_mode="HTML")
            except Exception: pass
            await call.answer("📦 Marked delivered.")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("received_"):
            tid = data.replace("received_", "")
            d = get_deal(tid)
            if not d or uid != d['buyer_id']: await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, status="completed", completed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            log_event(tid, uid, "buyer_received_release")
            bu = get_user(d['buyer_id']); se = get_user(d['seller_id'])
            if bu: update_user(d['buyer_id'], completed_deals=(bu['completed_deals'] or 0) + 1,
                               total_volume=(bu['total_volume'] or 0) + d['amount'])
            if se: update_user(d['seller_id'], completed_deals=(se['completed_deals'] or 0) + 1,
                               total_volume=(se['total_volume'] or 0) + d['amount'])
            try: await bot.send_message(d['seller_id'], f"🏁 Deal {tid} completed!", parse_mode="HTML")
            except Exception: pass
            for oid in (OWNER_ID_1, OWNER_ID_2):
                try: await bot.send_message(oid, f"🏁 Deal <code>{tid}</code> completed.", parse_mode="HTML")
                except Exception: pass
            await call.answer("🏁 Deal completed.")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("dispute_"):
            tid = data.replace("dispute_", "")
            d = get_deal(tid)
            if not d or uid not in (d['buyer_id'], d['seller_id']):
                await call.answer("Invalid.", show_alert=True); return
            update_deal(tid, status="disputed"); log_event(tid, uid, "dispute")
            u = get_user(uid)
            if u: update_user(uid, disputed_deals=(u['disputed_deals'] or 0) + 1)
            for oid in (OWNER_ID_1, OWNER_ID_2):
                try: await bot.send_message(oid, f"⚠️ Dispute on <code>{tid}</code>", parse_mode="HTML")
                except Exception: pass
            await call.answer("⚠️ Dispute raised.")
            await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), uid))
            return

        if data.startswith("msg_"):
            tid = data.replace("msg_", "")
            d = get_deal(tid)
            if not d or uid not in (d['buyer_id'], d['seller_id']):
                await call.answer("Invalid.", show_alert=True); return
            await state.set_state(ChatRelay.waiting_message)
            await state.update_data(trade_id=tid)
            await show(call, f"💬 Send your message for deal <code>{tid}</code> now. (send /cancel to abort)", None)
            await call.answer(); return

        if data.startswith("chatlog_"):
            tid = data.replace("chatlog_", "")
            rows = get_deal_msgs(tid)
            t = f"📜 <b>Chat log: {tid}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            if not rows:
                t += "No messages yet."
            else:
                for r in reversed(rows):
                    t += f"• <code>{r['sender_id']}</code>: {r['content'][:120]}\n"
            await show(call, t, InlineKeyboardMarkup(inline_keyboard=[[KB("⬅ Back", f"open_{tid}", "primary")]]))
            await call.answer(); return

        if data.startswith("timeline_"):
            tid = data.replace("timeline_", "")
            rows = get_events(tid)
            t = f"📜 <b>Timeline: {tid}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            if not rows:
                t += "No events."
            else:
                for r in reversed(rows):
                    t += f"• {r['created_at']} — <code>{r['actor_id']}</code>: {r['action']} {r['notes'] or ''}\n"
            await show(call, t, InlineKeyboardMarkup(inline_keyboard=[[KB("⬅ Back", f"open_{tid}", "primary")]]))
            await call.answer(); return

        # ---------- ADMIN ----------
        if data == "admin_panel":
            if not is_admin(uid): await call.answer("Denied.", show_alert=True); return
            await show(call, "🛡 <b>Admin Control Panel</b>\nSelect an option:", admin_menu())
            await call.answer(); return

        if data.startswith("adm_"):
            if not is_admin(uid): await call.answer("Denied.", show_alert=True); return
            log_act(uid, data)
            await handle_admin(call, uid, data)
            return

        await call.answer("Unknown action.")
    except Exception as e:
        print(f"[cb] {e}")
        try: await call.answer(f"Error: {e}", show_alert=True)
        except Exception: pass


async def handle_admin(call: CallbackQuery, uid, data):
    if data == "adm_refresh":
        await show(call, "🛡 <b>Admin Panel</b>\nRefreshed.", admin_menu()); await call.answer(); return

    if data == "adm_stats":
        s = gstats()
        t = (f"📊 <b>Stats</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"👥 Users: {s['users']}\n💼 Deals: {s['deals']}\n"
             f"🏁 Completed: {s['completed']}\n💰 Volume: ₹{s['volume']:.2f}\n"
             f"💸 Fee: {get_fee()}%")
        await show(call, t, admin_menu()); await call.answer(); return

    if data == "adm_users":
        rows = all_users()
        t = "👥 <b>Users:</b>\n"
        for u in rows[:40]:
            t += f"• @{u['username']} — <code>{u['telegram_id']}</code>\n"
        if len(rows) > 40: t += f"...and {len(rows)-40} more."
        await show(call, t, admin_menu()); await call.answer(); return

    if data == "adm_active":
        c = db()
        rows = c.execute("SELECT * FROM deals WHERE status NOT IN ('completed','cancelled') ORDER BY id DESC LIMIT 30").fetchall()
        c.close()
        if not rows:
            await show(call, "No active deals.", admin_menu()); await call.answer(); return
        btns = [[KB(f"{r['trade_id']} | ₹{r['amount']:.0f} | {status_emoji(r['status'])}", f"open_{r['trade_id']}", "primary")] for r in rows]
        btns.append([KB("⬅ Back", "admin_panel", "primary")])
        await show(call, "💼 <b>Active Deals:</b>", InlineKeyboardMarkup(inline_keyboard=btns))
        await call.answer(); return

    if data == "adm_all_deals":
        rows = all_deals(limit=30)
        if not rows:
            await show(call, "No deals.", admin_menu()); await call.answer(); return
        btns = [[KB(f"{r['trade_id']} | ₹{r['amount']:.0f} | {status_emoji(r['status'])}", f"open_{r['trade_id']}", "primary")] for r in rows]
        btns.append([KB("⬅ Back", "admin_panel", "primary")])
        await show(call, "📜 <b>All Deals:</b>", InlineKeyboardMarkup(inline_keyboard=btns))
        await call.answer(); return

    if data == "adm_disputes":
        c = db()
        rows = c.execute("SELECT * FROM deals WHERE status='disputed' ORDER BY id DESC LIMIT 30").fetchall()
        c.close()
        if not rows:
            await show(call, "No disputes.", admin_menu()); await call.answer(); return
        btns = [[KB(f"{r['trade_id']} | ₹{r['amount']:.0f}", f"open_{r['trade_id']}", "danger")] for r in rows]
        btns.append([KB("⬅ Back", "admin_panel", "primary")])
        await show(call, "⚠️ <b>Disputed Deals:</b>", InlineKeyboardMarkup(inline_keyboard=btns))
        await call.answer(); return

    if data == "adm_logs":
        rows = get_logs()
        t = "📝 <b>Activity Log:</b>\n\n"
        for l in rows:
            t += f"• <code>{l['admin_id']}</code> → {l['action']} ({l['details']})\n"
        await show(call, t, admin_menu()); await call.answer(); return

    if data == "adm_export":
        rows = all_deals(limit=500)
        if not rows:
            await call.answer("No deals.", show_alert=True); return
        lines = ["trade_id,buyer,seller,amount,fee,net,status,created"]
        for d in rows:
            lines.append(f"{d['trade_id']},{d['buyer_id']},{d['seller_id']},{d['amount']},{d['fee']},{d['net_release']},{d['status']},{d['created_at']}")
        await call.message.answer(f"<pre>{chr(10).join(lines)[:3800]}</pre>", parse_mode="HTML")
        await call.answer("Exported.", show_alert=True); return

    if data == "adm_settings":
        t = (f"⚙️ <b>Settings</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"• Bot: {BOT_NAME}\n• Owner1: <code>{OWNER_ID_1}</code>\n"
             f"• Owner2: <code>{OWNER_ID_2}</code>\n• Fee: {get_fee()}%\n"
             f"• Colored: {'✅ ON' if HAS_STYLE else '⚠️ OFF'}")
        await show(call, t, admin_menu()); await call.answer(); return

    ack = {
        "adm_ban": "Reply to a user with /ban or use /ban <id>.",
        "adm_unban": "Reply to a user with /unban or use /unban <id>.",
        "adm_broadcast": "Send /broadcast <msg>.",
        "adm_track": "Send /track <user_id>.",
        "adm_setfee": "Send /setfee <percent>.",
        "adm_release": "Open a deal and use Force Release.",
        "adm_cancel": "Open a deal and use Cancel Deal.",
    }
    await call.answer(ack.get(data, "Action triggered."), show_alert=True)


# ============ admin callbacks from deal view ============
@dp.callback_query(F.data.startswith("adm_payrecv_"))
async def cb_payrecv(call: CallbackQuery):
    if not is_admin(call.from_user.id): await call.answer("Denied.", show_alert=True); return
    tid = call.data.replace("adm_payrecv_", "")
    update_deal(tid, status="payment_received", payment_received_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log_event(tid, call.from_user.id, "admin_payment_received")
    d = get_deal(tid)
    try:
        await bot.send_message(d['seller_id'], f"✅ Mediator confirmed payment for <code>{tid}</code>. You may deliver.", parse_mode="HTML")
    except Exception: pass
    await call.answer("✅ Payment received.")
    await show(call, deal_text(d), deal_actions_kb(d, call.from_user.id))


@dp.callback_query(F.data.startswith("adm_release_"))
async def cb_release(call: CallbackQuery):
    if not is_admin(call.from_user.id): await call.answer("Denied.", show_alert=True); return
    tid = call.data.replace("adm_release_", "")
    d = get_deal(tid)
    if not d: await call.answer("Not found.", show_alert=True); return
    update_deal(tid, status="completed", completed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    log_event(tid, call.from_user.id, "admin_release")
    log_act(call.from_user.id, "release", tid)
    for pid in (d['buyer_id'], d['seller_id']):
        try: await bot.send_message(pid, f"🏁 Deal {tid} released by admin.")
        except Exception: pass
    await call.answer("🏁 Released.")
    await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), call.from_user.id))


@dp.callback_query(F.data.startswith("adm_cancel_"))
async def cb_cancel(call: CallbackQuery):
    if not is_admin(call.from_user.id): await call.answer("Denied.", show_alert=True); return
    tid = call.data.replace("adm_cancel_", "")
    update_deal(tid, status="cancelled", cancel_reason="admin cancel")
    log_event(tid, call.from_user.id, "admin_cancel")
    log_act(call.from_user.id, "cancel", tid)
    await call.answer("❌ Cancelled.")
    await show(call, deal_text(get_deal(tid)), deal_actions_kb(get_deal(tid), call.from_user.id))


# ===================== CHAT RELAY STATE =====================
@dp.message(ChatRelay.waiting_message)
async def receive_chat(m: Message, state: FSMContext):
    if m.text and m.text.startswith("/cancel"):
        await state.clear()
        await m.reply("Cancelled.")
        return
    data = await state.get_data()
    tid = data.get("trade_id")
    if not tid:
        await state.clear(); return
    d = get_deal(tid)
    if not d:
        await state.clear(); await m.reply("Deal gone."); return
    uid = m.from_user.id
    if uid == d['buyer_id']: other = d['seller_id']
    elif uid == d['seller_id']: other = d['buyer_id']
    else:
        await state.clear(); await m.reply("Not part of this deal."); return
    text = m.text or "[non-text]"
    add_deal_msg(tid, uid, text)
    log_event(tid, uid, "msg_sent")
    try:
        await bot.send_message(other, f"💬 <b>Deal {tid}</b>\nFrom: <code>{uid}</code>\n\n{text}", parse_mode="HTML")
        await m.reply("✅ Sent.")
    except Exception as e:
        await m.reply(f"⚠️ Delivery failed: {e}")
    await state.clear()


# ===================== STARTUP =====================
async def startup_notify():
    msg = (
        "🤖 <b>Paltan Escrow Mediator Bot is ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Bot: {BOT_NAME}\n"
        f"🔹 Fee: {get_fee()}%\n"
        f"🔹 Colored Buttons: {'✅ ON' if HAS_STYLE else '⚠️ Plain'}\n"
        f"🔹 Mediator: <code>{OWNER_ID_1}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Buyers and sellers: use /help for all commands."
    )
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try: await bot.send_message(oid, msg, parse_mode="HTML")
        except Exception as e: print(f"[notify {oid}] {e}")


async def main():
    init_db()
    print("✅ DB ready.")
    await startup_notify()
    print("🤖 Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())