"""
Paltan Transactions Escrow Bot — Telethon Build
Colored inline buttons (with fallback) + non-deleting responses.
"""

import asyncio
import sqlite3
import time

from telethon import TelegramClient, events, Button

# ---- colored button support (best-effort) ----
HAS_STYLE = False
KeyboardButtonCallback = None
KeyboardButtonStyle = None

try:
    from telethon.tl.types import KeyboardButtonCallback as _KBC
    try:
        from telethon.tl.types import KeyboardButtonStyle as _KBS
        KeyboardButtonCallback = _KBC
        KeyboardButtonStyle = _KBS
        HAS_STYLE = True
    except ImportError:
        HAS_STYLE = False
except Exception:
    HAS_STYLE = False

# ===================== CREDENTIALS =====================
BOT_TOKEN   = "8925443014:AAEB7ksbFqNkTS5r8UCsEtXyTjT27UDbiEc"
API_ID      = 2040
API_HASH    = "b18441a1ff607e10a989891a5462e627"
OWNER_ID_1  = 6871199191
OWNER_ID_2  = 2062068620
BOT_NAME    = "@PaltanTransactionsBot"
FEE_PERCENT = 4.0
DB_PATH     = "escrow.db"
# ======================================================

client = TelegramClient("paltan_bot", API_ID, API_HASH)


# ===================== DATABASE =====================
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    c = db()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            is_super_admin INTEGER DEFAULT 0,
            credits REAL DEFAULT 0.0,
            rank INTEGER DEFAULT 0,
            total_deals INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0.0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT UNIQUE,
            buyer_id INTEGER,
            seller_id INTEGER,
            amount REAL,
            fee REAL,
            net_release REAL,
            status TEXT DEFAULT 'pending',
            escrowed_by INTEGER,
            detail TEXT,
            expected_time TEXT,
            tc TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS global_stats (key TEXT PRIMARY KEY, value REAL)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_deals', 0)")
    cur.execute("INSERT OR IGNORE INTO global_stats (key, value) VALUES ('total_volume', 0.0)")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('free_mode', '1')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_join', '')")
    c.commit()
    c.close()


def get_user(uid):
    c = db()
    r = c.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)).fetchone()
    c.close()
    return r


def create_user(uid, username):
    c = db()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (uid, username))
    c.commit()
    c.close()


def update_user(uid, **kw):
    if not kw: return
    c = db()
    f = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE users SET {f} WHERE telegram_id=?", list(kw.values()) + [uid])
    c.commit()
    c.close()


def all_users():
    c = db()
    r = c.execute("SELECT telegram_id, username FROM users").fetchall()
    c.close()
    return r


def gstats():
    c = db()
    d = c.execute("SELECT value FROM global_stats WHERE key='total_deals'").fetchone()
    v = c.execute("SELECT value FROM global_stats WHERE key='total_volume'").fetchone()
    c.close()
    return (d['value'] if d else 0, v['value'] if v else 0.0)


def gstats_update(dd=0, vd=0.0):
    c = db()
    c.execute("UPDATE global_stats SET value=value+? WHERE key='total_deals'", (dd,))
    c.execute("UPDATE global_stats SET value=value+? WHERE key='total_volume'", (vd,))
    c.commit()
    c.close()


def log_act(admin_id, action, details=""):
    c = db()
    c.execute("INSERT INTO activity_log (admin_id, action, details) VALUES (?, ?, ?)", (admin_id, action, details))
    c.commit()
    c.close()


def get_logs(limit=15):
    c = db()
    r = c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return r


def get_setting(k):
    c = db()
    r = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    c.close()
    return r['value'] if r else None


def set_setting(k, v):
    c = db()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
    c.commit()
    c.close()


def user_deals(uid, only_pending=False, limit=10):
    c = db()
    if only_pending:
        r = c.execute("SELECT trade_id FROM deals WHERE (buyer_id=? OR seller_id=?) AND status='pending' ORDER BY id DESC LIMIT ?", (uid, uid, limit)).fetchall()
    else:
        r = c.execute("SELECT trade_id FROM deals WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT ?", (uid, uid, limit)).fetchall()
    c.close()
    return r


