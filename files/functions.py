import os
import json
import pytz
import requests
from dotenv import load_dotenv

# === Google Sheets ===
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# === Telegram ===
from telegram import Bot

# === OpenAI Assistant ===
import openai

# Загрузка переменных окружения
load_dotenv()

# === Инициализация Google Sheets ===
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
GOOGLE_SHEETS_NAME = os.getenv('GOOGLE_SHEETS_NAME')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH')

credentials = Credentials.from_service_account_file(
    GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
)
sheets_service = build('sheets', 'v4', credentials=credentials)

# === Инициализация Telegram Bot ===
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID')
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# === Инициализация OpenAI Assistant ===
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')

def test_google_sheets():
    """
    Тестирует подключение к Google Sheets
    """
    try:
        # Пробуем получить метаданные таблицы
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=GOOGLE_SHEET_ID).execute()
        print("✅ Подключение к Google Sheets успешно")
        print(f"Название таблицы: {sheet_metadata.get('properties', {}).get('title')}")
        print(f"ID таблицы: {GOOGLE_SHEET_ID}")
        
        # Пробуем прочитать данные
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="A1:A1"
        ).execute()
        print("✅ Чтение данных успешно")
        
        # Пробуем записать тестовые данные
        test_values = [["TEST", "TEST", "TEST", "TEST", "TEST", "TEST", "TEST"]]
        sheets_service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Лист1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": test_values}
        ).execute()
        print("✅ Запись данных успешна")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка Google Sheets: {e}")
        return False

# === Google Sheets: запись заявки ===
def save_application_to_sheets(data: dict):
    """
    Сохраняет заявку в Google Sheets.
    data: {
        'Имя', 'Телефон', 'Услуга', 'Дата', 'Мастер', 'Комментарий', 'Источник'
    }
    """
    values = [[
        data.get('Имя', ''),
        data.get('Телефон', ''),
        data.get('Услуга', ''),
        data.get('Дата', ''),
        data.get('Мастер', ''),
        data.get('Комментарий', ''),
        data.get('Источник', '')
    ]]
    
    try:
        print("Пробуем сохранить данные:", values)
        # Пробуем использовать русское название листа
        sheets_service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Лист1!A1",  # Используем правильное название листа
            valueInputOption="USER_ENTERED",
            body={"values": values}
        ).execute()
        print("✅ Заявка успешно сохранена в Google Sheets")
    except Exception as e:
        print(f"❌ Ошибка при сохранении в Google Sheets: {e}")
        # Если не получилось, пробуем без указания листа
        try:
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEET_ID,
                range="A1",  # Без указания листа
                valueInputOption="USER_ENTERED",
                body={"values": values}
            ).execute()
            print("✅ Заявка сохранена в первый лист")
        except Exception as e2:
            print(f"❌ Критическая ошибка: {e2}")
            raise e2  # Пробрасываем ошибку дальше

# === Telegram: отправка уведомления в служебный чат ===
async def send_telegram_notification(text: str):
    """
    Отправляет уведомление в служебный Telegram-чат.
    """
    try:
        # Создаем новое подключение к боту для отправки уведомления
        from telegram import Bot
        notification_bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        await notification_bot.send_message(chat_id=TELEGRAM_ADMIN_CHAT_ID, text=text)
        print("✅ Уведомление отправлено в Telegram")
        
        # Закрываем соединение
        await notification_bot.close()
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")

# === OpenAI Assistant: получить ответ ассистента ===
def ask_openai_assistant(messages: list):
    """
    Отправляет сообщения дообученному ассистенту OpenAI и возвращает ответ.
    messages: список сообщений в формате OpenAI (role, content)
    """
    try:
        client = openai.Client(api_key=OPENAI_API_KEY)
        
        # Создаем thread
        thread = client.beta.threads.create()
        
        # Добавляем сообщения в thread
        for message in messages:
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role=message["role"],
                content=message["content"]
            )
        
        # Запускаем assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=OPENAI_ASSISTANT_ID
        )
        
        # Ожидаем завершения
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            elif run_status.status == 'failed':
                print(f"❌ Run failed: {run_status.last_error}")
                return "Извините, произошла ошибка при обработке запроса."
        
        # Получаем ответ
        messages_response = client.beta.threads.messages.list(thread_id=thread.id)
        answer = messages_response.data[0].content[0].text.value
        return answer
        
    except Exception as e:
        print(f"❌ Ошибка OpenAI Assistant: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

# === Вспомогательные функции ===
def validate_phone(phone: str) -> bool:
    """
    Простейшая валидация телефона.
    """
    return phone.isdigit() and 7 <= len(phone) <= 15