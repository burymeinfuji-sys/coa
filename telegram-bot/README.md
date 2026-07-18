# Telegram Poll Bot

A Telegram bot that lets users submit poll requests via DM. Admins review each submission in a private group and can **Accept** (posts the poll publicly) or **Reject** (notifies the user).

---

## Flow

```
User DMs /poll
  → picks poll type (HOF / MK / Duo / Alias Claim / Custom)
  → enters title
  → enters description
  → enters options (one per line)
  → submission sent to admin group with ✅ Accept / ❌ Reject buttons

Admin presses ✅ Accept  → poll posted to public group, user notified
Admin presses ❌ Reject  → user receives rejection DM
```

---

## Environment variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_GROUP_ID` | Numeric ID of the private admin group (negative number, e.g. `-1001234567890`) |
| `PUBLIC_GROUP_ID` | Numeric ID of the public group where approved polls are posted |

---

## Getting group IDs

1. Add [@userinfobot](https://t.me/userinfobot) to a group and send any message — it replies with the group ID.
2. Alternatively, forward a message from the group to [@userinfobot](https://t.me/userinfobot).

The bot **must be an admin** in both the admin group and the public group so it can post messages and polls.

---

## Setup (local)

```bash
cd telegram-bot
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python main.py
```

---

## Running on Replit

Set `BOT_TOKEN`, `ADMIN_GROUP_ID`, and `PUBLIC_GROUP_ID` as Replit Secrets, then start the **Telegram Poll Bot** workflow.

---

## Bot commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/poll` | Start a poll submission |
| `/cancel` | Cancel an in-progress submission |
