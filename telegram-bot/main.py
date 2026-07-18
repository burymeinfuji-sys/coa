#!/usr/bin/env python3
"""
Telegram Poll Bot
Users DM /poll, pick a type, fill in details, and admins approve/reject.
"""

import os
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_GROUP_ID = int(os.environ["ADMIN_GROUP_ID"])
PUBLIC_GROUP_ID = int(os.environ["PUBLIC_GROUP_ID"])

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
CHOOSING_TYPE, ENTERING_TITLE, ENTERING_DESCRIPTION, ENTERING_OPTIONS = range(4)

# ---------------------------------------------------------------------------
# Poll type options
# ---------------------------------------------------------------------------
POLL_TYPES = ["HOF Poll", "MK Poll", "Duo Poll", "Alias Claim", "Custom Poll"]

# ---------------------------------------------------------------------------
# In-memory store: poll_id → poll data
# Survives only for the process lifetime; good enough for most deployments.
# ---------------------------------------------------------------------------
pending_polls: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome! Use /poll to submit a poll request to the admins."
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send back the current chat's ID — run this inside your admin/public group."""
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 This chat's ID is:\n`{cid}`\n\n"
        f"Configured ADMIN_GROUP_ID: `{ADMIN_GROUP_ID}`\n"
        f"Configured PUBLIC_GROUP_ID: `{PUBLIC_GROUP_ID}`",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /poll  →  show poll-type keyboard
# ---------------------------------------------------------------------------
async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton(pt, callback_data=f"type:{pt}")]
        for pt in POLL_TYPES
    ]
    await update.message.reply_text(
        "📊 Choose a poll type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSING_TYPE


# ---------------------------------------------------------------------------
# Step 0: poll type selected
# ---------------------------------------------------------------------------
async def poll_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    poll_type = query.data.split(":", 1)[1]
    context.user_data["poll_type"] = poll_type
    await query.edit_message_text(
        f"📊 *{poll_type}* selected.\n\n"
        "Step 1 of 3 — Enter a *title* for your poll:",
        parse_mode="Markdown",
    )
    return ENTERING_TITLE


# ---------------------------------------------------------------------------
# Step 1: title
# ---------------------------------------------------------------------------
async def enter_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2 of 3 — Enter a *description* for your poll:",
        parse_mode="Markdown",
    )
    return ENTERING_DESCRIPTION


# ---------------------------------------------------------------------------
# Step 2: description
# ---------------------------------------------------------------------------
async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 3 of 3 — Enter the *poll options*, one per line "
        "(2–10 options required):",
        parse_mode="Markdown",
    )
    return ENTERING_OPTIONS


# ---------------------------------------------------------------------------
# Step 3: options  →  send to admin group
# ---------------------------------------------------------------------------
async def enter_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    options = [line.strip() for line in raw.splitlines() if line.strip()]

    if len(options) < 2:
        await update.message.reply_text(
            "⚠️ Please enter at least *2 options*, one per line:",
            parse_mode="Markdown",
        )
        return ENTERING_OPTIONS

    if len(options) > 10:
        await update.message.reply_text(
            "⚠️ Telegram polls support at most *10 options*. "
            "Please shorten your list:",
            parse_mode="Markdown",
        )
        return ENTERING_OPTIONS

    user = update.effective_user
    poll_id = uuid.uuid4().hex[:10]

    pending_polls[poll_id] = {
        "user_id": user.id,
        "user_name": user.full_name,
        "user_handle": f"@{user.username}" if user.username else user.full_name,
        "poll_type": context.user_data["poll_type"],
        "title": context.user_data["title"],
        "description": context.user_data["description"],
        "options": options,
    }

    poll = pending_polls[poll_id]
    options_text = "\n".join(f"  {i + 1}. {o}" for i, o in enumerate(options))

    admin_msg = (
        f"📬 *New Poll Submission*\n\n"
        f"👤 *User:* {poll['user_handle']} (`{poll['user_id']}`)\n"
        f"🏷 *Type:* {poll['poll_type']}\n"
        f"📌 *Title:* {poll['title']}\n"
        f"📝 *Description:* {poll['description']}\n"
        f"🗳 *Options:*\n{options_text}\n\n"
        f"_Poll ID: `{poll_id}`_"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"accept:{poll_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{poll_id}"),
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=admin_msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    await update.message.reply_text(
        "✅ Your poll has been submitted for review.\n"
        "You'll receive a DM once an admin makes a decision."
    )

    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /cancel — escape hatch at any step
# ---------------------------------------------------------------------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Poll submission cancelled.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Admin: Accept / Reject callback
# ---------------------------------------------------------------------------
async def handle_admin_decision(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    action, poll_id = query.data.split(":", 1)
    poll = pending_polls.get(poll_id)

    if poll is None:
        # Already processed
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "⚠️ This submission has already been processed."
        )
        return

    admin_name = query.from_user.full_name

    if action == "accept":
        # Post a context message + native Telegram poll to the public group
        await context.bot.send_message(
            chat_id=PUBLIC_GROUP_ID,
            text=(
                f"📊 *{poll['poll_type']}*\n"
                f"{poll['description']}"
            ),
            parse_mode="Markdown",
        )

        question = poll["title"]
        if len(question) > 255:
            question = question[:252] + "…"

        await context.bot.send_poll(
            chat_id=PUBLIC_GROUP_ID,
            question=question,
            options=poll["options"],
            is_anonymous=False,
        )

        # DM the submitter
        try:
            await context.bot.send_message(
                chat_id=poll["user_id"],
                text=(
                    f"✅ Your poll *{poll['title']}* has been *approved* "
                    f"and posted to the group!"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Could not DM user %s: %s", poll["user_id"], e)

        # Update admin group message
        await query.edit_message_text(
            text=query.message.text + f"\n\n✅ *Accepted* by {admin_name}",
            parse_mode="Markdown",
        )

    elif action == "reject":
        # DM the submitter
        try:
            await context.bot.send_message(
                chat_id=poll["user_id"],
                text=(
                    f"❌ Your poll submission *{poll['title']}* "
                    f"was *rejected* by an admin."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Could not DM user %s: %s", poll["user_id"], e)

        # Update admin group message
        await query.edit_message_text(
            text=query.message.text + f"\n\n❌ *Rejected* by {admin_name}",
            parse_mode="Markdown",
        )

    del pending_polls[poll_id]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("poll", poll_command)],
        states={
            CHOOSING_TYPE: [
                CallbackQueryHandler(poll_type_chosen, pattern=r"^type:")
            ],
            ENTERING_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_title)
            ],
            ENTERING_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description)
            ],
            ENTERING_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_options)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        # Allow the user to restart /poll mid-conversation
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(conv_handler)
    app.add_handler(
        CallbackQueryHandler(handle_admin_decision, pattern=r"^(accept|reject):")
    )

    logger.info("Bot is running — polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
