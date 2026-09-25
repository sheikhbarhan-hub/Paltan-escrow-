import asyncio
import re
import uuid
import logging
from html import escape

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

# =========================================================
# PALTAN TRANSACTIONS ESCROW BOT
# =========================================================

BOT_TOKEN = "8925443014:AAEB7ksbFqNkTS5r8UCsEtXyTjT27UDbiEc"

BOT_USERNAME = "@PaltanTransactionsBot"

# YOUR ADMIN TELEGRAM ID
ADMIN_ID = 6871199191

# SECOND OWNER
OWNER_ID_2 = 2062068620

# OWNER USERNAME
OWNER_USERNAME = "@ZORO_BHAI"

# LOGGER
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger("paltan")

# =========================================================
# BOT + DISPATCHER
# =========================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

# ---- colored button support check ----
HAS_STYLE = False

try:
    _t = InlineKeyboardButton(
        text="t",
        callback_data="t",
        style="success",
    )
    HAS_STYLE = getattr(_t, "style", None) is not None
except Exception:
    HAS_STYLE = False

log.info(f"Colored buttons: {HAS_STYLE}")


# =========================================================
# OWNER CHECK
# =========================================================

def is_admin(uid: int) -> bool:
    return uid in (ADMIN_ID, OWNER_ID_2)


# =========================================================
# ESCROW FEE
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
# GET FIELD FROM ESCROW FORM
# =========================================================

def get_field(text, field_names):
    """
    Finds values from lines such as:

    • 𝗦𝗘𝗟𝗟𝗘𝗥 : @username
    • 𝗕𝗨𝗬𝗘𝗥 : @username
    """

    for line in text.splitlines():

        line = line.strip()

        for field in field_names:

            # Remove bullet and spaces
            pattern = rf"^[•\-\s]*{re.escape(field)}\s*:\s*(.*)$"

            match = re.search(pattern, line, re.IGNORECASE)

            if match:
                value = match.group(1).strip()

                if value:
                    return value

    return "Not Provided"


# =========================================================
# GET AMOUNT
# =========================================================

def get_amount(text):

    amount_text = get_field(
        text,
        [
            "𝗗𝗘𝗔𝗟 𝗔𝗠𝗢𝗨𝗡𝗧",
            "DEAL AMOUNT",
        ],
    )

    # Remove currency symbols and commas
    cleaned = amount_text.replace(",", "")
    cleaned = cleaned.replace("₹", "")
    cleaned = cleaned.replace("INR", "")
    cleaned = cleaned.strip()

    match = re.search(r"\d+(?:\.\d+)?", cleaned)

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


# =========================================================
# MONEY FORMAT
# =========================================================

def money(amount):
    return f"₹{amount:,.2f}"


# =========================================================
# TRADE ID
# =========================================================

def generate_trade_id():

    random_part = uuid.uuid4().hex[:6].upper()

    return f"DL-{random_part}"


# =========================================================
# COLORED BUTTON HELPER
# =========================================================

def KB(text, data, style="primary"):

    if HAS_STYLE:

        try:
            return InlineKeyboardButton(
                text=text,
                callback_data=data,
                style=style,
            )
        except Exception:
            pass

    return InlineKeyboardButton(
        text=text,
        callback_data=data,
    )


def main_menu():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [KB("📖 Help", "menu_help", "primary")],
            [KB("🆔 My ID", "menu_myid", "primary")],
            [KB("✅ Close Deal", "menu_close", "success")],
            [KB("🛡 Admin Info", "menu_admin", "danger")],
        ]
    )


# =========================================================
# START
# =========================================================

@dp.message(Command("start"))
async def start(m: Message):

    message = (
        "🛡️ <b>𝗣𝗔𝗟𝗧𝗔𝗡 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡𝗦 𝗘𝗦𝗖𝗥𝗢𝗪</b>\n\n"

        "Professional escrow deal management bot.\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "<b>𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦</b>\n\n"

        "/start - Start bot\n"
        "/help - Show help\n"
        "/myid - Show your Telegram ID\n"
        "/close - Complete a deal\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "To complete a deal, reply to the original "
        "ESCROW DEAL form and send <code>/close</code>."
    )

    await m.answer(
        message,
        reply_markup=main_menu(),
    )


