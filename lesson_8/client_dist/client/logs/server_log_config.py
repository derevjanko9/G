import logging
from logging.handlers import TimedRotatingFileHandler
import os

log = logging.getLogger('server')

path = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(path, 'server.log')
file_hand = TimedRotatingFileHandler(path, when='D', interval=1, backupCount=0, encoding='utf-8', delay=False,
                                     utc=False, atTime=None)

# file_hand.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelno)s - %(module)s - %(message)s ")
file_hand.setFormatter(formatter)

log.addHandler(file_hand)
log.setLevel(logging.DEBUG)

if __name__ == '__main__':
    log.debug('Отладочная информация')
    log.info('Информационное сообщение')
    log.warning('Предупреждение')
    log.error('Ошибка')
    log.critical('Критическое общение')
