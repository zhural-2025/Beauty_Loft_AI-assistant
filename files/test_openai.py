#!/usr/bin/env python3
"""
Тест подключения к OpenAI Assistant
"""

import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def test_openai_connection():
    """Тестирует подключение к OpenAI"""
    
    print("🔍 Тестирование подключения к OpenAI...")
    print("=" * 50)
    
    # Проверяем переменные окружения
    openai_api_key = os.getenv('OPENAI_API_KEY')
    openai_assistant_id = os.getenv('OPENAI_ASSISTANT_ID')
    
    if not openai_api_key:
        print("❌ OPENAI_API_KEY не найден в .env")
        return False
    
    if not openai_assistant_id:
        print("❌ OPENAI_ASSISTANT_ID не найден в .env")
        return False
    
    print(f"✅ OPENAI_API_KEY: {openai_api_key[:20]}...")
    print(f"✅ OPENAI_ASSISTANT_ID: {openai_assistant_id}")
    
    # Пробуем импортировать OpenAI
    try:
        import openai
        print("✅ OpenAI библиотека импортирована")
    except ImportError as e:
        print(f"❌ Ошибка импорта OpenAI: {e}")
        print("   Установите: pip install openai")
        return False
    
    # Пробуем создать клиент
    try:
        client = openai.Client(api_key=openai_api_key)
        print("✅ OpenAI клиент создан")
    except Exception as e:
        print(f"❌ Ошибка создания клиента: {e}")
        return False
    
    # Пробуем получить информацию об ассистенте
    try:
        assistant = client.beta.assistants.retrieve(openai_assistant_id)
        print(f"✅ Ассистент найден: {assistant.name}")
    except Exception as e:
        print(f"❌ Ошибка получения ассистента: {e}")
        return False
    
    # Пробуем создать thread и отправить сообщение
    try:
        # Создаем thread
        thread = client.beta.threads.create()
        print("✅ Thread создан")
        
        # Добавляем сообщение
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Привет! Как дела?"
        )
        print("✅ Сообщение добавлено")
        
        # Запускаем assistant
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=openai_assistant_id
        )
        print("✅ Run запущен")
        
        # Ожидаем завершения
        import time
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            elif run_status.status == 'failed':
                print(f"❌ Run failed: {run_status.last_error}")
                return False
            time.sleep(1)
        
        # Получаем ответ
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        if messages.data:
            answer = messages.data[0].content[0].text.value
            print(f"✅ Получен ответ: {answer[:100]}...")
        else:
            print("❌ Ответ не получен")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка тестирования ассистента: {e}")
        return False
    
    print("=" * 50)
    print("🎉 Все тесты OpenAI пройдены!")
    return True

if __name__ == "__main__":
    success = test_openai_connection()
    exit(0 if success else 1)
