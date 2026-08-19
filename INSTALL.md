# O'rnatish Yo'riqnomasi — Open Budget Uzbekistan Bot

## Talablar

- Python 3.10 yoki undan yuqori versiyasi
- pip (Python paket menejeri)
- Telegram bot token (@BotFather dan)
- Telegram ADMIN_ID (sizning Telegram ID raqamingiz)
- API kaliti ([@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) dan)

---

## 1. Repozitoriyani Clone Qilish

`ash
git clone https://github.com/tajiboyevjahongir5-sudo/openbudget-uz-bot.git
cd openbudget-uz-bot
`

---

## 2. Python Versiyasini Tekshirish

`ash
python --version
# yoki
python3 --version
`

Python 3.10 yoki undan yuqori bo'lishi shart. Agar kichikroq versiya bo'lsa:
- Windows: [python.org](https://www.python.org/downloads/) dan yuklab oling
- Ubuntu/Debian: sudo apt install python3.11

---

## 3. Dependencylarni O'rnatish

`ash
pip install -r requirements.txt
`

Yoki kutubxonalarni alohida o'rnating:

`ash
pip install aiogram>=3.0.0 aiohttp>=3.9.0 aiosqlite>=0.19.0
`

---

## 4. .env Sozlash

`ash
# .env.example faylini nusxalang
cp .env.example .env
`

.env faylini oching va quyidagi maydonlarni to'ldiring:

`env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_id_here
API_URL=https://openbudjet-production.up.railway.app/api/v1
DATABASE_PATH=client_bot.db
`

### BOT_TOKEN olish
1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing
2. /newbot buyrug'ini yuboring
3. Bot nomini va username'ini kiriting
4. Olingan tokenni BOT_TOKEN ga yozing

### ADMIN_ID olish
1. Telegramda [@userinfobot](https://t.me/userinfobot) ga /start yuboring
2. U sizga Telegram ID raqamingizni ko'rsatadi
3. Shu raqamni ADMIN_ID ga yozing

---

## 5. Telegram Bot Token Kiritish

.env faylidagi BOT_TOKEN ni @BotFather dan olingan token bilan almashtiring.

---

## 6. API Sozlamalarini Kiritish

1. [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) dan API kalitini xarid qiling
2. Botni ishga tushirgandan keyin /admin buyrug'ini yuboring
3. **"🔑 API Kalitni ulash"** tugmasini bosing va API kalitingizni kiriting
4. **"📌 Loyiha IDni sozlash"** tugmasini bosing va openbudget.uz dagi loyiha IDni kiriting

---

## 7. Botni Ishga Tushirish

`ash
python open_budget_client_bot.py
`

Muvaffaqiyatli ishga tushsa, terminalda quyidagi xabar ko'rinadi:
`
Bot ishga tushdi! @YourBotUsername
`

---

## Serverda 24/7 Ishlatish

### Railway.app

1. [Railway.app](https://railway.app) ga kiring
2. **New Project → Deploy from GitHub repo** ni tanlang
3. Ushbu repozitoriyani ulang
4. **Variables** bo'limiga quyidagilarni kiriting:
   - BOT_TOKEN = telegram bot tokeningiz
   - ADMIN_ID = telegram ID raqamingiz
   - API_URL = https://openbudjet-production.up.railway.app/api/v1
   - DATABASE_PATH = /data/client_bot.db
5. **Settings → Volumes → Mount Volume** ni bosing (1GB yetarli)
6. **Custom Start Command**: python open_budget_client_bot.py

> **Muhim:** Volume ulamasangiz, server yangilanganda barcha ma'lumotlar (foydalanuvchilar, sozlamalar) o'chib ketadi!

### VPS / Ubuntu Linux

`ash
# 1. Fayllarni serverga yuklang
scp -r . user@your-server-ip:/home/user/openbudget-bot/

# 2. Serverga SSH orqali kiring
ssh user@your-server-ip

# 3. Kutubxonalarni o'rnating
pip3 install -r requirements.txt

# 4. Systemd service yarating
sudo nano /etc/systemd/system/openbudget-bot.service
`

Systemd fayl mazmuni:
`ini
[Unit]
Description=Open Budget Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/user/openbudget-bot
ExecStart=/usr/bin/python3 open_budget_client_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
`

`ash
# 5. Botni ishga tushiring
sudo systemctl enable openbudget-bot
sudo systemctl start openbudget-bot
sudo systemctl status openbudget-bot
`

---

## Muammolarni Hal Qilish

**Bot ishga tushmasa:**
- BOT_TOKEN ni tekshiring — @BotFather dan to'g'ri token ekani
- Internet ulanishini tekshiring
- pip install -r requirements.txt ni qayta ishga tushiring

**API ulanmasa:**
- API_URL to'g'ri yozilganini tekshiring
- API kalitingiz faol ekanini [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) dan tekshiring

**Ma'lumotlar o'chib ketsa (Railway):**
- Railway panelida Volume ulanganini tekshiring
- DATABASE_PATH=/data/client_bot.db o'zgaruvchisi mavjudligini tekshiring