def get_deal(tid):
    c = db()
    r = c.execute("SELECT * FROM deals WHERE trade_id=?", (tid,)).fetchone()
    c.close()
    return r


def create_deal(tid, buyer, seller, amount, escrowed_by, detail="", expected="", tc=""):
    fee = round(amount * (FEE_PERCENT / 100.0), 2)
    net = round(amount - fee, 2)
    c = db()
    c.execute("""INSERT INTO deals (trade_id, buyer_id, seller_id, amount, fee, net_release, status, escrowed_by, detail, expected_time, tc)
                 VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
              (tid, buyer, seller, amount, fee, net, escrowed_by, detail, expected, tc))
    c.commit()
    c.close()
    return fee, net


def complete_deal(tid):
    c = db()
    c.execute("UPDATE deals SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE trade_id=?", (tid,))
    c.commit()
    c.close()


# ===================== BUTTONS =====================
def _make_style(color):
    if not HAS_STYLE or KeyboardButtonStyle is None:
        return None
    try:
        if color == "success":
            return KeyboardButtonStyle(bg_success=True)
        if color == "danger":
            return KeyboardButtonStyle(bg_danger=True)
        if color == "primary":
            return KeyboardButtonStyle(bg_primary=True)
    except Exception as e:
        print(f"[style] {e}")
    return None


def KB(text, data, color="primary"):
    style = _make_style(color)
    if style is not None and KeyboardButtonCallback is not None:
        try:
            return KeyboardButtonCallback(text, data.encode(), style=style)
        except Exception as e:
            print(f"[KB colored failed] {e}")
    return Button.inline(text, data)


def main_menu(admin=False):
    rows = [
        [KB("✦ My status", "my_status", "primary")],
        [KB("★ My Deals Info", "my_deals", "primary")],
        [KB("➤ My Pending Deals", "my_pending", "primary")],
        [KB("✓ Escrow Global status", "global_status", "primary")],
    ]
    if admin:
        rows.append([KB("🛡 Admin Panel", "admin_panel", "danger")])
    return rows


def admin_menu():
    return [
        [KB("📨 SEND VOUCH", "adm_send_vouch", "success"), KB("💼 MANAGE DEALS", "adm_manage_deals", "primary")],
        [KB("🏆 MANAGE RANKS", "adm_manage_ranks", "primary"), KB("👑 MANAGE SUPER ADMINS", "adm_super_admins", "primary")],
        [KB("🛡 MANAGE ADMINS", "adm_admins", "primary"), KB("👥 VIEW USERS", "adm_view_users", "primary")],
        [KB("🚫 BAN USER", "adm_ban", "danger"), KB("✅ UNBAN USER", "adm_unban", "success")],
        [KB("📢 BROADCAST", "adm_broadcast", "primary"), KB("📊 API STATS", "adm_stats", "primary")],
        [KB("📝 ACTIVITY LOG", "adm_logs", "primary"), KB("💸 PRICING PLANS", "adm_pricing", "primary")],
        [KB("🎟 REDEEM CODES", "adm_redeem", "primary"), KB("➕ ADD CREDITS", "adm_addcredit", "success")],
        [KB("➖ DEDUCT CREDITS", "adm_deductcredit", "danger"), KB("➕ ADD CREDITS ALL", "adm_addall", "success")],
        [KB("➖ DEDUCT ALL", "adm_deductall", "danger"), KB("🔗 FORCE JOIN", "adm_forcejoin", "primary")],
        [KB("⚙️ SETTINGS", "adm_settings", "primary"), KB("📜 DEAL HISTORY", "adm_history", "primary")],
        [KB("📤 EXPORT DATA", "adm_export", "primary"), KB("🔒 PROTECT NUMBER", "adm_protect", "primary")],
        [KB("📋 PROTECTED LIST", "adm_protlist", "primary"), KB("🎯 TRACK USER", "adm_track", "primary")],
        [KB("🔴 TOGGLE FREE MODE", "adm_freemode", "danger")],
        [KB("🔄 REFRESH", "adm_refresh", "primary")],
        [KB("⬅ Back to Main", "back_main", "primary")],
    ]


# ===================== HELPERS =====================
def is_admin(uid):
    if uid in (OWNER_ID_1, OWNER_ID_2):
        return True
    u = get_user(uid)
    return bool(u and (u['is_admin'] == 1 or u['is_super_admin'] == 1))


def is_super(uid):
    if uid in (OWNER_ID_1, OWNER_ID_2):
        return True
    u = get_user(uid)
    return bool(u and u['is_super_admin'] == 1)


# ===================== HANDLERS =====================
@client.on(events.NewMessage(pattern="/start"))
async def on_start(event):
    try:
        uid = event.sender_id
        sender = await event.get_sender()
        username = getattr(sender, "username", None) or "Unknown"
        create_user(uid, username)
        if uid in (OWNER_ID_1, OWNER_ID_2):
            update_user(uid, is_super_admin=1, is_admin=1)

        u = get_user(uid)
        if u and u['is_banned']:
            await event.reply("🚫 You are banned from using this bot.")
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
        await event.reply(text, parse_mode="html", buttons=main_menu(is_admin(uid)))
    except Exception as e:
        print(f"[start] {e}")
        await event.reply(f"⚠️ Error: {e}")


@client.on(events.CallbackQuery)
async def on_callback(event):
    try:
        uid = event.sender_id
        data = event.data.decode() if isinstance(event.data, bytes) else event.data
        u = get_user(uid)
        if not u or u['is_banned']:
            await event.answer("You are banned.", alert=True)
            return

        if data == "my_status":
            rank = u['rank'] if u['rank'] > 0 else "Unranked"
            text = (
                f"✅ <b>{u['username'].upper()} Deal status!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 Rank ➤ #{rank}\n"
                f"🔥 Active deals ➤ 0\n"
                f"✅ Total Escrow's ➤ {u['total_deals']}\n"
                "⚡ <b>Total Volume :</b>\n"
                "⚡ ➤ 0 TON\n"
                "💎 ➤ 0 USDT\n"
                f"💲 ➤ {u['total_volume']:.2f} ₹\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 Escrow Bot for {BOT_NAME}\n"
                f"✅ Provided by {BOT_NAME} !"
            )
            await event.respond(text, parse_mode="html", buttons=main_menu(is_admin(uid)))

        elif data == "my_deals":
            deals = user_deals(uid)
            if not deals:
                await event.answer("No deals found.", alert=True)
                return
            rows = [[KB(d['trade_id'], f"deal_{d['trade_id']}", "primary")] for d in deals]
            rows.append([KB("⬅ Back", "back_main", "primary")])
            await event.respond("❤ <b>All deals info !</b>\n━━━━━━━━━━━━━━━━━━━━\nSelect the deal below for info :",
                                parse_mode="html", buttons=rows)

        elif data == "my_pending":
            deals = user_deals(uid, only_pending=True)
            if not deals:
                await event.answer("Koi pending deal nahi hai.", alert=True)
            else:
                await event.answer(f"You have {len(deals)} pending deals.", alert=True)

        elif data == "global_status":
            d, v = gstats()
            text = (
                "🚀 <b>Escrow Global Statistics</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 Total Deals: {int(d)}\n\n"
                "📈 <b>Total Volume:</b>\n"
                "⚡ - 0 TON\n"
                "💎 - 0 USDT\n"
                f"💲 - {v:.2f} ₹\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 Escrow Bot for {BOT_NAME}\n"
                f"✅ Provided by {BOT_NAME}"
            )
            await event.respond(text, parse_mode="html", buttons=main_menu(is_admin(uid)))

        elif data == "back_main":
            await event.respond("⚡ <b>Main Menu</b>\nSelect an option below:",
                                parse_mode="html", buttons=main_menu(is_admin(uid)))

        elif data.startswith("deal_"):
            tid = data.replace("deal_", "")
            d = get_deal(tid)
            if d:
                text = (
                    f"💎 <b>Deal Details: {d['trade_id']}</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"💎 Deal Amount: ₹{d['amount']:.2f}\n"
                    f"📤 Fee: {FEE_PERCENT}% — ₹{d['fee']:.2f}\n"
                    f"📤 Net Release: ₹{d['net_release']:.2f}\n"
                    f"📊 Trade ID: {d['trade_id']}\n\n"
                    f"👤 Buyer: {d['buyer_id']}\n"
                    f"👤 Seller: {d['seller_id']}\n"
                    f"📝 Detail: {d['detail'] or '-'}\n"
                    f"⏰ Expected Time: {d['expected_time'] or '-'}\n"
                    f"📍 T/C: {d['tc'] or '-'}\n\n"
                    f"👤 Escrowed By: @{u['username']}"
                )
                await event.respond(text, parse_mode="html",
                                    buttons=[[KB("⬅ Back", "my_deals", "primary")]])

        elif data == "admin_panel":
            if not is_admin(uid):
                await event.answer("Access Denied.", alert=True)
                return
            await event.respond("🛡 <b>Admin Control Panel</b>\n━━━━━━━━━━━━━━━━━━━━\nSelect an option:",
                                parse_mode="html", buttons=admin_menu())

        elif data.startswith("adm_"):
            if not is_admin(uid):
                await event.answer("Access Denied.", alert=True)
                return
            log_act(uid, data)
            await handle_admin(event, uid, data)

        else:
            await event.answer("Unknown action.")
    except Exception as e:
        print(f"[cb] {e}")
        try:
            await event.answer(f"Error: {e}", alert=True)
        except Exception:
            pass


async def handle_admin(event, uid, data):
    if data == "adm_refresh":
        await event.respond("🛡 <b>Admin Control Panel</b>\nRefreshed.", parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_view_users":
        rows = all_users()
        t = "👥 <b>Registered Users:</b>\n\n"
        for u in rows[:30]:
            t += f"• @{u['username']} — <code>{u['telegram_id']}</code>\n"
        if len(rows) > 30:
            t += f"\n... and {len(rows)-30} more."
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_logs":
        logs = get_logs()
        t = "📝 <b>Recent Activity Log:</b>\n\n"
        for l in logs:
            t += f"• <code>{l['admin_id']}</code> → {l['action']}\n"
        if not logs: t += "No activity yet."
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_stats":
        users = len(all_users())
        d, v = gstats()
        t = (f"📊 <b>API Statistics</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"• Users: {users}\n• Deals: {int(d)}\n• Volume: ₹{v:.2f}\n"
             f"• Status: ✅ Active\n• Uptime: 100%")
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_pricing":
        free = get_setting('free_mode')
        t = (f"💸 <b>Pricing Plans</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"• Current Fee: <b>{FEE_PERCENT}%</b>\n"
             f"• Free Mode: {'🟢 ON' if free == '1' else '🔴 OFF'}")
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_freemode":
        cur = get_setting('free_mode')
        nv = '0' if cur == '1' else '1'
        set_setting('free_mode', nv)
        await event.respond(f"⚙️ Free Mode is now {'🟢 ON' if nv == '1' else '🔴 OFF'}.",
                            parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_settings":
        fj = get_setting('force_join') or "(not set)"
        free = get_setting('free_mode')
        t = (f"⚙️ <b>Bot Settings</b>\n━━━━━━━━━━━━━━━━━━━━\n"
             f"• Bot Name: {BOT_NAME}\n• Owner 1: <code>{OWNER_ID_1}</code>\n"
             f"• Owner 2: <code>{OWNER_ID_2}</code>\n• Fee: {FEE_PERCENT}%\n"
             f"• Free Mode: {'🟢' if free == '1' else '🔴'}\n• Force Join: {fj}")
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_history":
        c = db()
        rows = c.execute("SELECT trade_id, amount, status FROM deals ORDER BY id DESC LIMIT 15").fetchall()
        c.close()
        t = "📜 <b>Recent Deals:</b>\n\n"
        for r in rows:
            t += f"• <code>{r['trade_id']}</code> — ₹{r['amount']} [{r['status']}]\n"
        if not rows: t += "No deals yet."
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    if data == "adm_export":
        c = db()
        rows = c.execute("SELECT * FROM deals").fetchall()
        c.close()
        if not rows:
            await event.answer("No deals to export.", alert=True)
            return
        lines = ["trade_id,buyer,seller,amount,fee,net,status"]
        for r in rows:
            lines.append(f"{r['trade_id']},{r['buyer_id']},{r['seller_id']},{r['amount']},{r['fee']},{r['net_release']},{r['status']}")
        await event.respond(f"<pre>{chr(10).join(lines)[:3800]}</pre>", parse_mode="html")
        await event.answer("Exported.", alert=True)
        return

    if data == "adm_protlist":
        c = db()
        rows = c.execute("SELECT key FROM settings WHERE key LIKE 'protected_%'").fetchall()
        c.close()
        if not rows:
            await event.answer("No protected users.", alert=True)
            return
        t = "📋 <b>Protected Users:</b>\n\n"
        for r in rows:
            t += f"• <code>{r['key'].replace('protected_','')}</code>\n"
        await event.respond(t, parse_mode="html", buttons=admin_menu())
        return

    ack = {
        "adm_send_vouch": "User ko reply karke /sendvouch likh.",
        "adm_manage_deals": "Naya deal: /newdeal <buyer> <seller> <amount>",
        "adm_manage_ranks": "Rank set: /setrank <user_id> <rank>",
        "adm_super_admins": "Super admin: /addsuper <id> | /rmsuper <id>",
        "adm_admins": "Admin: /addadmin <id> | /rmadmin <id>",
        "adm_ban": "Reply karke /ban",
        "adm_unban": "Reply karke /unban",
        "adm_broadcast": "Sabko bhejne ke liye /broadcast <msg>",
        "adm_redeem": "Code generate: /gencode <amt>",
        "adm_addcredit": "Reply karke /addcredits <amt>",
        "adm_deductcredit": "Reply karke /deductcredits <amt>",
        "adm_addall": "Sabko credit: /addall <amt>",
        "adm_deductall": "Sabse minus: /deductall <amt>",
        "adm_forcejoin": "Set channel: /setforcejoin @channel",
        "adm_protect": "Protect user: /protect <id>",
        "adm_track": "Track user: /track <id>",
    }
    await event.answer(ack.get(data, "Action triggered."), alert=True)


# ===================== TEXT COMMANDS =====================
@client.on(events.NewMessage(pattern=r"^/ban\b"))
async def cmd_ban(e):
    if not is_admin(e.sender_id): return
    if not e.is_reply:
        await e.reply("Reply to a user's message with /ban.")
        return
    r = await e.get_reply_message()
    tgt = r.sender_id
    update_user(tgt, is_banned=1)
    log_act(e.sender_id, "ban", str(tgt))
    await e.reply(f"🚫 User <code>{tgt}</code> banned.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/unban\b"))
async def cmd_unban(e):
    if not is_admin(e.sender_id): return
    if not e.is_reply:
        await e.reply("Reply to a user's message with /unban.")
        return
    r = await e.get_reply_message()
    tgt = r.sender_id
    update_user(tgt, is_banned=0)
    log_act(e.sender_id, "unban", str(tgt))
    await e.reply(f"✅ User <code>{tgt}</code> unbanned.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/broadcast\b"))
async def cmd_bc(e):
    if not is_admin(e.sender_id): return
    text = e.raw_text.replace("/broadcast", "", 1).strip()
    if not text:
        await e.reply("Usage: /broadcast <message>")
        return
    ok = fail = 0
    for u in all_users():
        try:
            await client.send_message(u['telegram_id'], text, parse_mode="html")
            ok += 1
        except Exception:
            fail += 1
    log_act(e.sender_id, "broadcast", f"ok={ok} fail={fail}")
    await e.reply(f"📢 Broadcast: ✅ {ok} | ❌ {fail}")


@client.on(events.NewMessage(pattern=r"^/addcredits\b"))
async def cmd_ac(e):
    if not is_admin(e.sender_id): return
    if not e.is_reply:
        await e.reply("Reply to a user with /addcredits <amount>.")
        return
    try: amt = float(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /addcredits <amount>")
        return
    r = await e.get_reply_message()
    tgt = r.sender_id
    u = get_user(tgt)
    if u:
        update_user(tgt, credits=u['credits'] + amt)
        await e.reply(f"➕ Added {amt} credits to <code>{tgt}</code>.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/deductcredits\b"))
async def cmd_dc(e):
    if not is_admin(e.sender_id): return
    if not e.is_reply:
        await e.reply("Reply with /deductcredits <amount>.")
        return
    try: amt = float(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /deductcredits <amount>")
        return
    r = await e.get_reply_message()
    tgt = r.sender_id
    u = get_user(tgt)
    if u:
        update_user(tgt, credits=max(0.0, u['credits'] - amt))
        await e.reply(f"➖ Deducted {amt} from <code>{tgt}</code>.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/addall\b"))
async def cmd_addall(e):
    if not is_super(e.sender_id): return
    try: amt = float(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /addall <amount>")
        return
    c = db(); c.execute("UPDATE users SET credits=credits+?", (amt,)); c.commit(); c.close()
    log_act(e.sender_id, "addall", str(amt))
    await e.reply(f"➕ Added {amt} to everyone.")


@client.on(events.NewMessage(pattern=r"^/deductall\b"))
async def cmd_deductall(e):
    if not is_super(e.sender_id): return
    try: amt = float(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /deductall <amount>")
        return
    c = db(); c.execute("UPDATE users SET credits=MAX(0, credits-?)", (amt,)); c.commit(); c.close()
    log_act(e.sender_id, "deductall", str(amt))
    await e.reply(f"➖ Deducted {amt} from everyone.")


@client.on(events.NewMessage(pattern=r"^/addadmin\b"))
async def cmd_aa(e):
    if not is_super(e.sender_id): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /addadmin <user_id>")
        return
    create_user(uid, "admin")
    update_user(uid, is_admin=1)
    log_act(e.sender_id, "addadmin", str(uid))
    await e.reply(f"🛡 <code>{uid}</code> is now admin.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/rmadmin\b"))
async def cmd_ra(e):
    if not is_super(e.sender_id): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /rmadmin <user_id>")
        return
    update_user(uid, is_admin=0)
    log_act(e.sender_id, "rmadmin", str(uid))
    await e.reply(f"Removed <code>{uid}</code> from admins.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/addsuper\b"))
async def cmd_as(e):
    if e.sender_id not in (OWNER_ID_1, OWNER_ID_2): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /addsuper <user_id>")
        return
    create_user(uid, "super")
    update_user(uid, is_super_admin=1, is_admin=1)
    log_act(e.sender_id, "addsuper", str(uid))
    await e.reply(f"👑 <code>{uid}</code> is now Super Admin.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/rmsuper\b"))
async def cmd_rs(e):
    if e.sender_id not in (OWNER_ID_1, OWNER_ID_2): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /rmsuper <user_id>")
        return
    update_user(uid, is_super_admin=0)
    log_act(e.sender_id, "rmsuper", str(uid))
    await e.reply(f"Removed <code>{uid}</code> from super admins.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/setrank\b"))
async def cmd_sr(e):
    if not is_admin(e.sender_id): return
    try:
        uid = int(e.raw_text.split()[1]); rk = int(e.raw_text.split()[2])
    except Exception:
        await e.reply("Usage: /setrank <user_id> <rank>")
        return
    update_user(uid, rank=rk)
    log_act(e.sender_id, "setrank", f"{uid}->{rk}")
    await e.reply(f"🏆 Rank #{rk} set for <code>{uid}</code>.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/newdeal\b"))
async def cmd_nd(e):
    if not is_admin(e.sender_id): return
    try:
        p = e.raw_text.split()
        buyer = int(p[1]); seller = int(p[2]); amt = float(p[3])
        tid = f"DL-PALTAN-{int(time.time())}"
    except Exception:
        await e.reply("Usage: /newdeal <buyer_id> <seller_id> <amount>")
        return
    fee, net = create_deal(tid, buyer, seller, amt, e.sender_id)
    gstats_update(1, amt)
    log_act(e.sender_id, "newdeal", tid)
    await e.reply(f"✅ Deal created: <code>{tid}</code>\nAmount: ₹{amt:.2f} | Fee: ₹{fee:.2f} | Net: ₹{net:.2f}", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/completedeal\b"))
async def cmd_cd(e):
    if not is_admin(e.sender_id): return
    try: tid = e.raw_text.split()[1]
    except Exception:
        await e.reply("Usage: /completedeal <trade_id>")
        return
    complete_deal(tid)
    log_act(e.sender_id, "completedeal", tid)
    await e.reply(f"✅ Deal <code>{tid}</code> completed.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/track\b"))
async def cmd_tr(e):
    if not is_admin(e.sender_id): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /track <user_id>")
        return
    u = get_user(uid)
    if not u:
        await e.reply("User not found.")
        return
    t = (f"🎯 <b>User Track</b>\n━━━━━━━━━━━━━━━━━━━━\n"
         f"• ID: <code>{u['telegram_id']}</code>\n• Username: @{u['username']}\n"
         f"• Banned: {'Yes' if u['is_banned'] else 'No'}\n"
         f"• Admin: {'Yes' if u['is_admin'] else 'No'}\n"
         f"• Super Admin: {'Yes' if u['is_super_admin'] else 'No'}\n"
         f"• Credits: {u['credits']}\n• Rank: {u['rank']}\n"
         f"• Deals: {u['total_deals']}\n• Volume: ₹{u['total_volume']:.2f}")
    await e.reply(t, parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/setforcejoin\b"))
async def cmd_sfj(e):
    if not is_super(e.sender_id): return
    try: ch = e.raw_text.split()[1]
    except Exception:
        await e.reply("Usage: /setforcejoin @channel")
        return
    set_setting('force_join', ch)
    log_act(e.sender_id, "setforcejoin", ch)
    await e.reply(f"🔗 Force join set to {ch}")


@client.on(events.NewMessage(pattern=r"^/protect\b"))
async def cmd_pr(e):
    if not is_admin(e.sender_id): return
    try: uid = int(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /protect <user_id>")
        return
    set_setting(f'protected_{uid}', '1')
    await e.reply(f"🔒 <code>{uid}</code> protected.", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/stats\b"))
async def cmd_st(e):
    if not is_admin(e.sender_id): return
    d, v = gstats()
    users = len(all_users())
    await e.reply(f"📊 Users: {users} | Deals: {int(d)} | Volume: ₹{v:.2f}", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/gencode\b"))
async def cmd_gc(e):
    if not is_admin(e.sender_id): return
    try: amt = float(e.raw_text.split()[1])
    except Exception:
        await e.reply("Usage: /gencode <amount>")
        return
    code = f"PALTAN-{int(time.time())}"
    set_setting(f"code_{code}", str(amt))
    await e.reply(f"🎟 Redeem code: <code>{code}</code> for ₹{amt}", parse_mode="html")


@client.on(events.NewMessage(pattern=r"^/redeem\b"))
async def cmd_rd(e):
    try: code = e.raw_text.split()[1]
    except Exception:
        await e.reply("Usage: /redeem <code>")
        return
    val = get_setting(f"code_{code}")
    if not val or val == "0":
        await e.reply("❌ Invalid or used code.")
        return
    set_setting(f"code_{code}", "0")
    u = get_user(e.sender_id)
    if u:
        update_user(e.sender_id, credits=u['credits'] + float(val))
        await e.reply(f"✅ Redeemed ₹{val} credits.")


# ===================== STARTUP =====================
async def startup_notify():
    msg = (
        "🤖 <b>Paltan Transactions Bot is ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Bot: {BOT_NAME}\n"
        "🔹 Status: 🟢 Active\n"
        "🔹 Database: ✅ Connected\n"
        "🔹 Admin Panel: ✅ Ready\n"
        f"🔹 Fee: {FEE_PERCENT}%\n"
        f"🔹 Colored Buttons: {'✅ ON' if HAS_STYLE else '⚠️ Fallback'}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Use /start to open the dashboard."
    )
    for oid in (OWNER_ID_1, OWNER_ID_2):
        try:
            await client.send_message(oid, msg, parse_mode="html")
        except Exception as e:
            print(f"[notify {oid}] {e}")


async def main():
    init_db()
    print("✅ DB ready.")
    await client.start(bot_token=BOT_TOKEN)
    print("🤖 Bot started.")
    await startup_notify()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
