import asyncio
import html
import os
import sqlite3
from urllib.parse import urlparse
import aiohttp
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

class AddProperty(StatesGroup):
    title = State()
    price = State()
    address = State()
    area = State()
    floor = State()
    deadline = State()
    photo = State()


class AddCase(StatesGroup):
    title = State()
    location = State()
    goal = State()
    photo = State()
    story = State()
    result = State()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, phone TEXT, telegram TEXT, goal TEXT, contact TEXT, status TEXT DEFAULT 'new'
        )
    ''')
    # Обновленная таблица с подробными характеристиками
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            address TEXT,
            area TEXT,
            floor TEXT,
            deadline TEXT,
            photo_url TEXT,
            photo_file_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            location TEXT NOT NULL,
            goal TEXT NOT NULL,
            photo_url TEXT,
            photo_file_id TEXT,
            story TEXT NOT NULL,
            result TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for table in ('properties', 'cases'):
        columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
        if 'photo_file_id' not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN photo_file_id TEXT")
    conn.commit()
    conn.close()

init_db()

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Заявки"), KeyboardButton(text="🏢 Квартиры")],
            [KeyboardButton(text="📚 Кейсы")]
        ],
        resize_keyboard=True
    )

# --- БОТ ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👋 Панель управления:", reply_markup=get_main_keyboard())

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
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done_{lead_id}")]
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

@dp.message(F.text == "📚 Кейсы")
async def show_cases_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кейс", callback_data="add_case")],
        [InlineKeyboardButton(text="📋 Список кейсов", callback_data="list_cases")],
    ])
    await message.answer("📚 <b>Кейсы клиентов (без имён)</b>", parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "add_case")
async def start_add_case(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AddCase.title)
    await callback.message.answer("1️⃣ Заголовок кейса (например: «Квартира для молодой семьи»):")
    await callback.answer()


@dp.message(AddCase.title)
async def case_title(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddCase.location)
    await message.answer("2️⃣ Город или жилой комплекс:")


@dp.message(AddCase.location)
async def case_location(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(location=(message.text or "").strip())
    await state.set_state(AddCase.goal)
    await message.answer("3️⃣ Запрос клиента и какая квартира нужна (без имени и личных данных):")


@dp.message(AddCase.goal)
async def case_goal(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(goal=(message.text or "").strip())
    await state.set_state(AddCase.photo)
    await message.answer("4️⃣ Отправьте фотографию квартиры/объекта или пришлите ссылку. Напишите «пропустить», если без фото.")


@dp.message(AddCase.photo)
async def case_photo(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    photo_url = ""
    photo_file_id = ""
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text and message.text.strip().lower() != "пропустить":
        photo_url = message.text.strip()
    await state.update_data(photo_url=photo_url, photo_file_id=photo_file_id)
    await state.set_state(AddCase.story)
    await message.answer("5️⃣ Краткая история подбора и сделки. Не указывайте имя или контакты клиента:")


@dp.message(AddCase.story)
async def case_story(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(story=(message.text or "").strip())
    await state.set_state(AddCase.result)
    await message.answer("6️⃣ Результат: что подобрали и чем завершилась история?")


@dp.message(AddCase.result)
async def case_result(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    result = (message.text or "").strip()
    data = await state.get_data()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, location, goal, photo_url, photo_file_id, story, result, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'published')",
        (data["title"], data["location"], data["goal"], data.get("photo_url", ""), data.get("photo_file_id", ""), data["story"], result),
    )
    case_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(f"✅ Кейс #{case_id} опубликован на сайте. Данные клиентов не публикуются.")


@dp.callback_query(F.data == "list_cases")
async def list_cases(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, location, status FROM cases ORDER BY id DESC")
    cases = cursor.fetchall()
    conn.close()
    if not cases:
        await callback.message.answer("📭 Кейсов пока нет.")
    for case_id, title, location, status in cases:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_case_{case_id}")
        ]])
        state_label = "На сайте" if status == "published" else "Черновик"
        await callback.message.answer(
            f"<b>Кейс #{case_id}: {html.escape(title)}</b>\n{html.escape(location)} · {state_label}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("del_case_"))
async def delete_case(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    case_id = callback.data.rsplit("_", 1)[-1]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    await callback.message.edit_text("🗑 Кейс удалён." if deleted else "Кейс не найден.")
    await callback.answer()


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
        await callback.message.answer(f"🏠 **{title}**\n💰 {price}", parse_mode="Markdown", reply_markup=kb)
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

# --- ПОШАГОВЫЙ ОПРОС ---

@dp.callback_query(F.data == "add_property")
async def start_add_property(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddProperty.title)
    await callback.message.answer("1️⃣ Введите **название** (напр.: *1-к квартира, 42 м²*):", parse_mode="Markdown")
    await callback.answer()

@dp.message(AddProperty.title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddProperty.price)
    await message.answer("2️⃣ Введите **стоимость** (напр.: *12 500 000 ₽*):", parse_mode="Markdown")

@dp.message(AddProperty.price)
async def process_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await state.set_state(AddProperty.address)
    await message.answer("3️⃣ Введите **ЖК или адрес** (напр.: *ЖК «Светлый берег», корпус 2*):", parse_mode="Markdown")

@dp.message(AddProperty.address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(AddProperty.area)
    await message.answer("4️⃣ Введите **площадь** (напр.: *42 м²*):", parse_mode="Markdown")

@dp.message(AddProperty.area)
async def process_area(message: types.Message, state: FSMContext):
    await state.update_data(area=message.text)
    await state.set_state(AddProperty.floor)
    await message.answer("5️⃣ Введите **этаж** (напр.: *8/24*):", parse_mode="Markdown")

@dp.message(AddProperty.floor)
async def process_floor(message: types.Message, state: FSMContext):
    await state.update_data(floor=message.text)
    await state.set_state(AddProperty.deadline)
    await message.answer("6️⃣ Введите **срок сдачи** (напр.: *IV кв. 2026* или *Сдан*):", parse_mode="Markdown")

@dp.message(AddProperty.deadline)
async def process_deadline(message: types.Message, state: FSMContext):
    await state.update_data(deadline=message.text)
    await state.set_state(AddProperty.photo)
    await message.answer("7️⃣ Отправьте **фотографию** объекта (или ссылку):", parse_mode="Markdown")

@dp.message(AddProperty.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo_url = ""
    photo_file_id = ""
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text:
        photo_url = message.text.strip()

    data = await state.get_data()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO properties (title, price, address, area, floor, deadline, photo_url, photo_file_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (data['title'], data['price'], data['address'], data['area'], data['floor'], data['deadline'], photo_url, photo_file_id)
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ **Квартира успешно добавлена на сайт!**", parse_mode="Markdown")

# --- API СЕРВЕРА ---

async def handle_get_check(request):
    return web.Response(text="Server is running!")

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

async def handle_get_properties(request):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, price, address, area, floor, deadline, photo_url, photo_file_id FROM properties")
    rows = cursor.fetchall()
    conn.close()

    properties = []
    for row in rows:
        photo_url = row[7] or ""
        photo_file_id = row[8] or ""
        parsed_photo_url = urlparse(photo_url)
        if photo_file_id or (parsed_photo_url.hostname == "api.telegram.org" and parsed_photo_url.path.startswith("/file/bot")):
            # Ask Telegram for a fresh download URL; file URLs are temporary.
            photo_url = f"/api/property-photo/{row[0]}"

        properties.append({
            "id": row[0],
            "title": row[1],
            "price": row[2],
            "address": row[3],
            "area": row[4],
            "floor": row[5],
            "deadline": row[6],
            "photo_url": photo_url,
        })

    return web.json_response(properties)


async def handle_get_cases(request):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, location, goal, photo_url, story, result, photo_file_id FROM cases WHERE status = 'published' ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    cases = []
    for row in rows:
        photo_url = row[4] or ""
        photo_file_id = row[7] or ""
        parsed_photo_url = urlparse(photo_url)
        if photo_file_id or (parsed_photo_url.hostname == "api.telegram.org" and parsed_photo_url.path.startswith("/file/bot")):
            photo_url = f"/api/case-photo/{row[0]}"
        cases.append({
            "id": row[0],
            "title": row[1],
            "location": row[2],
            "goal": row[3],
            "photo_url": photo_url,
            "story": row[5],
            "result": row[6],
        })
    return web.json_response(cases)


async def get_photo_download_url(file_id):
    """Resolve a stable Telegram file_id into a fresh temporary download URL."""
    telegram_file = await bot.get_file(file_id)
    if not telegram_file.file_path:
        raise web.HTTPBadGateway(text="Telegram did not return a photo path")
    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{telegram_file.file_path}"


async def handle_case_photo(request):
    case_id = request.match_info["case_id"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT photo_url, photo_file_id FROM cases WHERE id = ? AND status = 'published'", (case_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not (row[0] or row[1]):
        raise web.HTTPNotFound()
    photo_url, file_id = row
    if file_id:
        photo_url = await get_photo_download_url(file_id)
    parsed_photo_url = urlparse(photo_url)
    expected_prefix = f"/file/bot{BOT_TOKEN}/"
    is_telegram_file = (parsed_photo_url.scheme == "https" and parsed_photo_url.hostname == "api.telegram.org"
                        and parsed_photo_url.path.startswith(expected_prefix))
    if not file_id and not is_telegram_file:
        raise web.HTTPNotFound()
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(photo_url, allow_redirects=True) as response:
                if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                    raise web.HTTPBadGateway(text="Could not retrieve case photo")
                body = await response.content.read(12 * 1024 * 1024 + 1)
                if len(body) > 12 * 1024 * 1024:
                    raise web.HTTPBadGateway(text="Case photo is too large")
                return web.Response(
                    body=body,
                    content_type=response.headers["Content-Type"].split(";", 1)[0],
                    headers={"Cache-Control": "public, max-age=3600"},
                )
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        raise web.HTTPBadGateway(text="Could not retrieve case photo") from error


async def handle_property_photo(request):
    property_id = request.match_info["property_id"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT photo_url, photo_file_id FROM properties WHERE id = ?", (property_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not (row[0] or row[1]):
        raise web.HTTPNotFound()

    photo_url, file_id = row
    if file_id:
        photo_url = await get_photo_download_url(file_id)
    parsed_photo_url = urlparse(photo_url)
    expected_prefix = f"/file/bot{BOT_TOKEN}/"
    is_telegram_file = (
        parsed_photo_url.scheme == "https"
        and parsed_photo_url.hostname == "api.telegram.org"
        and parsed_photo_url.path.startswith(expected_prefix)
    )
    if not file_id and not is_telegram_file:
        raise web.HTTPNotFound()

    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(photo_url, allow_redirects=True) as response:
                if response.status != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                    raise web.HTTPBadGateway(text="Could not retrieve property photo")
                body = await response.content.read(12 * 1024 * 1024 + 1)
                if len(body) > 12 * 1024 * 1024:
                    raise web.HTTPBadGateway(text="Property photo is too large")
                return web.Response(
                    body=body,
                    content_type=response.headers["Content-Type"].split(";", 1)[0],
                    headers={"Cache-Control": "public, max-age=3600"},
                )
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        raise web.HTTPBadGateway(text="Could not retrieve property photo") from error

async def main():
    app = web.Application()

    app.router.add_get('/', handle_get_check)
    app.router.add_get('/api/lead', handle_get_check)
    app.router.add_post('/api/lead', handle_web_lead)
    app.router.add_get('/api/properties', handle_get_properties)
    app.router.add_get('/api/property-photo/{property_id}', handle_property_photo)
    app.router.add_get('/api/cases', handle_get_cases)
    app.router.add_get('/api/case-photo/{case_id}', handle_case_photo)

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