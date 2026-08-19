# API Hujjatlari — Open Budget Uzbekistan Bot

Ushbu hujjat Open Budget bot tomonidan foydalaniladigan API endpointlarini tasvirlaydi.

> **Eslatma:** API kalitlari, tokenlar va maxfiy ma'lumotlarni hech qachon ommaviy repozitoriyaga qo'shmang.

---

## Asosiy Ma'lumot

- **Base URL**: https://openbudjet-production.up.railway.app/api/v1
- **Autentifikatsiya**: X-API-Key header orqali
- **Format**: JSON

---

## Endpointlar

### 1. Tariflar Ro'yxati

API kalit sotib olish uchun mavjud tariflarni ko'rsatadi.

`
GET /tariffs
`

**Headers:**
`
Content-Type: application/json
`

**Muvaffaqiyatli javob (200):**
`json
{
  "status": "ok",
  "tariffs": [
    {
      "votes": 100,
      "price": 50000
    },
    {
      "votes": 500,
      "price": 200000
    }
  ]
}
`

---

### 2. To'lov Statusini Tekshirish

`
GET /check-purchase/{purchase_id}
`

**Path parametrlari:**
| Parametr | Turi | Tavsif |
|----------|------|--------|
| purchase_id | integer | Xarid ID raqami |

**Muvaffaqiyatli javob (200) — To'lov tasdiqlandi:**
`json
{
  "status": "COMPLETED",
  "api_key": "ob_api_xxxxxxxxxxxxx",
  "votes_count": 100
}
`

**Kutilmoqda (200):**
`json
{
  "status": "PENDING"
}
`

**Bekor qilingan (200):**
`json
{
  "status": "CANCELLED"
}
`

---

### 3. API Kalitni Tekshirish

Kalitning haqiqiyligi va balansini tekshiradi.

`
GET /verify
`

**Headers:**
`
X-API-Key: ob_api_your_key_here
`

**Muvaffaqiyatli javob (200):**
`json
{
  "status": "ok",
  "votes_remaining": 75,
  "votes_total": 100
}
`

**Xato javob (401):**
`json
{
  "status": "error",
  "message": "API kalit topilmadi yoki faol emas"
}
`

---

### 4. Loyiha Ma'lumotlari

Loyiha ID bo'yicha tafsilotlarni qaytaradi.

`
GET /project/{project_id}
`

**Headers:**
`
X-API-Key: ob_api_your_key_here
`

**Path parametrlari:**
| Parametr | Turi | Tavsif |
|----------|------|--------|
| project_id | string | openbudget.uz dagi loyiha ID |

**Muvaffaqiyatli javob (200):**
`json
{
  "status": "ok",
  "project": {
    "id": "12345",
    "categoryName": "Muhit",
    "regionName": "Toshkent",
    "districtName": "Yunusobod",
    "description": "Ko'cha chirog'larini ta'mirlash",
    "votes": 142
  }
}
`

---

### 5. Ovoz Berish

Foydalanuvchi nomidan loyihaga ovoz beradi.

`
POST /vote
`

**Headers:**
`
X-API-Key: ob_api_your_key_here
Content-Type: application/json
`

**Request body:**
`json
{
  "project_id": "12345",
  "phone": "+998901234567"
}
`

**Muvaffaqiyatli javob (200):**
`json
{
  "status": "ok",
  "message": "Ovoz muvaffaqiyatli berildi"
}
`

**Xato javoblari:**

| HTTP kod | Tavsif |
|----------|--------|
| 400 | Noto'g'ri so'rov parametrlari |
| 401 | API kalit noto'g'ri yoki faol emas |
| 402 | Balansdagi ovozlar tugagan |
| 409 | Bu raqamdan ovoz allaqachon berilgan |
| 500 | Server xatosi |

---

## Xato Kodlari

| Kod | Ma'no |
|-----|-------|
| 200 | Muvaffaqiyatli |
| 400 | Noto'g'ri so'rov |
| 401 | Autentifikatsiya xatosi |
| 402 | Balans yetarli emas |
| 403 | Kirish taqiqlangan |
| 404 | Topilmadi |
| 409 | Conflict (duplikat) |
| 429 | Juda ko'p so'rov (Rate limit) |
| 500 | Server ichki xatosi |

---

## Xavfsizlik

- API kalitlarini .env faylida saqlang
- .env faylini .gitignore ga qo'shing
- Kalitni hech kimga bermang va GitHub'ga yuklamang
- Agar kalit tarqalib ketsa, darhol [@Budjetuz2026_Bot](https://t.me/Budjetuz2026_Bot) orqali yangi kalit oling
