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

class AddStudentStates(StatesGroup):
    waiting_for_student_info = State()
    waiting_for_parent_username = State()

class AddTestStates(StatesGroup):
    waiting_for_pack_name = State()
    waiting_for_bulk_questions = State()

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
            logging.error(f"Xatolik: {e}")

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить тест"), KeyboardButton(text="🗑 Удалить тест")],
            [KeyboardButton(text="📋 Список тестов"), KeyboardButton(text="📊 ТОП учеников")],
            [KeyboardButton(text="📥 Excel отчет"), KeyboardButton(text="⚙️ Управление временем")],
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

def get_restart_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start")]
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
                    "⏰ **ВНИМАНИЕ! ВРЕМЯ УРОКА!**\n\n"
                    f"📚 Уважаемые ученики и родители, наступило время урока (`{LESSON_TIME}`)!\n"
                    "Готовимся к занятию! 🚀"
                )
                for g_id in GROUP_IDS:
                    try:
                        await bot.send_message(chat_id=g_id, text=reminder_text, parse_mode="Markdown")
                    except Exception:
                        pass
                await asyncio.sleep(60)

# --- ДОБАВЛЕНИЕ ТЕСТОВ КНОПКОЙ ---

@dp.message(F.text == "➕ Добавить тест")
async def start_add_test_flow(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📦 **Введите название темы (комплекта тестов):**\n"
        "(Например: `usmonov` или `algebra`)",
        parse_mode="Markdown"
    )
    await state.set_state(AddTestStates.waiting_for_pack_name)

