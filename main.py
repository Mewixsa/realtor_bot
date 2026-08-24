import asyncio
import os
import sqlite3
from aiohttp import web
import aiohttp_cors
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5270819992"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_PATH = "leads.db"

# Состояния для добавления квартиры
class AddProperty(StatesGroup):
    title = State()
    price = State()
    description = State()
    photo_url = State()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Таблица заявок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, phone TEXT, telegram TEXT, goal TEXT, contact TEXT, status TEXT DEFAULT 'new'
        )
    ''')
    # Таблица квартир
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            description TEXT,
            photo_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Заявки"), KeyboardButton(text="🏢 Квартиры")]
        ],
        resize_keyboard=True
    )

# --- ТЕЛЕГРАМ БОТ ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👋 **Добро пожаловать в панель управления!**\n\nВыберите нужный раздел в меню ниже:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# --- ЗАЯВКИ ---
@dp.message(F.text == "📥 Заявки")
async def show_leads(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, phone, telegram, goal, contact FROM leads WHERE status='new'")
    leads = cursor.fetchall()
    conn.close()

    if not leads:
        await message.answer("🎉 Активных заявок нет!")
        return

    for lead in leads:
        lead_id, name, phone, tg, goal, contact = lead
        text = (
            f"<b>Заявка #{lead_id}</b>\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"📞 <b>Тел:</b> {phone}\n"
            f"✈️ <b>TG:</b> {tg}\n"
            f"🎯 <b>Цель:</b> {goal}\n"
            f"💬 <b>Связь:</b> {contact}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено (Удалить)", callback_data=f"done_{lead_id}")]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.startswith('done_'))
async def process_done(callback: types.CallbackQuery):
    lead_id = callback.data.split('_')[1]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status='done' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"<s>Заявка #{lead_id} выполнена</s>", parse_mode="HTML")
    await callback.answer("Заявка выполнена!")

# --- КВАРТИРЫ ---
@dp.message(F.text == "🏢 Квартиры")
async def show_properties_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить квартиру", callback_data="add_property")],
        [InlineKeyboardButton(text="📋 Список всех квартир", callback_data="list_properties")]
    ])
    await message.answer("🏢 **Управление квартирами:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "list_properties")
async def list_properties(callback: types.CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, price FROM properties")
    props = cursor.fetchall()
    conn.close()

    if not props:
        await callback.message.answer("📭 Список квартир пуст.")
        await callback.answer()
        return

    for prop_id, title, price in props:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_prop_{prop_id}")]
        ])
        await callback.message.answer(f"🏠 **{title}**\n💰 Цена: {price}", parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("del_prop_"))
async def delete_property(callback: types.CallbackQuery):
    prop_id = callback.data.split("_")[2]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM properties WHERE id=?", (prop_id,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text("❌ Квартира удалена!")
    await callback.answer("Удалено!")

# --- Пошаговое добавление квартиры ---
@dp.callback_query(F.data == "add_property")
async def start_add_property(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddProperty.title)
    await callback.message.answer("Введите **название объекта** (например: *2-к квартира, 65 м²*):", parse_mode="Markdown")
    await callback.answer()

@dp.message(AddProperty.title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddProperty.price)
    await message.answer("Введите **стоимость** (например: *15 000 000 ₽*):", parse_mode="Markdown")

@dp.message(AddProperty.price)
async def process_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(AddProperty.description)
    await message.answer("Введите **краткое описание** объекта:")

@dp.message(AddProperty.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddProperty.photo_url)
    await message.answer("Отправьте **ссылку на фото** (или отправьте любой текст, если фото пока нет):")

@dp.message(AddProperty.photo_url)
async def process_photo(message: types.Message, state: FSMContext):
    photo_url = message.text
    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO properties (title, price, description, photo_url) VALUES (?, ?, ?, ?)",
        (data['title'], data['price'], data['description'], photo_url)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ **Квартира успешно добавлена на сайт!**", parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР (API) ---

async def handle_get_check(request):
    return web.Response(text="Server is running!")

# Отправка заявок с сайта
async def handle_web_lead(request):
    try:
        data = await request.json()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO leads (name, phone, telegram, goal, contact) VALUES (?, ?, ?, ?, ?)",
            (data.get('name'), data.get('phone'), data.get('telegram'), data.get('goal'), data.get('contact'))
        )
        lead_id = cursor.lastrowid
        conn.commit()
        conn.close()

        text = (
            f"⚡️ <b>НОВАЯ ЗАЯВКА #{lead_id}!</b>\n\n"
            f"👤 <b>Имя:</b> {data.get('name')}\n"
            f"📞 <b>Телефон:</b> {data.get('phone')}\n"
            f"✈️ <b>Telegram:</b> {data.get('telegram')}\n"
            f"🎯 <b>Цель:</b> {data.get('goal')}\n"
            f"💬 <b>Связь:</b> {data.get('contact')}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done_{lead_id}")]
        ])
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=kb)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

# Получение квартир для отображения на сайте
async def handle_get_properties(request):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, price, description, photo_url FROM properties")
    rows = cursor.fetchall()
    conn.close()

    properties = [
        {
            "id": row[0],
            "title": row[1],
            "price": row[2],
            "description": row[3],
            "photo_url": row[4]
        }
        for row in rows
    ]
    return web.json_response(properties)

async def main():
    app = web.Application()

    app.router.add_get('/', handle_get_check)
    app.router.add_get('/api/lead', handle_get_check)
    app.router.add_post('/api/lead', handle_web_lead)
    
    # Новое API для сайта
    app.router.add_get('/api/properties', handle_get_properties)

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })

    for resource in list(app.router.resources()):
        cors.add(resource)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await asyncio.gather(
        site.start(),
        dp.start_polling(bot)
    )

if __name__ == '__main__':
    asyncio.run(main())
