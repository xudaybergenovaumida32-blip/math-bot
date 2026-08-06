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
PARENT_USERNAME_TO_ID = ""  
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
    waiting_for_full_name = State()       # 1-etap: F.I.O (Familyasi ismi)
    waiting_for_student_username = State() # 2-etap: O'quvchi username
    waiting_for_group = State()           # 3-etap: Guruh raqami
    waiting_for_parent_username = State() # 4-etap: Ota-onaning username

# Test qo'shish uchun holatlar (FSM)
class AddTestStates(StatesGroup):
    waiting_for_pack_name = State()       # Test mavzusi (to'plam nomi)
    waiting_for_question_data = State()   # 10 ta savolni kiritish

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

    # O'zining username bilan ota-onaning username bir xil bo'lmasligini qat'iy nazorat qilish
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

@dp.message(Command("add_student"))
async def add_student_command_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "1️⃣ **1-etap:** O'quvchining **F.I.O (Familyasi ismi)**ni yuboring (Masalan: `Содиқов Анвар`):",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_full_name)

@dp.message(Command("broadcast"))
async def broadcast_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        text_to_send = message.text.split(" ", 1)[1].strip()
    except Exception:
        await message.answer("⚠️ Oшибка! Введите текст сообщения:\n`/broadcast Привет, ученики!`", parse_mode="Markdown")
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
            "📝 **Test qo'shish:**\nIltimos, yangi test uchun **mavzu nomini (to'plam nomini)** kiriting (masalan: `n1` yoki `Matematika-1`):",
            parse_mode="Markdown"
        )
        await state.set_state(AddTestStates.waiting_for_pack_name)
    
    await callback.answer()

