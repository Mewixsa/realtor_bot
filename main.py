import asyncio
import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8979887985:AAH4ncXa3H7Du7ekrrRdPqS0UJFaszGO4rw"
ADMIN_ID = 5270819992  # Ваш Telegram ID из @userinfobot

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Локальная база данных
DB_PATH = "leads.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            telegram TEXT,
            goal TEXT,
            contact TEXT,
            status TEXT DEFAULT 'new'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ОБРАБОТКА ТЕЛЕГРАМ БОТА ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📥 Активные заявки")]],
        resize_keyboard=True
    )
    await message.answer("Панель управления заявками:", reply_markup=kb)

@dp.message(lambda msg: msg.text == "📥 Активные заявки" or msg.text == "/leads")
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

@dp.callback_query(lambda c: c.data.startswith('done_'))
async def process_done(callback: types.CallbackQuery):
    lead_id = callback.data.split('_')[1]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status='done' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()

    await callback.message.edit_text(f"<s>Заявка #{lead_id} выполнена</s>", parse_mode="HTML")
    await callback.answer("Заявка выполнена!")

# --- ВЕБ-СЕРВЕР ДЛЯ ПРИЕМА ЗАЯВОК ---

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

async def main():
    app = web.Application()
    app.router.add_post('/api/lead', handle_web_lead)
    
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