# =========================================================
# HELP
# =========================================================

@dp.message(Command("help"))
async def help_command(m: Message):

    message = (
        "🛡️ <b>𝗣𝗔𝗟𝗧𝗔𝗡 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡𝗦 𝗘𝗦𝗖𝗥𝗢𝗪</b>\n\n"

        "<b>How to close a deal:</b>\n\n"

        "1️⃣ Post the ESCROW DEAL form.\n"
        "2️⃣ Complete the deal.\n"
        "3️⃣ Admin replies to that form.\n"
        "4️⃣ Admin sends <code>/close</code>.\n"
        "5️⃣ Bot automatically creates the Completed Deal summary.\n\n"

        "No payment system is connected."
    )

    await m.answer(
        message,
        reply_markup=main_menu(),
    )


# =========================================================
# MY ID
# =========================================================

@dp.message(Command("myid"))
async def myid(m: Message):

    user_id = m.from_user.id

    await m.answer(
        f"Your Telegram ID: <code>{user_id}</code>"
    )


# =========================================================
# CLOSE DEAL
# =========================================================

@dp.message(Command("close"))
async def close_deal(m: Message):

    # -----------------------------------------------------
    # GET USER ID
    # -----------------------------------------------------

    user_id = m.from_user.id

    # -----------------------------------------------------
    # ADMIN CHECK
    # -----------------------------------------------------

    if not is_admin(user_id):

        await m.answer(
            "❌ Only an authorized admin can close a deal.\n\n"
            f"Your ID: {user_id}\n"
            f"Owner: {OWNER_USERNAME}"
        )

        return

    # -----------------------------------------------------
    # MUST BE REPLY
    # -----------------------------------------------------

    if not m.reply_to_message:

        await m.answer(
            "⚠️ Please reply to the original "
            "𝗘𝗦𝗖𝗥𝗢𝗪 𝗗𝗘𝗔𝗟 form and send /close."
        )

        return

    # -----------------------------------------------------
    # ORIGINAL DEAL MESSAGE
    # -----------------------------------------------------

    original_message = m.reply_to_message

    deal_text = (
        original_message.text
        or original_message.caption
        or ""
    )

    if not deal_text:

        await m.answer(
            "❌ I couldn't read the original ESCROW DEAL form."
        )

        return

    # -----------------------------------------------------
    # READ DEAL DETAILS
    # -----------------------------------------------------

    seller = get_field(
        deal_text,
        [
            "𝗦𝗘𝗟𝗟𝗘𝗥",
            "SELLER",
        ],
    )

    buyer = get_field(
        deal_text,
        [
            "𝗕𝗨𝗬𝗘𝗥",
            "BUYER",
        ],
    )

    detail = get_field(
        deal_text,
        [
            "𝗗𝗘𝗔𝗟 𝗗𝗘𝗧𝗔𝗜𝗟",
            "DEAL DETAIL",
        ],
    )

    expected_time = get_field(
        deal_text,
        [
            "𝗘𝗫𝗣𝗘𝗖𝗧𝗘𝗗 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘 𝗗𝗘𝗔𝗟",
            "EXPECTED TIME TO COMPLETE DEAL",
        ],
    )

    terms = get_field(
        deal_text,
        [
            "𝗧/𝗖 (𝗜𝗙 𝗔𝗡𝗬)",
            "𝗧/𝗖",
            "T/C (IF ANY)",
            "T/C",
        ],
    )

    # -----------------------------------------------------
    # GET AMOUNT
    # -----------------------------------------------------

    amount = get_amount(deal_text)

    if amount is None:

        await m.answer(
            "❌ Deal amount could not be detected.\n\n"

            "Use this format in the deal form:\n\n"

            "• 𝗗𝗘𝗔𝗟 𝗔𝗠𝗢𝗨𝗡𝗧 : ₹1040"
        )

        return

    # -----------------------------------------------------
    # CALCULATE FEE
    # -----------------------------------------------------

    fee, fee_label = calculate_fee(amount)

    net_release = amount - fee

    # -----------------------------------------------------
    # ESCROW ADMIN
    # -----------------------------------------------------

    admin_user = m.from_user

    if admin_user.username:

        escrowed_by = f"@{admin_user.username}"

    else:

        escrowed_by = admin_user.first_name or "Admin"

    # -----------------------------------------------------
    # TRADE ID
    # -----------------------------------------------------

    trade_id = generate_trade_id()

    # -----------------------------------------------------
    # ESCAPE USER DATA FOR HTML
    # -----------------------------------------------------

    seller = escape(seller)
    buyer = escape(buyer)
    detail = escape(detail)
    expected_time = escape(expected_time)
    terms = escape(terms)
    escrowed_by = escape(escrowed_by)

    # -----------------------------------------------------
    # COMPLETED DEAL
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # SEND COMPLETED DEAL
    # -----------------------------------------------------

    await m.reply(
        completed_message
    )


