import socket
import sys
import time
import logging
import json
import threading
import hashlib
import hmac
import binascii
from PyQt5.QtCore import pyqtSignal, QObject

sys.path.append('../')
from common.decorator import log
from common.utils import get_message, send_message
from common.variables import default_port, default_ip_address
from common.errors import ServerError

# Логер и объект блокировки для работы с сокетом.
LOGGER = logging.getLogger('client')
socket_lock = threading.Lock()


class ClientTransport(threading.Thread, QObject):
    '''
    Класс реализующий транспортную подсистему клиентского
    модуля. Отвечает за взаимодействие с сервером.
    '''
    # Сигналы новое сообщение и потеря соединения
    new_message = pyqtSignal(dict)
    message_205 = pyqtSignal()
    connection_lost = pyqtSignal()

    def __init__(self, port, ip_address, database, username, passwd, keys):
        # Вызываем конструкторы предков
        threading.Thread.__init__(self)
        QObject.__init__(self)

        # Класс База данных - работа с базой
        self.database = database
        # Имя пользователя
        self.username = username
        # Пароль
        self.password = passwd
        # Сокет для работы с сервером
        self.transport = None
        # Набор ключей для шифрования
        self.keys = keys
        # Устанавливаем соединение:
        self.connection_init(port, ip_address)
        # Обновляем таблицы известных пользователей и контактов
        try:
            self.user_list_update()
            self.contacts_list_update()
        except OSError as err:
            if err.errno:
                LOGGER.critical(f'Потеряно соединение с сервером.')
                raise ServerError('Потеряно соединение с сервером!')
            LOGGER.error(
                'Timeout соединения при обновлении списков пользователей.')
        except json.JSONDecodeError:
            LOGGER.critical(f'Потеряно соединение с сервером.')
            raise ServerError('Потеряно соединение с сервером!')
            # Флаг продолжения работы транспорта.
        self.running = True

    def connection_init(self, port, ip):
        '''Метод отвечающий за устанновку соединения с сервером.'''
        # Инициализация сокета и сообщение серверу о нашем появлении
        self.transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Таймаут необходим для освобождения сокета.
        self.transport.settimeout(5)

        # Соединяемся, 5 попыток соединения, флаг успеха ставим в True если
        # удалось
        connected = False
        for i in range(5):
            LOGGER.info(f'Попытка подключения №{i + 1}')
            try:
                self.transport.connect((ip, port))
            except (OSError, ConnectionRefusedError):
                pass
            else:
                connected = True
                LOGGER.debug("Connection established.")
                break
            time.sleep(1)

        # Если соединится не удалось - исключение
        if not connected:
            LOGGER.critical('Не удалось установить соединение с сервером')
            raise ServerError('Не удалось установить соединение с сервером')

        LOGGER.debug('Starting auth dialog.')

        # Запускаем процедуру авторизации
        # Получаем хэш пароля
        passwd_bytes = self.password.encode('utf-8')
        salt = self.username.lower().encode('utf-8')
        passwd_hash = hashlib.pbkdf2_hmac('sha512', passwd_bytes, salt, 10000)
        passwd_hash_string = binascii.hexlify(passwd_hash)

        LOGGER.debug(f'Passwd hash ready: {passwd_hash_string}')

        # Получаем публичный ключ и декодируем его из байтов
        pubkey = self.keys.publickey().export_key().decode('ascii')

        # Авторизируемся на сервере
        with socket_lock:
            presense = {
                'action': 'presence',
                'time': time.time(),
                'user': {
                    'account_name': self.username,
                    'pubkey': pubkey
                }
            }
            LOGGER.debug(f"Presense message = {presense}")
            # Отправляем серверу приветственное сообщение.
            try:
                send_message(self.transport, presense)
                ans = get_message(self.transport)
                LOGGER.debug(f'Server response = {ans}.')
                # Если сервер вернул ошибку, бросаем исключение.
                if 'response' in ans:
                    if ans['response'] == 400:
                        raise ServerError(ans['error'])
                    elif ans['response'] == 511:
                        # Если всё нормально, то продолжаем процедуру
                        # авторизации.
                        ans_data = ans['bin']
                        hash = hmac.new(passwd_hash_string, ans_data.encode('utf-8'), 'MD5')
                        digest = hash.digest()
                        my_ans = {'response': 511, 'bin': None}
                        my_ans['bin'] = binascii.b2a_base64(
                            digest).decode('ascii')
                        send_message(self.transport, my_ans)
                        self.process_server_ans(get_message(self.transport))
            except (OSError, json.JSONDecodeError) as err:
                LOGGER.debug(f'Connection error.', exc_info=err)
                raise ServerError('Сбой соединения в процессе авторизации.')

    def process_server_ans(self, message):
        '''Метод обработчик поступающих сообщений с сервера.'''
        LOGGER.debug(f'Разбор сообщения от сервера: {message}')

        # Если это подтверждение чего-либо
        if 'response' in message:
            if message['response'] == 200:
                return
            elif message['response'] == 400:
                raise ServerError(f'{message["error"]}')
            elif message['response'] == 205:
                self.user_list_update()
                self.contacts_list_update()
                self.message_205.emit()
            else:
                LOGGER.error(
                    f'Принят неизвестный код подтверждения {message["response"]}')

        # Если это сообщение от пользователя добавляем в базу, даём сигнал о
        # новом сообщении
        elif 'action' in message and message['action'] == 'message' and 'from' in message and 'to' in message \
                and 'mess_text' in message and message['to'] == self.username:
            LOGGER.debug(
                f'Получено сообщение от пользователя {message["from"]}:{message["mess_text"]}')
            self.new_message.emit(message)

    def contacts_list_update(self):
        '''Метод обновляющий с сервера список контактов.'''
        self.database.contacts_clear()
        LOGGER.debug(f'Запрос контакт листа для пользователся {self.name}')
        req = {
            'action': 'get_contacts',
            'time': time.time(),
            'user': self.username
        }
        LOGGER.debug(f'Сформирован запрос {req}')
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        LOGGER.debug(f'Получен ответ {ans}')
        if 'response' in ans and ans['response'] == 202:
            for contact in ans['data_list']:
                self.database.add_contact(contact)
        else:
            LOGGER.error('Не удалось обновить список контактов.')

    def user_list_update(self):
        '''Метод обновляющий с сервера список пользователей.'''
        LOGGER.debug(f'Запрос списка известных пользователей {self.username}')
        req = {
            'action': 'get_users',
            'time': time.time(),
            'account_name': self.username
        }
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        if 'response' in ans and ans['response'] == 202:
            self.database.add_users(ans['data_list'])
        else:
            LOGGER.error('Не удалось обновить список известных пользователей.')

    def key_request(self, user):
        '''Метод запрашивающий с сервера публичный ключ пользователя.'''
        LOGGER.debug(f'Запрос публичного ключа для {user}')
        req = {
            'action': 'pubkey_need',
            'time': time.time(),
            'account_name': user
        }
        with socket_lock:
            send_message(self.transport, req)
            ans = get_message(self.transport)
        if 'response' in ans and ans['response'] == 511:
            return ans['bin']
        else:
            LOGGER.error(f'Не удалось получить ключ собеседника{user}.')

    def add_contact(self, contact):
        '''Метод отправляющий на сервер сведения о добавлении контакта.'''
        LOGGER.debug(f'Создание контакта {contact}')
        req = {
            'action': 'add',
            'time': time.time(),
            'user': self.username,
            'account_name': contact
        }
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def remove_contact(self, contact):
        '''Метод отправляющий на сервер сведения о удалении контакта.'''
        LOGGER.debug(f'Удаление контакта {contact}')
        req = {
            'action': 'remove',
            'time': time.time(),
            'user': self.username,
            'account_name': contact
        }
        with socket_lock:
            send_message(self.transport, req)
            self.process_server_ans(get_message(self.transport))

    def transport_shutdown(self):
        '''Метод уведомляющий сервер о завершении работы клиента.'''
        self.running = False
        message = {
            'action': 'exit',
            'time': time.time(),
            'account_name': self.username
        }
        with socket_lock:
            try:
                send_message(self.transport, message)
            except OSError:
                pass
        LOGGER.debug('Транспорт завершает работу.')
        time.sleep(0.5)

    def send_message(self, to, message):
        '''Метод отправляющий на сервер сообщения для пользователя.'''
        message_dict = {
            'action': 'message',
            'from': self.username,
            'to': to,
            'time': time.time(),
            'mess_text': message
        }
        LOGGER.debug(f'Сформирован словарь сообщения: {message_dict}')
        # Необходимо дождаться освобождения сокета для отправки сообщения
        with socket_lock:
            send_message(self.transport, message_dict)
            self.process_server_ans(get_message(self.transport))
            LOGGER.info(f'Отправлено сообщение для пользователя {to}')

    def run(self):
        '''Метод содержащий основной цикл работы транспортного потока.'''
        LOGGER.debug('Запущен процесс - приёмник собщений с сервера.')
        while self.running:
            # Отдыхаем секунду и снова пробуем захватить сокет.
            # если не сделать тут задержку, то отправка может достаточно долго
            # ждать освобождения сокета.
            time.sleep(1)
            message = None
            with socket_lock:
                try:
                    self.transport.settimeout(0.5)
                    message = get_message(self.transport)
                except OSError as err:
                    if err.errno:
                        LOGGER.critical(f'Потеряно соединение с сервером.')
                        self.running = False
                        self.connection_lost.emit()
                # Проблемы с соединением
                except (ConnectionError, ConnectionAbortedError, ConnectionResetError, json.JSONDecodeError, TypeError):
                    LOGGER.debug(f'Потеряно соединение с сервером.')
                    self.running = False
                    self.connection_lost.emit()
                finally:
                    self.transport.settimeout(5)

            # Если сообщение получено, то вызываем функцию обработчик:
            if message:
                LOGGER.debug(f'Принято сообщение с сервера: {message}')
                self.process_server_ans(message)
