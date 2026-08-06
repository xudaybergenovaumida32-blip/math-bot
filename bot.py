import asyncio
import csv
import io
import json
import os
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, BufferedInputFile, ReplyKeyboardMarkup, 
    KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

API_TOKEN = "8975832001:AAF82sH4YnODYNSF32bVAVLkbDl5t13jWMQ"
ADMIN_ID = 8151686416                     
GROUP_IDS = [-5490289085, -5403695064]                

DATA_FILE = "bot_data.json"

TEST_DATA = {}          
STUDENTS_DATA = {}          
STUDENT_TO_NAME = {}        
PARENT_USERNAME_TO_ID = {}  
WRONG_STATS = {}
STUDENT_RESULTS = {}
STUDENT_TEST_START = {}
STUDENT_SESSION = {}     

DEADLINE_TIME = None         
LESSON_TIME = "09:00"        
TEST_DURATION_MINUTES = None 

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# O'quvchini bosqichma-bosqich qo'shish uchun holatlar (FSM)
class AddStudentStates(StatesGroup):
    waiting_for_full_name = State()       
    waiting_for_student_username = State() 
    waiting_for_group = State()            
    waiting_for_parent_username = State() 

# Viktorina shaklida test qo'shish uchun FSM holatlari
class AddTestStates(StatesGroup):
    waiting_for_pack_name = State()       # To'plam nomi (Mavzu)
    waiting_for_question_text = State()   # Savol matni
    waiting_for_option = State()          # Variantlarni bittalab yuborish
    waiting_for_correct_answer = State()  # To'g'ri javobni tanlash (Inline-tugma orqali)

def save_data():
    data = {
        "tests": TEST_DATA,
        "students": STUDENTS_DATA,
        "student_to_name": STUDENT_TO_NAME,
        "parent_username_to_id": PARENT_USERNAME_TO_ID,
        "wrong_stats": WRONG_STATS,
        "student_results": STUDENT_RESULTS
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_data():
    global TEST_DATA, STUDENTS_DATA, STUDENT_TO_NAME, PARENT_USERNAME_TO_ID, WRONG_STATS, STUDENT_RESULTS
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                raw_tests = data.get("tests", {})
                formatted_tests = {}
                for pack_name, tests_dict in raw_tests.items():
                    formatted_tests[pack_name] = {int(k): v for k, v in tests_dict.items()}
                TEST_DATA.update(formatted_tests)

                STUDENTS_DATA.update({int(k): v for k, v in data.get("students", {}).items()})
                STUDENT_TO_NAME.update(data.get("student_to_name", {}))
                PARENT_USERNAME_TO_ID.update(data.get("parent_username_to_id", {}))
                WRONG_STATS.update(data.get("wrong_stats", {}))
                STUDENT_RESULTS.update({int(k): v for k, v in data.get("student_results", {}).items()})
        except Exception as e:
            logging.error(f"Ma'lumotlarni yuklashda xatolik: {e}")

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 ТОП учеников"), KeyboardButton(text="📥 Excel отчет")],
            [KeyboardButton(text="⚙️ Управление временем"), KeyboardButton(text="📋 Список тестов")],
            [KeyboardButton(text="👨‍🎓 Управление учениками"), KeyboardButton(text="📊 Статистика ошибок")],
            [KeyboardButton(text="📢 Рассылка сообщений")]
        ],
        resize_keyboard=True
    )

def get_time_settings_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏰ Установить дедлайн", callback_data="set_dl"),
             InlineKeyboardButton(text="🔓 Снять дедлайн", callback_data="off_dl")],
            [InlineKeyboardButton(text="🔔 Время урока", callback_data="set_less"),
             InlineKeyboardButton(text="🔕 Откл. урок", callback_data="off_less")],
            [InlineKeyboardButton(text="⏱️ Время на тест", callback_data="set_t_time"),
             InlineKeyboardButton(text="🔓 Откл. тест-тайм", callback_data="off_t_time")]
        ]
    )

