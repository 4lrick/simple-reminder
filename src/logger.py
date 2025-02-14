import logging
import sys

def setup_logger():
    logger = logging.getLogger('reminder_bot')
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler('data/bot.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger