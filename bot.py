"""
YESH ESCROW SERVICE — aiogram 3.19+ Build
Colored inline buttons. Same escrow features: /start /help /myid /close.
"""

import os
import re
import uuid
import logging
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yesh")

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID  = 7346725373   # <-- change this to your ID if needed
# ==================================================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---- colored button support ----
HAS_STYLE = False
try:
    _t = InlineKeyboardButton(text="t", callback_data="t", style="success")
    HAS_STYLE = getattr(_t, "style", None) is not None
except Exception:
    HAS_STYLE = False
log.info(f"Colored buttons: {HAS_STYLE}")


# =========================================================
# FEE
# =========================================================
def calculate_fee(amount):
    if amount < 200:
        return 10.0, "₹10"
    elif amount <= 1000:
        return 20.0, "₹20"
    else:
        fee = amount * 2 / 100
        return fee, "2%"


# =========================================================
# FORM PARSER
# =========================================================
def get_field(text, field_names):
    for line in text.splitlines():
        line = line.strip()
        for field in field_names:
            pattern = rf"^[•\-\s]*{re.escape(field)}\s*:\s*(.*)$"
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
    return "Not Provided"


def get_amount(text):
    amount_text = get_field(text, ["𝗗𝗘𝗔𝗟 𝗔𝗠𝗢𝗨𝗡𝗧", "DEAL AMOUNT"])
    cleaned = amount_text.replace(",", "").replace("₹", "").replace("INR", "").strip()
    m = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def money(amount):
    return f"₹{amount:,.2f}"


def generate_trade_id():
    return f"DL-{uuid.uuid4().hex[:6].upper()}"


# =========================================================
# KEYBOARDS
# =========================================================
def KB(text, data, style="primary"):
    if HAS_STYLE:
        try:
            return InlineKeyboardButton(text=text, callback_data=data, style=style)
        except Exception:
            pass
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [KB("📖 Help", "menu_help", "primary")],
        [KB("🆔 My ID", "menu_myid", "primary")],
        [KB("✅ Close Deal", "menu_close", "success")],
        [KB("🛡 Admin Info", "menu_admin", "danger")],
    ])


# =========================================================
# /start
# =========================================================
@dp.message(Command("start"))
async def start(m: Message):
    text = (
        "🛡️ <b>𝗬𝗘𝗦𝗛 𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
        "Professional escrow deal management bot.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<b>𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n\n"
        "/start — Start bot\n"
        "/help — Show help\n"
        "/myid — Show your Telegram ID\n"
        "/close — Complete a deal\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "To complete a deal, reply to the original "
        "ESCROW DEAL form and send <code>/close</code>."
    )
    await m.answer(text, reply_markup=main_menu())


# =========================================================
# /help
# =========================================================
@dp.message(Command("help"))
async def help_cmd(m: Message):
    text = (
        "🛡️ <b>𝗬𝗘𝗦𝗛 𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
        "<b>How to close a deal:</b>\n\n"
        "1️⃣ Post the ESCROW DEAL form.\n"
        "2️⃣ Complete the deal.\n"
        "3️⃣ Admin replies to that form.\n"
        "4️⃣ Admin sends <code>/close</code>.\n"
        "5️⃣ Bot automatically creates the Completed Deal summary.\n\n"
        "No payment system is connected."
    )
    await m.answer(text, reply_markup=main_menu())


# =========================================================
# /myid
# =========================================================
@dp.message(Command("myid"))
async def myid_cmd(m: Message):
    await m.answer(f"Your Telegram ID: <code>{m.from_user.id}</code>")


