# 🗳️ Open Budget Bot (Tashabbusli Budjet Ovoz Berish Boti) — v2.0

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/Aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram" alt="Aiogram 3" />
  <img src="https://img.shields.io/badge/SQLite-WAL_Database-003B57?style=for-the-badge&logo=sqlite" alt="SQLite" />
  <img src="https://img.shields.io/badge/Official_API-@Budjetuz2026__Bot-26A5E4?style=for-the-badge&logo=telegram" alt="Telegram Bot" />
</p>

---

## 📌 Loyiha Haqida (About Project)

Ushbu loyiha — O'zbekistondagi **Open Budget (Tashabbusli Budjet — openbudget.uz)** platformasi uchun tayyor, yuqori tezlikdagi va zamonaviy **Telegram Ovoz Berish Boti** shablonidir.

Bot o'zining ichki asinxron ma'lumotlar bazasiga (**aiosqlite + WAL mode**) ega bo'lib, alohida PostgreSQL yoki MySQL server talab qilmaydi. 

* 🤖 **Rasmiy API Gateway & Kalitlar Boti**: [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot)
* 🌐 **API Server**: `https://openbudjet-production.up.railway.app`
* 📚 **Batafsil Qo'llanma**: `QOLLANMA.txt` faylida

---

## ⚡ Asosiy Imkoniyatlar

- 🟢 **Rangli va Zamonaviy Tugmalar** (Telegram Bot API 9.4 native styles).
- 🧩 **Avtomatlashtirilgan Captcha va SMS integratsiyasi**.
- 💳 **O'rnatilgan Admin Panel (`/admin`)**:
  - API kalitni to'g'ridan-to'g'ri bot ichidan sotib olish va sozlash;
  - Ovoz yig'ilayotgan Loyiha ID sini o'rnatish;
  - Har bir ovoz uchun foydalanuvchiga to'lanadigan UZS mukofotini belgilash;
  - Foydalanuvchilarning pul yechish so'rovlarini (Uzcard/Humo) tasdiqlash yoki rad etish;
  - Barcha ovoz berganlar ro'yxatini hisobot (TXT) sifatida yuklab olish;
  - Barcha foydalanuvchilarga reklama va xabar tarqatish (Broadcast).

---

## 🚀 5 Daqiqada Ishga Tushirish (Quickstart)

### 1. Kerakli kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```
*(yoki `pip install aiogram aiohttp aiosqlite`)*

### 2. Sozlamalarni kiritish (.env yoki kod ichida)
`.env` fayl yarating yoki `open_budget_client_bot.py` faylining boshidagi o'zgaruvchilarni kiriting:
```env
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # @BotFather dan olingan token
ADMIN_ID=123456789                                    # Sizning Telegram ID raqamingiz
API_URL=https://openbudjet-production.up.railway.app/api/v1
```

### 3. Botni ishga tushirish
```bash
python open_budget_client_bot.py
```

### 4. API Kalitni ulash
1. Botingizga kiring va **/admin** buyrug'ini yuboring.
2. **"💳 API Kalit sotib olish"** tugmasini bosing yoki [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) botidan sotib olingan kalitni **"🔑 API Kalitni sozlash"** orqali kiriting.
3. **"📌 Loyiha IDni sozlash"** orqali o'z tashabbusingiz raqamini biriktiring.

Tabriklaymiz! Botingiz ovozlarni qabul qilishga to'liq tayyor! 🚀

---

## ☁️ Serverda 24/7 Ishga Tushirish

- **XUSS Hosting / cPanel / Beget**: Faylni yuklab, Terminalda `pip3 install aiogram aiohttp aiosqlite` buyrug'ini yozing va "Doimiy ishga tushirish"ni bosing.
- **Railway.app**: Ushbu GitHub repozitoriyani to'g'ridan-to'g'ri ulab, Variables bo'limiga `BOT_TOKEN` va `ADMIN_ID` ni qo'ying.
- **VPS / Ubuntu Linux**: `QOLLANMA.txt` faylidagi Systemd ko'rsatmalariga qarang.

---

## 🔑 API Kalit Olish

Open Budget tizimi orqali ovozlarni rasman qabul qilish uchun API kalitlarni [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) orqali xarid qilishingiz mumkin.

---
<p align="center">Made with ❤️ for Open Budget Uzbekistan Developers</p>
