from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
import aiohttp
from states import Form, FoodForm


router = Router()
users = {}


def initialize_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "weight": None,
            "height": None,
            "age": None,
            "activity": None,
            "city": None,
            "water_goal": None,
            "calorie_goal": None,
            "logged_water": 0,
            "logged_calories": 0,
            "burned_calories": 0
        }


def calculate_water(weight, activity):
    base_water = weight * 30
    additional_activity = (activity // 30) * 500
    return base_water + additional_activity


def calculate_calories(weight, height, age, activity):
    base_calories = (10 * weight) + (6.25 * height) - (5 * age)
    activity_calories = activity * (200 / 60)
    return base_calories + activity_calories


async def get_food_info(food_name):
    url = f"https://world.openfoodfacts.org/api/v0/product/{food_name}.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if 'product' in data and 'nutriments' in data['product']:
                    product_name = data['product'].get('product_name', 'Неизвестный продукт')
                    calories_per_100g = data['product']['nutriments'].get('energy-kcal_100g', None)
                    return product_name, calories_per_100g
    return None, None


def calculate_calories_burned(workout_type, duration):
    calories_per_minute = {
        'бег': 10,
        'велосипед': 8,
        'плавание': 7,
        'силовая': 6,
    }
    return calories_per_minute.get(workout_type.lower(), 5) * duration


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Добро пожаловать! Я бот для расчета нормы воды и калорий. \nВведите /help для списка команд.")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply("Доступные команды:\n"
                        "/start - Начало работы\n"
                        "/set_profile - Настройка профиля пользователя\n"
                        "/log_water - Логирование воды в мл.\n"
                        "/log_food - Логирование съеденных ккал.\n"
                        "/log_workout - Логирование тренировок\n"
                        "/check_progress - Проверить прогресс пользователя\n")


@router.message(Command("set_profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await message.reply("Введите ваш вес (в кг):")
    await state.set_state(Form.weight)


@router.message(Form.weight)
async def process_weight(message: Message, state: FSMContext):
    await state.update_data(weight=message.text)
    await message.reply("Введите ваш рост (в см):")
    await state.set_state(Form.height)


@router.message(Form.height)
async def process_height(message: Message, state: FSMContext):
    await state.update_data(height=message.text)
    await message.reply("Введите ваш возраст:")
    await state.set_state(Form.age)


@router.message(Form.age)
async def process_age(message: Message, state: FSMContext):
    await state.update_data(age=message.text)
    await message.reply("Сколько минут активности у вас в день?")
    await state.set_state(Form.activity)


@router.message(Form.activity)
async def process_activity(message: Message, state: FSMContext):
    await state.update_data(activity=message.text)
    await message.reply("В каком городе вы находитесь?")
    await state.set_state(Form.city)


@router.message(Form.city)
async def process_city(message: Message, state: FSMContext):
    data = await state.get_data()

    user_id = message.from_user.id
    initialize_user(user_id)

    users[user_id]["weight"] = float(data.get("weight"))
    users[user_id]["height"] = float(data.get("height"))
    users[user_id]["age"] = int(data.get("age"))
    users[user_id]["activity"] = int(data.get("activity"))
    users[user_id]["city"] = message.text

    water_goal = calculate_water(users[user_id]["weight"],
                                 users[user_id]["activity"])
    calorie_goal = calculate_calories(users[user_id]["weight"],
                                      users[user_id]["height"],
                                      users[user_id]["age"],
                                      users[user_id]["activity"])

    users[user_id]["water_goal"] = water_goal
    users[user_id]["calorie_goal"] = calorie_goal

    await message.reply(f"Готово! Проверьте свой статус с помощью /check_progress")
    await state.clear()


@router.message(Command("log_water"))
async def cmd_log_water(message: Message, command: CommandObject):
    user_id = message.from_user.id
    consumed_water = int(command.args.strip())
    users[user_id]["logged_water"] = consumed_water
    await message.reply(f"Записано: {consumed_water} мл. \n"
                        f"Осталось выпить: {users[user_id]['water_goal'] - consumed_water} мл.")


@router.message(Command("log_food"))
async def cmd_log_food(message: Message, command: CommandObject, state: FSMContext):
    product_name, calories_per_100g = await get_food_info(command.args.strip())
    await state.update_data(calories_per_100g=calories_per_100g)

    if calories_per_100g is None:
        await message.reply("Не удалось найти информацию о продукте.")
        return

    await message.reply(f"{product_name} — {calories_per_100g} ккал на 100 г. Сколько грамм вы съели?")
    await state.set_state(FoodForm.calorie_num)


@router.message(FoodForm.calorie_num)
async def process_calories(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id

    try:
        grams = float(message.text)
        calories_per_100g = float(data.get("calories_per_100g"))
        consumed_calories = (calories_per_100g * grams) / 100
        users[user_id]["logged_calories"] += consumed_calories

        await message.reply(f"Записано: {consumed_calories:.2f} ккал.")
        await state.clear()
    except ValueError:
        await message.reply("Пожалуйста, введите корректное количество граммов.")


@router.message(Command("log_workout"))
async def cmd_log_workout(message: Message, command: CommandObject):
    args = command.args.split()

    if len(args) < 2:
        await message.reply("Пожалуйста, укажите тип тренировки и время в минутах. Пример: /log_workout бег 30")
        return

    workout_type = args[0]

    try:
        duration = int(args[1])
        calories_burned = calculate_calories_burned(workout_type, duration)
        water_needed = (duration // 30) * 200
        user_id = message.from_user.id
        users[user_id]["burned_calories"] += calories_burned

        await message.reply(
            f"🏃‍♂️ {workout_type.capitalize()} {duration} минут — {calories_burned} ккал. \n"
            f"Дополнительно: выпейте {water_needed} мл воды."
        )
    except ValueError:
        await message.reply("Пожалуйста, укажите корректное время в минутах.")


@router.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    user_id = message.from_user.id

    if user_id not in users:
        await message.reply("Сначала настройте профиль с помощью команды /set_profile.")
        return

    user_data = users[user_id]

    logged_water = user_data.get("logged_water", 0)
    water_goal = user_data.get("water_goal", 0)

    logged_calories = user_data.get("logged_calories", 0)
    calorie_goal = user_data.get("calorie_goal", 0)
    burned_calories = user_data.get("burned_calories", 0)

    progress_message = (
        "📊 Прогресс:\n"
        "Вода:\n"
        f"- Выпито: {logged_water} мл из {water_goal} мл.\n"
        f"- Осталось: {water_goal - logged_water} мл.\n\n"
        "Калории:\n"
        f"- Потреблено: {logged_calories} ккал из {calorie_goal} ккал.\n"
        f"- Сожжено: {burned_calories} ккал.\n"
        f"- Баланс: {calorie_goal - logged_calories + burned_calories} ккал."
    )

    await message.reply(progress_message)
