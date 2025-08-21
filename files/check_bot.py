import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot

async def check_bot():
    load_dotenv()
    bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
    try:
        me = await bot.get_me()
        print('✅ Telegram Bot активен:', me.first_name, '(@' + me.username + ')')
        return True
    except Exception as e:
        print('❌ Ошибка Telegram Bot:', e)
        return False

if __name__ == '__main__':
    asyncio.run(check_bot())
