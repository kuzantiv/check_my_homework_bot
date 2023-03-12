import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("homework_bot.log"),
        logging.StreamHandler(stream=sys.stdout)
    ]
)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет достумны ли переменные окружения."""
    if not all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        logging.critical('Необходимо указать все переменные окружения')
        sys.exit()


def send_message(bot, message: str):
    """Отправляет сообщение в телеграм чат о статусе ДЗ."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f"Сообщение отправлено в Telegram: {message}")
    except telegram.TelegramError as e:
        logging.error(f"Ошибка отправки сообщения в Telegram: {e}")


def get_api_answer(timestamp: int):
    """Делает запрос к API и обрабатывает ошибки."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            logging.error(f'Ошибка при запросе к API Practicum: '
                          f'{response.status_code} - {response.text}')
            raise None
        else:
            return response.json()

    except requests.exceptions.RequestException as error:
        logging.error(f'Ошибка при запросе к API Practicum: {error}')
        return None


def check_response(response):
    """Обрабатывает ответ запроса."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API Practicum не является словарем')
    if 'homeworks' not in response:
        raise KeyError('Ответ API Practicum не содержит ключа "homeworks"')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Ответ API Practicum содержит информацию о работах, '
                        'но это не список')
    if len(response['homeworks']) == 0:
        logging.info('Ответ API Practicum не содержит информации о работах')
        return None
    return response['homeworks'][0]


def parse_status(homework):
    """Обрабатывае статус ответа."""
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" не найден в ответе API Practicum')
    homework_name = homework['homework_name']
    if 'status' not in homework:
        raise KeyError('Ключ "status" не найден в ответе API Practicum')
    if homework['status'] not in HOMEWORK_VERDICTS:
        logging.error(f"Неожиданный статус работы: {homework['status']}")
        raise ValueError(f"Неожиданный статус работы: {homework['status']}")
    verdict = HOMEWORK_VERDICTS[homework['status']]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - RETRY_PERIOD
    # timestamp = 0

    while True:
        try:
            response = get_api_answer(timestamp)
            if response is not None:
                homework = check_response(response)
                if homework is not None:
                    message = parse_status(homework)
                    if message is not None:
                        send_message(bot, message)
        except Exception as error:
            logging.error(f'Сбой в работе программы: {error}')
        timestamp = int(time.time())
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
