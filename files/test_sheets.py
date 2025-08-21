#!/usr/bin/env python3
"""
Тест подключения к Google Sheets
Проверяет работоспособность сервисного аккаунта и доступ к таблице
"""

import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def test_google_sheets_connection():
    """Тестирует подключение к Google Sheets"""
    
    print("🔍 Тестирование подключения к Google Sheets...")
    print("=" * 50)
    
    # Проверяем наличие файла credentials.json
    credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
    if not os.path.exists(credentials_path):
        print(f"❌ Файл {credentials_path} не найден!")
        print("   Создайте новый сервисный аккаунт и скачайте ключ JSON")
        return False
    
    print(f"✅ Файл {credentials_path} найден")
    
    # Проверяем переменные окружения
    required_vars = [
        'GOOGLE_SHEET_ID',
        'GOOGLE_CREDENTIALS_PATH',
        'GOOGLE_CREDENTIALS_EMAIL'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        else:
            print(f"✅ {var}: {value}")
    
    if missing_vars:
        print(f"❌ Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        return False
    
    # Пробуем импортировать Google API
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        print("✅ Google API библиотеки импортированы")
    except ImportError as e:
        print(f"❌ Ошибка импорта Google API: {e}")
        print("   Установите: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return False
    
    # Пробуем создать credentials
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        print("✅ Сервисный аккаунт загружен")
    except Exception as e:
        print(f"❌ Ошибка загрузки сервисного аккаунта: {e}")
        print("   Возможно, ключ поврежден или недействителен")
        return False
    
    # Пробуем создать сервис
    try:
        sheets_service = build('sheets', 'v4', credentials=credentials)
        print("✅ Google Sheets API сервис создан")
    except Exception as e:
        print(f"❌ Ошибка создания API сервиса: {e}")
        return False
    
    # Пробуем получить метаданные таблицы
    sheet_id = os.getenv('GOOGLE_SHEET_ID')
    try:
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        print(f"✅ Доступ к таблице получен")
        print(f"   Название: {sheet_metadata.get('properties', {}).get('title')}")
        print(f"   ID: {sheet_id}")
    except Exception as e:
        print(f"❌ Ошибка доступа к таблице: {e}")
        print("   Проверьте:")
        print("   1. ID таблицы в переменной GOOGLE_SHEET_ID")
        print("   2. Права доступа сервисного аккаунта к таблице")
        print("   3. Существование таблицы")
        return False
    
    # Пробуем прочитать данные
    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="A1:A1"
        ).execute()
        print("✅ Чтение данных успешно")
    except Exception as e:
        print(f"❌ Ошибка чтения данных: {e}")
        return False
    
    # Пробуем записать тестовые данные
    try:
        test_values = [["TEST", "TEST", "TEST", "TEST", "TEST", "TEST", "TEST"]]
        sheets_service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Лист1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": test_values}
        ).execute()
        print("✅ Запись тестовых данных успешна")
    except Exception as e:
        print(f"❌ Ошибка записи данных: {e}")
        print("   Возможно, недостаточно прав для записи")
        return False
    
    print("=" * 50)
    print("🎉 Все тесты пройдены! Google Sheets подключение работает корректно")
    return True

if __name__ == "__main__":
    success = test_google_sheets_connection()
    sys.exit(0 if success else 1)