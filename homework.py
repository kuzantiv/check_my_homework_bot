import logging
import sys
import time
from functools import wraps

import exceptions
import requests
import telegram
from dotenv import dotenv_values

env_variables: dict[str, str | None] = dotenv_values()

PRACTICUM_TOKEN: str = env_variables.get('PRACTICUM_TOKEN') or ''
TELEGRAM_TOKEN: str = env_variables.get('TELEGRAM_TOKEN') or ''
TELEGRAM_CHAT_ID: str = env_variables.get('TELEGRAM_CHAT_ID') or ''

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: dict[str, str] = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: dict[str, str] = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('homework_bot.log'),
        logging.StreamHandler(stream=sys.stdout)
    ]
)


def check_tokens() -> None:
    """Проверяет достумны ли переменные окружения."""
    if not all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        logging.critical('Необходимо указать все переменные окружения')
        sys.exit('Выполнение программы остановлено, '
                 'не найдены необходимые переменные окружения')


def deduplicate_messages(func):
    """Предотвращает отправку повторяющихся сообщений в Telegram."""
    last_message = None

    @wraps(func)
    def wrapper(bot: telegram.Bot, message: str) -> None:
        nonlocal last_message

        if message == last_message:
            logging.debug(f"Повторное сообщение не будет отправлено: {message}")
        else:
            func(bot, message)
            last_message = message

    return wrapper


@deduplicate_messages
def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в телеграм чат о статусе ДЗ."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug(f'Сообщение отправлено в Telegram: {message}')
    except telegram.TelegramError as e:
        logging.error(f'Ошибка отправки сообщения в Telegram: {e}')


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к API и обрабатывает ошибки."""
    payload: dict[str, int] = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params=payload,
                                timeout=5)
        if response.status_code != 200:
            logging.error(f'Ошибка при запросе к API Practicum: '
                          f'{response.status_code} - {response.text}')
            raise exceptions.APIRequestError(
                'Ошибка при запросе к API Practicum'
            )
        else:
            logging.info('API ответ получен')
            return response.json()

    except requests.exceptions.RequestException as error:
        logging.error(f'Ошибка при запросе к API Practicum: {error}')
        raise exceptions.APIRequestError('Ошибка при запросе к API Practicum')


def check_response(response: dict[str, list[dict[str, str]]]
                   ) -> dict[str, str] | None:
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


def parse_status(homework: dict[str, str]) -> str:
    """Обрабатывает статус ответа."""
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" не найден в ответе API Practicum')
    homework_name = homework['homework_name']
    if 'status' not in homework:
        raise KeyError('Ключ "status" не найден в ответе API Practicum')
    if homework['status'] not in HOMEWORK_VERDICTS:
        logging.error(f'Неожиданный статус работы: {homework["status"]}')
        raise ValueError(f'Неожиданный статус работы: {homework["status"]}')
    verdict = HOMEWORK_VERDICTS[homework["status"]]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp: int = int(time.time()) - RETRY_PERIOD
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework)
                send_message(bot, message)
            else:
                logging.debug("Пока новых работ нет")

        except exceptions.HomeworkStatusError as e:
            message = f"Ошибка получения статуса ДЗ: {e}"
            logging.error(message)
            send_message(bot, message)

        except Exception as e:
            message = f"Неизвестная ошибка: {e}"
            logging.error(message)
            send_message(bot, message)

        finally:
            logging.info(f"Ожидание {RETRY_PERIOD} секунд до следующего запроса")
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
