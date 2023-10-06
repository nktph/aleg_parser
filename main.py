import logging
import random

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext

import requests
from peewee import IntegrityError
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import os
import time

# Прокси добавлять сюда
proxies = [
    # {'http': "http://proxy.example.com:8080",
    #  'https': "https://proxy.example.com:8080"},

    # {'http': "socks5://user:pass@host:port",
    #  'https': "socks5://user:pass@host:port"},
]

# Счётчик для переключения прокси
i = 0

# Замените 'YOUR_BOT_API_TOKEN' на токен вашего бота
API_TOKEN = 'YOUR_BOT_API_TOKEN'

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot=bot, storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)
dp.middleware.setup(LoggingMiddleware())
s = Service(executable_path='chromedriver.exe')
driver = webdriver.Chrome(service=s)

# Клавиатура пользователя
advert = KeyboardButton(text="Парсинг объявления")
category = KeyboardButton(text="Парсинг категории")
kb = ReplyKeyboardMarkup(resize_keyboard=True).add(advert, category)

by_number = KeyboardButton(text="Только с номером")
by_no_number = KeyboardButton(text="Только без номера")
list_all = KeyboardButton(text="Все")
sorting_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(by_number, by_no_number, list_all)


 # Машина состояний бота
class StateWorker(StatesGroup):
    parsing_ad = State()
    parsing_category = State()
    set_parsing_count = State()
    set_filter = State()

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def on_start(message: types.Message):
    await message.answer("Привет! Выберите опцию", reply_markup=kb)