def get_students_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍🎓 Список учеников", callback_data="list_students")],
            [InlineKeyboardButton(text="➕ Добавить ученика", callback_data="start_add_student")],
            [InlineKeyboardButton(text="🗑️ Удалить", callback_data="help_del_student")]
        ]
    )

def get_test_navigation_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Следующий вопрос"), KeyboardButton(text="⏭ Пропустить")]
        ],
        resize_keyboard=True
    )

async def check_lesson_schedule():
    global LESSON_TIME
    while True:
        await asyncio.sleep(30)
        if LESSON_TIME:
            current_time = datetime.now().strftime("%H:%M")
            if current_time == LESSON_TIME:
                reminder_text = (
                    "⏰ **ВНИМАНИЕ! ОБЪЯВЛЕНИЕ!**\n\n"
                    f"📚 Уважаемые ученики и родители, настало время урока (`{LESSON_TIME}`)!\n"
                    "Просим всех подготовиться к уроку! 🚀"
                )
                for g_id in GROUP_IDS:
                    try:
                        await bot.send_message(chat_id=g_id, text=reminder_text, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Ошибка ({g_id}): {e}")
                await asyncio.sleep(60)

@dp.message(F.text == "⚙️ Управление временем")
async def menu_time_settings(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    status_text = (
        "⚙️ **УПРАВЛЕНИЕ ВРЕМЕНЕМ И ДЕДЛАЙНАМИ**\n\n"
        f"• Дедлайн домашнего задания: `{DEADLINE_TIME or 'Не установлен'}`\n"
        f"• Время урока: `{LESSON_TIME or 'Не установлено'}`\n"
        f"• Время на тест: `{TEST_DURATION_MINUTES or 'Без ограничений'} мин.`\n\n"
        "Нажмите нужную кнопку:"
    )
    await message.answer(status_text, parse_mode="Markdown", reply_markup=get_time_settings_keyboard())

@dp.message(F.text == "👨‍🎓 Управление учениками")
async def menu_students_management(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👨‍🎓 **УПРАВЛЕНИЕ БАЗОЙ УЧЕНИКОВ**\n\n"
        "Yangi o'quvchi qo'shish uchun tugmani bosing.",
        parse_mode="Markdown",
        reply_markup=get_students_menu_keyboard()
    )

@dp.callback_query(F.data == "start_add_student")
async def callback_start_add_student(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "1️⃣ **1-etap:** O'quvchining **F.I.O (Familyasi ismi)**ni yuboring (Masalan: `Содиқов Анвар`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_full_name)
    await callback.answer()

@dp.message(AddStudentStates.waiting_for_full_name)
async def process_student_fullname(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    await message.answer(
        f"✅ F.I.O qabul qilindi: `{full_name}`\n\n"
        "2️⃣ **2-etap:** O'quvchining Telegram **username**ini yuboring (masalan: `@anvar_student`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_student_username)

@dp.message(AddStudentStates.waiting_for_student_username)
async def process_student_username(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    s_username = message.text.strip()
    if not s_username.startswith("@"):
        await message.answer("⚠️ Username `@` belgisi bilan boshlanishi kerak! Qaytadan kiriting:")
        return
    await state.update_data(student_username=s_username)
    await message.answer(
        f"✅ O'quvchi username qabul qilindi: `{s_username}`\n\n"
        "3️⃣ **3-etap:** O'quvchining **guruh raqami**ni yuboring (masalan: `10-А`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_group)

@dp.message(AddStudentStates.waiting_for_group)
async def process_student_group(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    group_num = message.text.strip()
    await state.update_data(group_num=group_num)
    await message.answer(
        f"✅ Guruh qabul qilindi: `{group_num}`\n\n"
        "4️⃣ **4-etap:** Ota yoki onasining Telegram **username**ini yuboring (masalan: `@ota_username`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_parent_username)

@dp.message(AddStudentStates.waiting_for_parent_username)
async def process_parent_username(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    parent_username = message.text.strip()
    if not parent_username.startswith("@"):
        await message.answer("⚠️ Ota-ona username `@` belgisi bilan boshlanishi kerak! Qaytadan kiriting:")
        return

    data = await state.get_data()
    student_username = data.get("student_username")

    if parent_username.lower() == student_username.lower():
        await message.answer("❌ **Xatolik!** O'quvchining username'i va ota-onaning username'i bir xil bo'lishi mumkin emas! Iltimos, ota-onaning boshqa username'ini kiriting:")
        return

    student_name = data.get("full_name")
    group_num = data.get("group_num")

    STUDENT_TO_NAME[student_name] = {
        "group": group_num,
        "student_username": student_username,
        "parent_username": parent_username,
        "user_id": None
    }
    save_data()
    await state.clear()

    await message.answer(
        f"🎉 **O'quvchi va ota-onasi muvaffaqiyatli qo'shildi!**\n\n"
        f"👤 F.I.O: `{student_name}`\n"
        f"🎓 O'quvchi: `{student_username}`\n"
        f"🏷️ Guruh: `{group_num}`\n"
        f"👩‍👦 Ota-ona: `{parent_username}`",
        parse_mode="Markdown"
    )

@dp.message(Command("broadcast"))
async def broadcast_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        text_to_send = message.text.split(" ", 1)[1].strip()
    except Exception:
        await message.answer("⚠️ Ошибка! Введите текст сообщения:\n`/broadcast Привет, ученики!`", parse_mode="Markdown")
        return

    count = 0
    for u_id in STUDENTS_DATA.keys():
        try:
            await bot.send_message(chat_id=u_id, text=f"📢 **Сообщение от учителя:**\n\n{text_to_send}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await message.answer(f"✅ Сообщение успешно отправлено **{count}** ученикам!")

@dp.callback_query(F.data.in_(["set_dl", "set_less", "set_t_time", "help_del_student", "start_add_test"]))
async def inline_actions_handler(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Только для администратора!", show_alert=True)
        return
    
    if callback.data == "set_dl":
        await callback.message.answer("✍️ `/set_deadline 21:00`", parse_mode="Markdown")
    elif callback.data == "set_less":
        await callback.message.answer("✍️ `/set_lesson_time 14:00`", parse_mode="Markdown")
    elif callback.data == "set_t_time":
        await callback.message.answer("✍️ `/set_test_time 30`", parse_mode="Markdown")
    elif callback.data == "help_del_student":
        await callback.message.answer("🗑️ **Для удаления:**\n`/del_student Содиқов Анвар`", parse_mode="Markdown")
    elif callback.data == "start_add_test":
        await callback.message.answer(
            "📝 **Viktorina testini yaratish:**\nIltimos, yangi test uchun **mavzu (to'plam) nomini** kiriting (masalan: `n1` yoki `Matematika-1`):",
            parse_mode="Markdown"
        )
        await state.set_state(AddTestStates.waiting_for_pack_name)
    
    await callback.answer()

# --- VIKTORINA (QUIZ) USULIDA TEST QO'SHISH JARAYONI ---

@dp.message(AddTestStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    pack_name = message.text.strip()
    await state.update_data(pack_name=pack_name, questions_list=[])
    await message.answer(
        f"✅ Mavzu nomi saqlandi: `{pack_name}`\n\n"
        "1️⃣ Endi **1-savol matnini** yuboring:",
        parse_mode="Markdown"
    )
    await state.set_state(AddTestStates.waiting_for_question_text)

@dp.message(AddTestStates.waiting_for_question_text)
async def process_question_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    q_text = message.text.strip()
    await state.update_data(current_question=q_text, current_options=[])
    await message.answer(
        f"✅ Savol qabul qilindi: *{q_text}*\n\n"
        "Endi ushbu savol uchun **variantlarni bittalab yuboring** (Har bir variantni alohida xabar qilib yuboring).\n"
        "Barcha variantlarni kiritib bo'lgach, pastdagi tugmani bosing:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Variantlarni kiritib bo'ldim", callback_data="finish_options")]
        ])
    )
    await state.set_state(AddTestStates.waiting_for_option)

@dp.message(AddTestStates.waiting_for_option)
async def process_option_input(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    option_text = message.text.strip()
    data = await state.get_data()
    options = data.get("current_options", [])
    
    options.append(option_text)
    await state.update_data(current_options=options)
    
    opts_str = "\n".join([f"{i+1}) {opt}" for i, opt in enumerate(options)])
    await message.answer(
        f"➕ Variant qo'shildi!\n\n**Hozirgi variantlar:**\n{opts_str}\n\n"
        "Keyingi variantni yuboring yoki tugmani bosing:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Variantlarni kiritib bo'ldim", callback_data="finish_options")]
        ])
    )

@dp.callback_query(F.data == "finish_options", AddTestStates.waiting_for_option)
async def finish_options_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    options = data.get("current_options", [])
    
    if len(options) < 2:
        await callback.message.answer("⚠️ Kamida 2 ta variant kiritishingiz kerak!")
        await callback.answer()
        return

    # To'g'ri javobni tanlash uchun inline tugmalarni tuzamiz
    inline_kb = []
    for i, opt in enumerate(options):
        inline_kb.append([InlineKeyboardButton(text=f"{i+1}) {opt}", callback_data=f"correct_opt_{i}")])
    
    await callback.message.edit_text(
        "🎯 Ajoyib! Endi bu variantlar ichidan **to'g'ri javobni** tanlang (bitta tugmani bosing):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb)
    )
    await state.set_state(AddTestStates.waiting_for_correct_answer)
    await callback.answer()

@dp.callback_query(F.data.startswith("correct_opt_"), AddTestStates.waiting_for_correct_answer)
async def process_correct_answer_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    idx = int(callback.data.split("_")[2])
    data = await state.get_data()
    pack_name = data.get("pack_name")
    q_text = data.get("current_question")
    options = data.get("current_options")
    correct_ans = options[idx]

    if pack_name not in TEST_DATA:
        TEST_DATA[pack_name] = {}
    
    next_num = len(TEST_DATA[pack_name]) + 1
    TEST_DATA[pack_name][next_num] = {
        "question": q_text,
        "options": options,
        "ans": correct_ans,
        "solution": "Viktorina testi"
    }
    save_data()

    await callback.message.edit_text(
        f"✅ **{next_num}-savol muvaffaqiyatli saqlandi!**\n\n"
        f"📌 Savol: {q_text}\n"
        f"✔️ To'g'ri javob: *{correct_ans}*",
        parse_mode="Markdown"
    )

    # Keyingi savolga o'tish yoki tugatish uchun taklif
    await callback.message.answer(
        "Nima qilamiz?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yana savol qo'shish", callback_data="add_next_question")],
            [InlineKeyboardButton(text="🏁 Test yaratishni yakunlash", callback_data="finish_all_tests")]
        ])
    )
    await state.set_state(AddTestStates.waiting_for_pack_name) # Vaqtinchalik holat

@dp.callback_query(F.data == "add_next_question")
async def add_next_question_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("✍️ Keyingi savol matnini yuboring:", parse_mode="Markdown")
    await state.set_state(AddTestStates.waiting_for_question_text)
    await callback.answer()

@dp.callback_query(F.data == "finish_all_tests")
async def finish_all_tests_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await callback.message.answer("🎉 Testlar to'plami muvaffaqiyatli yakunlandi va saqlandi! O'quvchilarga xabar yuborildi.", reply_markup=get_admin_keyboard())
    
    for g_id in GROUP_IDS:
        try:
            await bot.send_message(chat_id=g_id, text="📢 **YANGI VIKTORINA TESTI QO'SHILDI!**\nBotga kirib `/start` orqali testni yechishingiz mumkin! 🚀", parse_mode="Markdown")
        except Exception:
            pass
    await callback.answer()

# --- DAVOMIY KOD (O'quvchilar vaqt, statistika va boshqalar) ---

@dp.callback_query(F.data.in_(["off_dl", "off_less", "off_t_time"]))
async def inline_off_handler(callback: CallbackQuery):
    global DEADLINE_TIME, LESSON_TIME, TEST_DURATION_MINUTES
    if callback.from_user.id != ADMIN_ID:
        return

    if callback.data == "off_dl":
        DEADLINE_TIME = None
        await callback.message.answer("🔓 Дедлайн отключен!")
    elif callback.data == "off_less":
        LESSON_TIME = None
        await callback.message.answer("🔕 Напоминание об уроке отключено!")
    elif callback.data == "off_t_time":
        TEST_DURATION_MINUTES = None
        await callback.message.answer("🔓 Ограничение по времени теста отключено!")
    
    await callback.answer()

@dp.callback_query(F.data == "list_students")
async def inline_list_students(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    if not STUDENT_TO_NAME:
        await callback.message.answer("📭 Список учеников пуст.")
    else:
        text = "👨‍🎓 **База учеников и родителей:**\n\n"
        for name, info in STUDENT_TO_NAME.items():
            uid = info["user_id"]
            group = info["group"]
            s_user = info["student_username"]
            p_user = info["parent_username"]
            status = "✅ (Вошел)" if uid else "⏳ (Не вошел)"
            text += f"• **{name}** (Группа: `{group}`)\n  - Ученик: `{s_user}` {status}\n  - Родитель: `{p_user}`\n───\n"
        await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.message(Command("set_deadline"))
async def set_deadline_handler(message: Message):
    global DEADLINE_TIME
    if message.from_user.id != ADMIN_ID:
        return
    try:
        time_str = message.text.split(" ", 1)[1].strip()
        datetime.strptime(time_str, "%H:%M")
        DEADLINE_TIME = time_str
        await message.answer(f"⏰ Дедлайн: `{DEADLINE_TIME}`", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Формат: `/set_deadline 21:00`", parse_mode="Markdown")

@dp.message(Command("set_lesson_time"))
async def set_lesson_time_handler(message: Message):
    global LESSON_TIME
    if message.from_user.id != ADMIN_ID:
        return
    try:
        time_str = message.text.split(" ", 1)[1].strip()
        datetime.strptime(time_str, "%H:%M")
        LESSON_TIME = time_str
        await message.answer(f"🔔 Время урока: `{LESSON_TIME}`", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Формат: `/set_lesson_time 14:00`", parse_mode="Markdown")

@dp.message(Command("set_test_time"))
async def set_test_time_handler(message: Message):
    global TEST_DURATION_MINUTES
    if message.from_user.id != ADMIN_ID:
        return
    try:
        minutes = int(message.text.split(" ", 1)[1].strip())
        TEST_DURATION_MINUTES = minutes
        await message.answer(f"⏱️ Время на тест: `{TEST_DURATION_MINUTES} мин`", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Формат: `/set_test_time 30`", parse_mode="Markdown")

@dp.message(Command("delete"))
async def delete_test_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        content = message.text.split(" ", 1)[1].strip()
        parts = [p.strip() for p in content.split("|")]
        pack_name = parts[0]
        test_num = int(parts[1])

        if pack_name in TEST_DATA and test_num in TEST_DATA[pack_name]:
            del TEST_DATA[pack_name][test_num]
            if not TEST_DATA[pack_name]:
                del TEST_DATA[pack_name]
            
            stat_key = f"{pack_name}_{test_num}"
            if stat_key in WRONG_STATS:
                del WRONG_STATS[stat_key]

            save_data()
            await message.answer(f"🗑️ Топлам [{pack_name}] dagi №{test_num} тест удален!", parse_mode="Markdown")
        else:
            await message.answer("⚠️ Тест не найден.")
    except Exception:
        await message.answer("⚠️ Формат: `/delete n1 | 3`", parse_mode="Markdown")

@dp.message(Command("list"))
@dp.message(F.text == "📋 Список тестов")
async def list_tests_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    add_test_inline = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить тест (Viktorina)", callback_data="start_add_test")]
        ]
    )

    if not TEST_DATA:
        await message.answer("📭 База тестов пуста.", reply_markup=add_test_inline)
        return
    
    text = "📋 **База тестов по топламам:**\n\n"
    for pack_name, tests in sorted(TEST_DATA.items()):
        text += f"📦 **Топлам: {pack_name}**\n"
        for num, data in sorted(tests.items()):
            text += f"  • №{num}: {data['question']}\n    💡 To'g'ri javob: `{data['ans']}`\n"
        text += "───\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=add_test_inline)

@dp.message(Command("clear"))
async def clear_tests_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    TEST_DATA.clear()
    WRONG_STATS.clear()
    STUDENT_TEST_START.clear()
    STUDENT_SESSION.clear()
    save_data()
    await message.answer("🧹 Все тесты очищены!", parse_mode="Markdown")

@dp.message(Command("del_student"))
async def del_student_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        student_name = message.text.split(" ", 1)[1].strip()
        found = False
        for name in list(STUDENT_TO_NAME.keys()):
            if name.lower() == student_name.lower():
                info = STUDENT_TO_NAME[name]
                uid = info["user_id"]
                del STUDENT_TO_NAME[name]
                if uid and uid in STUDENTS_DATA:
                    del STUDENTS_DATA[uid]
                found = True
                break
        
        if found:
            save_data()
            await message.answer(f"🗑️ Удален: `{student_name}`", parse_mode="Markdown")
        else:
            await message.answer("⚠️ Не найдено.", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Формат: `/del_student Содиқов Анвар`", parse_mode="Markdown")

@dp.message(Command("my_stats"))
async def my_stats_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in STUDENTS_DATA:
        await message.answer("⛔ Вы не зарегистрированы как ученик.")
        return
    
    student_name = STUDENTS_DATA[user_id]
    records = STUDENT_RESULTS.get(user_id, [])
    
    if not records:
        await message.answer(f"👤 **{student_name}**\n📊 Вы еще не сдали ни одного теста.", parse_mode="Markdown")
        return

    text = f"📊 **Ваша личная статистика:**\n👤 {student_name}\n\n"
    for i, rec in enumerate(records, 1):
        text += f"{i}-я попытка | Дата: {rec['date']} | Результат: **{rec['score']}/{rec['total']}**\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("export"))
@dp.message(F.text == "📥 Excel отчет")
async def export_excel_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Группа", "Ф.И.О (Фамилия Имя)", "ID", "Username ученика", "Username родителя", "Дата", "Балл", "Всего"])
    
    for u_id, records in STUDENT_RESULTS.items():
        name = STUDENTS_DATA.get(u_id, "Неизвестно")
        group, s_user, p_user = "Неизвестно", "Неизвестно", "Неизвестно"
        for s_name, info in STUDENT_TO_NAME.items():
            if info["user_id"] == u_id:
                group = info["group"]
                name = s_name  
                s_user = info["student_username"]
                p_user = info["parent_username"]
                break
        for rec in records:
            writer.writerow([group, name, u_id, s_user, p_user, rec["date"], rec["score"], rec["total"]])
            
    output.seek(0)
    input_file = BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="report_results.csv")
    await message.answer_document(document=input_file, caption="📊 Excel отчет")

@dp.message(Command("top"))
@dp.message(F.text == "📊 ТОП учеников")
async def top_students_handler(message: Message):
    if not STUDENT_RESULTS:
        await message.answer("📊 Пока нет результатов.")
        return
    scores = {}
    for u_id, records in STUDENT_RESULTS.items():
        name = STUDENTS_DATA.get(u_id, f"ID: {u_id}")
        last_rec = records[-1]
        scores[name] = last_rec["score"]

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 **РЕЙТИНГ (ТОП):**\n\n"
    for i, (name, score) in enumerate(sorted_scores[:5], 1):
        text += f"{i}. **{name}**: {score} балл(ов)\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("stats"))
@dp.message(F.text == "📊 Статистика ошибок")
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not WRONG_STATS:
        await message.answer("📊 Нет ошибок.")
        return
    sorted_stats = sorted(WRONG_STATS.items(), key=lambda x: x[1], reverse=True)
    text = "📊 **Вопросы, в которых чаще всего ошибались:**\n\n"
    for rank, (key, count) in enumerate(sorted_stats, 1):
        pack_name, num = key.split("_", 1)
        text += f"{rank}. 📌 **Топлам [{pack_name}] - Вопрос №{num}**: {count} ошибок\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.photo)
async def handle_photo_solution(message: Message):
    user_id = message.from_user.id
    student_name = STUDENTS_DATA.get(user_id)
    if not student_name:
        return
    
    now_str = datetime.now().strftime('%d.%m.%Y | %H:%M')
    await message.answer("✅ Фото отправлено учителю!", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

    group_name, parent_username = "Неизвестно", "Неизвестно"
    for s_name, info in STUDENT_TO_NAME.items():
        if info["user_id"] == user_id:
            group_name = info["group"]
            parent_username = info["parent_username"]
            break

    try:
        await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=f"📩 **ФОТО РЕШЕНИЯ**\n👤 Ученик: {student_name}\n🏷️ Группа: {group_name}\n👩‍👦 Родитель: {parent_username}\n📅 {now_str}", parse_mode="Markdown")
    except Exception:
        pass

    group_photo_caption = (
        "📸 **НОВОЕ ДОМАШНЕЕ ЗАДАНИЕ (ФОТО)**\n\n"
        f"👤 Ученик: **{student_name}**\n"
        f"🏷️ Группа: {group_name}\n"
        f"👩‍👦 Родитель: {parent_username}\n"
        f"📅 Время: {now_str}"
    )
    for g_id in GROUP_IDS:
        try:
            await bot.send_photo(chat_id=g_id, photo=message.photo[-1].file_id, caption=group_photo_caption, parse_mode="Markdown")
        except Exception:
            pass

@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else None

    if user_id == ADMIN_ID:
        await message.answer("👑 Панель администратора", reply_markup=get_admin_keyboard())
        return

    if not username:
        await message.answer("⛔ У вас нет Telegram username! Пожалуйста, укажите username в настройках Telegram и отправьте /start снова.")
        return

    for s_name, info in STUDENT_TO_NAME.items():
        if info["parent_username"] and info["parent_username"].lower() == username.lower():
            PARENT_USERNAME_TO_ID[username] = user_id
            await message.answer(f"👋 Уважаемый родитель! Вы подключились для отслеживания результатов `{s_name}`.", parse_mode="Markdown")
            return

    matched_student_name = None
    for s_name, info in STUDENT_TO_NAME.items():
        if info["student_username"] and info["student_username"].lower() == username.lower():
            info["user_id"] = user_id
            matched_student_name = s_name
            break

    if not matched_student_name:
        await message.answer("⛔ Извините, этот username не найден в базе. Обратитесь к учителю.")
        return

    STUDENTS_DATA[user_id] = matched_student_name
    save_data()

    if TEST_DURATION_MINUTES:
        STUDENT_TEST_START[user_id] = datetime.now()

    if not TEST_DATA:
        await message.answer(f"Привет, {matched_student_name}! Пока нет тестов. Вы можете отправить команду /my_stats, чтобы посмотреть свою статистику.")
        return

    all_questions = []
    for pack_name, tests in sorted(TEST_DATA.items()):
        for q_num in sorted(tests.keys()):
            all_questions.append((pack_name, q_num))

    STUDENT_SESSION[user_id] = {
        "current_index": 0,
        "answers": {},
        "questions_list": all_questions
    }

    await message.answer(f"👋 Привет, **{matched_student_name}**!\n🚀 Тест начался, отправляйте ответы.", parse_mode="Markdown")
    await send_next_question(message, user_id)

async def send_next_question(message_or_callback, user_id: int):
    session = STUDENT_SESSION.get(user_id)
    if not session:
        return
    
    idx = session["current_index"]
    q_list = session["questions_list"]

    if idx >= len(q_list):
        await finish_test(message_or_callback, user_id)
        return

    pack_name, q_num = q_list[idx]
    q_data = TEST_DATA[pack_name][q_num]

    # Agar savolda variantlar bo'lsa, ularni ham inline tugma qilib chiqarish mumkin yoki matn ko'rinishida
    options_text = ""
    if "options" in q_data and q_data["options"]:
        options_text = "\n\n**Variantlar:**\n" + "\n".join([f"{i+1}) {opt}" for i, opt in enumerate(q_data["options"])])

    text = f"📌 **Топлам [{pack_name}] - Вопрос №{q_num} ({idx + 1} / {len(q_list)}):**\n{q_data['question']}{options_text}\n\n✍️ Отправьте ваш ответ:"
    markup = get_test_navigation_keyboard()

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, parse_mode="Markdown", reply_markup=markup)
    elif isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(text, parse_mode="Markdown", reply_markup=markup)

async def finish_test(message_or_callback, user_id: int):
    session = STUDENT_SESSION.pop(user_id, None)
    if not session:
        return

    user_answers = session["answers"]
    correct_count = 0
    total = sum(len(tests) for tests in TEST_DATA.values())
    student_name = STUDENTS_DATA.get(user_id, "Ученик")

    for pack_name, tests in TEST_DATA.items():
        for num, correct_info in tests.items():
            user_ans = user_answers.get((pack_name, num), "нет")
            if str(user_ans).strip().lower() == str(correct_info["ans"]).strip().lower():
                correct_count += 1

    now_str = datetime.now().strftime('%d.%m.%Y | %H:%M')
    if user_id not in STUDENT_RESULTS:
        STUDENT_RESULTS[user_id] = []
    STUDENT_RESULTS[user_id].append({"date": now_str, "score": correct_count, "total": total})
    save_data()

    percent = round((correct_count / total) * 100) if total > 0 else 0

    group_name, parent_username = "Неизвестно", "Неизвестно"
    for s_name, info in STUDENT_TO_NAME.items():
        if info["user_id"] == user_id:
            group_name = info["group"]
            parent_username = info["parent_username"]
            break

    result_msg = (
        f"📊 **РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ**\n\n"
        f"👤 Ученик: **{student_name}**\n"
        f"🏷️ Группа: {group_name}\n"
        f"✅ Правильных ответов: {correct_count} из {total} ({percent}%)\n"
        f"📅 Дата: {now_str}"
    )

    for p_user, p_id in PARENT_USERNAME_TO_ID.items():
        if p_user.lower() == parent_username.lower():
            try:
                await bot.send_message(chat_id=p_id, text=result_msg, parse_mode="Markdown")
            except Exception:
                pass

    for g_id in GROUP_IDS:
        try:
            await bot.send_message(chat_id=g_id, text=result_msg, parse_mode="Markdown")
        except Exception:
            pass

    finish_text = f"🏁 **Тест завершен!**\n\nРезультат: {correct_count} / {total}\n📸 Теперь отправьте фото решения из тетради!"
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(finish_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
    elif isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(finish_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

@dp.message()
async def handle_student_answers(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in STUDENTS_DATA:
        return

    text = message.text.strip()
    if text in ["➡️ Следующий вопрос", "⏭ Пропустить"]:
        session = STUDENT_SESSION.get(user_id)
        if session:
            idx = session["current_index"]
            q_list = session["questions_list"]
            pack_name, q_num = q_list[idx]
            if text == "⏭ Пропустить":
                session["answers"][(pack_name, q_num)] = "пропущено"
            session["current_index"] += 1
            await send_next_question(message, user_id)
        return

    session = STUDENT_SESSION.get(user_id)
    if not session:
        return

    idx = session["current_index"]
    q_list = session["questions_list"]
    if idx >= len(q_list):
        return

    pack_name, q_num = q_list[idx]
    
    if TEST_DURATION_MINUTES and user_id in STUDENT_TEST_START:
        start_time = STUDENT_TEST_START[user_id]
        if datetime.now() - start_time > timedelta(minutes=TEST_DURATION_MINUTES):
            await message.answer("⏰ Время на прохождение теста истекло!", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
            await finish_test(message, user_id)
            return

    session["answers"][(pack_name, q_num)] = text
    
    correct_ans = TEST_DATA[pack_name][q_num]["ans"]
    if str(text).strip().lower() != str(correct_ans).strip().lower():
        stat_key = f"{pack_name}_{q_num}"
        WRONG_STATS[stat_key] = WRONG_STATS.get(stat_key, 0) + 1
        save_data()

    session["current_index"] += 1
    await send_next_question(message, user_id)

async def main():
    logging.basicConfig(level=logging.INFO)
    load_data()
    asyncio.create_task(check_lesson_schedule())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
