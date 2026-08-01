# 🍎 Meva Garden — Telegram Mini App + Python Backend

Frontend HTML/CSS/JS endi Python backend bilan ishlaydi. Olma, reklama, suv, daily bonus va referral ma'lumotlari `SQLite` bazasida saqlanadi.

## 1. Local test

Python 3.11+ tavsiya qilinadi.

```bash
pip install -r requirements.txt
```

`.env.example` faylidan `.env` yarating:

```env
BOT_TOKEN=BOTFATHERDAN_OLINGAN_TOKEN
BOT_USERNAME=bot_username
WEBAPP_URL=http://127.0.0.1:10000
CHANNEL_USERNAME=@kanal_username
PORT=10000
```

Keyin:

```bash
python bot.py
```

Mini Appni Telegram ichidan oching. `http://127.0.0.1` Telegram uchun internetdan ko'rinmaydi, shuning uchun local testda tunnel (masalan, HTTPS tunnel) kerak bo'ladi.

## 2. Serverga qo'yish

Eng oson variant — Render/VPS.

Render uchun:
- GitHub'ga `bit/` papkasini va rootdagi `requirements.txt`, `bot.py`, `render.yaml` fayllarini push qiling.
- Render Web Service yarating.
- Environment Variables:
  - `BOT_TOKEN`
  - `BOT_USERNAME`
  - `WEBAPP_URL` — Render bergan HTTPS domen
  - `CHANNEL_USERNAME` — masalan `@meva_garden`
- Start command: `gunicorn bot:app`

## 3. BotFather'da Mini App

BotFather'da botni yarating va tokenni `.env`ga yozing.

Bot ishga tushgandan keyin `/start` bosilganda Python bot:
`🍎 Meva Gardenni ochish` tugmasini beradi.

`WEBAPP_URL` aynan Mini App ochiladigan HTTPS manzil bo'lishi kerak.

## 4. Kanal vazifasi

`CHANNEL_USERNAME=@kanal_username` yozing.

Botni kanalga **admin** qilib qo'yish tavsiya qilinadi. Shunda backend foydalanuvchi kanalga a'zo ekanini Telegram API orqali tekshiradi.

## 5. Muhim

Frontend endi `localStorage` orqali asosiy balansni saqlamaydi. Asosiy ma'lumot serverdagi `meva_garden.db` SQLite bazasida.

Telegram `initData` serverda HMAC orqali tekshiriladi. Shu sabab foydalanuvchi brauzerdan shunchaki `+100 olma` qilib yubora olmaydi.

### Hozir serverda ishlayotganlar

- Telegram user ID / username
- 🍎 Olma balansi
- 📺 Reklama soni
- 💧 Suv
- 🌳 3 ta reklama → sug'orish → +5 olma
- 🎁 Kunlik bonus → +2 olma
- 📢 Kanal vazifasi → +5 olma
- 👥 Referral
- 🏆 Top 5 referral
- 👤 Profil statistikasi
- SQLite database
- Telegram Mini App authentication

Keyingi bosqichda sotish, omborni upgrade qilish, barcha meva turlarini serverga o'tkazish va admin panelni qo'shish mumkin.