# =========================================================
# CALLBACKS (menu buttons)
# =========================================================

@dp.callback_query()
async def on_cb(call: CallbackQuery):

    data = call.data
    uid = call.from_user.id

    if data == "menu_help":

        text = (
            "🛡️ <b>𝗣𝗔𝗟𝗧𝗔𝗡 𝗧𝗥𝗔𝗡𝗦𝗔𝗖𝗧𝗜𝗢𝗡𝗦 𝗘𝗦𝗖𝗥𝗢𝗪</b>\n\n"

            "<b>How to close a deal:</b>\n\n"

            "1️⃣ Post the ESCROW DEAL form.\n"
            "2️⃣ Complete the deal.\n"
            "3️⃣ Admin replies to that form.\n"
            "4️⃣ Admin sends <code>/close</code>.\n"
            "5️⃣ Bot creates the Completed Deal summary."
        )

        await call.message.answer(text, reply_markup=main_menu())
        await call.answer()

    elif data == "menu_myid":

        await call.message.answer(
            f"Your Telegram ID: <code>{uid}</code>",
            reply_markup=main_menu(),
        )
        await call.answer()

    elif data == "menu_close":

        if not is_admin(uid):
            await call.answer("❌ Only admin can close deals.", show_alert=True)
            return

        await call.message.answer(
            "⚠️ Reply to the original ESCROW DEAL form and send <code>/close</code>.",
            reply_markup=main_menu(),
        )
        await call.answer()

    elif data == "menu_admin":

        await call.message.answer(
            f"🛡 Owner: <code>{OWNER_USERNAME}</code>\n"
            f"Your ID: <code>{uid}</code>\n"
            f"{'✅ You are admin.' if is_admin(uid) else '❌ You are not admin.'}",
            reply_markup=main_menu(),
        )
        await call.answer()

    else:

        await call.answer("Unknown action.", show_alert=True)


# =========================================================
# STARTUP NOTIFICATION TO OWNERS
# =========================================================

async def startup_notify():

    msg = (
        "🤖 <b>PALTAN TRANSACTIONS ESCROW BOT — ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 Bot: {BOT_USERNAME}\n"
        "🔹 Status: 🟢 Active\n"
        f"🔹 Owner: {OWNER_USERNAME}\n"
        f"🔹 Colored Buttons: {'✅ ON' if HAS_STYLE else '⚠️ Plain'}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Use /start in your chat to begin."
    )

    for oid in (ADMIN_ID, OWNER_ID_2):

        try:
            await bot.send_message(oid, msg)
            log.info(f"Startup notified owner {oid}")
        except Exception as e:
            log.warning(f"[notify {oid}] {e}")


# =========================================================
# MAIN
# =========================================================

async def main():

    log.info("PALTAN TRANSACTIONS ESCROW BOT IS RUNNING...")

    await startup_notify()

    await dp.start_polling(bot)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    asyncio.run(main())