@dp.message_handler(lambda message: message.text.lower() == '/cancel', state='*')
async def cancel_input(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("Ввод URL отменен.")
    await on_start(message)


@dp.message_handler(state=StateWorker.set_parsing_count)
async def set_parse_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count in range(1, 35):
            print(count)
            async with state.proxy() as data:
                data['count'] = count

            await StateWorker.set_filter.set()
            await message.answer("Укажите фильтр. Показывать объявления...", reply_markup=sorting_kb)
        else:
            await message.answer("Введите число в диапазоне от 1 до 35")
    except ValueError:
        await message.reply("Введите положительное целое число")


@dp.message_handler(state=StateWorker.set_filter)
async def set_filters(message: types.Message, state: FSMContext):
    if message.text == 'Только с номером':
        async with state.proxy() as data:
            data['filter'] = "number"
        await StateWorker.parsing_category.set()
        await message.answer("Введите URL категории. Воспользуйтесь /cancel для отмены")
    elif message.text == 'Только без номера':
        async with state.proxy() as data:
            data['filter'] = "nonumber"
        await StateWorker.parsing_category.set()
        await message.answer("Введите URL категории. Воспользуйтесь /cancel для отмены")
    elif message.text == 'Все':
        async with state.proxy() as data:
            data['filter'] = "all"
        await StateWorker.parsing_category.set()
        await message.answer("Введите URL категории. Воспользуйтесь /cancel для отмены")
    else:
        await message.reply("Нет такого фильтра, повторите попытку")


@dp.message_handler(lambda message: message.text.startswith("http"), state=StateWorker.parsing_category)
async def parse_category(message: types.Message, state: FSMContext):
    global i
    category_url = message.text
    print(category_url)
    response = ""
    while not response:
        if i >= len(proxies):
            await bot.send_message(chat_id=message.chat.id,
                                   text=f"Не удалось получить страницу {category_url}. Список прокси исчерпан")
            i = 0
            await state.finish()
            return
        try:
            proxy = proxies[i]
            response = requests.get(category_url, proxies=proxy)
        except requests.exceptions.ConnectionError:
            await bot.send_message(chat_id=message.chat.id, text=f"Не удалось получить страницу {category_url}. Ждём 10 сек и меняем прокси")
            i += 1
            time.sleep(10)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.findAll('article')
        links = []
        await message.answer("Парсим...")

        ads_count = 0
        filter = ""
        async with state.proxy() as data:
            ads_count = data['count']
            filter = data['filter']

        for card in cards:
            a = card.find('a')
            link = "https://allegrolokalnie.pl"+a['href']
            links.append(link)

        count = 0
        for link in links:
            if count >= ads_count:
                break
            try:
                db.Ad.create(link=link)
                if await parse_ad(url=link, chat_id=message.chat.id, filter=filter):
                    count += 1
            except IntegrityError:
                print(f"Объявление {link} уже парсилось, пропускаем")
                pass

        await message.answer("Парсинг страницы завершён")
        await state.finish()


# Обработчик текстового сообщения (URL)
@dp.message_handler(lambda message: message.text.startswith("http"), state=StateWorker.parsing_ad)
async def parse_ad_from_msg(message: types.Message, state: FSMContext):
    ad_url = message.text
    await message.reply(f"<b>Произвожу парсинг этого обьявления...</b>", parse_mode="html")
    await parse_ad(url=ad_url, chat_id=message.chat.id)

    await state.finish()

async def parse_ad(url:str, chat_id: int, filter: str):
    # Здесь добавляем код для парсинга страницы с использованием requests и BeautifulSoup
    global i
    response = ""
    while not response:
        if i >= len(proxies):
            await bot.send_message(chat_id=chat_id,
                                   text=f"Не удалось получить страницу {url}. Список прокси исчерпан")
            i = 0
            return
        try:
            proxy = proxies[i]
            response = requests.get(url, proxies=proxy)
        except requests.exceptions.ConnectionError:
            await bot.send_message(chat_id=chat_id,
                                   text=f"Не удалось получить страницу {url}. Ждём 10 сек и меняем прокси")
            i += 1
            time.sleep(10)

    if response.status_code == 200:
        driver.maximize_window()
        driver.get(url)
        print(url)
        time.sleep(3)
        try:
            driver.find_element(By.CLASS_NAME,
                                      "allegro-gdpr-consents-plugin__actions-container__accept-button").click()
        except NoSuchElementException:
            pass
        time.sleep(1)
        phone = ""
        try:
            driver.find_element(By.CLASS_NAME, "mlc-seller-details-contact__row-icon-obfuscated").click()
            time.sleep(1)
            nmb = driver.find_element(By.CLASS_NAME, "mlc-seller-details-contact__text")
            print(nmb)
            phone = nmb.text
            print(phone)
            if filter == 'nonumber':
                return False
        except NoSuchElementException:
            phone="None"
            if filter == 'number':
                return False

        soup = BeautifulSoup(response.text, "html.parser")
        h1_element = soup.find("h1", class_="ml-m-b-8")
        currency_span = soup.find("span", class_="ml-offer-price__currency")
        dollars_span = soup.find("span", class_="ml-offer-price__dollars")

        h2_element = soup.find("h2", class_="mlc-seller-details-header__heading")
        img_element = soup.find("img", class_="photo-carousel-photo-preview__image--not-full-screen", src=True)
        a_element = soup.find("a", class_="mlc-buyer-actions__secondary-action--message", href=True)
        if h1_element and currency_span and dollars_span and a_element and img_element:
            name = h1_element.get_text().replace('\n', '')
            currency_text = currency_span.get_text()
            dollars_text = dollars_span.get_text()

            href = a_element["href"]
            photo_url = img_element["src"]

            # Создаем папку "photos" (если она не существует)
            if not os.path.exists("photos"):
                os.makedirs("photos")

            # Получаем имя файла из ссылки на объявление
            file_name = os.path.join("photos", os.path.basename(photo_url))

            # Выводим ссылку на фото
            print("Ссылка на фото:", photo_url)

            # Скачиваем фото и сохраняем его в файл
            response = requests.get(photo_url, proxies=proxies[i])
            if response.status_code == 200:
                with open(f"{file_name}.png", "wb") as photo_file:
                    photo_file.write(response.content)
                    print(f"Фото успешно скачано и сохранено в файл '{file_name}.png'.")
            caption = f"<b>🛍 <a href='{url}'>{name}</a></b>\n\n💳 <code>{dollars_text}</code><b>{currency_text}</b>\n\n📞<code>{phone}</code>\n\n\n<b><a href='{url}'>⛓Ссылка на обьявление</a></b>\n<b><a href='https://allegrolokalnie.pl{href}'>⛓Ссылка на чатик</a>\n<a href='{photo_url}'>⛓Ссылка на фотку</a></b>"
            print(photo_file)
            await bot.send_photo(chat_id, open(str(file_name) + ".png", "rb"), caption=caption,
                                 parse_mode="html")
        else:
            await bot.send_message(chat_id=chat_id, text=f"Не смог пропарсить страницу {url}, выбери другой юрл или напиши кодеру!")
    else:
        await bot.send_message(chat_id=chat_id, text=f"Не удалось получить страницу {url}. МБ блокнуло айпи")

@dp.message_handler()
async def decision(message: types.Message):
    if message.text == 'Парсинг объявления':
        await message.answer("Введите URL объявления. Воспользуйтесь командой /cancel для отмены")
        await StateWorker.parsing_ad.set()
    elif message.text == 'Парсинг категории':
        await message.answer("Сколько объявлений парсить? (макс - 35)")
        await StateWorker.set_parsing_count.set()
    else:
        await message.answer("Нет такой команды.")

if __name__ == '__main__':
    from aiogram import executor
    import database as db
    db.connect()
    executor.start_polling(dp, skip_updates=True)
