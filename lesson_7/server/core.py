import threading
import logging
import select
import socket
import json
import hmac
import binascii
import os
import sys
sys.path.append('../')
from metaclasses import ServerVerifier
from descrptrs import Port
from common.decorator import log
from common.variables import max_connections
from common.utils import send_message, get_message

# Загрузка логера
LOGGER = logging.getLogger('server')


class MessageProcessor(threading.Thread):
    """
    Основной класс сервера. Принимает содинения, словари - пакеты
    от клиентов, обрабатывает поступающие сообщения.
    Работает в качестве отдельного потока.
    """
    port = Port()

    def __init__(self, listen_address, listen_port, database):
        # Параметры подключения
        self.addr = listen_address
        self.port = listen_port

        # База данных сервера
        self.database = database

        # Сокет, через который будет осуществляться работа
        self.sock = None

        # Список подключённых клиентов.
        self.clients = []

        # Сокеты
        self.listen_sockets = None
        self.error_sockets = None

        # Флаг продолжения работы
        self.running = True

        # Словарь содержащий сопоставленные имена и соответствующие им сокеты.
        # {'test1': <socket.socket fd=25, family=AddressFamily.AF_INET, type=SocketKind.SOCK_STREAM, proto=0, laddr=('127.0.0.1', 7777), raddr=('127.0.0.1', 52420)>}
        self.names = dict()

        # Конструктор предка
        super().__init__()

    def run(self):
        '''Метод основной цикл потока.'''
        # Инициализация Сокета
        self.init_socket()

        # Основной цикл программы сервера
        while self.running:
            # Ждём подключения, если таймаут вышел, ловим исключение.
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                LOGGER.info(f'Установлено соедение с ПК {client_address}')
                client.settimeout(5)
                self.clients.append(client)

            recv_data_lst = []
            send_data_lst = []
            err_lst = []
            # Проверяем на наличие ждущих клиентов
            try:
                if self.clients:
                    recv_data_lst, self.listen_sockets, self.error_sockets = select.select(
                        self.clients, self.clients, [], 0)
            except OSError as err:
                LOGGER.error(f'Ошибка работы с сокетами: {err.errno}')

            # принимаем сообщения и если ошибка, исключаем клиента.
            if recv_data_lst:
                for client_with_message in recv_data_lst:
                    try:
                        self.process_client_message(
                            get_message(client_with_message), client_with_message)
                    except (OSError, json.JSONDecodeError, TypeError) as err:
                        LOGGER.debug(f'Getting data from client exception.', exc_info=err)
                        self.remove_client(client_with_message)

    def remove_client(self, client):
        '''
        Метод обработчик клиента с которым прервана связь.
        Ищет клиента и удаляет его из списков и базы:
        '''
        LOGGER.info(f'Клиент {client.getpeername()} отключился от сервера.')
        for name in self.names:
            if self.names[name] == client:
                self.database.user_logout(name)
                del self.names[name]
                break
        self.clients.remove(client)
        client.close()

    def init_socket(self):
        '''Метод инициализатор сокета.'''
        LOGGER.info(
            f'Запущен сервер, порт для подключений: {self.port} , адрес с которого принимаются подключения: {self.addr}. Если адрес не указан, принимаются соединения с любых адресов.')
        # Готовим сокет
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        # Начинаем слушать сокет.
        self.sock = transport
        self.sock.listen(max_connections)

    def process_message(self, message):
        '''
        Метод отправки сообщения клиенту.
        '''
        if message['to'] in self.names and self.names[message['to']
        ] in self.listen_sockets:
            try:
                send_message(self.names[message['to']], message)
                LOGGER.info(
                    f'Отправлено сообщение пользователю {message["to"]} от пользователя {message["from"]}.')
            except OSError:
                self.remove_client(message['to'])
        elif message['to'] in self.names and self.names[message['to']] not in self.listen_sockets:
            LOGGER.error(
                f'Связь с клиентом {message["to"]} была потеряна. Соединение закрыто, доставка невозможна.')
            self.remove_client(self.names[message['to']])
        else:
            LOGGER.error(
                f'Пользователь {message["to"]} не зарегистрирован на сервере, отправка сообщения невозможна.')

    @log
    def process_client_message(self, message, client):
        """ Метод обработчик поступающих сообщений. """
        LOGGER.debug(f'Разбор сообщения от клиента : {message}')
        # Если это сообщение о присутствии, принимаем и отвечаем
        if 'action' in message and message['action'] == 'presence' and 'time' in message and 'user' in message:
            # Если сообщение о присутствии то вызываем функцию авторизации.
            self.autorize_user(message, client)

        # Если это сообщение, то отправляем его получателю.
        elif 'action' in message and message['action'] == 'message' and 'to' in message and 'time' in message \
                and 'from' in message and 'mess_text' in message and self.names[message['from']] == client:
            if message['to'] in self.names:
                self.database.process_message(
                    message['from'], message['to'])
                self.process_message(message)
                try:
                    send_message(client, {'response': 200})
                except OSError:
                    self.remove_client(client)
            else:
                response = {'response': 400, 'error': None}
                response['error'] = 'Пользователь не зарегистрирован на сервере.'
                try:
                    send_message(client, response)
                except OSError:
                    pass
            return

        # Если клиент выходит
        elif 'action' in message and message['action'] == 'exit' and 'account_name' in message \
                and self.names[message['account_name']] == client:
            self.remove_client(client)

        # Если это запрос контакт-листа
        elif 'action' in message and message['action'] == 'get_contacts' and 'user' in message and \
                self.names[message['user']] == client:
            response = {'response': 202, 'data_list': None}
            response['data_list'] = self.database.get_contacts(message['user'])
            try:
                send_message(client, response)
            except OSError:
                self.remove_client(client)

        # Если это добавление контакта
        elif 'action' in message and message['action'] == 'add' and 'account_name' in message and 'user' in message \
                and self.names[message['user']] == client:
            self.database.add_contact(message['user'], message['account_name'])
            try:
                send_message(client, {'response': 200})
            except OSError:
                self.remove_client(client)

        # Если это удаление контакта
        elif 'action' in message and message['action'] == 'remove' and 'account_name' in message and 'user' in message \
                and self.names[message['user']] == client:
            self.database.remove_contact(message['user'], message['account_name'])
            try:
                send_message(client, {'response': 200})
            except OSError:
                self.remove_client(client)

        # Если это запрос известных пользователей
        elif 'action' in message and message['action'] == 'get_users' and 'account_name' in message \
                and self.names[message['account_name']] == client:
            response = {'response': 202, 'data_list': None}
            response['data_list'] = [user[0] for user in self.database.users_list()]
            try:
                send_message(client, response)
            except OSError:
                self.remove_client(client)

        # Если это запрос публичного ключа пользователя
        elif 'action' in message and message['action'] == 'pubkey_need' and 'account_name' in message:
            response = {'response': 511, 'bin': None}
            response['bin'] = self.database.get_pubkey(message['account_name'])
            # может быть, что ключа ещё нет (пользователь никогда не логинился,
            # тогда шлём 400)
            if response['bin']:
                try:
                    send_message(client, response)
                except OSError:
                    self.remove_client(client)
            else:
                response = {'response': 400, 'error': None}
                response['error'] = 'Нет публичного ключа для данного пользователя'
                try:
                    send_message(client, response)
                except OSError:
                    self.remove_client(client)

        # Иначе отдаём Bad request
        else:
            response = {'response': 400, 'error': None}
            response['error'] = 'Запрос некорректен.'
            try:
                send_message(client, response)
            except OSError:
                self.remove_client(client)

    def autorize_user(self, message, sock):
        """ Метод реализующий авторизацию пользователей. """
        # Если имя пользователя уже занято то возвращаем 400
        LOGGER.debug(f'Start auth process for {message["user"]}')
        if message['user']['account_name'] in self.names.keys():
            response = {'response': 400, 'error': None}
            response['error'] = 'Имя пользователя уже занято.'
            try:
                LOGGER.debug(f'Username busy, sending {response}')
                send_message(sock, response)
            except OSError:
                LOGGER.debug('OS Error')
                pass
            self.clients.remove(sock)
            sock.close()
        # Проверяем что пользователь зарегистрирован на сервере.
        elif not self.database.check_user(message['user']['account_name']):
            response = {'response': 400, 'error': None}
            response['error'] = 'Пользователь не зарегистрирован.'
            try:
                LOGGER.debug(f'Unknown username, sending {response}')
                send_message(sock, response)
            except OSError:
                pass
            self.clients.remove(sock)
            sock.close()
        else:
            LOGGER.debug('Correct username, starting passwd check.')
            # Иначе отвечаем 511 и проводим процедуру авторизации
            # Словарь - заготовка
            message_auth = {'response': 511, 'bin': None}
            # Набор байтов в hex представлении
            random_str = binascii.hexlify(os.urandom(64))
            # В словарь байты нельзя, декодируем (json.dumps -> TypeError)
            message_auth['bin'] = random_str.decode('ascii')
            # Создаём хэш пароля и связки с рандомной строкой, сохраняем
            # серверную версию ключа
            hash = hmac.new(self.database.get_hash(message['user']['account_name']), random_str, 'MD5')
            digest = hash.digest()
            LOGGER.debug(f'Auth message = {message_auth}')
            try:
                # Обмен с клиентом
                send_message(sock, message_auth)
                ans = get_message(sock)
            except OSError as err:
                LOGGER.debug('Error in auth, data:', exc_info=err)
                sock.close()
                return
            client_digest = binascii.a2b_base64(ans['bin'])
            # Если ответ клиента корректный, то сохраняем его в список
            # пользователей.
            if 'response' in ans and ans['response'] == 511 and \
                    hmac.compare_digest(digest, client_digest):
                self.names[message['user']['account_name']] = sock
                client_ip, client_port = sock.getpeername()
                try:
                    send_message(sock, {'response': 200})
                except OSError:
                    self.remove_client(message['user']['account_name'])
                # добавляем пользователя в список активных и,
                # если у него изменился открытый ключ, то сохраняем новый
                self.database.user_login(
                    message['user']['account_name'],
                    client_ip,
                    client_port,
                    message['user']['pubkey'])
            else:
                response = {'response': 400, 'error': None}
                response['error'] = 'Неверный пароль.'
                try:
                    send_message(sock, response)
                except OSError:
                    pass
                self.clients.remove(sock)
                sock.close()

    def service_update_lists(self):
        '''Метод реализующий отправки сервисного сообщения 205 клиентам.'''
        for client in self.names:
            try:
                send_message(self.names[client], {'response': 205})
            except OSError:
                self.remove_client(self.names[client])
