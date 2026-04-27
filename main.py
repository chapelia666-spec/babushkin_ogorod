import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiosqlite

logging.basicConfig(level=logging.INFO)

bot = Bot(token="8706567904:AAEfCZPdKpHN0qaPUFRlmUZ22zNJs5hhjEE", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

DB = "ogorod.db"

# ====================== БАЗА ДАННЫХ ======================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                tap_power INTEGER DEFAULT 1,
                energy INTEGER DEFAULT 1000,
                max_energy INTEGER DEFAULT 1000,
                profit_per_hour INTEGER DEFAULT 0,
                last_save TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                combo_streak INTEGER DEFAULT 0,
                last_combo DATE
            );
            
            CREATE TABLE IF NOT EXISTS upgrades (
                user_id INTEGER,
                name TEXT,
                level INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, name)
            );
        ''')
        await db.commit()

# ====================== УЛУЧШЕНИЯ ======================
UPGRADES = {
    "лопата": {"name": "🔨 Лопата", "base_cost": 100, "power": 5},
    "поливалка": {"name": "💧 Поливалка", "base_cost": 300, "power": 15},
    "куры": {"name": "🐔 Куры", "base_cost": 1000, "power": 60},
    "корова": {"name": "🐄 Корова", "base_cost": 5000, "power": 300},
    "трактор": {"name": "🚜 Трактор", "base_cost": 25000, "power": 1500},
    "теплица": {"name": "🏡 Теплица", "base_cost": 100000, "power": 8000},
}

async def get_user_data(user_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                return {"balance":0, "tap_power":1, "energy":1000, "max_energy":1000, "profit_per_hour":0, "combo_streak":0}
            return dict(zip([c[0] for c in cur.description], row))

async def save_user(user_id: int, data: dict):
    async with aiosqlite.connect(DB) as db:
        await db.execute('''
            UPDATE users SET balance=?, tap_power=?, energy=?, max_energy=?, 
            profit_per_hour=?, combo_streak=?, last_save=CURRENT_TIMESTAMP 
            WHERE user_id=?
        ''', (data["balance"], data["tap_power"], data["energy"], 
              data["max_energy"], data["profit_per_hour"], data["combo_streak"], user_id))
        await db.commit()

# ====================== КЛАВИАТУРЫ ======================
def main_menu():
    kb = [
        [InlineKeyboardButton(text="🌱 Тапнуть!", callback_data="tap")],
        [InlineKeyboardButton(text="🛒 Улучшения", callback_data="upgrades")],
        [InlineKeyboardButton(text="⚡ Бусты", callback_data="boosts")],
        [InlineKeyboardButton(text="👥 Друзья (+капустинки)", callback_data="referral")],
        [InlineKeyboardButton(text="🔥 Ежедневный комбо", callback_data="combo")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ====================== ХЕНДЛЕРЫ ======================
@dp.message(Command("start"))
async def start(msg: Message):
    await init_db()
    await msg.answer(
        "🌾 <b>Добро пожаловать в Бабушкин Огород!</b>\n\n"
        "Тапай по бабушке, собирай капустинки, покупай улучшения и стань самым богатым фермером в деревне! 🥬",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "tap")
async def tap_handler(call: CallbackQuery):
    user = await get_user_data(call.from_user.id)
    if user["energy"] <= 0:
        await call.answer("Энергия закончилась! Подожди немного ⏳", show_alert=True)
        return

    earn = user["tap_power"]
    user["balance"] += earn
    user["energy"] -= 1

    await save_user(call.from_user.id, user)

    await call.answer(f"+{earn} 🥬", show_alert=False)
    await call.message.edit_text(
        f"🥬 <b>Баланс:</b> {user['balance']:,} капустинок\n"
        f"⚡ Энергия: {user['energy']}/{user['max_energy']}\n"
        f"💪 Мощность тапа: {user['tap_power']}\n"
        f"📈 Прибыль в час: {user['profit_per_hour']}",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "upgrades")
async def upgrades_handler(call: CallbackQuery):
    user = await get_user_data(call.from_user.id)
    text = f"🛒 <b>Улучшения Бабушкиного Огорода</b>\n🥬 Баланс: {user['balance']:,}\n\n"

    kb = []
    for key, up in UPGRADES.items():
        level = 0  # можно добавить таблицу уровней позже
        cost = up["base_cost"] * (level + 1) ** 2
        kb.append([InlineKeyboardButton(
            text=f"{up['name']} (ур. {level+1}) — {cost} 🥬",
            callback_data=f"buy_{key}"
        )])
    kb.append([InlineKeyboardButton(text="← Назад", callback_data="back")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("buy_"))
async def buy_upgrade(call: CallbackQuery):
    key = call.data[4:]
    if key not in UPGRADES:
        return
    user = await get_user_data(call.from_user.id)
    up = UPGRADES[key]
    cost = up["base_cost"]  # упрощённо

    if user["balance"] >= cost:
        user["balance"] -= cost
        user["profit_per_hour"] += up["power"]
        await save_user(call.from_user.id, user)
        await call.answer(f"Куплено {up['name']}! +{up['power']} в час", show_alert=True)
        await upgrades_handler(call)
    else:
        await call.answer("Не хватает капустинок! 🌱", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await call.message.edit_text("Главное меню", reply_markup=main_menu())

# Пассивный доход каждые 60 секунд (можно в отдельном таске)
async def passive_income():
    while True:
        await asyncio.sleep(60)
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT user_id, profit_per_hour FROM users") as cur:
                async for row in cur:
                    if row[1] > 0:
                        add = row[1] // 60
                        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (add, row[0]))
            await db.commit()

# Запуск
async def main():
    await init_db()
    asyncio.create_task(passive_income())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())