"""
╔══════════════════════════════════════════════════════════╗
║       Open Budget Mijoz Boti  —  v2.0 Premium           ║
║  Muallif: Open Budget API xizmati uchun tayyorlangan     ║
╚══════════════════════════════════════════════════════════╝

.env fayl namunasi:
    BOT_TOKEN=7xxxxxxxxxx:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ADMIN_ID=123456789
    API_URL=https://openbudjet-production.up.railway.app/api/v1
    VOTE_COOLDOWN_HOURS=0

O'rnatish:
    pip install aiogram aiohttp
    python open_budget_client_bot.py
"""

import logging
import html
import asyncio
import os
import aiohttp
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional
import base64

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# ──────────────────────────────────────────────
#  LOGGER
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)s │ %(levelname)s │ %(message)s"
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  SOZLAMALAR (muhit o'zgaruvchilari)
# ──────────────────────────────────────────────
BOT_TOKEN           = os.getenv("BOT_TOKEN", "1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
ADMIN_ID            = int(os.getenv("ADMIN_ID", "0"))
API_URL             = os.getenv("API_URL", "https://openbudjet-production.up.railway.app/api/v1")
VOTE_COOLDOWN_HOURS = int(os.getenv("VOTE_COOLDOWN_HOURS", "0"))  # 0 = cheklovsiz

DB_PATH = os.getenv("DATABASE_PATH", "client_bot.db")

_http_session: aiohttp.ClientSession | None = None

async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        timeout = aiohttp.ClientTimeout(total=30)
        _http_session = aiohttp.ClientSession(timeout=timeout)
    return _http_session

# ══════════════════════════════════════════════
#  MA'LUMOTLAR BAZASI (Doimiy Connection Pooling)
# ══════════════════════════════════════════════

_db_conn: aiosqlite.Connection | None = None

async def get_db_conn() -> aiosqlite.Connection:
    global _db_conn
    if _db_conn is None:
        # Agar ma'lumotlar bazasi papkasi mavjud bo'lmasa, uni yaratamiz
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        _db_conn = await aiosqlite.connect(DB_PATH)
        await _db_conn.execute("PRAGMA journal_mode=WAL;")
        await _db_conn.execute("PRAGMA synchronous=NORMAL;")
        await _db_conn.execute("PRAGMA busy_timeout=5000;")
    return _db_conn

async def init_db():
    conn = await get_db_conn()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username    TEXT    DEFAULT '',
            full_name   TEXT    DEFAULT '',
            balance     INTEGER DEFAULT 0,
            votes_count INTEGER DEFAULT 0,
            is_blocked  INTEGER DEFAULT 0,
            joined_at   TEXT    NOT NULL
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS votes_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id  INTEGER NOT NULL,
            phone_number TEXT    NOT NULL,
            voted_at     TEXT    NOT NULL
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            amount      INTEGER NOT NULL,
            card_number TEXT    NOT NULL,
            status      TEXT    DEFAULT 'PENDING',
            created_at  TEXT    NOT NULL
        )
    """)

    defaults = [
        ("api_key",        ""),
        ("project_id",     ""),
        ("project_name",   ""),
        ("voter_reward",   "1000"),
        ("min_withdrawal", "5000"),
        ("voting_enabled", "1"),
    ]
    for k, v in defaults:
        await conn.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))

    await conn.commit()

# ──────────────────────────────────────────────
#  DB YORDAMCHI FUNKSIYALAR
# ──────────────────────────────────────────────

async def get_setting(key: str) -> str:
    conn = await get_db_conn()
    async with conn.execute("SELECT value FROM settings WHERE key=?", (key,)) as c:
        row = await c.fetchone()
    return row[0] if row else ""

async def set_setting(key: str, value: str):
    conn = await get_db_conn()
    await conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    await conn.commit()

# ─── Foydalanuvchilar ───

async def get_or_create_user(tid: int, username: str = "", full_name: str = "") -> tuple:
    conn = await get_db_conn()
    async with conn.execute(
        "SELECT telegram_id, username, full_name, balance, votes_count, is_blocked, joined_at "
        "FROM users WHERE telegram_id=?", (tid,)
    ) as c:
        row = await c.fetchone()
    
    if not row:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(
            "INSERT OR IGNORE INTO users (telegram_id,username,full_name,balance,votes_count,is_blocked,joined_at) "
            "VALUES (?,?,?,0,0,0,?)",
            (tid, username, full_name, now)
        )
        await conn.commit()
        async with conn.execute(
            "SELECT telegram_id, username, full_name, balance, votes_count, is_blocked, joined_at "
            "FROM users WHERE telegram_id=?", (tid,)
        ) as c:
            row = await c.fetchone()
    elif username and (row[1] != username or row[2] != full_name):
        await conn.execute("UPDATE users SET username=?,full_name=? WHERE telegram_id=?", (username, full_name, tid))
        await conn.commit()
    return row

async def get_user(tid: int) -> Optional[tuple]:
    conn = await get_db_conn()
    async with conn.execute(
        "SELECT telegram_id, username, full_name, balance, votes_count, is_blocked, joined_at "
        "FROM users WHERE telegram_id=?", (tid,)
    ) as c:
        row = await c.fetchone()
    return row

async def get_all_users() -> list:
    conn = await get_db_conn()
    async with conn.execute(
        "SELECT telegram_id, username, full_name, balance, votes_count "
        "FROM users ORDER BY votes_count DESC"
    ) as c:
        rows = await c.fetchall()
    return rows

async def get_total_users() -> int:
    conn = await get_db_conn()
    async with conn.execute("SELECT COUNT(*) FROM users") as c:
        row = await c.fetchone()
        n = row[0] if row else 0
    return n

async def set_user_blocked(tid: int, block: bool):
    conn = await get_db_conn()
    await conn.execute("UPDATE users SET is_blocked=? WHERE telegram_id=?", (1 if block else 0, tid))
    await conn.commit()

# ─── Ovozlar ───

async def get_total_votes() -> int:
    conn = await get_db_conn()
    async with conn.execute("SELECT COUNT(*) FROM votes_history") as c:
        row = await c.fetchone()
        n = row[0] if row else 0
    return n

async def get_today_votes() -> int:
    conn = await get_db_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    async with conn.execute("SELECT COUNT(*) FROM votes_history WHERE voted_at LIKE ?", (f"{today}%",)) as c:
        row = await c.fetchone()
        n = row[0] if row else 0
    return n

async def get_user_last_vote(tid: int) -> Optional[datetime]:
    conn = await get_db_conn()
    async with conn.execute("SELECT voted_at FROM votes_history WHERE telegram_id=? ORDER BY id DESC LIMIT 1", (tid,)) as c:
        row = await c.fetchone()
    return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") if row else None

async def get_user_votes_history(tid: int) -> list:
    conn = await get_db_conn()
    async with conn.execute(
        "SELECT phone_number, voted_at FROM votes_history "
        "WHERE telegram_id=? ORDER BY id DESC LIMIT 10", (tid,)
    ) as c:
        rows = await c.fetchall()
    return rows

async def get_all_votes_history() -> list:
    conn = await get_db_conn()
    async with conn.execute("SELECT phone_number, voted_at FROM votes_history ORDER BY id DESC") as c:
        rows = await c.fetchall()
    return rows

async def add_vote(tid: int, phone: str, reward: int):
    conn = await get_db_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        "INSERT INTO votes_history (telegram_id,phone_number,voted_at) VALUES (?,?,?)",
        (tid, phone, now)
    )
    await conn.execute(
        "UPDATE users SET balance=balance+?, votes_count=votes_count+1 WHERE telegram_id=?",
        (reward, tid)
    )
    await conn.commit()

# ─── Pul yechish ───

async def get_total_paid() -> int:
    conn = await get_db_conn()
    async with conn.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='APPROVED'") as c:
        row = await c.fetchone()
        n = row[0] if row else 0
    return n

async def create_withdrawal(tid: int, amount: int, card: str) -> int:
    conn = await get_db_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 1. Balansni atomik tarzda tekshirib yechamiz (Race Condition va Double-Spend oldi olinadi)
    async with conn.execute(
        "UPDATE users SET balance = balance - ? WHERE telegram_id = ? AND balance >= ?",
        (amount, tid, amount)
    ) as c:
        if c.rowcount == 0:
            return 0
    # 2. Yechish so'rovini bazaga saqlaymiz
    async with conn.execute(
        "INSERT INTO withdrawals (telegram_id,amount,card_number,status,created_at) VALUES (?,?,?,'PENDING',?)",
        (tid, amount, card, now)
    ) as c:
        lid = c.lastrowid
    await conn.commit()
    return lid

async def get_pending_withdrawals() -> list:
    conn = await get_db_conn()
    async with conn.execute(
        "SELECT id, telegram_id, amount, card_number, created_at "
        "FROM withdrawals WHERE status='PENDING' ORDER BY id ASC"
    ) as c:
        rows = await c.fetchall()
    return rows

async def process_withdrawal(wd_id: int, approve: bool) -> tuple:
    conn = await get_db_conn()
    new_status = "APPROVED" if approve else "REJECTED"
    # Atomik UPDATE orqali bir necha marta bosilganda ikki marta pul qaytarish (Double Refund) oldi olinadi
    async with conn.execute(
        "UPDATE withdrawals SET status=? WHERE id=? AND status='PENDING' RETURNING telegram_id, amount",
        (new_status, wd_id)
    ) as c:
        row = await c.fetchone()
    if not row:
        return False, 0, 0
    tid, amount = row
    if not approve:
        await conn.execute("UPDATE users SET balance=balance+? WHERE telegram_id=?", (amount, tid))
    await conn.commit()
    return True, tid, amount

# ══════════════════════════════════════════════
#  REGION VA TUMANLAR (STATIK MA'LUMOT)
# ══════════════════════════════════════════════

REGIONS = [
    {"id": 2, "name": "Қорақалпоғистон Республикаси", "short_name": "Қорақалпоғистон Республикаси"},
    {"id": 3, "name": "Андижон вилояти", "short_name": "Андижон вилояти"},
    {"id": 13, "name": "Бухоро вилояти", "short_name": "Бухоро вилояти"},
    {"id": 4, "name": "Жиззах вилояти", "short_name": "Жиззах вилояти"},
    {"id": 5, "name": "Қашқадарё вилояти", "short_name": "Қашқадарё вилояти"},
    {"id": 6, "name": "Навоий вилояти", "short_name": "Навоий вилояти"},
    {"id": 7, "name": "Наманган вилояти", "short_name": "Наманган вилояти"},
    {"id": 8, "name": "Самарқанд вилояти", "short_name": "Самарқанд вилояти"},
    {"id": 9, "name": "Сурхондарё вилояти", "short_name": "Сурхондарё вилояти"},
    {"id": 10, "name": "Сирдарё вилояти", "short_name": "Сирдарё вилояти"},
    {"id": 14, "name": "Тошкент вилояти", "short_name": "Тошкент вилояти"},
    {"id": 11, "name": "Фарғона вилояти", "short_name": "Фарғона вилояти"},
    {"id": 12, "name": "Хоразм вилояти", "short_name": "Хоразм вилояти"},
    {"id": 1, "name": "Тошкент шаҳри", "short_name": "Тошкент шаҳри"}
]

DISTRICTS = {
    2: [{"id": 23, "name": "Амударё тумани"}, {"id": 12, "name": "Беруний тумани"}, {"id": 209, "name": "Бўзатов тумани"}, {"id": 15, "name": "Кегейли тумани"}, {"id": 13, "name": "Қонликўл тумани"}, {"id": 14, "name": "Қораўзак тумани"}, {"id": 16, "name": "Қўнғирот тумани"}, {"id": 24, "name": "Мўйноқ тумани"}, {"id": 25, "name": "Нукус тумани"}, {"id": 11, "name": "Нукус шаҳри"}, {"id": 17, "name": "Тахиатош тумани"}, {"id": 18, "name": "Тахтакўпир тумани"}, {"id": 19, "name": "Тўрткўл тумани"}, {"id": 20, "name": "Хўжайли тумани"}, {"id": 21, "name": "Чимбой тумани"}, {"id": 22, "name": "Шуманай тумани"}, {"id": 210, "name": "Элликқалъа тумани"}],
    3: [{"id": 29, "name": "Андижон тумани"}, {"id": 26, "name": "Андижон шаҳри"}, {"id": 39, "name": "Асака тумани"}, {"id": 30, "name": "Балиқчи тумани"}, {"id": 32, "name": "Булоқбоши тумани"}, {"id": 31, "name": "Бўстон тумани"}, {"id": 40, "name": "Жалақудуқ тумани"}, {"id": 33, "name": "Избоскан тумани"}, {"id": 34, "name": "Қўрғонтепа тумани"}, {"id": 35, "name": "Марҳамат тумани"}, {"id": 36, "name": "Олтинкўл тумани"}, {"id": 37, "name": "Пахтаобод тумани"}, {"id": 38, "name": "Улуғнор тумани"}, {"id": 27, "name": "Хонобод шаҳри"}, {"id": 41, "name": "Хўжаобод тумани"}, {"id": 28, "name": "Шаҳрихон тумани"}],
    13: [{"id": 171, "name": "Бухоро тумани"}, {"id": 176, "name": "Бухоро шаҳри"}, {"id": 170, "name": "Вобкент тумани"}, {"id": 169, "name": "Ғиждувон тумани"}, {"id": 168, "name": "Жондор тумани"}, {"id": 167, "name": "Когон тумани"}, {"id": 175, "name": "Когон шаҳри"}, {"id": 166, "name": "Қоракўл тумани"}, {"id": 165, "name": "Қоровулбозор тумани"}, {"id": 172, "name": "Олот тумани"}, {"id": 173, "name": "Пешку тумани"}, {"id": 174, "name": "Ромитан тумани"}, {"id": 177, "name": "Шофиркон тумани"}],
    4: [{"id": 43, "name": "Арнасой тумани"}, {"id": 44, "name": "Бахмал тумани"}, {"id": 45, "name": "Ғаллаорол тумани"}, {"id": 54, "name": "Дўстлик тумани"}, {"id": 42, "name": "Жиззах шаҳри"}, {"id": 48, "name": "Зарбдор тумани"}, {"id": 49, "name": "Зафаробод тумани"}, {"id": 47, "name": "Зомин тумани"}, {"id": 50, "name": "Мирзачўл тумани"}, {"id": 51, "name": "Пахтакор тумани"}, {"id": 52, "name": "Фориш тумани"}, {"id": 53, "name": "Янгиобод тумани"}, {"id": 46, "name": "Шароф Рашидов тумани"}],
    5: [{"id": 56, "name": "Ғузор тумани"}, {"id": 57, "name": "Деҳқонобод тумани"}, {"id": 60, "name": "Касби тумани"}, {"id": 61, "name": "Китоб тумани"}, {"id": 68, "name": "Косон тумани"}, {"id": 214, "name": "Кўкдала тумани"}, {"id": 58, "name": "Қамаши тумани"}, {"id": 59, "name": "Қарши тумани"}, {"id": 55, "name": "Қарши шаҳри"}, {"id": 62, "name": "Миришкор тумани"}, {"id": 63, "name": "Муборак тумани"}, {"id": 64, "name": "Нишон тумани"}, {"id": 65, "name": "Чироқчи тумани"}, {"id": 66, "name": "Шаҳрисабз тумани"}, {"id": 69, "name": "Шаҳрисабз шаҳри"}, {"id": 67, "name": "Яккабоғ тумани"}],
    6: [{"id": 70, "name": "Ғозғон шаҳри"}, {"id": 71, "name": "Зарафшон шаҳри"}, {"id": 74, "name": "Кармана тумани"}, {"id": 73, "name": "Конимех тумани"}, {"id": 75, "name": "Қизилтепа тумани"}, {"id": 76, "name": "Навбаҳор тумани"}, {"id": 72, "name": "Навоий шаҳри"}, {"id": 77, "name": "Нурота тумани"}, {"id": 78, "name": "Томди тумани"}, {"id": 79, "name": "Учқудуқ тумани"}, {"id": 80, "name": "Хатирчи тумани"}],
    7: [{"id": 213, "name": "Давлатобод тумани"}, {"id": 83, "name": "Косонсой тумани"}, {"id": 85, "name": "Мингбулоқ тумани"}, {"id": 86, "name": "Наманган тумани"}, {"id": 81, "name": "Наманган шаҳри"}, {"id": 87, "name": "Норин тумани"}, {"id": 88, "name": "Поп тумани"}, {"id": 89, "name": "Тўрақўрғон тумани"}, {"id": 90, "name": "Уйчи тумани"}, {"id": 91, "name": "Учқўрғон тумани"}, {"id": 92, "name": "Чортоқ тумани"}, {"id": 93, "name": "Чуст тумани"}, {"id": 84, "name": "Янги Наманган тумани"}],
    8: [{"id": 107, "name": "Булунғур тумани"}, {"id": 101, "name": "Жомбой тумани"}, {"id": 100, "name": "Иштихон тумани"}, {"id": 106, "name": "Каттақўрғон тумани"}, {"id": 108, "name": "Каттақўрғон шаҳри"}, {"id": 99, "name": "Қўшрабод тумани"}, {"id": 103, "name": "Нарпай тумани"}, {"id": 105, "name": "Нуробод тумани"}, {"id": 95, "name": "Оқдарё тумани"}, {"id": 96, "name": "Пайариқ тумани"}, {"id": 97, "name": "Пастдарғом тумани"}, {"id": 98, "name": "Пахтачи тумани"}, {"id": 104, "name": "Самарқанд тумани"}, {"id": 94, "name": "Самарқанд шаҳри"}, {"id": 102, "name": "Тайлоқ тумани"}, {"id": 109, "name": "Ургут тумани"}],
    9: [{"id": 122, "name": "Ангор тумани"}, {"id": 207, "name": "Бандихон тумани"}, {"id": 118, "name": "Бойсун тумани"}, {"id": 117, "name": "Денов тумани"}, {"id": 116, "name": "Жарқўрғон тумани"}, {"id": 115, "name": "Қизириқ тумани"}, {"id": 114, "name": "Қумқўрғон тумани"}, {"id": 113, "name": "Музработ тумани"}, {"id": 119, "name": "Олтинсой тумани"}, {"id": 120, "name": "Сариосиё тумани"}, {"id": 110, "name": "Термиз тумани"}, {"id": 111, "name": "Термиз шаҳри"}, {"id": 121, "name": "Узун тумани"}, {"id": 112, "name": "Шерабод тумани"}, {"id": 123, "name": "Шўрчи тумани"}],
    10: [{"id": 128, "name": "Боёвут тумани"}, {"id": 127, "name": "Гулистон тумани"}, {"id": 133, "name": "Гулистон шаҳри"}, {"id": 126, "name": "Мирзаобод тумани"}, {"id": 129, "name": "Оқолтин тумани"}, {"id": 130, "name": "Сардоба тумани"}, {"id": 125, "name": "Сирдарё тумани"}, {"id": 131, "name": "Ховос тумани"}, {"id": 132, "name": "Ширин шаҳри"}, {"id": 124, "name": "Янгиер шаҳри"}],
    14: [{"id": 180, "name": "Ангрен шаҳри"}, {"id": 184, "name": "Бекобод тумани"}, {"id": 181, "name": "Бекобод шаҳри"}, {"id": 185, "name": "Бўка тумани"}, {"id": 195, "name": "Бўстонлиқ тумани"}, {"id": 196, "name": "Зангиота тумани"}, {"id": 186, "name": "Қибрай тумани"}, {"id": 187, "name": "Қуйичирчиқ тумани"}, {"id": 197, "name": "Нурафшон шаҳри"}, {"id": 188, "name": "Оққўрғон тумани"}, {"id": 189, "name": "Оҳангарон тумани"}, {"id": 182, "name": "Оҳангарон шаҳри"}, {"id": 190, "name": "Паркент тумани"}, {"id": 191, "name": "Пискент тумани"}, {"id": 192, "name": "Тошкент тумани"}, {"id": 193, "name": "Ўртачирчиқ тумани"}, {"id": 194, "name": "Чиноз тумани"}, {"id": 183, "name": "Чирчиқ шаҳри"}, {"id": 208, "name": "Юқоричирчиқ тумани"}],
    11: [{"id": 134, "name": "Бешариқ тумани"}, {"id": 135, "name": "Боғдод тумани"}, {"id": 151, "name": "Бувайда тумани"}, {"id": 150, "name": "Данғара тумани"}, {"id": 140, "name": "Ёзёвон тумани"}, {"id": 152, "name": "Қувасой шаҳри"}, {"id": 149, "name": "Қува тумани"}, {"id": 139, "name": "Қўқон шаҳри"}, {"id": 148, "name": "Қўштепа тумани"}, {"id": 138, "name": "Марғилон шаҳри"}, {"id": 141, "name": "Олтиариқ тумани"}, {"id": 147, "name": "Риштон тумани"}, {"id": 142, "name": "Сўх тумани"}, {"id": 143, "name": "Тошлоқ тумани"}, {"id": 144, "name": "Учкўприк тумани"}, {"id": 145, "name": "Фарғона тумани"}, {"id": 137, "name": "Фарғона шаҳри"}, {"id": 146, "name": "Фурқат тумани"}],
    12: [{"id": 162, "name": "Боғот тумани"}, {"id": 161, "name": "Гурлан тумани"}, {"id": 160, "name": "Қўшкўпир тумани"}, {"id": 159, "name": "Урганч тумани"}, {"id": 153, "name": "Урганч шаҳри"}, {"id": 158, "name": "Хазорасп тумани"}, {"id": 157, "name": "Хива тумани"}, {"id": 154, "name": "Хива шаҳри"}, {"id": 156, "name": "Хонқа тумани"}, {"id": 163, "name": "Шовот тумани"}, {"id": 164, "name": "Янгиариқ тумани"}, {"id": 155, "name": "Янгибозор тумани"}, {"id": 211, "name": "Тупроққалъа тумани"}],
    1: [{"id": 1, "name": "Бектемир тумани"}, {"id": 198, "name": "Мирзо Улуғбек тумани"}, {"id": 9, "name": "Миробод тумани"}, {"id": 8, "name": "Олмазор тумани"}, {"id": 6, "name": "Сергели тумани"}, {"id": 4, "name": "Учтепа тумани"}, {"id": 3, "name": "Чилонзор тумани"}, {"id": 5, "name": "Шайхонтоҳур тумани"}, {"id": 7, "name": "Юнусобод тумани"}, {"id": 2, "name": "Яккасарой тумани"}, {"id": 10, "name": "Яшнобод тумани"}, {"id": 212, "name": "Янгиҳаёт тумани"}]
}

# ══════════════════════════════════════════════
#  BOT & ROUTER
# ══════════════════════════════════════════════

bot    = Bot(token=BOT_TOKEN)
dp     = Dispatcher(storage=MemoryStorage())
router = Router()

# ──────────────────────────────────────────────
#  FSM HOLATLARI
# ──────────────────────────────────────────────

class VoteStates(StatesGroup):
    PHONE      = State()
    CAPTCHA_1  = State()
    SMS        = State()
    CAPTCHA_2  = State()
    # Ro'yxatdan o'tish
    REG_NAME     = State()
    REG_BIRTHDAY = State()
    REG_GENDER   = State()
    REG_REGION   = State()
    REG_DISTRICT = State()
    REG_CAPTCHA  = State()
    REG_SMS      = State()

class AdminStates(StatesGroup):
    SET_API_KEY   = State()
    SET_PROJECT   = State()
    SET_REWARD    = State()
    SET_MIN_WD    = State()
    BROADCAST     = State()
    CUSTOM_TARIFF = State()
    TOPUP_VOTES   = State()

class WithdrawStates(StatesGroup):
    CARD   = State()
    AMOUNT = State()

# ══════════════════════════════════════════════
#  API ULANISH
# ══════════════════════════════════════════════

async def call_api(
    endpoint: str,
    method: str = "POST",
    json_data: dict = None,
    api_key_override: str = None
) -> tuple[dict, int]:
    api_key = api_key_override or await get_setting("api_key")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    url = f"{API_URL.rstrip('/')}/{endpoint.lstrip('/')}"

    session = await get_http_session()
    try:
        if method.upper() == "GET":
            async with session.get(url, headers=headers) as r:
                return await r.json(), r.status
        else:
            async with session.post(url, headers=headers, json=json_data) as r:
                return await r.json(), r.status
    except asyncio.TimeoutError:
        return {"detail": "Server javob bermadi (timeout). Keyinroq urinib ko'ring."}, 504
    except Exception as e:
        logger.error(f"API xato: {e}")
        return {"detail": "Server bilan ulanib bo'lmadi."}, 502

async def validate_api_key(key: str) -> tuple[bool, str]:
    """API kalitni serverda real tekshiradi."""
    res, status = await call_api("/boards", "GET", api_key_override=key)
    if   status == 200: return True,  "✅ API kalit muvaffaqiyatli tasdiqlandi!"
    elif status == 401: return False, "❌ Noto'g'ri API kalit — yaroqsiz yoki mavjud emas."
    elif status == 402: return False, "⚠️ API kalit balansi yetarli emas! Admin panelidan to'ldiring."
    elif status == 403: return False, "🚫 API kalit bloklangan."
    elif status == 0:   return False, "🔌 API manzili bilan ulanib bo'lmadi."
    else:               return False, f"❌ Server xatosi (HTTP {status}). Keyinroq urinib ko'ring."

# ══════════════════════════════════════════════
#  KLABYATURALAR (KEYBOARDS)
# ══════════════════════════════════════════════

def kb_regions() -> InlineKeyboardMarkup:
    buttons = []
    for r in REGIONS:
        buttons.append([InlineKeyboardButton(text=r["name"], callback_data=f"reg_reg_{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_districts(region_id: int) -> InlineKeyboardMarkup:
    buttons = []
    districts = DISTRICTS.get(region_id, [])
    for d in districts:
        buttons.append([InlineKeyboardButton(text=d["name"], callback_data=f"reg_dist_{region_id}_{d['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_gender() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨 Erkak", callback_data="reg_gender_M"),
        InlineKeyboardButton(text="👩 Ayol", callback_data="reg_gender_F"),
    ]])

def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡ OVOZ BERISH 🗳️", style="success")],
        [
            KeyboardButton(text="💎 Mening hisobim", style="primary"),
            KeyboardButton(text="📋 Ovozlar tarixim", style="primary"),
        ],
    ], resize_keyboard=True, is_persistent=True)

def kb_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Telefon raqamni ulashish", request_contact=True, style="success")],
        [KeyboardButton(text="🔙 Orqaga qaytish", style="danger")],
    ], resize_keyboard=True, is_persistent=True)

def kb_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Bekor qilish", style="danger")],
    ], resize_keyboard=True, is_persistent=True)

async def kb_admin() -> ReplyKeyboardMarkup:
    pending_count = len(await get_pending_withdrawals())
    wd_badge      = f" ({pending_count})" if pending_count > 0 else ""
    voting_on     = await get_setting("voting_enabled") == "1"
    toggle_text   = "🟢 Ovoz berish: YOQIQ" if voting_on else "🔴 Ovoz berish: O'CHIQ"
    toggle_style  = "success" if voting_on else "danger"
    has_key       = bool(await get_setting("api_key"))

    key_btn1 = "💳 API Balansini to'ldirish ⚡" if has_key else "💳 API Kalit sotib olish ✨"
    key_btn2 = "🔑 API Kalit sozlamalari 🛠️" if has_key else "🔑 API Kalitni ulash 🛠️"

    return ReplyKeyboardMarkup(keyboard=[
        [
            KeyboardButton(text=key_btn1, style="success"),
            KeyboardButton(text=key_btn2, style="primary"),
        ],
        [
            KeyboardButton(text="📌 Loyiha IDni sozlash 🎯", style="primary"),
            KeyboardButton(text=toggle_text, style=toggle_style),
        ],
        [
            KeyboardButton(text="💰 Mukofot", style="primary"),
            KeyboardButton(text="💳 Min. yechish", style="primary"),
        ],
        [
            KeyboardButton(text=f"💸 Yechish so'rovlari{wd_badge}", style="danger" if pending_count > 0 else "primary"),
            KeyboardButton(text="👥 Foydalanuvchilar ro'yxati", style="primary"),
        ],
        [
            KeyboardButton(text="📊 Hisobot (TXT fayl)", style="primary"),
            KeyboardButton(text="📢 Broadcast (Xabar tarqatish)", style="primary"),
        ],
        [
            KeyboardButton(text="✖️ Yopish", style="danger"),
        ],
    ], resize_keyboard=True, is_persistent=True)

def kb_wd_action(wd_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_app_{wd_id}", style="success"),
        InlineKeyboardButton(text="❌ Rad etish",  callback_data=f"adm_rej_{wd_id}", style="danger"),
    ]])

def kb_user_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ 🗳️ Ovoz berish 🗳️ ⚡", callback_data="u_vote", style="success")],
        [
            InlineKeyboardButton(text="💎 Mening hisobim", callback_data="u_balance", style="primary"),
            InlineKeyboardButton(text="📋 Ovozlar tarixim", callback_data="u_history", style="primary"),
        ],
        [InlineKeyboardButton(text="👤 Profilim", callback_data="u_profile", style="primary")]
    ])

def kb_balance(show_wd: bool) -> Optional[InlineKeyboardMarkup]:
    if not show_wd:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💸  Pulni kartaga yechib olish 💳", callback_data="user_withdraw", style="success"),
    ]])

def kb_users_nav(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_users_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page + 1} / {total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_users_{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        nav,
        [InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back")],
    ])

# ──────────────────────────────────────────────
#  ADMIN PANEL MATNI
# ──────────────────────────────────────────────

async def admin_panel_text() -> str:
    api_key      = await get_setting("api_key")
    project_id   = await get_setting("project_id")
    project_name = await get_setting("project_name")
    reward       = int(await get_setting("voter_reward") or 1000)
    min_wd       = int(await get_setting("min_withdrawal") or 5000)
    voting_on    = await get_setting("voting_enabled") == "1"

    total_users  = await get_total_users()
    total_votes  = await get_total_votes()
    today_votes  = await get_today_votes()
    total_paid   = await get_total_paid()
    pending_wds  = len(await get_pending_withdrawals())

    api_display  = (
        f"<code>{api_key[:11]}...{api_key[-4:]}</code>"
        if len(api_key) > 15 else (f"<code>{api_key}</code>" if api_key else "❌ Kiritilmagan")
    )
    
    votes_info = ""
    if api_key:
        try:
            res_k, status_k = await call_api("/key-info", "GET")
            if status_k == 200 and "votes_remaining" in res_k:
                rem = res_k["votes_remaining"]
                bal = res_k.get("balance_uzs", 0)
                votes_info = f"\n⚡ <b>Ovoz limiti:</b>   <b>{rem:,} ta ovoz</b> qoldi (Balans: {bal:,} UZS)"
            elif status_k == 401:
                votes_info = "\n⚠️ <b>Kalit holati:</b>   ❌ Yaroqsiz yoki topilmadi"
        except Exception:
            pass

    proj_display = project_name or project_id or "❌ Kiritilmagan"
    vote_status  = "🟢 Yoqiq" if voting_on else "🔴 O'chirilgan"

    return (
        "⚙️ <b>Admin Boshqaruv Paneli</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>API Kalit:</b>    {api_display}{votes_info}\n"
        f"📌 <b>Loyiha:</b>       <b>{proj_display}</b>\n"
        f"💰 <b>Mukofot:</b>      <b>{reward:,} UZS</b> / ovoz\n"
        f"💳 <b>Min. yechish:</b> <b>{min_wd:,} UZS</b>\n"
        f"🗳️ <b>Ovoz berish:</b>  {vote_status}\n\n"
        "📊 <b>Statistika</b>\n"
        "────────────────────────────\n"
        f"👥 Foydalanuvchilar:  <b>{total_users:,} ta</b>\n"
        f"🗳️ Jami ovozlar:     <b>{total_votes:,} ta</b>\n"
        f"📅 Bugun:             <b>{today_votes} ta</b>\n"
        f"💸 To'langan:         <b>{total_paid:,} UZS</b>\n"
        f"⏳ Kutilayotgan:      <b>{pending_wds} ta yechish so'rovi</b>"
    )

# ──────────────────────────────────────────────
#  GUARD FUNKSIYALAR
# ──────────────────────────────────────────────

async def bot_is_ready() -> bool:
    return bool(await get_setting("api_key")) and bool(await get_setting("project_id"))

async def voting_is_enabled() -> bool:
    return await get_setting("voting_enabled") == "1"

async def user_is_blocked(tid: int) -> bool:
    u = await get_user(tid)
    return u is not None and u[5] == 1

# ══════════════════════════════════════════════
#  HANDLERLAR
# ══════════════════════════════════════════════

# ──────────────────────────────────────────────
#  /start  /help
# ──────────────────────────────────────────────

@router.message(CommandStart(), StateFilter("*"))
@router.message(Command("start", "help"), StateFilter("*"))
@router.message(F.text.startswith("/start"), StateFilter("*"))
@router.message(F.text.startswith("/help"), StateFilter("*"))
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    u = msg.from_user

    # Foydalanuvchi bazada mavjudligini tekshiramiz
    conn = await get_db_conn()
    async with conn.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (u.id,)) as c:
        is_existing = await c.fetchone() is not None

    await get_or_create_user(u.id, u.username or "", u.full_name or "")

    if await user_is_blocked(u.id):
        return await msg.answer("⛔ <b>Sizning hisobingiz bloklangan.</b>", parse_mode="HTML")

    admin_note = ""
    if u.id == ADMIN_ID:
        api_key = await get_setting("api_key")
        project_id = await get_setting("project_id")
        if not api_key:
            admin_note = "\n\n<i>⚠️ Eslatma (Admin): API kalit ulanmagan. /admin orqali sozlang.</i>"
        elif not project_id:
            admin_note = "\n\n<i>⚠️ Eslatma (Admin): Loyiha ID sozlanmagan. /admin orqali sozlang.</i>"

    welcome_status = "Qayta tashrifingizdan xursandmiz." if is_existing else "Xush kelibsiz!"

    await msg.answer(
        f"🗳️ <b>Open Budget — Ovoz Berish Tizimi</b>\n\n"
        f"Assalomu alaykum, <b>{html.escape(str(u.first_name))}</b>!\n\n"
        f"{welcome_status}\n"
        f"👇 Boshlash uchun quyidagi menyudan tanlang:{admin_note}",
        reply_markup=kb_main(),
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────
#  /admin
# ──────────────────────────────────────────────

@router.message(Command("admin"), StateFilter("*"))
@router.message(F.text.startswith("/admin"), StateFilter("*"))
async def cmd_admin(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")

# ─── Admin panel — matnli tugmalar (ReplyKeyboard) ───

@router.message(StateFilter(None), F.text, F.from_user.id == ADMIN_ID)
async def admin_menu_handler(msg: Message, state: FSMContext):
    text = msg.text.strip()
    
    if "API Balansini to'ldirish" in text:
        api_key = await get_setting("api_key")
        if api_key:
            display_key = f"{api_key[:11]}...{api_key[-4:]}" if len(api_key) > 15 else api_key
            res_k, status_k = await call_api("/key-info", "GET")
            rem = res_k.get("votes_remaining", 0) if status_k == 200 else 0
            
            await state.set_state(AdminStates.TOPUP_VOTES)
            await msg.answer(
                f"⚡ <b>API Kalit balansini to'ldirish</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔑 <b>Mavjud kalit:</b> <code>{display_key}</code>\n"
                f"📊 <b>Joriy qolgan ovozlar:</b> <b>{rem:,} ta ovoz</b>\n\n"
                f"✍️ <b>Nechta ovoz qo'shmoqchisiz?</b>\n"
                f"• Masalan: <code>50</code>, <code>100</code>, <code>250</code>, <code>500</code>\n"
                f"• Narx: 1 ta ovoz = <b>1,000 UZS</b>\n\n"
                f"<i>Qo'shiladigan ovozlar sonini yozib yuboring (kamida 10 ta):</i>",
                reply_markup=kb_cancel(),
                parse_mode="HTML"
            )
        else:
            loading = await msg.answer("🔄 <b>Tariflar serverdan yuklanmoqda...</b>", parse_mode="HTML")
            res, status = await call_api("/tariffs", "GET")
            await loading.delete()
            
            if status != 200 or "tariffs" not in res:
                return await msg.answer(
                    "❌ Tariflar ro'yxatini yuklab bo'lmadi. Keyinroq urinib ko'ring.",
                    parse_mode="HTML"
                )
                
            tariffs = res.get("tariffs", [])
            buttons = [
                [InlineKeyboardButton(text="✍️ Boshqa miqdor (O'zim kiritaman)", callback_data="adm_custom_tariff", style="success")]
            ]
            for t in tariffs:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"📦 {t['votes']} ta Ovoz — {t['price']:,} UZS",
                        callback_data=f"adm_tariff_{t['votes']}",
                        style="primary"
                    )
                ])
            buttons.append([InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back", style="danger")])
            await msg.answer(
                "💳 <b>API Kalit sotib olish</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Botingiz uchun kerakli ovoz limitiga mos tarifni tanlang yoki o'zingiz xohlagan miqdorni kiriting:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )

    elif "API Kalit sotib olish" in text:
        loading = await msg.answer("🔄 <b>Tariflar serverdan yuklanmoqda...</b>", parse_mode="HTML")
        res, status = await call_api("/tariffs", "GET")
        await loading.delete()
        
        if status != 200 or "tariffs" not in res:
            return await msg.answer(
                "❌ Tariflar ro'yxatini yuklab bo'lmadi. Keyinroq urinib ko'ring.",
                parse_mode="HTML"
            )
            
        tariffs = res.get("tariffs", [])
        if not tariffs:
            return await msg.answer("Hozircha faol tariflar mavjud emas.", parse_mode="HTML")
            
        buttons = [
            [InlineKeyboardButton(text="✍️ Boshqa miqdor (O'zim kiritaman)", callback_data="adm_custom_tariff", style="success")]
        ]
        for t in tariffs:
            buttons.append([
                InlineKeyboardButton(
                    text=f"📦 {t['votes']} ta Ovoz — {t['price']:,} UZS",
                    callback_data=f"adm_tariff_{t['votes']}",
                    style="primary"
                )
            ])
        buttons.append([InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back", style="danger")])
        await msg.answer(
            "💳 <b>API Kalit sotib olish</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔑 <b>API Kalit nima?</b>\n"
            "Bu botingiz asosiy serverga ulanib, <b>captchalarni sun'iy intellekt (AI) yordamida avtomatik yechishi</b> va barqaror ishlashi uchun kerakli balans (yoqilg'i) hisoblanadi.\n\n"
            "⚠️ <b>Muhim eslatma:</b> Ushbu tariflar odamlar yig'gan ovozi uchun to'lanadigan mukofot puli emas! Bu botingiz serverga ulanib ishlashi uchun ketadigan sarf-xarajat to'lovidir.\n\n"
            "Botingiz uchun kerakli ovoz limitiga mos tarifni tanlang yoki o'zingiz xohlagan miqdorni kiriting:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )

    elif "API Kalit" in text:
        api_key = await get_setting("api_key")
        if api_key:
            text_card, kb_card = await get_api_key_info_card(api_key)
            await msg.answer(text_card, reply_markup=kb_card, parse_mode="HTML")
        else:
            await state.set_state(AdminStates.SET_API_KEY)
            await msg.answer(
                "🔑 <b>Asosiy botdan sotib olgan API kalitingizni yuboring:</b>\n\n"
                "• Kalit <code>ob_api_</code> bilan boshlanishi shart\n"
                "• Kiritilgandan so'ng server bilan <b>avtomatik tekshiriladi</b>",
                reply_markup=kb_cancel(), parse_mode="HTML"
            )

    elif "Loyiha IDni sozlash" in text:
        api_key = await get_setting("api_key")
        if not api_key:
            return await msg.answer("⚠️ Avval API kalitni ulashingiz shart!")
            
        cur_id = await get_setting("project_id")
        cur_name = await get_setting("project_name")
        
        if cur_id:
            buttons = [
                [InlineKeyboardButton(text="✏️ Yangi ID kiritish (Almashtirish)", callback_data="adm_change_project", style="primary")],
                [InlineKeyboardButton(text="🗑️ Faol Loyihani o'chirish", callback_data="adm_delete_project", style="danger")],
                [InlineKeyboardButton(text="✖️ Yopish", callback_data="adm_close_prompt", style="secondary")]
            ]
            await msg.answer(
                f"📌 <b>Loyiha Sozlamalari</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🔹 <b>Hozirgi faol loyiha:</b>\n"
                f"🆔 <b>ID:</b> <code>{cur_id}</code>\n"
                f"📋 <b>Nomi:</b> <b>{cur_name or cur_id}</b>\n\n"
                f"ℹ️ <i>Eslatma: Botda faqat 1 ta loyiha faol bo'la oladi. Yangi ID kiritilsa, avvalgisi avtomatik almashadi.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
        else:
            await state.set_state(AdminStates.SET_PROJECT)
            await msg.answer(
                "📌 <b>Loyiha ID raqamini yuboring:</b>\n\n"
                "<i>(Masalan: 32541 yoki to'liq havola/UUID)</i>",
                reply_markup=kb_cancel(), parse_mode="HTML"
            )

    elif "Mukofot" in text:
        current = int(await get_setting("voter_reward") or 1000)
        await state.set_state(AdminStates.SET_REWARD)
        await msg.answer(
            f"💰 <b>Ovoz mukofotini kiriting (UZS):</b>\n\n"
            f"Hozirgi qiymat: <b>{current:,} UZS</b>",
            reply_markup=kb_cancel(), parse_mode="HTML"
        )

    elif "Min. yechish" in text:
        current = int(await get_setting("min_withdrawal") or 5000)
        await state.set_state(AdminStates.SET_MIN_WD)
        await msg.answer(
            f"💳 <b>Minimal yechish miqdorini kiriting (UZS):</b>\n\n"
            f"Hozirgi qiymat: <b>{current:,} UZS</b>",
            reply_markup=kb_cancel(), parse_mode="HTML"
        )

    elif "Ovoz berish:" in text:
        current = await get_setting("voting_enabled")
        new_val = "0" if current == "1" else "1"
        await set_setting("voting_enabled", new_val)
        status_txt = "yoqildi 🟢" if new_val == "1" else "o'chirildi 🔴"
        await msg.answer(f"Ovoz berish {status_txt}!")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")

    elif "Yechish so'rovlari" in text:
        wds = await get_pending_withdrawals()
        if not wds:
            return await msg.answer("📭 Kutilayotgan pul yechish so'rovlari mavjud emas.")
            
        for w in wds[:10]:
            w_id, user_id, amount, card, status, date = w
            u = await get_user(user_id)
            username = f"@{u[1]}" if u and u[1] else "—"
            await msg.answer(
                f"👤 <b>Foydalanuvchi:</b> {username} (ID: {user_id})\n"
                f"💵 <b>Summa:</b> <code>{amount:,} UZS</code>\n"
                f"💳 <b>Karta:</b> <code>{card}</code>\n"
                f"📅 <b>Sana:</b> {date}",
                reply_markup=kb_wd_action(w_id),
                parse_mode="HTML"
            )

    elif "Foydalanuvchilar ro'yxati" in text:
        conn = await get_db_conn()
        async with conn.execute("SELECT COUNT(*) FROM users") as c:
            total = (await c.fetchone())[0]
        
        if total == 0:
            return await msg.answer("👥 Foydalanuvchilar mavjud emas.")
            
        total_pages = (total + 9) // 10
        page = 0
        offset = page * 10
        async with conn.execute("SELECT telegram_id, username, balance FROM users LIMIT 10 OFFSET ?", (offset,)) as c:
            users_list = await c.fetchall()
            
        lines = []
        for i, u in enumerate(users_list, start=offset+1):
            uname = f"@{u[1]}" if u[1] else "—"
            lines.append(f"{i}. ID: <code>{u[0]}</code> | {uname} | Balans: <b>{u[2]:,} UZS</b>")
            
        await msg.answer(
            f"👥 <b>Foydalanuvchilar ro'yxati (Jami: {total} ta):</b>\n\n" + "\n".join(lines),
            reply_markup=kb_users_nav(page, total_pages),
            parse_mode="HTML"
        )

    elif "Hisobot" in text:
        conn = await get_db_conn()
        async with conn.execute("""
            SELECT u.telegram_id, u.username, u.balance,
                   (SELECT COUNT(*) FROM votes_history v WHERE v.telegram_id = u.telegram_id AND v.status = 'SUCCESS') as vote_count
            FROM users u
        """) as c:
            users = await c.fetchall()
            
        report = ["ID | Username | Balans | Ovozlar soni\n" + "-"*50]
        for u in users:
            uname = f"@{u[1]}" if u[1] else "—"
            report.append(f"{u[0]} | {uname} | {u[2]:,} UZS | {u[3]} ta")
            
        txt_data = "\n".join(report).encode("utf-8")
        file = BufferedInputFile(txt_data, filename="foydalanuvchilar_hisoboti.txt")
        await msg.answer_document(file, caption="📊 Bot foydalanuvchilari hisoboti")

    elif "Broadcast" in text:
        await state.set_state(AdminStates.BROADCAST)
        await msg.answer(
            "📢 <b>Barcha bot foydalanuvchilariga yuboriladigan xabarni kiriting:</b>\n\n"
            "• Rasm, video yoki oddiy matn yuborishingiz mumkin.",
            reply_markup=kb_cancel(), parse_mode="HTML"
        )

    elif "Yopish" in text:
        await state.clear()
        await msg.answer("Boshqaruv paneli yopildi.", reply_markup=kb_main())

# ─── Admin panel — umumiy callbacks ───

@router.callback_query(F.data == "adm_refresh")
async def adm_refresh(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    try:
        await cb.message.edit_text(await admin_panel_text(), parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("♻️ Yangilandi!")

@router.callback_query(F.data == "adm_back")
async def adm_back(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data == "adm_close")
async def adm_close(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.delete()
    await cb.message.answer("Asosiy menyu:", reply_markup=kb_main())
    await cb.answer()

@router.callback_query(F.data == "noop")
async def noop_cb(cb: CallbackQuery):
    await cb.answer()

# ──────────────────────────────────────────────
#  API KALIT SOTIB OLISH (Asosiy bot tizimiga ulangan)
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_buy_api")
async def adm_buy_api(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    
    loading = await cb.message.answer("🔄 <b>Tariflar serverdan yuklanmoqda...</b>", parse_mode="HTML")
    res, status = await call_api("/tariffs", "GET")
    await loading.delete()
    
    if status != 200 or "tariffs" not in res:
        return await cb.message.answer(
            "❌ Tariflar ro'yxatini yuklab bo'lmadi. Keyinroq urinib ko'ring.",
            parse_mode="HTML"
        )
        
    tariffs = res.get("tariffs", [])
    if not tariffs:
        return await cb.message.answer("Hozircha faol tariflar mavjud emas.", parse_mode="HTML")
        
    buttons = [
        [InlineKeyboardButton(text="✍️ Boshqa miqdor (O'zim kiritaman)", callback_data="adm_custom_tariff", style="success")]
    ]
    for t in tariffs:
        buttons.append([
            InlineKeyboardButton(
                text=f"📦 {t['votes']} ta Ovoz — {t['price']:,} UZS",
                callback_data=f"adm_tariff_{t['votes']}",
                style="primary"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back", style="danger")])
    
    await cb.message.answer(
        "💳 <b>API Kalit sotib olish</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔑 <b>API Kalit nima?</b>\n"
        "Bu botingiz asosiy serverga ulanib, <b>captchalarni sun'iy intellekt (AI) yordamida avtomatik yechishi</b> va barqaror ishlashi uchun kerakli balans (yoqilg'i) hisoblanadi.\n\n"
        "⚠️ <b>Muhim eslatma:</b> Ushbu tariflar odamlar yig'gan ovozi uchun to'lanadigan mukofot puli emas! Bu botingiz serverga ulanib ishlashi uchun ketadigan sarf-xarajat to'lovidir.\n\n"
        "Botingiz uchun kerakli ovoz limitiga mos tarifni tanlang yoki o'zingiz xohlagan miqdorni kiriting:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await cb.answer()

@router.callback_query(F.data == "adm_custom_tariff")
async def adm_custom_tariff_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await state.set_state(AdminStates.CUSTOM_TARIFF)
    await cb.message.delete()
    await cb.message.answer(
        "✍️ <b>Kerakli ovoz miqdorini kiriting:</b>\n\n"
        "• Masalan: <code>250</code> yoki <code>750</code>\n"
        "• Narx: 1 ta ovoz = <b>1,000 UZS</b>\n\n"
        "<i>Bekor qilish uchun pastdagi ❌ Bekor qilish tugmasini bosing:</i>",
        reply_markup=kb_cancel(),
        parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.CUSTOM_TARIFF, F.text)
async def process_custom_tariff(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
        return
        
    if not text.isdigit() or int(text) < 10:
        return await msg.answer(
            "❌ Iltimos, musbat butun son kiriting (kamida 10 ta ovoz):",
            parse_mode="HTML"
        )
        
    votes = int(text)
    unit_price = 1000
    price = votes * unit_price
    await state.clear()
    
    buttons = [
        [InlineKeyboardButton(text=f"✅ {price:,} UZS — To'lov qilish", callback_data=f"adm_tariff_{votes}", style="success")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="adm_buy_api", style="danger")]
    ]
    
    await msg.answer(
        f"📦 <b>Buyurtma ma'lumotlari:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🗳️ <b>Ovozlar soni:</b> {votes:,} ta\n"
        f"💵 <b>Hisoblangan summa:</b> <b>{price:,} UZS</b>\n"
        f"📊 <i>(1 ta ovoz = {unit_price:,} UZS)</i>\n\n"
        f"To'lov fakturasi va karta raqamini olish uchun <b>«To'lov qilish»</b> tugmasini bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

async def poll_purchase_status(purchase_id: int, chat_id: int):
    """
    To'lov amalga oshirilishini fonda kuzatib boradi.
    Bank SMS-xabari kelib, asosiy serverda to'lov tasdiqlanishi bilan,
    ushbu mijoz boti adminga to'g'ridan-to'g'ri yangi kalitni taqdim etadi
    va uni botga avtomatik ulab beradi!
    """
    for _ in range(40):  # 40 x 8 soniya = 5 daqiqa davomida kuzatadi
        await asyncio.sleep(8)
        try:
            res, status = await call_api(f"/check-purchase/{purchase_id}", "GET")
            if status == 200 and res.get("status") == "COMPLETED" and res.get("api_key"):
                api_key = res["api_key"]
                votes = res.get("votes_count", "")
                await set_setting("api_key", api_key)
                await bot.send_message(
                    chat_id,
                    f"🎉 <b>Tabriklaymiz! To'lovingiz muvaffaqiyatli qabul qilindi!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📦 Xarid: <b>{votes} ta Ovoz</b>\n"
                    f"🔑 <b>Yangi API Kalitingiz:</b>\n"
                    f"<code>{api_key}</code>\n\n"
                    f"✅ <b>Ushbu kalit botingizga AVTOMATIK TARZDA ulandi va faollashtirildi!</b>\n"
                    f"Endi botingiz ovozlarni to'liq qabul qilishga tayyor! 🚀",
                    parse_mode="HTML"
                )
                break
            elif status == 200 and res.get("status") == "CANCELLED":
                break
        except Exception:
            pass


@router.callback_query(F.data.startswith("adm_tariff_"))
async def adm_select_tariff(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
        
    votes = int(cb.data.split("_")[-1])
    loading = await cb.message.answer("🔄 <b>To'lov fakturasi yaratilmoqda...</b>", parse_mode="HTML")
    
    res, status = await call_api("/buy-key-invoice", "POST", {
        "telegram_id": cb.from_user.id,
        "votes": votes
    })
    await loading.delete()
    
    if status != 200 or "unique_price" not in res:
        err = res.get("detail", "To'lov fakturasi yaratishda xatolik yuz berdi.")
        return await cb.message.answer(f"❌ {err}", parse_mode="HTML")
        
    purchase_id = res["purchase_id"]
    unique_price = res["unique_price"]
    base_price = res["base_price"]
    card_number = res["card_number"]
    
    # Fondagi avtomatik tekshiruvni ishga tushiramiz
    asyncio.create_task(poll_purchase_status(purchase_id, cb.from_user.id))
    
    kb_invoice = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 To'ladim (Tekshirish)", callback_data=f"adm_paid_{purchase_id}", style="success")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"adm_cancel_inv_{purchase_id}", style="danger")],
        [InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back", style="secondary")]
    ])
    
    await cb.message.answer(
        f"💳 <b>API Kalit sotib olish uchun to'lov fakturasi:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Tarif: <b>{votes} ta Ovoz</b>\n"
        f"💰 Asl narxi: <b>{base_price:,} UZS</b>\n"
        f"💳 Karta raqami (Uzcard/Humo): <code>{card_number}</code>\n\n"
        f"💵 <b>O'TKAZISHINGIZ KERAK BO'LGAN ANIQ SUMMA:</b>\n"
        f"👉 <b><code>{unique_price:,} UZS</code></b> 👈\n\n"
        f"⏱️ <b>To'lov muddati: 30 daqiqa!</b>\n\n"
        f"⚠️ <b>QAT'IY TALAB (DIQQAT):</b>\n"
        f"Karta hisobiga aynan <b><code>{unique_price:,} UZS</code></b> o'tkazishingiz shart (tiyinlarigacha aniq!).\n"
        f"O'tkazma kartaga tushishi bilan asosiy server to'lovni <b>avtomatik aniqlaydi</b> va yangi API kalitingiz botingizga <b>avtomatik ulanadi</b>!",
        reply_markup=kb_invoice,
        parse_mode="HTML"
    )
    await cb.answer()

@router.callback_query(F.data.startswith("adm_paid_"))
async def adm_paid_invoice(cb: CallbackQuery):
    purchase_id = int(cb.data.split("_")[-1])
    
    checking = await cb.message.answer("🔄 <b>To'lov holati serverdan tekshirilmoqda...</b>", parse_mode="HTML")
    res, status = await call_api(f"/check-purchase/{purchase_id}", "GET")
    await checking.delete()
    
    if status == 200 and res.get("status") == "COMPLETED" and res.get("api_key"):
        api_key = res["api_key"]
        votes = res.get("votes_count", "")
        # Kalitni avtomatik tarzda botning o'z sozlamalariga saqlaymiz!
        await set_setting("api_key", api_key)
        
        await cb.message.answer(
            f"🎉 <b>Tabriklaymiz! To'lovingiz muvaffaqiyatli qabul qilindi!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Xarid qilingan ovozlar: <b>{votes} ta</b>\n"
            f"🔑 <b>Yangi API Kalitingiz:</b>\n"
            f"<code>{api_key}</code>\n\n"
            f"✅ <b>Ushbu API kalit botingizga AVTOMATIK TARZDA ulandi va faollashtirildi!</b>\n"
            f"Endi botingizdan to'liq foydalanishingiz mumkin! 🚀",
            parse_mode="HTML"
        )
    elif status == 200 and res.get("status") == "PENDING":
        await cb.message.answer(
            "⏳ <b>To'lov hali bank hisobiga tushmadi.</b>\n\n"
            "O'tkazma bank kartasiga yetib kelishi bilan (odatda 1-3 daqiqa) to'lov avtomatik tasdiqlanadi va kalit botingizga avtomatik ulanadi.\n\n"
            "Iltimos, to'lovni aniq summa bilan bajarganingizga ishonch hosil qilib, birozdan so'ng yana <b>🔄 To'ladim (Tekshirish)</b> tugmasini bosing.",
            parse_mode="HTML"
        )
    else:
        await cb.message.answer(
            "❌ Xarid topilmadi yoki bekor qilingan.",
            parse_mode="HTML"
        )
    await cb.answer()

@router.callback_query(F.data.startswith("adm_cancel_inv_"))
async def adm_cancel_invoice(cb: CallbackQuery):
    purchase_id = int(cb.data.split("_")[-1])
    await call_api(f"/cancel-key-invoice/{purchase_id}", "POST")
    await cb.message.edit_text("❌ To'lov fakturasi bekor qilindi.", parse_mode="HTML")
    await cb.answer()

# ──────────────────────────────────────────────
#  API KALITNI SOZLASH VA MA'LUMOTLARI
# ──────────────────────────────────────────────

async def get_api_key_info_card(api_key: str) -> tuple[str, InlineKeyboardMarkup]:
    res, status = await call_api("/key-info", "GET")
    if status == 200 and "votes_remaining" in res:
        created_at = res.get("created_at", "—")
        rem = res.get("votes_remaining", 0)
        total_bought = res.get("total_votes_bought", rem)
        paid = res.get("total_paid_uzs", total_bought * 1000)
        bal = res.get("balance_uzs", 0)
        is_active = res.get("is_active", True)
        status_txt = "🟢 Faol" if is_active else "🔴 Bloklangan"
        
        display_key = f"{api_key[:11]}...{api_key[-4:]}" if len(api_key) > 15 else api_key
        
        text = (
            "🔑 <b>API Kalit Ma'lumotlari</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔑 <b>Kalit:</b> <code>{display_key}</code>\n"
            f"📅 <b>Faollashtirilgan sana:</b> {created_at}\n"
            f"💵 <b>To'langan summa:</b> <b>{paid:,} UZS</b> ({total_bought:,} ta ovoz uchun)\n"
            f"📊 <b>Ovozlar holati:</b> <b>{total_bought:,} / {rem:,} ta qoldi</b>\n"
            f"💰 <b>Joriy balans:</b> <b>{bal:,} UZS</b>\n"
            f"⚡ <b>Holati:</b> {status_txt}\n\n"
            f"<i>Kalit balansini to'ldirish yoki boshqa kalit ulash uchun quyidagi tugmalardan birini tanlang:</i>"
        )
    else:
        display_key = f"{api_key[:11]}...{api_key[-4:]}" if len(api_key) > 15 else api_key
        text = (
            "🔑 <b>API Kalit Ma'lumotlari</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔑 <b>Kalit:</b> <code>{display_key}</code>\n"
            f"⚠️ Serverdan to'liq ma'lumot olib bo'lmadi.\n\n"
            f"<i>Quyidagi tugmalar orqali sozlang:</i>"
        )
        
    buttons = [
        [InlineKeyboardButton(text="➕ Ovoz sotib olish (Balansni to'ldirish)", callback_data="adm_topup_key", style="success")],
        [InlineKeyboardButton(text="✏️ Boshqa kalit ulash", callback_data="adm_input_new_key", style="primary")],
        [InlineKeyboardButton(text="🗑️ Kalitni uzish / o'chirish", callback_data="adm_delete_key", style="danger")],
        [InlineKeyboardButton(text="✖️ Yopish", callback_data="adm_close_prompt", style="secondary")]
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "adm_set_api")
async def adm_set_api(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    
    api_key = await get_setting("api_key")
    if api_key:
        text, kb = await get_api_key_info_card(api_key)
        await cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await state.set_state(AdminStates.SET_API_KEY)
        await cb.message.answer(
            "🔑 <b>Yangi API kalitni yuboring:</b>\n\n"
            "• Kalit <code>ob_api_</code> bilan boshlanishi shart\n"
            "• Kiritilgandan so'ng server bilan <b>avtomatik tekshiriladi</b>",
            reply_markup=kb_cancel(), parse_mode="HTML"
        )
    await cb.answer()

@router.callback_query(F.data == "adm_input_new_key")
async def adm_input_new_key_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await state.set_state(AdminStates.SET_API_KEY)
    await cb.message.delete()
    await cb.message.answer(
        "🔑 <b>Yangi API kalitingizni yuboring:</b>\n\n"
        "• Kalit <code>ob_api_</code> bilan boshlanishi shart\n"
        "• Kiritilgandan so'ng server bilan <b>avtomatik tekshiriladi</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.callback_query(F.data == "adm_delete_key")
async def adm_delete_key_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await set_setting("api_key", "")
    await cb.message.delete()
    await cb.message.answer(
        "🗑️ <b>API kalit uzildi / o'chirildi!</b>\n\n"
        "Yangi kalit kiritmaguningizcha bot ovozlarni qabul qila olmaydi.",
        parse_mode="HTML"
    )
    await cb.message.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
    await cb.answer("API kalit o'chirildi!")

@router.callback_query(F.data == "adm_topup_key")
async def adm_topup_key_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await state.set_state(AdminStates.TOPUP_VOTES)
    await cb.message.delete()
    await cb.message.answer(
        "✍️ <b>Mavjud kalitingizga nechta ovoz qo'shmoqchisiz?</b>\n\n"
        "• Masalan: <code>50</code>, <code>100</code>, <code>500</code>\n"
        "• Narx: 1 ta ovoz = <b>1,000 UZS</b>\n\n"
        "<i>Kerakli miqdorni yozib yuboring:</i>",
        reply_markup=kb_cancel(),
        parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.TOPUP_VOTES, F.text)
async def process_topup_votes(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
        return
        
    if not text.isdigit() or int(text) < 10:
        return await msg.answer(
            "❌ Iltimos, musbat butun son kiriting (kamida 10 ta ovoz):",
            parse_mode="HTML"
        )
        
    votes = int(text)
    unit_price = 1000
    price = votes * unit_price
    await state.clear()
    
    api_key = await get_setting("api_key")
    display_key = f"{api_key[:11]}...{api_key[-4:]}" if api_key and len(api_key) > 15 else (api_key or "—")
    
    buttons = [
        [InlineKeyboardButton(text=f"✅ {price:,} UZS — To'lovga o'tish", callback_data=f"adm_topup_pay_{votes}", style="success")],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="adm_set_api", style="danger")]
    ]
    
    await msg.answer(
        f"📦 <b>Balansni to'ldirish buyurtmasi:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>To'ldiriladigan kalit:</b> <code>{display_key}</code>\n"
        f"🗳️ <b>Qo'shiladigan ovozlar:</b> +{votes:,} ta\n"
        f"💵 <b>Hisoblangan summa:</b> <b>{price:,} UZS</b>\n"
        f"📊 <i>(1 ta ovoz = {unit_price:,} UZS)</i>\n\n"
        f"To'lov fakturasi va karta raqamini olish uchun <b>«To'lovga o'tish»</b> tugmasini bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("adm_topup_pay_"))
async def adm_topup_pay_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
        
    votes = int(cb.data.split("_")[-1])
    api_key = await get_setting("api_key")
    loading = await cb.message.answer("🔄 <b>To'lov fakturasi yaratilmoqda...</b>", parse_mode="HTML")
    
    res, status = await call_api("/buy-key-invoice", "POST", {
        "telegram_id": cb.from_user.id,
        "votes": votes,
        "target_key": api_key
    })
    await loading.delete()
    
    if status != 200 or "unique_price" not in res:
        err = res.get("detail", "To'lov fakturasi yaratishda xatolik yuz berdi.")
        return await cb.message.answer(f"❌ {err}", parse_mode="HTML")
        
    purchase_id = res["purchase_id"]
    unique_price = res["unique_price"]
    base_price = res["base_price"]
    card_number = res["card_number"]
    
    # Fondagi avtomatik tekshiruvni ishga tushiramiz
    asyncio.create_task(poll_purchase_status(purchase_id, cb.from_user.id))
    
    kb_invoice = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 To'ladim (Tekshirish)", callback_data=f"adm_paid_{purchase_id}", style="success")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"adm_cancel_inv_{purchase_id}", style="danger")],
        [InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="adm_back", style="secondary")]
    ])
    
    display_key = f"{api_key[:11]}...{api_key[-4:]}" if api_key and len(api_key) > 15 else (api_key or "—")
    
    await cb.message.answer(
        f"💳 <b>Balansni to'ldirish uchun to'lov fakturasi:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>Kalit:</b> <code>{display_key}</code>\n"
        f"📦 <b>Qo'shiladigan ovozlar:</b> +{votes:,} ta\n"
        f"💰 Asl narxi: <b>{base_price:,} UZS</b>\n"
        f"💳 Karta raqami (Uzcard/Humo): <code>{card_number}</code>\n\n"
        f"💵 <b>O'TKAZISHINGIZ KERAK BO'LGAN ANIQ SUMMA:</b>\n"
        f"👉 <b><code>{unique_price:,} UZS</code></b> 👈\n\n"
        f"⏱️ <b>To'lov muddati: 30 daqiqa!</b>\n\n"
        f"⚠️ <b>QAT'IY TALAB (DIQQAT):</b>\n"
        f"Karta hisobiga aynan <b><code>{unique_price:,} UZS</code></b> o'tkazishingiz shart (tiyinlarigacha aniq!).\n"
        f"O'tkazma kartaga tushishi bilan asosiy server to'lovni <b>avtomatik aniqlaydi</b> va kalitingiz balansi <b>avtomatik to'ldiriladi</b>!",
        reply_markup=kb_invoice,
        parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.SET_API_KEY, F.text)
async def process_api_key(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
        return

    if not text.startswith("ob_api_"):
        return await msg.answer(
            "❌ Noto'g'ri format!\n\n"
            "Kalit <code>ob_api_</code> bilan boshlanishi kerak:",
            parse_mode="HTML"
        )

    checking = await msg.answer("🔄 <b>API kalit serverda tekshirilmoqda...</b>", parse_mode="HTML")
    valid, result_msg = await validate_api_key(text)

    if not valid:
        return await checking.edit_text(
            f"{result_msg}\n\nQayta to'g'ri kalit yuboring:",
            parse_mode="HTML"
        )

    await set_setting("api_key", text)
    await state.clear()
    await checking.edit_text(
        f"✅ <b>API kalit muvaffaqiyatli saqlandi!</b>\n\n{result_msg}",
        parse_mode="HTML"
    )
    await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")

# ──────────────────────────────────────────────
#  LOYIHA IDni SOZLASH
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_set_project")
async def adm_set_project(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()

    # API kalit ulanmaganligini tekshiramiz
    api_key = await get_setting("api_key")
    if not api_key:
        return await cb.answer("⚠️ Avval API kalitni ulashingiz shart!", show_alert=True)

    cur_id = await get_setting("project_id")
    cur_name = await get_setting("project_name")
    
    if cur_id:
        buttons = [
            [InlineKeyboardButton(text="✏️ Yangi ID kiritish (Almashtirish)", callback_data="adm_change_project", style="primary")],
            [InlineKeyboardButton(text="🗑️ Faol Loyihani o'chirish", callback_data="adm_delete_project", style="danger")],
            [InlineKeyboardButton(text="✖️ Yopish", callback_data="adm_close_prompt", style="secondary")]
        ]
        await cb.message.answer(
            f"📌 <b>Loyiha Sozlamalari</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔹 <b>Hozirgi faol loyiha:</b>\n"
            f"🆔 <b>ID:</b> <code>{cur_id}</code>\n"
            f"📋 <b>Nomi:</b> <b>{cur_name or cur_id}</b>\n\n"
            f"ℹ️ <i>Eslatma: Botda faqat 1 ta loyiha faol bo'la oladi. Yangi ID kiritilsa, avvalgisi avtomatik almashadi.</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    else:
        await state.set_state(AdminStates.SET_PROJECT)
        await cb.message.answer(
            "📌 <b>Yangi Loyiha ID raqamini yuboring:</b>\n\n"
            "<i>(Masalan: 32541 yoki havola/UUID)</i>",
            reply_markup=kb_cancel(), parse_mode="HTML"
        )
    await cb.answer()

@router.callback_query(F.data == "adm_change_project")
async def adm_change_project_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await state.set_state(AdminStates.SET_PROJECT)
    await cb.message.delete()
    await cb.message.answer(
        "📌 <b>Yangi Loyiha ID raqamini yuboring:</b>\n\n"
        "<i>(Masalan: 32541 yoki to'liq havola/UUID)</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.callback_query(F.data == "adm_delete_project")
async def adm_delete_project_cb(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    await set_setting("project_id", "")
    await set_setting("project_name", "")
    await cb.message.delete()
    await cb.message.answer(
        "🗑️ <b>Faol loyiha ID o'chirildi!</b>\n\n"
        "Endi botda biriktirilgan loyiha mavjud emas. Yangi loyiha qo'shilmaguncha ovoz berish to'xtatiladi.",
        parse_mode="HTML"
    )
    await cb.message.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
    await cb.answer("Loyiha o'chirildi!")

@router.callback_query(F.data == "adm_close_prompt")
async def adm_close_prompt_cb(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()

@router.message(AdminStates.SET_PROJECT, F.text)
async def process_project_id(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("Bekor qilindi.")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")
        return

    checking = await msg.answer(
        f"🔄 <b>Loyiha <code>{text}</code> tekshirilmoqda...</b>", parse_mode="HTML"
    )

    api_key = await get_setting("api_key")
    if not api_key:
        await state.clear()
        await checking.edit_text("❌ Xatolik: API kalit ulanmagan. Sozlash bekor qilindi.")
        return

    res, status = await call_api(f"/initiative/{text}", "GET")

    if status == 200 and "initiative" in res:
        initiative   = res["initiative"]
        category     = initiative.get("categoryName") or "Loyiha"
        region       = initiative.get("regionName") or ""
        district     = initiative.get("districtName") or ""
        quarter      = initiative.get("quarterName") or ""
        vote_cnt     = initiative.get("voteCount") or 0
        desc         = initiative.get("description") or ""

        # Loyiha nomini hudud bilan chiroyli shakllantiramiz
        loc = district or region
        name = f"{category} ({loc})" if loc else category

        await set_setting("project_id",   text)
        await set_setting("project_name", str(name))
        await state.clear()

        details_text = (
            "✅ <b>Yangi faol loyiha saqlandi!</b>\n\n"
            f"📅 <b>Mavsum:</b> {html.escape(str(initiative.get('boardTitle', 'Tashabbusli Budjet')))}\n"
            f"🏢 <b>Hudud:</b> {html.escape(str(region))}, {html.escape(str(district))}\n"
            f"🏡 <b>Mahalla:</b> {html.escape(str(quarter))}\n"
            f"📂 <b>Kategoriya:</b> {html.escape(str(category))}\n"
            f"🗳️ <b>Ovozlar soni:</b> {vote_cnt} ta\n"
            f"📝 <b>Tavsif:</b> {html.escape(str(desc[:300]))}...\n\n"
            f"🆔 <b>Loyiha ID:</b> <code>{text}</code>"
        )

        await checking.edit_text(details_text, parse_mode="HTML")
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")

    elif status == 404:
        await checking.edit_text(
            f"❌ ID <code>{text}</code> bo'yicha loyiha topilmadi!\n\n"
            f"Boshqa ID yuborib ko'ring:",
            parse_mode="HTML"
        )
    else:
        # Server xatosi bo'lsa ham saqlaydi
        await set_setting("project_id",   text)
        await set_setting("project_name", text)
        await state.clear()
        await checking.edit_text(
            f"⚠️ Server tekshirishda xato (HTTP {status}), lekin ID saqlandi.\n\n"
            f"🆔 ID: <code>{text}</code>",
            parse_mode="HTML"
        )
        await msg.answer(await admin_panel_text(), reply_markup=await kb_admin(), parse_mode="HTML")

# ──────────────────────────────────────────────
#  MUKOFOT MIQDORI
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_set_reward")
async def adm_set_reward(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    current = int(await get_setting("voter_reward") or 1000)
    await state.set_state(AdminStates.SET_REWARD)
    await cb.message.answer(
        f"💰 <b>Ovoz mukofotini kiriting (UZS):</b>\n\n"
        f"Hozirgi qiymat: <b>{current:,} UZS</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.SET_REWARD, F.text)
async def process_reward(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if not text.isdigit() or int(text) < 0:
        return await msg.answer("❌ Faqat musbat butun son kiriting:")
    await set_setting("voter_reward", text)
    await state.clear()
    await msg.answer(
        f"✅ Mukofot <b>{int(text):,} UZS</b> ga o'zgartirildi!",
        reply_markup=kb_main(), parse_mode="HTML"
    )

# ──────────────────────────────────────────────
#  MINIMAL PUL YECHISH
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_set_min_wd")
async def adm_set_min_wd(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    current = int(await get_setting("min_withdrawal") or 5000)
    await state.set_state(AdminStates.SET_MIN_WD)
    await cb.message.answer(
        f"💳 <b>Minimal yechish miqdorini kiriting (UZS):</b>\n\n"
        f"Hozirgi qiymat: <b>{current:,} UZS</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.SET_MIN_WD, F.text)
async def process_min_wd(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if not text.isdigit() or int(text) < 0:
        return await msg.answer("❌ Faqat musbat butun son kiriting:")
    await set_setting("min_withdrawal", text)
    await state.clear()
    await msg.answer(
        f"✅ Minimal yechish <b>{int(text):,} UZS</b> ga o'zgartirildi!",
        reply_markup=kb_main(), parse_mode="HTML"
    )

# ──────────────────────────────────────────────
#  OVOZ BERISHNI YOQISH / O'CHIRISH
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_toggle_vote")
async def adm_toggle_vote(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    current = await get_setting("voting_enabled")
    new_val = "0" if current == "1" else "1"
    await set_setting("voting_enabled", new_val)
    status_txt = "🟢 yoqildi" if new_val == "1" else "🔴 o'chirildi"
    await cb.answer(f"Ovoz berish {status_txt}!", show_alert=True)
    try:
        await cb.message.edit_text(await admin_panel_text(), parse_mode="HTML")
    except Exception:
        pass

# ──────────────────────────────────────────────
#  BROADCAST
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()
    total = await get_total_users()
    await state.set_state(AdminStates.BROADCAST)
    await cb.message.answer(
        f"📢 <b>Broadcast — barcha foydalanuvchilarga xabar</b>\n\n"
        f"👥 Jami: <b>{total} ta</b> foydalanuvchi\n\n"
        f"Yuboriladigan xabarni yozing:\n"
        f"<i>(matn, rasm, video — istalgan format)</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.message(AdminStates.BROADCAST)
async def process_broadcast(msg: Message, state: FSMContext):
    if msg.text and msg.text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Broadcast bekor qilindi.", reply_markup=kb_main())

    await state.clear()
    users   = await get_all_users()
    sent    = 0
    failed  = 0
    prog    = await msg.answer(f"📤 Yuborilmoqda... 0 / {len(users)}")

    for i, (uid, *_) in enumerate(users):
        try:
            await msg.copy_to(uid)
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 25 == 0:
            try:
                await prog.edit_text(f"📤 Yuborilmoqda... {i + 1} / {len(users)}")
            except Exception:
                pass
        await asyncio.sleep(0.04)

    await prog.edit_text(
        f"✅ <b>Broadcast yakunlandi!</b>\n\n"
        f"📬 Muvaffaqiyatli: <b>{sent} ta</b>\n"
        f"❌ Xato:           <b>{failed} ta</b>",
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────
#  FOYDALANUVCHILAR RO'YXATI
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_users_"))
async def adm_users_list(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()

    page     = int(cb.data.split("_")[-1])
    per_page = 10
    users    = await get_all_users()
    total    = len(users)

    if total == 0:
        await cb.answer("Hozircha foydalanuvchilar yo'q.", show_alert=True)
        return

    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = min(page, total_pages - 1)
    chunk       = users[page * per_page:(page + 1) * per_page]

    lines = [f"👥 <b>Foydalanuvchilar</b> — sahifa {page + 1}/{total_pages} (jami {total} ta)\n"]
    for i, (uid, uname, fname, bal, votes) in enumerate(chunk, page * per_page + 1):
        display = fname or (f"@{uname}" if uname else str(uid))
        lines.append(
            f"{i}. <b>{display}</b>\n"
            f"   🗳️ {votes} ovoz  •  💰 {bal:,} UZS"
        )

    try:
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=kb_users_nav(page, total_pages),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()

# ──────────────────────────────────────────────
#  HISOBOT (TXT)
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_report")
async def adm_report(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()

    history = await get_all_votes_history()
    if not history:
        await cb.answer("Hozircha ovozlar tarixi yo'q.", show_alert=True)
        return

    lines = [
        "=" * 48,
        "     OPEN BUDGET — OVOZLAR HISOBOTI",
        "=" * 48,
        f"Sana:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Jami:  {len(history)} ta muvaffaqiyatli ovoz",
        "-" * 48,
    ]
    for i, (phone, date_str) in enumerate(history, 1):
        lines.append(f"{i:05d} │ +{phone:12s} │ {date_str}")
    lines += ["=" * 48, ""]

    file_bytes  = "\n".join(lines).encode("utf-8")
    report_file = BufferedInputFile(
        file_bytes,
        filename=f"hisobot_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    )
    await cb.message.answer_document(
        report_file,
        caption=(
            f"📊 <b>Ovozlar hisoboti</b>\n\n"
            f"📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"🗳️ Jami: <b>{len(history)} ta</b>"
        ),
        parse_mode="HTML"
    )
    await cb.answer()

# ──────────────────────────────────────────────
#  YECHISH SO'ROVLARI (admin)
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_wd_list")
async def adm_wd_list(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return await cb.answer()

    pending = await get_pending_withdrawals()
    if not pending:
        await cb.answer("✅ Kutilayotgan yechish so'rovlari yo'q.", show_alert=True)
        return

    await cb.message.answer(
        f"💸 <b>Kutilayotgan so'rovlar — {len(pending)} ta</b>",
        parse_mode="HTML"
    )
    for wd_id, tid, amount, card, date_str in pending:
        u       = await get_user(tid)
        display = (u[2] or u[1] or str(tid)) if u else str(tid)
        await cb.message.answer(
            f"🆔 So'rov: <b>#{wd_id}</b>\n"
            f"👤 Foydalanuvchi: <b>{display}</b> (<code>{tid}</code>)\n"
            f"💳 Karta:   <code>{card}</code>\n"
            f"💵 Summa:   <b>{amount:,} UZS</b>\n"
            f"📅 Sana:    {date_str}",
            reply_markup=kb_wd_action(wd_id),
            parse_mode="HTML"
        )
    await cb.answer()

@router.callback_query(F.data.startswith("adm_app_"))
async def adm_approve_wd(cb: CallbackQuery):
    wd_id      = int(cb.data.split("_")[-1])
    ok, tid, amount = await process_withdrawal(wd_id, True)
    if ok:
        await cb.message.edit_text(
            cb.message.text + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML"
        )
        try:
            await bot.send_message(
                tid,
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"💸 <b>{amount:,} UZS</b> yechish so'rovingiz tasdiqlandi va kartangizga o'tkazildi!\n\n"
                f"Ko'proq ovoz berib, ko'proq pul ishlang! 🚀",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await cb.answer("✅ Tasdiqlandi!" if ok else "❌ So'rov topilmadi")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_reject_wd(cb: CallbackQuery):
    wd_id      = int(cb.data.split("_")[-1])
    ok, tid, amount = await process_withdrawal(wd_id, False)
    if ok:
        await cb.message.edit_text(
            cb.message.text + "\n\n❌ <b>RAD ETILDI — pul balansgа qaytarildi</b>",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                tid,
                f"⚠️ <b>Yechish so'rovi rad etildi</b>\n\n"
                f"💵 <b>{amount:,} UZS</b> balansingizga qaytarildi.\n\n"
                f"Muammo bo'lsa administrator bilan bog'laning.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await cb.answer("Rad etildi" if ok else "❌ So'rov topilmadi")

# ══════════════════════════════════════════════
#  FOYDALANUVCHI HANDLERLARI
# ══════════════════════════════════════════════

@router.message(F.text.lower().contains("orqaga") | F.text.lower().contains("bekor qilish"), StateFilter("*"))
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Bekor qilindi.", reply_markup=kb_main())

# ──────────────────────────────────────────────
#  💎 MENING HISOBIM
# ──────────────────────────────────────────────

@router.message(F.text.lower().contains("hisobim"), StateFilter("*"))
async def cmd_my_account(msg: Message, state: FSMContext):
    await state.clear()
    tid = msg.from_user.id

    if await user_is_blocked(tid):
        return await msg.answer("⛔ <b>Hisobingiz bloklangan.</b>", parse_mode="HTML")

    u      = await get_or_create_user(tid, msg.from_user.username or "", msg.from_user.full_name or "")
    bal    = u[3]
    votes  = u[4]
    reward = int(await get_setting("voter_reward") or 1000)
    min_wd = int(await get_setting("min_withdrawal") or 5000)

    await msg.answer(
        f"<tg-emoji emoji-id='5469950790893946284'>💎</tg-emoji> <b>Mening hisobim</b> <tg-emoji emoji-id='5469950790893946284'>✨</tg-emoji>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<tg-emoji emoji-id='5471971711481666499'>💰</tg-emoji> <b>Hamyon balansi:</b> <b>{bal:,} UZS</b>\n"
        f"<tg-emoji emoji-id='5471983050186938952'>🗳️</tg-emoji> <b>Berilgan ovozlar:</b> <b>{votes} ta</b>\n"
        f"<tg-emoji emoji-id='5472164874884394982'>📈</tg-emoji> <b>Jami daromad:</b> <b>{votes * reward:,} UZS</b>\n\n"
        f"💳 Minimal yechish: <b>{min_wd:,} UZS</b>",
        reply_markup=kb_balance(bal >= min_wd),
        parse_mode="HTML"
    )

# ──────────────────────────────────────────────
#  📋 TARIXIM
# ──────────────────────────────────────────────

@router.message(F.text.lower().contains("tarixim") | F.text.lower().contains("tarix"), StateFilter("*"))
async def cmd_history(msg: Message, state: FSMContext):
    await state.clear()
    if await user_is_blocked(msg.from_user.id):
        return await msg.answer("⛔ <b>Hisobingiz bloklangan.</b>", parse_mode="HTML")

    history = await get_user_votes_history(msg.from_user.id)
    if not history:
        return await msg.answer(
            "📋 <b>Siz hali ovoz bermagansiz.</b>\n\n"
            "Boshlash uchun <b>🗳️ Ovoz berish</b> tugmasini bosing!",
            parse_mode="HTML"
        )

    lines = ["📋 <b>So'nggi 10 ta ovozingiz:</b>\n"]
    for i, (phone, date_str) in enumerate(history, 1):
        lines.append(f"<b>{i}.</b> 📱 +{phone}\n    🕐 {date_str}")

    await msg.answer("\n".join(lines), parse_mode="HTML")

@router.callback_query(F.data == "u_vote")
async def cb_u_vote(cb: CallbackQuery, state: FSMContext):
    await start_vote(cb.message, state)
    await cb.answer()

@router.callback_query(F.data == "u_balance")
async def cb_u_balance(cb: CallbackQuery, state: FSMContext):
    await cmd_my_account(cb.message, state)
    await cb.answer()

@router.callback_query(F.data == "u_history")
async def cb_u_history(cb: CallbackQuery, state: FSMContext):
    await cmd_history(cb.message, state)
    await cb.answer()

@router.callback_query(F.data == "u_profile")
async def cb_u_profile(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    u = await get_user(cb.from_user.id)
    bal = u[3] if u else 0
    votes = u[4] if u else 0
    text = (
        f"👤 <b>Foydalanuvchi Profili</b>\n\n"
        f"🆔 <b>ID:</b> <code>{cb.from_user.id}</code>\n"
        f"👤 <b>Ism:</b> {html.escape(str(cb.from_user.full_name))}\n"
        f"💳 <b>Balans:</b> <b>{bal:,} UZS</b>\n"
        f"🗳️ <b>Ovozlar:</b> <b>{votes} ta</b>"
    )
    await cb.message.answer(text, reply_markup=kb_user_inline(), parse_mode="HTML")
    await cb.answer()

# ──────────────────────────────────────────────
#  💸 PUL YECHISH (Foydalanuvchi)
# ──────────────────────────────────────────────

@router.callback_query(F.data == "user_withdraw")
async def start_withdraw(cb: CallbackQuery, state: FSMContext):
    u      = await get_or_create_user(cb.from_user.id)
    bal    = u[3]
    min_wd = int(await get_setting("min_withdrawal") or 5000)
    if bal < min_wd:
        return await cb.answer(
            f"💳 Balansda yetarli mablag' yo'q!\nMinimal: {min_wd:,} UZS",
            show_alert=True
        )
    await state.set_state(WithdrawStates.CARD)
    await cb.message.answer(
        "💳 <b>Plastik karta raqamingizni kiriting:</b>\n\n"
        "<i>16–20 raqamli Uzcard yoki Humo karta</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await cb.answer()

@router.message(WithdrawStates.CARD, F.text)
async def process_wd_card(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    card = text.replace(" ", "").replace("-", "")
    if not card.isdigit() or not (16 <= len(card) <= 20):
        return await msg.answer("❌ Noto'g'ri karta! 16–20 xonali raqam kiriting:")
    await state.update_data(card=card)
    u   = await get_or_create_user(msg.from_user.id)
    bal = u[3]
    await state.set_state(WithdrawStates.AMOUNT)
    await msg.answer(
        f"💵 <b>Qancha yechmoqchisiz?</b>\n\n"
        f"Mavjud balans: <b>{bal:,} UZS</b>\n\n"
        f"Summani kiriting:",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )

@router.message(WithdrawStates.AMOUNT, F.text)
async def process_wd_amount(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if not text.isdigit():
        return await msg.answer("❌ Faqat raqam kiriting:")

    amount = int(text)
    u      = await get_or_create_user(msg.from_user.id)
    bal    = u[3]
    min_wd = int(await get_setting("min_withdrawal") or 5000)

    if amount < min_wd:
        return await msg.answer(f"❌ Minimal yechish: {min_wd:,} UZS. Qayta kiriting:")
    if amount > bal:
        return await msg.answer(f"❌ Balansingizda bunday summa yo'q! Maksimal: {bal:,} UZS:")

    data   = await state.get_data()
    card   = data["card"]
    req_id = await create_withdrawal(msg.from_user.id, amount, card)
    await state.clear()

    if not req_id:
        return await msg.answer(
            "❌ <b>Xatolik!</b> Balansingizda yetarli mablag' qolmagan bo'lishi mumkin.",
            reply_markup=kb_main(),
            parse_mode="HTML"
        )

    await msg.answer(
        "✅ <b>So'rov qabul qilindi!</b>\n\n"
        f"🆔 So'rov raqami: <b>#{req_id}</b>\n"
        f"💳 Karta:          <code>{card}</code>\n"
        f"💵 Summa:          <b>{amount:,} UZS</b>\n\n"
        "⏳ Administrator 24 soat ichida ko'rib chiqadi va kartangizga o'tkazadi.",
        reply_markup=kb_main(), parse_mode="HTML"
    )

    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 <b>Yangi yechish so'rovi #{req_id}!</b>\n\n"
                f"👤 ID:    <code>{msg.from_user.id}</code>\n"
                f"💳 Karta: <code>{card}</code>\n"
                f"💵 Summa: <b>{amount:,} UZS</b>\n\n"
                f"Tasdiqlash uchun /admin paneliga kiring.",
                parse_mode="HTML"
            )
        except Exception:
            pass

# ══════════════════════════════════════════════
#  OVOZ BERISH JARAYONI
# ══════════════════════════════════════════════

@router.message(F.text.lower().contains("ovoz berish"), StateFilter("*"))
async def start_vote(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id

    # ── Tekshiruvlar ──
    if await user_is_blocked(uid):
        return await msg.answer("⛔ <b>Sizning hisobingiz bloklangan.</b>", parse_mode="HTML")

    api_key = await get_setting("api_key")
    project_id = await get_setting("project_id")

    if not api_key:
        if uid == ADMIN_ID:
            return await msg.answer(
                "⚠️ <b>Ovoz berish uchun avval API kalitni ulang!</b>\n\n"
                "/admin paneliga kirib <b>💳 API Kalit sotib olish</b> yoki <b>🔑 API Kalitni sozlash</b> tugmasini bosing.",
                parse_mode="HTML"
            )
        return await msg.answer(
            "🔧 <b>Ovoz berish tizimi sozlanmoqda.</b>\n\nTez orada ovoz berish ochiladi, kuting! ⏳",
            parse_mode="HTML"
        )

    if not project_id:
        if uid == ADMIN_ID:
            return await msg.answer(
                "⚠️ <b>Loyiha ID raqami sozlanmagan!</b>\n\n"
                "/admin paneliga kirib <b>📌 Loyiha IDni sozlash</b> tugmasini bosing.",
                parse_mode="HTML"
            )
        return await msg.answer(
            "🔧 <b>Ovoz berish tizimi sozlanmoqda.</b>\n\nTez orada ovoz berish ochiladi, kuting! ⏳",
            parse_mode="HTML"
        )

    if not await voting_is_enabled():
        return await msg.answer(
            "⛔ <b>Ovoz berish hozirda vaqtincha to'xtatilgan.</b>\n\n"
            "Keyinroq urinib ko'ring.",
            parse_mode="HTML"
        )

    if VOTE_COOLDOWN_HOURS > 0:
        last = await get_user_last_vote(uid)
        if last:
            elapsed   = datetime.now() - last
            cooldown  = timedelta(hours=VOTE_COOLDOWN_HOURS)
            if elapsed < cooldown:
                remaining = cooldown - elapsed
                h = int(remaining.total_seconds() // 3600)
                m = int((remaining.total_seconds() % 3600) // 60)
                return await msg.answer(
                    f"⏳ <b>Keyingi ovozgacha:</b> <b>{h} soat {m} daqiqa</b>",
                    parse_mode="HTML"
                )

    await msg.answer(
        "📱 <b>Ovoz berish uchun telefon raqamingizni ulashing:</b>\n\n"
        "<i>Open Budget tizimida ro'yxatdan o'tgan raqam bo'lishi kerak.</i>",
        reply_markup=kb_phone(), parse_mode="HTML"
    )
    await state.set_state(VoteStates.PHONE)

# ─── Qadam 1: Telefon raqam ───

@router.message(VoteStates.PHONE)
async def vote_phone(msg: Message, state: FSMContext):
    if msg.text and msg.text in ("🔙 Orqaga", "❌ Bekor qilish"):
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())

    phone = ""
    if msg.contact:
        phone = msg.contact.phone_number
    elif msg.text:
        phone = msg.text.strip()

    phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not phone.startswith("998") or len(phone) != 12:
        return await msg.answer(
            "❌ Noto'g'ri raqam!\n\n"
            "Format: <code>+998XXXXXXXXX</code>\n"
            "Yoki telefon raqamni ulashish tugmasini bosing:",
            parse_mode="HTML"
        )

    await state.update_data(phone=phone)
    loading = await msg.answer("🔄 <b>Captcha yuklanmoqda...</b>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

    res, status = await call_api("/captcha", "POST")
    if status != 200 or "captcha" not in res:
        await state.clear()
        await loading.delete()
        return await msg.answer(
            "❌ Captcha yuklashda xatolik yuz berdi.\nQayta urinib ko'ring:",
            reply_markup=kb_main()
        )

    captcha = res["captcha"]
    await state.update_data(captcha_key=captcha["key"])

    solved_result = captcha.get("solved_result")
    if solved_result is not None:
        await loading.delete()
        sending = await msg.answer("🤖 <b>Captcha avtomatik yechildi. SMS kod yuborilmoqda...</b>", parse_mode="HTML")
        res_otp, status_otp = await call_api("/send-otp", "POST", {
            "phone_number": phone,
            "captcha_key":  captcha["key"],
            "captcha_result": int(solved_result),
            "project_id":   await get_setting("project_id"),
        })
        
        if status_otp != 200:
            err = res_otp.get("detail", "")
            err_lower = err.lower()
            not_reg_keywords = ["not_registered", "topilmadi", "foydalanuvchi",
                "топилмади", "фойдаланувчи", "маъluмотlari", "ҳеч қандай", "mavjud emas"]
            if any(k in err_lower for k in not_reg_keywords):
                await sending.delete()
                await start_reg_flow(msg, state, phone)
                return
            await state.clear()
            await sending.delete()
            return await msg.answer(f"❌ {err or 'Xatolik yuz berdi.'}", reply_markup=kb_main())

        await state.update_data(otp_key=res_otp.get("otp_key"))
        await sending.edit_text(
            f"📩 <b>SMS kod yuborildi!</b>\n\n"
            f"<code>{phone}</code> raqamiga yuborilgan <b>6 xonali kodni</b> kiriting:",
            parse_mode="HTML"
        )
        await state.set_state(VoteStates.SMS)
        return

    try:
        image_bytes = base64.b64decode(captcha["image"].split(",")[-1])
    except Exception:
        image_bytes = base64.b64decode(captcha["image"])

    photo = BufferedInputFile(image_bytes, filename="captcha.png")
    await loading.delete()
    await msg.answer_photo(
        photo,
        caption="🧩 <b>Rasmdagi raqamlarni kiriting:</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await state.set_state(VoteStates.CAPTCHA_1)

# ─── Qadam 2: 1-Captcha ───

@router.message(VoteStates.CAPTCHA_1, F.text)
async def vote_captcha1(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if not text.isdigit():
        return await msg.answer("❌ Faqat rasmdagi <b>raqamlarni</b> kiriting:", parse_mode="HTML")

    data = await state.get_data()
    sending = await msg.answer("🔄 <b>SMS kod yuborilmoqda...</b>", parse_mode="HTML")

    res, status = await call_api("/send-otp", "POST", {
        "phone_number": data["phone"],
        "captcha_key":  data["captcha_key"],
        "captcha_result": int(text),
        "project_id":   await get_setting("project_id"),
    })

    if status != 200:
        err = res.get("detail", "")
        err_lower = err.lower()
        not_reg_keywords = ["not_registered", "topilmadi", "foydalanuvchi",
            "топилмади", "фойдаланувчи", "маълумотлари", "ҳеч қандай", "mavjud emas"]
        if any(k in err_lower for k in not_reg_keywords):
            await sending.delete()
            await start_reg_flow(msg, state, data["phone"])
            return
        await state.clear()
        await sending.delete()
        return await msg.answer(f"❌ {err or 'Xatolik yuz berdi.'}", reply_markup=kb_main())

    await state.update_data(otp_key=res.get("otp_key"))
    await sending.edit_text(
        "📩 <b>SMS kod yuborildi!</b>\n\n"
        "Telefoningizga kelgan <b>6 xonali kodni</b> kiriting:",
        parse_mode="HTML"
    )
    await state.set_state(VoteStates.SMS)

# ─── REGISTRATION FLOW ───

async def start_reg_flow(msg: Message, state: FSMContext, phone: str):
    await state.update_data(phone=phone)
    await state.set_state(VoteStates.REG_NAME)
    await msg.answer(
        f"✅ <b>Telefon raqam: +{phone}</b>\n\n"
        "📋 <b>Ro'yxatdan o'tish kerak!</b>\n\n"
        "1️⃣ <b>Ism va Familiyangizni kiriting:</b>\n"
        "<i>(Masalan: Aliyev Jahongir)</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )

@router.message(VoteStates.REG_NAME, F.text)
async def reg_name(msg: Message, state: FSMContext):
    if msg.text and msg.text in ("🔙 Orqaga", "❌ Bekor qilish"):
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    
    await state.update_data(fullname=msg.text.strip())
    await state.set_state(VoteStates.REG_BIRTHDAY)
    await msg.answer(
        "2️⃣ <b>Tug'ilgan sanangizni kiriting:</b>\n"
        "<i>(Masalan: 01.01.1998)</i>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )

@router.message(VoteStates.REG_BIRTHDAY, F.text)
async def reg_birthday(msg: Message, state: FSMContext):
    if msg.text and msg.text in ("🔙 Orqaga", "❌ Bekor qilish"):
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    
    text = msg.text.strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y")
        birth_date = dt.strftime("%Y-%m-%d")
    except ValueError:
        return await msg.answer("❌ Noto'g'ri format. Iltimos, DD.MM.YYYY formatida kiriting (masalan: 01.01.1998):")
    
    await state.update_data(birth_date=birth_date)
    await state.set_state(VoteStates.REG_GENDER)
    await msg.answer("3️⃣ <b>Jinsingizni tanlang:</b>", reply_markup=kb_gender(), parse_mode="HTML")

@router.callback_query(F.data.startswith("reg_gender_"), VoteStates.REG_GENDER)
async def reg_gender(cb: CallbackQuery, state: FSMContext):
    gender = cb.data.split("_")[-1]
    await state.update_data(gender=gender)
    await state.set_state(VoteStates.REG_REGION)
    await cb.message.edit_text("4️⃣ <b>Viloyatni tanlang:</b>", reply_markup=kb_regions(), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("reg_reg_"), VoteStates.REG_REGION)
async def reg_region(cb: CallbackQuery, state: FSMContext):
    region_id = int(cb.data.split("_")[-1])
    await state.update_data(region_id=region_id)
    await state.set_state(VoteStates.REG_DISTRICT)
    await cb.message.edit_text("5️⃣ <b>Tumanni tanlang:</b>", reply_markup=kb_districts(region_id), parse_mode="HTML")
    await cb.answer()

@router.callback_query(F.data.startswith("reg_dist_"), VoteStates.REG_DISTRICT)
async def reg_district(cb: CallbackQuery, state: FSMContext):
    district_id = int(cb.data.split("_")[-1])
    await state.update_data(district_id=district_id)
    
    await cb.message.delete()
    loading = await cb.message.answer("🔄 <b>Captcha yuklanmoqda...</b>", parse_mode="HTML")
    
    res, status = await call_api("/captcha", "POST")
    if status != 200 or "captcha" not in res:
        await state.clear()
        await loading.delete()
        return await cb.message.answer("❌ Captcha yuklashda xatolik yuz berdi.", reply_markup=kb_main())

    captcha = res["captcha"]
    await state.update_data(reg_captcha_key=captcha["key"])

    solved_result = captcha.get("solved_result")
    if solved_result is not None:
        await loading.delete()
        sending = await cb.message.answer("🤖 <b>Captcha avtomatik yechildi. Ro'yxatdan o'tish ma'lumotlari yuborilmoqda...</b>", parse_mode="HTML")
        data = await state.get_data()
        
        payload = {
            "captcha_key": captcha["key"],
            "captcha_result": int(solved_result),
            "phone_number": data["phone"],
            "district_id": data["district_id"],
            "fullname": data["fullname"],
            "gender": data["gender"],
            "birth_date": data["birth_date"],
            "profession": "Xodim",
            "region_id": data["region_id"]
        }
        
        import aiohttp
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://openbudget.uz/",
            "Origin": "https://openbudget.uz"
        }
        try:
            session = await get_http_session()
            async with session.post("https://openbudget.uz/v1/register/send-otp", json=payload, headers=headers) as resp:
                res_reg = await resp.json()
                status_reg = resp.status
        except Exception as e:
            await state.clear()
            await sending.delete()
            await cb.answer()
            return await cb.message.answer(f"❌ Server xatosi: {e}", reply_markup=kb_main())

        if status_reg != 200:
            err = res_reg.get("message", "Xatolik yuz berdi.")
            await state.clear()
            await sending.delete()
            await cb.answer()
            return await cb.message.answer(f"❌ {err}", reply_markup=kb_main())

        await state.update_data(reg_otp_key=res_reg.get("otp_key") or res_reg.get("key", ""))
        await sending.edit_text(
            f"📩 <b>Registratsiya SMS kodi yuborildi!</b>\n\n"
            f"<code>{data['phone']}</code> raqamiga yuborilgan <b>6 xonali kodni</b> kiriting:",
            parse_mode="HTML"
        )
        await state.set_state(VoteStates.REG_SMS)
        await cb.answer()
        return

    try:
        image_bytes = base64.b64decode(captcha["image"].split(",")[-1])
    except Exception:
        image_bytes = base64.b64decode(captcha["image"])

    photo = BufferedInputFile(image_bytes, filename="reg_captcha.png")
    await loading.delete()
    await cb.message.answer_photo(
        photo,
        caption="6️⃣ <b>Rasmdagi raqamlarni kiriting (Registratsiya):</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await state.set_state(VoteStates.REG_CAPTCHA)
    await cb.answer()

@router.message(VoteStates.REG_CAPTCHA, F.text)
async def reg_captcha(msg: Message, state: FSMContext):
    if msg.text and msg.text in ("🔙 Orqaga", "❌ Bekor qilish"):
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    
    if not msg.text.isdigit():
        return await msg.answer("❌ Faqat rasmdagi <b>raqamlarni</b> kiriting:", parse_mode="HTML")
    
    data = await state.get_data()
    sending = await msg.answer("🔄 <b>Ro'yxatdan o'tish ma'lumotlari yuborilmoqda...</b>", parse_mode="HTML")
    
    payload = {
        "captcha_key": data["reg_captcha_key"],
        "captcha_result": int(msg.text),
        "phone_number": data["phone"],
        "district_id": data["district_id"],
        "fullname": data["fullname"],
        "gender": data["gender"],
        "birth_date": data["birth_date"],
        "profession": "Xodim",
        "region_id": data["region_id"]
    }
    
    import aiohttp
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://openbudget.uz/",
        "Origin": "https://openbudget.uz"
    }
    try:
        session = await get_http_session()
        async with session.post("https://openbudget.uz/v1/register/send-otp", json=payload, headers=headers) as resp:
            res = await resp.json()
            status = resp.status
    except Exception as e:
        await state.clear()
        await sending.delete()
        return await msg.answer(f"❌ Server xatosi: {e}", reply_markup=kb_main())

    if status != 200:
        err = res.get("message", "Xatolik yuz berdi.")
        await state.clear()
        await sending.delete()
        return await msg.answer(f"❌ {err}", reply_markup=kb_main())

    await state.update_data(reg_otp_key=res.get("otp_key") or res.get("key", ""))
    await sending.edit_text(
        "📩 <b>Registratsiya SMS kodi yuborildi!</b>\n\n"
        "Telefoningizga kelgan <b>6 xonali kodni</b> kiriting:",
        parse_mode="HTML"
    )
    await state.set_state(VoteStates.REG_SMS)

@router.message(VoteStates.REG_SMS, F.text)
async def reg_sms(msg: Message, state: FSMContext):
    if msg.text and msg.text in ("🔙 Orqaga", "❌ Bekor qilish"):
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    
    if len(msg.text) != 6 or not msg.text.isdigit():
        return await msg.answer("❌ SMS kod <b>6 xonali</b> bo'lishi kerak:", parse_mode="HTML")
    
    data = await state.get_data()
    checking = await msg.answer("🔄 <b>Kod tekshirilmoqda...</b>", parse_mode="HTML")
    
    payload = {
        "phone_number": data["phone"],
        "otp_code": msg.text,
        "otp_key": data.get("reg_otp_key", "")
    }
    
    import aiohttp
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://openbudget.uz/",
        "Origin": "https://openbudget.uz"
    }
    try:
        session = await get_http_session()
        async with session.post("https://openbudget.uz/v1/register/verify-otp", json=payload, headers=headers) as resp:
            res = await resp.json()
            status = resp.status
    except Exception as e:
        await state.clear()
        await checking.delete()
        return await msg.answer(f"❌ Server xatosi: {e}", reply_markup=kb_main())

    if status != 200:
        err = res.get("message", "SMS kod xato yoki eskirgan.")
        await state.clear()
        await checking.delete()
        return await msg.answer(f"❌ {err}", reply_markup=kb_main())

    await state.update_data(access_token=res.get("access_token"))
    
    # Muvaffaqiyatli ro'yxatdan o'tdi, darhol ovoz berish uchun 2-captcha yuklanadi
    await checking.edit_text("✅ <b>Muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n🔄 <b>Ovozni tasdiqlash uchun captcha yuklanmoqda...</b>", parse_mode="HTML")
    
    res2, status2 = await call_api("/captcha", "POST")
    if status2 != 200 or "captcha" not in res2:
        await state.clear()
        await checking.delete()
        return await msg.answer("❌ 2-captcha yuklashda xato.", reply_markup=kb_main())

    captcha2 = res2["captcha"]
    await state.update_data(captcha_key_2=captcha2["key"])

    solved_result2 = captcha2.get("solved_result")
    if solved_result2 is not None:
        await execute_cast_vote(
            msg=msg,
            state=state,
            access_token=res.get("access_token"),
            phone=data["phone"],
            captcha_key=captcha2["key"],
            captcha_result=int(solved_result2),
            waiting_msg_to_delete=checking
        )
        return

    try:
        image_bytes = base64.b64decode(captcha2["image"].split(",")[-1])
    except Exception:
        image_bytes = base64.b64decode(captcha2["image"])

    photo = BufferedInputFile(image_bytes, filename="captcha2.png")
    await checking.delete()
    await msg.answer_photo(
        photo,
        caption="🧩 <b>Ovozni tasdiqlash uchun yangi rasmdagi raqamlarni kiriting:</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await state.set_state(VoteStates.CAPTCHA_2)

# ─── Qadam 3: SMS kod ───

@router.message(VoteStates.SMS, F.text)
async def vote_sms(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if len(text) != 6 or not text.isdigit():
        return await msg.answer("❌ SMS kod <b>6 xonali</b> bo'lishi kerak:", parse_mode="HTML")

    data    = await state.get_data()
    checking = await msg.answer("🔄 <b>Kod tekshirilmoqda...</b>", parse_mode="HTML")

    res, status = await call_api("/verify-otp", "POST", {
        "phone_number": data["phone"],
        "otp_code":     text,
        "otp_key":      data["otp_key"],
    })

    if status != 200:
        err = res.get("detail", "SMS kod xato yoki eskirgan.")
        await state.clear()
        await checking.delete()
        return await msg.answer(f"❌ {err}", reply_markup=kb_main())

    await state.update_data(access_token=res.get("access_token"))

    # 2-captcha
    await checking.edit_text("🔄 <b>Ovozni tasdiqlash uchun captcha yuklanmoqda...</b>", parse_mode="HTML")
    res2, status2 = await call_api("/captcha", "POST")

    if status2 != 200 or "captcha" not in res2:
        await state.clear()
        await checking.delete()
        return await msg.answer("❌ 2-captcha yuklashda xato.", reply_markup=kb_main())

    captcha2 = res2["captcha"]
    await state.update_data(captcha_key_2=captcha2["key"])

    solved_result2 = captcha2.get("solved_result")
    if solved_result2 is not None:
        await execute_cast_vote(
            msg=msg,
            state=state,
            access_token=res.get("access_token"),
            phone=data["phone"],
            captcha_key=captcha2["key"],
            captcha_result=int(solved_result2),
            waiting_msg_to_delete=checking
        )
        return

    try:
        image_bytes = base64.b64decode(captcha2["image"].split(",")[-1])
    except Exception:
        image_bytes = base64.b64decode(captcha2["image"])

    photo = BufferedInputFile(image_bytes, filename="captcha2.png")
    await checking.delete()
    await msg.answer_photo(
        photo,
        caption="🧩 <b>Ovozni tasdiqlash uchun yangi rasmdagi raqamlarni kiriting:</b>",
        reply_markup=kb_cancel(), parse_mode="HTML"
    )
    await state.set_state(VoteStates.CAPTCHA_2)

async def execute_cast_vote(msg: Message, state: FSMContext, access_token: str, phone: str, captcha_key: str, captcha_result: int, waiting_msg_to_delete: Message = None):
    if waiting_msg_to_delete:
        try:
            await waiting_msg_to_delete.delete()
        except Exception:
            pass
    casting = await msg.answer("⚡ <b>Ovoz berilmoqda...</b>", parse_mode="HTML")
    
    res, status = await call_api("/cast-vote", "POST", {
        "project_id":   await get_setting("project_id"),
        "access_token": access_token,
        "captcha_key":  captcha_key,
        "captcha_result": captcha_result,
        "phone_number":   phone,
    })
    
    await state.clear()
    
    if status != 200:
        err = res.get("detail", "Ovoz berish muvaffaqiyatsiz tugadi.")
        await casting.delete()
        return await msg.answer(f"❌ {err}", reply_markup=kb_main())

    # ── Muvaffaqiyatli ovoz ──
    reward = int(await get_setting("voter_reward") or 1000)
    await add_vote(msg.from_user.id, phone, reward)

    u       = await get_user(msg.from_user.id)
    new_bal = u[3] if u else reward

    await casting.delete()
    await msg.answer(
        f"<tg-emoji emoji-id='5469950790893946284'>✨</tg-emoji> <b>TABRIKLAYMIZ! Ovoz muvaffaqiyatli qabul qilindi!</b> <tg-emoji emoji-id='5472164874884394982'>🔥</tg-emoji>\n\n"
        f"<tg-emoji emoji-id='5471971711481666499'>💰</tg-emoji> Sizga berilgan mukofot: <b>+{reward:,} UZS</b>\n"
        f"<tg-emoji emoji-id='5469950790893946284'>💎</tg-emoji> Yangi hamyon balansi: <b>{new_bal:,} UZS</b>\n\n"
        "Davom eting — qancha ko'p ovoz, shuncha ko'p daromad! 🚀",
        reply_markup=kb_main(), parse_mode="HTML"
    )

# ─── Qadam 4: 2-Captcha va Yakuniy Ovoz ───

@router.message(VoteStates.CAPTCHA_2, F.text)
async def vote_captcha2(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text == "❌ Bekor qilish":
        await state.clear()
        return await msg.answer("Bekor qilindi.", reply_markup=kb_main())
    if not text.isdigit():
        return await msg.answer("❌ Faqat rasmdagi <b>raqamlarni</b> kiriting:", parse_mode="HTML")

    data = await state.get_data()
    await execute_cast_vote(
        msg=msg,
        state=state,
        access_token=data["access_token"],
        phone=data["phone"],
        captcha_key=data["captcha_key_2"],
        captcha_result=int(text)
    )

# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

async def main():
    await init_db()
    dp.include_router(router)
    logger.info("🚀 Open Budget Mijoz Boti v2.0 ishga tushdi!")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        global _db_conn, _http_session
        if _db_conn:
            await _db_conn.close()
        if _http_session and not _http_session.closed:
            await _http_session.close()

if __name__ == "__main__":
    asyncio.run(main())
