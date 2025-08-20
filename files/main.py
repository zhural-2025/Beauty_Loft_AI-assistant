import os
import asyncio
import threading
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from functions import save_application_to_sheets, send_telegram_notification, ask_openai_assistant, validate_phone
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# === Flask-приложение ===
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type", "Authorization"]}})

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
application = Application.builder().token(TELEGRAM_BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()

# === Состояния для ConversationHandler ===
CHOOSING, TYPING_NAME, TYPING_PHONE, TYPING_SERVICE, TYPING_DATE, TYPING_MASTER = range(6)

# Клавиатуры для разных состояний
service_keyboard = ReplyKeyboardMarkup([
    ['Стрижка', 'Окрашивание'],
    ['Маникюр'],
    ['Отмена']
], resize_keyboard=True)

main_keyboard = ReplyKeyboardMarkup([
    ['Быстрая запись'],
    ['Консультация'],
], resize_keyboard=True)

# === История сообщений для OpenAI Assistant ===
user_histories = {}  # user_id: [messages]
user_data = {}  # user_id: {form_data}
HISTORY_LIMIT = 30

def extract_user_data(messages):
    """Извлекает данные пользователя из истории сообщений"""
    data = {}
    for msg in messages:
        if msg["role"] == "user":
            content = msg["content"].lower()
            original_content = msg["content"]
            
            # Услуга (содержит ключевые слова) - проверяем ПЕРВОЙ
            if not data.get('Услуга') and any(service in content for service in ['маникюр', 'окрашивание', 'стрижка', 'подстричься', 'хочу']):
                data['Услуга'] = original_content
            
            # Телефон (только цифры, 7-15 символов)
            elif not data.get('Телефон') and original_content.isdigit() and 7 <= len(original_content) <= 15:
                data['Телефон'] = original_content
            
            # Дата (содержит месяц)
            elif not data.get('Дата') and any(month in content for month in ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']):
                data['Дата'] = original_content
            
            # Мастер (содержит ключевые слова)
            elif not data.get('Мастер') and any(role in content for role in ['стилист', 'топ-стилист', 'арт-директор', 'ведущий']):
                data['Мастер'] = original_content
            
            # Имя (сообщение длиной до 50 символов, не цифры, не содержит ключевые слова услуг)
            elif not data.get('Имя') and len(original_content) <= 50 and not original_content.isdigit() and not any(char.isdigit() for char in original_content) and not any(service in content for service in ['маникюр', 'окрашивание', 'стрижка', 'подстричься', 'хочу']):
                data['Имя'] = original_content
            
            # Комментарий (ответ на вопрос о комментариях)
            elif not data.get('Комментарий') and (content in ['нет', 'без комментариев', 'нет комментариев', 'нте'] or 'комментари' in content):
                data['Комментарий'] = original_content
    
    print(f"Извлеченные данные: {data}")  # Отладочный вывод
    return data

async def try_save_application(user_id, source="Web"):
    """Пытается сохранить заявку, если собраны все необходимые данные"""
    try:
        # Получаем историю сообщений
        history = user_histories.get(user_id, [])
        
        # Извлекаем данные из истории
        data = extract_user_data(history)
        
        # Проверяем наличие всех необходимых данных
        required_fields = ['Имя', 'Телефон', 'Услуга', 'Дата', 'Мастер']
        if all(field in data for field in required_fields):
            # Добавляем источник и комментарий
            data['Источник'] = source
            if 'Комментарий' not in data:
                data['Комментарий'] = 'нет'
                
            print(f"Попытка сохранить данные: {data}")
            
            # Сохраняем в Google Sheets
            save_application_to_sheets(data)
            print(f"✅ Заявка успешно сохранена: {data}")
            
            # Отправляем уведомление в Telegram
            notification_text = f"🎉 НОВАЯ ЗАЯВКА!\n\nИмя: {data['Имя']}\nТелефон: {data['Телефон']}\nУслуга: {data['Услуга']}\nДата: {data['Дата']}\nМастер: {data['Мастер']}\nИсточник: {data['Источник']}"
            await send_telegram_notification(notification_text)
            
            # Очищаем историю после успешного сохранения
            user_histories[user_id] = []
            
            return True, "Заявка успешно сохранена"
    except Exception as e:
        print(f"❌ Ошибка при сохранении заявки: {e}")
        return False, f"Ошибка при сохранении: {str(e)}"
    
    return False, "Недостаточно данных"

# === Flask endpoint для веб-виджета (Tilda) ===
@app.route('/webchat', methods=['GET'])
def webchat_page():
    """Отображает HTML страницу веб-чата"""
    return '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Чат с салоном красоты</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .chat-container {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .chat-messages {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 5px;
            background-color: #fafafa;
        }
        .message {
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 10px;
            max-width: 80%;
        }
        .user-message {
            background-color: #007bff;
            color: white;
            margin-left: auto;
            text-align: right;
        }
        .bot-message {
            background-color: #e9ecef;
            color: #333;
        }
        .input-container {
            display: flex;
            gap: 10px;
        }
        #messageInput {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        #sendButton {
            padding: 10px 20px;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        #sendButton:hover {
            background-color: #0056b3;
        }
        .loading {
            color: #666;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <h2>💄 Чат с салоном красоты ArtBeauty</h2>
        <div class="chat-messages" id="chatMessages">
            <div class="message bot-message">
                Здравствуйте! Я помогу вам записаться на услуги нашего салона или отвечу на ваши вопросы. Чем могу помочь?
            </div>
        </div>
        <div class="input-container">
            <input type="text" id="messageInput" placeholder="Введите ваше сообщение..." />
            <button id="sendButton">Отправить</button>
        </div>
    </div>

    <script>
        const chatMessages = document.getElementById('chatMessages');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');

        function addMessage(text, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'bot-message'}`;
            messageDiv.textContent = text;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        // Создаем постоянный ID для сессии
        let sessionId = localStorage.getItem('webchat_session_id');
        if (!sessionId) {
            sessionId = 'web_' + Date.now();
            localStorage.setItem('webchat_session_id', sessionId);
        }

        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;

            addMessage(message, true);
            messageInput.value = '';
            sendButton.disabled = true;
            sendButton.textContent = 'Отправляется...';

            try {
                const response = await fetch('/webchat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        user_id: sessionId
                    })
                });

                const data = await response.json();
                
                if (data.answer) {
                    addMessage(data.answer);
                } else {
                    addMessage('Извините, произошла ошибка. Попробуйте позже.');
                }
            } catch (error) {
                console.error('Ошибка:', error);
                addMessage('Извините, произошла ошибка соединения. Попробуйте позже.');
            } finally {
                sendButton.disabled = false;
                sendButton.textContent = 'Отправить';
                messageInput.focus();
            }
        }

        sendButton.addEventListener('click', sendMessage);
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        messageInput.focus();
    </script>
</body>
</html>
    '''

@app.route('/webchat', methods=['POST'])
def webchat():
    try:
        print("Получен запрос к /webchat")  # Отладочный вывод
        data = request.get_json()
        if not data:
            print("Нет JSON данных")  # Отладочный вывод
            return jsonify({"error": "No JSON data"}), 400
            
        user_id = data.get('user_id', 'web')
        user_message = data.get('message', '')
        
        print(f"ID пользователя: {user_id}")  # Отладочный вывод
        print(f"Сообщение: {user_message}")  # Отладочный вывод
        
        if not user_message:
            print("Нет сообщения")  # Отладочный вывод
            return jsonify({"error": "No message provided"}), 400
            
        history = user_histories.get(user_id, [])
        history.append({"role": "user", "content": user_message})
        history = history[-HISTORY_LIMIT:]
        
        # Пробуем сохранить заявку после каждого сообщения (синхронно)
        saved, save_message = asyncio.run(try_save_application(user_id))
        if saved:
            print(f"✅ {save_message}")
        
        print("Отправляем запрос ассистенту...")  # Отладочный вывод
        answer = ask_openai_assistant(history)
        print(f"Получен ответ: {answer}")  # Отладочный вывод
        
        history.append({"role": "assistant", "content": answer})
        user_histories[user_id] = history
        
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"Ошибка в /webchat: {e}")  # Отладочный вывод
        return jsonify({"error": str(e)}), 500

# === Telegram Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало разговора с ботом"""
    await update.message.reply_text(
        "Здравствуйте! Я бот-администратор салона красоты. Чем могу помочь?",
        reply_markup=main_keyboard
    )
    return CHOOSING

async def handle_service_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора услуги"""
    user_message = update.message.text
    
    if user_message == 'Быстрая запись':
        await update.message.reply_text(
            "Как я могу к вам обращаться? Пожалуйста, напишите ваше имя.",
            reply_markup=ReplyKeyboardRemove()
        )
        return TYPING_NAME
    elif user_message == 'Консультация' or user_message.lower() != 'быстрая запись':
        # Добавляем сообщение пользователя в историю
        user_id = str(update.effective_user.id)
        history = user_histories.get(user_id, [])
        history.append({"role": "user", "content": user_message})
        
        try:
            # Получаем ответ от OpenAI Assistant
            print(f"Отправляем запрос ассистенту: {user_message}")
            answer = ask_openai_assistant(history)
            print(f"Получен ответ: {answer}")
            
            # Сохраняем ответ в историю
            history.append({"role": "assistant", "content": answer})
            user_histories[user_id] = history
            
            await update.message.reply_text(
                answer,
                reply_markup=main_keyboard
            )
        except Exception as e:
            print(f"Ошибка при обработке запроса: {str(e)}")
            await update.message.reply_text(
                "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте переформулировать или выберите 'Быстрая запись' для записи на услугу.",
                reply_markup=main_keyboard
            )
        return CHOOSING
    else:
        await update.message.reply_text(
            "Пожалуйста, воспользуйтесь кнопками меню.",
            reply_markup=main_keyboard
        )
        return CHOOSING

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение имени и запрос телефона"""
    user_data[update.effective_user.id] = {'name': update.message.text}
    await update.message.reply_text(
        "Спасибо! Теперь, пожалуйста, укажите ваш номер телефона в формате 79XXXXXXXXX"
    )
    return TYPING_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение телефона и запрос услуги"""
    phone = update.message.text
    if not validate_phone(phone):
        await update.message.reply_text(
            "Пожалуйста, введите корректный номер телефона в формате 79XXXXXXXXX"
        )
        return TYPING_PHONE
    
    user_data[update.effective_user.id]['phone'] = phone
    await update.message.reply_text(
        "Выберите услугу:",
        reply_markup=service_keyboard
    )
    return TYPING_SERVICE

async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение услуги и запрос даты"""
    user_message = update.message.text
    if user_message == 'Отмена':
        await update.message.reply_text(
            "Запись отменена. Чем еще могу помочь?",
            reply_markup=main_keyboard
        )
        return CHOOSING
    
    if user_message not in ['Стрижка', 'Окрашивание', 'Маникюр']:
        await update.message.reply_text(
            "Пожалуйста, выберите услугу из предложенных вариантов",
            reply_markup=service_keyboard
        )
        return TYPING_SERVICE
    
    user_data[update.effective_user.id]['service'] = user_message
    await update.message.reply_text(
        "На какую дату вы хотели бы записаться? (например, '15 сентября')",
        reply_markup=ReplyKeyboardRemove()
    )
    return TYPING_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение даты и запрос мастера"""
    user_data[update.effective_user.id]['date'] = update.message.text
    await update.message.reply_text(
        "Укажите предпочтительного мастера (если нет предпочтений, напишите 'любой')"
    )
    return TYPING_MASTER

async def handle_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение записи"""
    user_id = update.effective_user.id
    user_data[user_id]['master'] = update.message.text
    
    # Формируем данные для сохранения
    data = {
        'Имя': user_data[user_id]['name'],
        'Телефон': user_data[user_id]['phone'],
        'Услуга': user_data[user_id]['service'],
        'Дата': user_data[user_id]['date'],
        'Мастер': user_data[user_id]['master'],
        'Источник': 'Telegram',
        'Комментарий': 'нет'
    }
    
    try:
        # Сохраняем в Google Sheets
        save_application_to_sheets(data)
        
        # Отправляем уведомление в Telegram
        notification_text = f"🎉 НОВАЯ ЗАЯВКА!\n\nИмя: {data['Имя']}\nТелефон: {data['Телефон']}\nУслуга: {data['Услуга']}\nДата: {data['Дата']}\nМастер: {data['Мастер']}\nИсточник: {data['Источник']}"
        await send_telegram_notification(notification_text)
        
        await update.message.reply_text(
            f"Отлично! Ваша запись оформлена:\n"
            f"Имя: {data['Имя']}\n"
            f"Телефон: {data['Телефон']}\n"
            f"Услуга: {data['Услуга']}\n"
            f"Дата: {data['Дата']}\n"
            f"Мастер: {data['Мастер']}\n\n"
            f"Мы свяжемся с вами для подтверждения записи!",
            reply_markup=main_keyboard
        )
    except Exception as e:
        print(f"❌ Ошибка при сохранении заявки: {e}")
        await update.message.reply_text(
            "Извините, произошла ошибка при сохранении заявки. Пожалуйста, попробуйте позже.",
            reply_markup=main_keyboard
        )
    
    return CHOOSING

# Регистрируем обработчики
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service_choice)],
        TYPING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        TYPING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
        TYPING_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_service)],
        TYPING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
        TYPING_MASTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_master)],
    },
    fallbacks=[CommandHandler('start', start)]
)

application.add_handler(conv_handler)

def run_flask():
    """Запускает Flask сервер"""
    app.run(host='0.0.0.0', port=5000)

def run_telegram():
    """Запускает Telegram бота"""
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        print(f"❌ Ошибка в работе бота: {str(e)}")
        print("Перезапуск бота через 5 секунд...")
        time.sleep(5)
        run_telegram()  # Рекурсивный перезапуск

if __name__ == '__main__':
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    print("Запуск Telegram бота...")
    print("Бот готов к работе!")
    print("Отправьте /start в Telegram для начала работы")
    
    # Запускаем Telegram бота в основном потоке
    run_telegram()