@dp.message(AddTestStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    pack_name = message.text.strip()
    await state.update_data(pack_name=pack_name, current_q_num=1, temp_tests={})
    await message.answer(
        f"✅ Mavzu nomi saqlandi: `{pack_name}`\n\n"
        f"Hozir **1-savolni** quyidagi formatda yuboring:\n"
        "`Savol matni | To'g'ri javob | Yechimi (ixtiyoriy)`\n\n"
        "Masalan:\n`2x = 10 | 5 | 2 ga bo'lib topiladi`",
        parse_mode="Markdown"
    )
    await state.set_state(AddTestStates.waiting_for_question_data)

@dp.message(AddTestStates.waiting_for_question_data)
async def process_question_data(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text.strip()
    data = await state.get_data()
    pack_name = data.get("pack_name")
    current_num = data.get("current_num")
    temp_tests = data.get("temp_tests")

    try:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2:
            await message.answer("⚠️ Format noto'g'ri! Iltimos, quyidagicha yuboring:\n`Savol matni | To'g'ri javob | Yechimi`", parse_mode="Markdown")
            return

        q_text = parts[0]
        ans = parts[1]
        solution = parts[2] if len(parts) > 2 else "Решение не указано"

        temp_tests[current_num] = {
            "question": q_text,
            "ans": ans,
            "solution": solution
        }

        if current_num < 10:
            next_num = current_num + 1
            await state.update_data(current_num=next_num, temp_tests=temp_tests)
            await message.answer(
                f"✅ {current_num}-savol qabul qilindi!\n\n"
                f"Endi **{next_num}-savolni** yuboring (Format: `Savol | Javob | Yechim`):",
                parse_mode="Markdown"
            )
        else:
            # 10 ta savol to'ldi, avtomat saqlaymiz
            if pack_name not in TEST_DATA:
                TEST_DATA[pack_name] = {}
            TEST_DATA[pack_name].update(temp_tests)
            save_data()
            await state.clear()

            saved_text = f"✅ **[{pack_name}]** mavzusi ostida 10 ta savol avtomat tarzda muvaffaqiyatli saqlandi!"
            await message.answer(saved_text, parse_mode="Markdown")

            # Test saqlanganda o'quvchilar guruhiga (yoki barcha o'quvchilarga) avtomat tarzda test yoki savol bo'lib ko'rinishi uchun xabar yuborish
            for g_id in GROUP_IDS:
                try:
                    await bot.send_message(chat_id=g_id, text=f"📢 **YANGI TEST QO'SHILDI!**\n\nMavzu: `{pack_name}`\nBotga kirib `/start` orqali testni yechishingiz mumkin! 🚀", parse_mode="Markdown")
                except Exception:
                    pass
    except Exception:
        await message.answer("⚠️ Xatolik yuz berdi. Qaytadan urinib ko'ring (Format: `Savol | Javob | Yechim`)", parse_mode="Markdown")

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

@dp.message(Command("add"))
async def add_test_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        content = message.text.split(" ", 1)[1]
        parts = [p.strip() for p in content.split("|")]
        
        pack_name = parts[0]  
        test_num = int(parts[1])
        question_text = parts[2]
        ans = parts[3]  
        solution = parts[4] if len(parts) > 4 else "Решение не указано"

        if pack_name not in TEST_DATA:
            TEST_DATA[pack_name] = {}

        TEST_DATA[pack_name][test_num] = {
            "question": question_text,
            "ans": ans,
            "solution": solution
        }
        save_data()
        await message.answer(f"✅ **Тест добавлен в топлам [{pack_name}]!** №{test_num}", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Формат:\n`/add n1 | 1 | Решите уравнение: 2x = 10 | 5 | Решение: ...`", parse_mode="Markdown")

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
    
    # "Список тестов" ga kirganda + Добавить tugmasi chiqishi uchun Inline klaviatura qo'shildi
    add_test_inline = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить тест", callback_data="start_add_test")]
        ]
    )

    if not TEST_DATA:
        await message.answer("📭 База тестов пуста.", reply_markup=add_test_inline)
        return
    
    text = "📋 **База тестов по топламам:**\n\n"
    for pack_name, tests in sorted(TEST_DATA.items()):
        text += f"📦 **Топлам: {pack_name}**\n"
        for num, data in sorted(tests.items()):
            text += f"  • №{num}: {data['question']}\n    💡 Ответ: `{data['ans']}`\n"
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

    text = f"📌 **Топлам [{pack_name}] - Вопрос №{q_num} ({idx + 1} / {len(q_list)}):**\n{q_data['question']}\n\n✍️ Отправьте ваш ответ:"
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

    finish_text = f"🏁 **Тест завершен!**\n\nРезультат: {correct_count} / {total}\n📸 Теперь отправьте фото решения из тетради!"
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(finish_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
    elif isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(finish_text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

    percent = round((correct_count / total) * 100) if total > 0 else 0
    
    group_name, parent_username = "Неизвестно", "Неизвестно"
    for s_name, info in STUDENT_TO_NAME.items():
        if info["user_id"] == user_id:
            group_name = info["group"]
            parent_username = info["parent_username"]
            break

    try:
        await bot.send_message(chat_id=ADMIN_ID, text=f"📩 **ТЕСТ ЗАВЕРШЕН**\n👤 {student_name}\n🏷️ Группа: {group_name}\n📊 Результат: {correct_count}/{total} ({percent}%)\n📅 {now_str}", parse_mode="Markdown")
    except Exception:
        pass

    if parent_username and parent_username in PARENT_USERNAME_TO_ID:
        p_chat_id = PARENT_USERNAME_TO_ID[parent_username]
        try:
            await bot.send_message(chat_id=p_chat_id, text=f"📊 **Ваш ребенок сдал тест!**\n👤 {student_name}\n📈 Результат: {correct_count}/{total} ({percent}%)", parse_mode="Markdown")
        except Exception:
            pass

    group_report = (
        "📢 **РЕЗУЛЬТАТ ДОМАШНЕГО ЗАДАНИЯ**\n\n"
        f"👤 Ученик: **{student_name}**\n"
        f"🏷️ Группа: {group_name}\n"
        f"👩‍👦 Родитель: {parent_username}\n"
        f"📊 Результат: **{correct_count} / {total}** ({percent}%)\n"
        f"📅 Время: {now_str}"
    )
    for g_id in GROUP_IDS:
        try:    
            await bot.send_message(chat_id=g_id, text=group_report, parse_mode="Markdown")
        except Exception:
            pass

@dp.message()
async def process_student_input(message: Message):
    user_id = message.from_user.id

    if user_id == ADMIN_ID and message.text in [
        "📊 ТОП учеников", "📥 Excel отчет", "⚙️ Управление временем", 
        "📋 Список тестов", "👨‍🎓 Управление учениками", "📊 Статистика ошибок", "📢 Рассылка сообщений"
    ]:
        return

    if user_id not in STUDENT_SESSION:
        return

    if DEADLINE_TIME and datetime.now().strftime("%H:%M") > DEADLINE_TIME:
        STUDENT_SESSION.pop(user_id, None)
        await message.answer(f"⛔ Время вышло! Дедлайн: `{DEADLINE_TIME}`", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
        return

    if TEST_DURATION_MINUTES:
        start_time = STUDENT_TEST_START.get(user_id)
        if start_time and (datetime.now() - start_time > timedelta(minutes=TEST_DURATION_MINUTES)):
            STUDENT_SESSION.pop(user_id, None)
            await message.answer("⏳ Время вышло!", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))
            return

    session = STUDENT_SESSION[user_id]
    idx = session["current_index"]
    q_list = session["questions_list"]
    pack_name, current_q_num = q_list[idx]
    q_data = TEST_DATA[pack_name][current_q_num]

    text_input = message.text.strip()

    if text_input in ["⏭ Пропустить", "➡️ Следующий вопрос"]:
        session["answers"][(pack_name, current_q_num)] = "пропущено"
        await message.answer(f"⏭ Пропущено. Правильный ответ: `{q_data['ans']}`\n💡 Решение: {q_data['solution']}", parse_mode="Markdown")
    else:
        session["answers"][(pack_name, current_q_num)] = text_input
        if text_input.lower() == str(q_data['ans']).strip().lower():
            await message.answer("✅ Верно!", parse_mode="Markdown")
        else:
            stat_key = f"{pack_name}_{current_q_num}"
            WRONG_STATS[stat_key] = WRONG_STATS.get(stat_key, 0) + 1
            save_data()
            await message.answer(f"❌ Неверно.\n💡 Правильный ответ: `{q_data['ans']}`\n📖 Решение: {q_data['solution']}", parse_mode="Markdown")

    session["current_index"] += 1
    await send_next_question(message, user_id)

async def main():
    load_data()
    asyncio.create_task(check_lesson_schedule())
    await dp.start_polling(bot)

if __name__ == "__main__":
    async logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
