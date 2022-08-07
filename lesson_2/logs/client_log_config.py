import logging
import os

log = logging.getLogger('client')

path = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(path, 'client.log')
file_hand = logging.FileHandler(path, encoding='utf-8')

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