@dp.message(AddTestStates.waiting_for_pack_name)
async def process_pack_name(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    pack_name = message.text.strip()
    await state.update_data(pack_name=pack_name)
    
    await message.answer(
        f"✅ Название темы сохранено: **{pack_name}**\n\n"
        "✍️ Теперь отправьте вопросы в следующем формате (каждый вопрос с новой строки):\n\n"
        "`1 | Текст вопроса | Правильный ответ | Решение`\n\n"
        "**Пример:**\n"
        "1 | 2x = 10 | 5 | Делим 10 на 2\n"
        "2 | 5 + 5 * 2 | 15 | Сначала выполняется умножение",
        parse_mode="Markdown"
    )
    await state.set_state(AddTestStates.waiting_for_bulk_questions)

@dp.message(AddTestStates.waiting_for_bulk_questions)
async def process_bulk_questions(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    pack_name = data.get("pack_name")
    lines = message.text.strip().split("\n")
    
    added_count = 0
    if pack_name not in TEST_DATA:
        TEST_DATA[pack_name] = {}

    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                try:
                    q_num = int(parts[0])
                    q_text = parts[1]
                    ans = parts[2]
                    solution = parts[3] if len(parts) > 3 else "Решение не указано"

                    TEST_DATA[pack_name][q_num] = {
                        "question": q_text,
                        "ans": ans,
                        "solution": solution
                    }
                    added_count += 1
                except Exception:
                    continue

    save_data()
    await state.clear()
    await message.answer(
        f"🎉 **Успешно сохранено!**\n\n"
        f"📦 Тема: `{pack_name}`\n"
        f"✅ Добавлено вопросов: **{added_count} шт.**",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

# --- УДАЛЕНИЕ ТЕСТОВ КНОПКОЙ ---

@dp.message(F.text == "🗑 Удалить тест")
async def start_delete_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not TEST_DATA:
        await message.answer("📭 В базе пока нет тестов.")
        return
    
    keyboard_buttons = []
    for pack_name in TEST_DATA.keys():
        keyboard_buttons.append([InlineKeyboardButton(text=f"🗑 Удалить: {pack_name}", callback_data=f"del_pack_{pack_name}")])
    
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("🗑 Выберите тему (комплект), которую хотите удалить:", reply_markup=markup)

@dp.callback_query(F.data.startswith("del_pack_"))
async def callback_delete_pack(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    pack_name = callback.data.replace("del_pack_", "")
    
    if pack_name in TEST_DATA:
        del TEST_DATA[pack_name]
        keys_to_del = [k for k in WRONG_STATS.keys() if k.startswith(f"{pack_name}_")]
        for k in keys_to_del:
            del WRONG_STATS[k]
        save_data()
        await callback.message.answer(f"✅ Тема `{pack_name}` и все её вопросы были удалены!", parse_mode="Markdown")
    else:
        await callback.message.answer("⚠️ Такая тема не найдена.")
    
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

@dp.message(F.text == "⚙️ Управление временем")
async def menu_time_settings(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    status_text = (
        "⚙️ **УПРАВЛЕНИЕ ВРЕМЕНЕМ И ДЕДЛАЙНАМИ**\n\n"
        f"• Дедлайн ДЗ: `{DEADLINE_TIME or 'Не установлен'}`\n"
        f"• Время урока: `{LESSON_TIME or 'Не установлено'}`\n"
        f"• Время на тест: `{TEST_DURATION_MINUTES or 'Без ограничений'} мин.`"
    )
    await message.answer(status_text, parse_mode="Markdown", reply_markup=get_time_settings_keyboard())

@dp.message(F.text == "👨‍🎓 Управление учениками")
async def menu_students_management(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👨‍🎓 **УПРАВЛЕНИЕ БАЗОЙ УЧЕНИКОВ**",
        parse_mode="Markdown",
        reply_markup=get_students_menu_keyboard()
    )

@dp.callback_query(F.data == "start_add_student")
async def callback_start_add_student(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer(
        "1️⃣ Отправьте ФИО ученика, группу и `@username`:\n`Содиков Анвар | 10-А | @anvar_student`",
        parse_mode="Markdown"
    )
    await state.set_state(AddStudentStates.waiting_for_student_info)
    await callback.answer()

@dp.message(AddStudentStates.waiting_for_student_info)
async def process_student_info(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    try:
        parts = [p.strip() for p in text.split("|")]
        student_name, group_num, student_username = parts[0], parts[1], parts[2]
        await state.update_data(student_name=student_name, group_num=group_num, student_username=student_username)
        await message.answer("2️⃣ Теперь отправьте **Telegram username родителя** (например: `@parent_username`):")
        await state.set_state(AddStudentStates.waiting_for_parent_username)
    except Exception:
        await message.answer("⚠️ Неверный формат! Отправьте заново:\n`Содиков Анвар | 10-А | @anvar_student`")

@dp.message(AddStudentStates.waiting_for_parent_username)
async def process_parent_username(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parent_username = message.text.strip()
    data = await state.get_data()
    
    STUDENT_TO_NAME[data.get("student_name")] = {
        "group": data.get("group_num"),
        "student_username": data.get("student_username"),
        "parent_username": parent_username,
        "user_id": None
    }
    save_data()
    await state.clear()
    await message.answer("🎉 Ученик и родитель успешно добавлены!", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📋 Список тестов")
async def list_tests_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not TEST_DATA:
        await message.answer("📭 В базе нет тестов.")
        return
    text = "📋 **Список тем и тестов:**\n\n"
    for pack_name, tests in sorted(TEST_DATA.items()):
        text += f"📦 **Тема: {pack_name}** ({len(tests)} вопросов)\n"
        for num, data in sorted(tests.items()):
            text += f"  • №{num}: {data['question']} (Ответ: `{data['ans']}`)\n"
        text += "───\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 ТОП учеников")
async def top_students_handler(message: Message):
    if not STUDENT_RESULTS:
        await message.answer("📊 Пока нет результатов.")
        return
    scores = {}
    for u_id, records in STUDENT_RESULTS.items():
        name = STUDENTS_DATA.get(u_id, f"ID: {u_id}")
        scores[name] = records[-1]["score"]

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 **РЕЙТИНГ УЧЕНИКОВ (ТОП):**\n\n"
    for i, (name, score) in enumerate(sorted_scores[:5], 1):
        text += f"{i}. **{name}**: {score} баллов\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📥 Excel отчет")
async def export_excel_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Группа", "ФИО", "ID", "Username ученика", "Username родителя", "Дата", "Балл", "Всего"])
    
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
    input_file = BufferedInputFile(output.getvalue().encode('utf-8-sig'), filename="report.csv")
    await message.answer_document(document=input_file, caption="📊 Excel отчет")

@dp.message(F.text == "📊 Статистика ошибок")
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not WRONG_STATS:
        await message.answer("📊 Ошибок нет.")
        return
    sorted_stats = sorted(WRONG_STATS.items(), key=lambda x: x[1], reverse=True)
    text = "📊 **Самые частые ошибки по вопросам:**\n\n"
    for rank, (key, count) in enumerate(sorted_stats, 1):
        pack_name, num = key.split("_", 1)
        text += f"{rank}. 📌 Тема [{pack_name}] - Вопрос №{num}: {count} ошибок\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("broadcast"))
async def broadcast_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        text_to_send = message.text.split(" ", 1)[1].strip()
    except Exception:
        await message.answer("⚠️ Введите текст сообщения: `/broadcast Всем привет`", parse_mode="Markdown")
        return

    count = 0
    for u_id in STUDENTS_DATA.keys():
        try:
            await bot.send_message(chat_id=u_id, text=f"📢 **Сообщение от преподавателя:**\n\n{text_to_send}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass
    await message.answer(f"✅ Сообщение отправлено **{count}** ученикам!")

@dp.message(F.photo)
async def handle_photo_solution(message: Message):
    user_id = message.from_user.id
    student_name = STUDENTS_DATA.get(user_id)
    if not student_name:
        return
    
    now_str = datetime.now().strftime('%d.%m.%Y | %H:%M')
    await message.answer("✅ Фото отправлено преподавателю! Нажмите /start, чтобы пройти тест заново.", parse_mode="Markdown", reply_markup=get_restart_keyboard())

    group_name, parent_username = "Неизвестно", "Неизвестно"
    for s_name, info in STUDENT_TO_NAME.items():
        if info["user_id"] == user_id:
            group_name = info["group"]
            parent_username = info["parent_username"]
            break

    try:
        await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=f"📩 **ФОТО ДОМАШНЕГО ЗАДАНИЯ**\n👤 Ученик: {student_name}\n🏷️ Группа: {group_name}\n👩‍👦 Родитель: {parent_username}\n📅 {now_str}", parse_mode="Markdown")
    except Exception:
        pass

    group_photo_caption = (
        "📸 **НОВОЕ ДОМАШНЕЕ ЗАДАНИЕ (ФОТО)**\n\n"
        f"👤 Ученик: **{student_name}**\n"
        f"🏷️ Группа: {group_name}\n"
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
        await message.answer(
            "👑 **Панель администратора**", 
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )
        return

    if not username:
        await message.answer("⛔ У вас нет Telegram username! Установите его в настройках и нажмите /start.")
        return

    for s_name, info in STUDENT_TO_NAME.items():
        if info["parent_username"] and info["parent_username"].lower() == username.lower():
            PARENT_USERNAME_TO_ID[username] = user_id
            await message.answer(f"👋 Уважаемый родитель! Вы успешно привязаны для отслеживания результатов `{s_name}`.", parse_mode="Markdown")
            return

    matched_student_name = None
    for s_name, info in STUDENT_TO_NAME.items():
        if info["student_username"] and info["student_username"].lower() == username.lower():
            info["user_id"] = user_id
            matched_student_name = s_name
            break

    if not matched_student_name:
        await message.answer("⛔ Извините, ваш username не найден в базе. Обратитесь к преподавателю.")
        return

    STUDENTS_DATA[user_id] = matched_student_name
    save_data()

    if TEST_DURATION_MINUTES:
        STUDENT_TEST_START[user_id] = datetime.now()

    if not TEST_DATA:
        await message.answer(f"Привет, {matched_student_name}! Пока нет доступных тестов.")
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

    text = f"📌 **Тема [{pack_name}] - Вопрос №{q_num} ({idx + 1} / {len(q_list)}):**\n{q_data['question']}\n\n✍️ Отправьте ваш ответ:"
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

    finish_text = f"🏁 **Тест завершен!**\n\nРезультат: {correct_count} / {total}\n📸 Теперь отправьте фото решения в тетради!"
    
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(finish_text, parse_mode="Markdown", reply_markup=get_restart_keyboard())
    elif isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(finish_text, parse_mode="Markdown", reply_markup=get_restart_keyboard())

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
            await bot.send_message(chat_id=p_chat_id, text=f"📊 **Ваш ребёнок завершил тест!**\n👤 {student_name}\n📈 Результат: {correct_count}/{total} ({percent}%)", parse_mode="Markdown")
        except Exception:
            pass

    group_report = (
        "📢 **РЕЗУЛЬТАТ ДОМАШНЕГО ЗАДАНИЯ**\n\n"
        f"👤 Ученик: **{student_name}**\n"
        f"🏷️ Группа: {group_name}\n"
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
        "➕ Добавить тест", "🗑 Удалить тест", "📊 ТОП учеников", "📥 Excel отчет", 
        "⚙️ Управление временем", "📋 Список тестов", "👨‍🎓 Управление учениками", 
        "📊 Статистика ошибок", "📢 Рассылка сообщений"
    ]:
        return

    if user_id not in STUDENT_SESSION:
        return

    if DEADLINE_TIME and datetime.now().strftime("%H:%M") > DEADLINE_TIME:
        STUDENT_SESSION.pop(user_id, None)
        await message.answer(f"⛔ Время вышло! Дедлайн: `{DEADLINE_TIME}`", parse_mode="Markdown", reply_markup=get_restart_keyboard())
        return

    if TEST_DURATION_MINUTES:
        start_time = STUDENT_TEST_START.get(user_id)
        if start_time and (datetime.now() - start_time > timedelta(minutes=TEST_DURATION_MINUTES)):
            STUDENT_SESSION.pop(user_id, None)
            await message.answer("⏳ Время вышло!", parse_mode="Markdown", reply_markup=get_restart_keyboard())
            return

    session = STUDENT_SESSION[user_id]
    idx = session["current_index"]
    q_list = session["questions_list"]
    pack_name, current_q_num = q_list[idx]
    q_data = TEST_DATA[pack_name][current_q_num]

    text_input = message.text.strip()

    if text_input in ["⏭ Пропустить", "➡️ Следующий вопрос"]:
        session["answers"][(pack_name, current_q_num)] = "пропущено"
        await message.answer(f"⏭ Вопрос пропущен. Правильный ответ: `{q_data['ans']}`\n💡 Решение: {q_data['solution']}", parse_mode="Markdown")
    else:
        session["answers"][(pack_name, current_q_num)] = text_input
        if text_input.lower() == str(q_data['ans']).lower():
            await message.answer(f"✅ Верно! 🎉\n💡 Решение: {q_data['solution']}", parse_mode="Markdown")
        else:
            await message.answer(f"❌ Неверно.\n💡 Правильный ответ: `{q_data['ans']}`\n💡 Решение: {q_data['solution']}", parse_mode="Markdown")
            stat_key = f"{pack_name}_{current_q_num}"
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