# =========================================================
# /close  (admin only, must reply to deal form)
# =========================================================
@dp.message(Command("close"))
async def close_deal(m: Message):
    uid = m.from_user.id
    if uid != ADMIN_ID:
        await m.answer(
            "❌ Only an authorized admin can close a deal.\n\n"
            f"Your ID: <code>{uid}</code>\n"
            f"Admin ID: <code>{ADMIN_ID}</code>"
        )
        return

    if not m.reply_to_message:
        await m.answer("⚠️ Please reply to the original 𝗘𝗦𝗖𝗥𝗢𝗪 𝗗𝗘𝗔𝗟 form and send /close.")
        return

    orig = m.reply_to_message
    deal_text = orig.text or orig.caption or ""
    if not deal_text:
        await m.answer("❌ I couldn't read the original ESCROW DEAL form.")
        return

    seller = get_field(deal_text, ["𝗦𝗘𝗟𝗟𝗘𝗥", "SELLER"])
    buyer = get_field(deal_text, ["𝗕𝗨𝗬𝗘𝗥", "BUYER"])
    detail = get_field(deal_text, ["𝗗𝗘𝗔𝗟 𝗗𝗘𝗧𝗔𝗜𝗟", "DEAL DETAIL"])
    expected_time = get_field(deal_text, [
        "𝗘𝗫𝗣𝗘𝗖𝗧𝗘𝗗 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘 𝗗𝗘𝗔𝗟",
        "EXPECTED TIME TO COMPLETE DEAL",
    ])
    terms = get_field(deal_text, ["𝗧/𝗖 (𝗜𝗙 𝗔𝗡𝗬)", "𝗧/𝗖", "T/C (IF ANY)", "T/C"])

    amount = get_amount(deal_text)
    if amount is None:
        await m.answer(
            "❌ Deal amount could not be detected.\n\n"
            "Use this format in the deal form:\n\n"
            "• 𝗗𝗘𝗔𝗟 𝗔𝗠𝗢𝗨𝗡𝗧 : ₹1040"
        )
        return

    fee, fee_label = calculate_fee(amount)
    net_release = amount - fee

    admin_user = m.from_user
    escrowed_by = f"@{admin_user.username}" if admin_user.username else (admin_user.first_name or "Admin")

    trade_id = generate_trade_id()

    seller = escape(seller)
    buyer = escape(buyer)
    detail = escape(detail)
    expected_time = escape(expected_time)
    terms = escape(terms)
    escrowed_by = escape(escrowed_by)

    completed_message = (
        "✅ <b>𝗗𝗘𝗔𝗟 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗</b>\n\n"
        f"💰 <b>Deal Amount:</b> {money(amount)}\n"
        f"📤 <b>Fee:</b> {fee_label} — {money(fee)}\n"
        f"📤 <b>Net Release:</b> {money(net_release)}\n\n"
        f"🆔 <b>Trade ID:</b> {trade_id}\n"
        f"👤 <b>Buyer:</b> {buyer}\n"
        f"👤 <b>Seller:</b> {seller}\n\n"
        f"📝 <b>Detail:</b> {detail}\n"
        f"⏱️ <b>Expected Time:</b> {expected_time}\n\n"
        f"📌 <b>T/C:</b> {terms}\n\n"
        f"🛡 <b>Escrowed By:</b> {escrowed_by}"
    )

    await m.reply(completed_message)


# =========================================================
# CALLBACKS (menu buttons)
# =========================================================
@dp.callback_query()
async def on_cb(call: CallbackQuery):
    data = call.data
    uid = call.from_user.id

    if data == "menu_help":
        text = (
            "🛡️ <b>𝗬𝗘𝗦𝗛 𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
            "1️⃣ Post the ESCROW DEAL form.\n"
            "2️⃣ Complete the deal.\n"
            "3️⃣ Admin replies to that form.\n"
            "4️⃣ Admin sends <code>/close</code>.\n"
            "5️⃣ Bot posts the Completed Deal summary."
        )
        await call.message.answer(text, reply_markup=main_menu())
        await call.answer()

    elif data == "menu_myid":
        await call.message.answer(f"Your Telegram ID: <code>{uid}</code>", reply_markup=main_menu())
        await call.answer()

    elif data == "menu_close":
        if uid != ADMIN_ID:
            await call.answer("❌ Only admin can close deals.", show_alert=True)
            return
        await call.message.answer(
            "⚠️ Reply to the original ESCROW DEAL form and send <code>/close</code>.",
            reply_markup=main_menu(),
        )
        await call.answer()

    elif data == "menu_admin":
        await call.message.answer(
            f"🛡 Admin ID: <code>{ADMIN_ID}</code>\n"
            f"Your ID: <code>{uid}</code>\n"
            f"{'✅ You are admin.' if uid == ADMIN_ID else '❌ You are not admin.'}",
            reply_markup=main_menu(),
        )
        await call.answer()

    else:
        await call.answer("Unknown action.", show_alert=True)


# =========================================================
# MAIN
# =========================================================
async def main():
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN is not set. Add it in the Env tab of this deployment, then restart.")
        return
    log.info("YESH ESCROW SERVICE BOT IS RUNNING...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
