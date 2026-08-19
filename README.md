# Open Budget Uzbekistan 2026 — Telegram Bot

**Open Budget Uzbekistan (Ochiq Budjet) uchun tayyor, ochiq manbali Telegram bot.**

Ushbu loyiha O'zbekiston **Open Budget (openbudget.uz)** tizimi bilan integratsiya qiluvchi, ovoz berish, mukofot va admin boshqaruv imkoniyatlarini taqdim etuvchi to'liq funksional Telegram bot shablonidir.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram" alt="Aiogram 3" />
  <img src="https://img.shields.io/badge/SQLite-WAL_Database-003B57?style=for-the-badge&logo=sqlite" alt="SQLite" />
  <img src="https://img.shields.io/badge/Bot-@Budjetuz2026__bot-26A5E4?style=for-the-badge&logo=telegram" alt="Demo Bot" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License MIT" />
</p>

> **Demo bot:** [@Budjetuz2026_bot](https://t.me/Budjetuz2026_bot) · **API Gateway:** [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot)

---

## 📌 Loyiha Haqida

Ushbu loyiha — **Open Budget Uzbekistan (Ochiq Budjet)** platformasi uchun tayyor, zamonaviy Telegram ovoz berish bot kodi (source code).

Bot O'zbekiston Ochiq Budjet tashabbuslarini qo'llab-quvvatlash, ovozlarni avtomatik yig'ish, foydalanuvchilarga UZS mukofot to'lash va admin boshqaruvini osonlashtirish uchun ishlab chiqilgan.

**Asosiy links:**
- 🤖 **API Gateway Boti**: [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot)
- 🌐 **API Server**: `https://openbudjet-production.up.railway.app`
- 📚 **Batafsil O'rnatish Yo'riqnomasi**: [`INSTALL.md`](INSTALL.md)
- 📡 **API Hujjatlari**: [`API.md`](API.md)

---

## ⚡ Asosiy Imkoniyatlar

| Imkoniyat | Tavsif |
|-----------|--------|
| 🧠 **AI Captcha Solver** | Gemini AI yordamida captchalarni avtomatik hal qiladi |
| 💳 **Admin Panel** | `/admin` buyrug'i orqali to'liq boshqaruv |
| 🗳️ **Avtomatik Ovoz Berish** | Open Budget API bilan to'liq integratsiya |
| 💰 **Mukofot Tizimi** | Har bir ovoz uchun UZS mukofot (Uzcard/Humo) |
| 📊 **Hisobot** | Foydalanuvchilar va ovozlar statistikasi (TXT) |
| 📢 **Broadcast** | Barcha foydalanuvchilarga xabar tarqatish |
| 💾 **Doimiy DB** | aiosqlite + WAL, Railway Volume bilan persistent |
| 🛡️ **Xavfsiz** | FSM, async, thread-safe, .env orqali sozlash |

---

## 🚀 Tezkor Ishga Tushirish

```bash
# 1. Reponi yuklab oling
git clone https://github.com/tajiboyevjahongir5-sudo/openbudget-uz-bot.git
cd openbudget-uz-bot

# 2. Kutubxonalarni o'rnating
pip install -r requirements.txt

# 3. .env sozlamalarini to'ldiring
cp .env.example .env
# .env faylini oching va sozlamalarni kiriting

# 4. Botni ishga tushiring
python open_budget_client_bot.py
```

To'liq o'rnatish yo'riqnomasi uchun [`INSTALL.md`](INSTALL.md) ga qarang.

---

## ⚙️ Minimal Sozlamalar (`.env`)

```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_id_here
API_URL=https://openbudjet-production.up.railway.app/api/v1
DATABASE_PATH=client_bot.db
```

---

## ☁️ Serverda 24/7 Ishga Tushirish

### Railway.app (Tavsiya etiladi)
1. Ushbu repozitoriyani Railway'ga ulang.
2. `Variables` bo'limiga `BOT_TOKEN`, `ADMIN_ID`, `API_URL`, `DATABASE_PATH=/data/client_bot.db` ni kiriting.
3. `Settings → Volumes → Mount Volume` orqali doimiy disk uling (ma'lumotlar o'chib ketmasin).
4. Custom Start Command: `python open_budget_client_bot.py`

### VPS / Ubuntu Linux
```bash
pip3 install -r requirements.txt
# Systemd bilan ishga tushirish uchun QOLLANMA.txt yoki INSTALL.md ga qarang
```

---

## 🔑 API Kalit Olish

Open Budget tizimi orqali rasmiy ovozlarni qabul qilish uchun API kalitlari zarur.

> **API Kalit — bu ovoz uchun to'lov emas.** Bu — botingizning asosiy serverga ulanib, AI captcha yechish va barqaror ishlashi uchun kerakli yoqilg'i (xizmat to'lovi).

API kalitlarni **[@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot)** orqali xarid qilishingiz mumkin.

---

## 🗂️ Fayl Tuzilmasi

```
openbudget-uz-bot/
├── open_budget_client_bot.py   # Asosiy bot kodi
├── requirements.txt            # Python kutubxonalari
├── .env.example                # Sozlamalar namunasi
├── .gitignore                  # Git ignore qoidalari
├── README.md                   # Loyiha hujjati (bu fayl)
├── INSTALL.md                  # O'rnatish yo'riqnomasi
├── API.md                      # API hujjatlari
├── QOLLANMA.txt                # O'zbek tilidagi to'liq qo'llanma
└── LICENSE                     # MIT Litsenziya
```

---

## 🔍 Qidiruv Kalit So'zlari

Open Budget bot, Open Budget Uzbekistan, Open Budget 2026, Ochiq Budjet bot, Ochiq Budjet Telegram bot, O'zbekiston Open Budget, Open Budget API bot, Tashabbusli Budjet bot, openbudget.uz bot, Telegram bot source code Uzbekistan, openbudget-uz-bot, open budget bot kodi.

---

## 📝 Litsenziya

Ushbu loyiha [MIT](LICENSE) litsenziyasi ostida tarqatiladi.

---

<p align="center">Made with ❤️ for Open Budget Uzbekistan Developers · <a href="https://t.me/Budjetuz2026_bot">Demo: @Budjetuz2026_bot</a></p>
