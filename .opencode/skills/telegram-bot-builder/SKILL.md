---
name: telegram-bot-builder
description: Build and maintain Telegram bots with aiogram 3.x and the Bot API. Use when creating bot handlers, FSM flows, inline/reply keyboards, callback queries, media sending, commands, polling vs webhook, or deploying the Qagro bot. Triggers: telegram, aiogram, bot, handlers, FSM, keyboards, callback_query, webhook, polling.
license: MIT
compatibility: opencode
---

# Telegram Bot Builder

Guidance for building Telegram bots using the Bot API (v9.4) with aiogram 3.x
as the primary framework. Adapted from davila7/claude-code-templates
`telegram-bot-builder` for Qagro.

## Core Concepts

### Authentication

Every bot has a unique token from [@BotFather](https://t.me/BotFather).
All API calls go to: `https://api.telegram.org/bot<TOKEN>/METHOD_NAME`.

```bash
# .env file — the ONLY place for the token
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

Store the token in environment variables. Never commit it to source code,
never hardcode it, never print it in docs or README.

### Receiving Updates: Polling vs Webhook

**Long polling** — simpler, no HTTPS required, ideal for development and for
the Qagro MVP (bot runs next to the API via docker-compose):

```python
# aiogram 3.x polling (Qagro pattern, see src/bot.py)
import asyncio, os
from aiogram import Bot, Dispatcher

async def main() -> None:
    bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
    dp = Dispatcher()
    # ... register routers/handlers ...
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

**Webhook** — better for high-traffic production, requires HTTPS
(ports 443, 80, 88, or 8443). Choose polling for development and small bots.

### Message Types & Formatting

`sendMessage` parse modes: **HTML**
(`<b>`, `<i>`, `<code>`, `<pre>`, `<a href>`, `<tg-spoiler>`) or **MarkdownV2**
(`*bold*`, `_italic_`, `` `code` `` — requires escaping `_*[]()~>#+-=|{}.!`).
Prefer HTML for easier escaping.

### Keyboards & Interactive Elements

**Inline keyboard** (buttons attached to a message, `callback_data` max 64 bytes —
always call `answerCallbackQuery` to dismiss the loading indicator).
**Reply keyboard** (custom keyboard below the input, `resize_keyboard: true`).
Handle button presses via `callback_query`.

aiogram 3.x pattern (routers + filters, no global handlers):

```python
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

router = Router()

@router.message(F.text == "/start")
async def cmd_start(m: Message) -> None: ...

@router.callback_query(F.data.startswith("district:"))
async def on_district(c: CallbackQuery) -> None:
    await c.answer()  # always dismiss the indicator
    ...
```

Multi-step flows: aiogram FSM (`FSMContext`, states per chat) — for Qagro's
language -> district -> crop wizard. Keep state `{step, data}` per chat;
validate callbacks against allow-lists from `config/districts.yaml` + `ALL_CROPS`.

### Sending Media

Three ways to specify files: `file_id` (reuse), HTTP URL (Telegram downloads),
or multipart upload. Limits: ~50 MB upload, ~20 MB download via Bot API.
For Qagro PDF reports: `sendDocument` with bytes from `src/report_pdf.py`.

### Bot Commands

Register commands for the Telegram menu (`setMyCommands`: `/start`, `/help`,
plus Qagro's `/gis`, `/spray`, `/guide`, `/compare`, `/fields`, `/elevators`).
Commands can be scoped per chat/user/language.

### Error Handling

- **429**: read `retry_after`, wait, retry with exponential backoff.
- **403**: bot blocked/removed — stop messaging that chat.
- **400**: invalid parameters — check `description`.
- **409**: another instance polling with the same token — kill duplicates.
- Rate limits: ~30 msg/s to different chats, ~20 msg/min to the same group.

### Security Checklist

- Token in env only (`TELEGRAM_BOT_TOKEN`, see `.env.example`).
- Validate webhook secret header when webhooks are used.
- Verify user/chat IDs for admin commands; per-user rate limiting.
- Sanitize user input before storage; HTTPS-only webhooks.

---

## Qagro appendix (project-specific, takes precedence in this repo)

Bot: `src/bot.py` (aiogram 3.x). Launch: `python -m src.bot` (or `run_bot.bat`).

- Flow: `/start` -> language inline (RU/KZ/EN) -> district (10, from
  `config/districts.yaml`) -> crop (6, `ALL_CROPS`) -> answer card
  (yield + drought light + insurance + recommendation + PDF). Commands:
  `/gis` (satellite fields), `/spray` (spray window), `/guide` (diseases),
  `/compare` (2 crops), `/fields` (115: 109 OSM + 6 demo), `/elevators` (12).
  Geolocation button -> nearest district via haversine.
- Token ONLY from env `TELEGRAM_BOT_TOKEN` (via `python-dotenv`, `.env` file).
  No tokens in code/README/logs. Import-time failure pattern: `main()` raises
  loudly when the token is missing — keep it loud, never fall back to a demo token.
- Cache: SQLite `data/cache.db` (Open-Meteo + report payloads, TTL 24 h).
  Keep TTL logic; persist path `./data:/app/data` in compose.
- Offline honesty: when `src/predict.py` / `src/risk.py` / Open-Meteo fail, reply
  with the honest error card (no invented numbers), same as the API's
  `_safe_risk` contract. Reuse `src/` functions — never duplicate ML logic in bot.
- i18n: all user-visible strings via language dicts (ru/kz/en parity); tech ids
  (`Esil`, `P_loss`) stay in small captions only, per `DESIGN.md` rule 6.
