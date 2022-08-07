"""Программа-сервер"""

import sys
import socket
import argparse
import logging
import select
import logs.server_log_config
from common.variables import default_port, max_connections
from common.utils import get_message, send_message
from decorator import log
from descrptrs import Port
from metaclasses import ServerVerifier

# Инициализация логирования сервера.
LOGGER = logging.getLogger('server')


# Парсер аргументов командной строки.
@log
def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=default_port, type=int, nargs='?')
    parser.add_argument('-a', default='', nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_address = namespace.a
    listen_port = namespace.p
    return listen_address, listen_port


# Основной класс сервера
class Server(metaclass=ServerVerifier):
    port = Port()

    def __init__(self, listen_address, listen_port):
        # Параметры подключения
        self.addr = listen_address
        self.port = listen_port

        # Список подключённых клиентов.
        self.clients = []

        # Список сообщений на отправку.
        self.messages = []

        # Словарь содержащий сопоставленные имена и соответствующие им сокеты.
        self.names = dict()

    def init_socket(self):
        LOGGER.info(
            f'Запущен сервер, порт для подключений: {self.port}, '
            f'адрес с которого принимаются подключения: {self.addr}. '
            f'Если адрес не указан, принимаются соединения с любых адресов.')
        # Готовим сокет
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        # Начинаем слушать сокет.
        self.sock = transport
        self.sock.listen(max_connections)

    def main_loop(self):
        # Инициализация Сокета
        self.init_socket()

        # Основной цикл программы сервера
        while True:
            # Ждём подключения, если таймаут вышел, ловим исключение.
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                LOGGER.info(f'Установлено соедение с ПК {client_address}')
                self.clients.append(client)

            recv_data_lst = []
            send_data_lst = []
            err_lst = []
            # Проверяем на наличие ждущих клиентов
            try:
                if self.clients:
                    recv_data_lst, send_data_lst, err_lst = select.select(self.clients, self.clients, [], 0)
            except OSError:
                pass

            # принимаем сообщения и если ошибка, исключаем клиента.
            if recv_data_lst:
                for client_with_message in recv_data_lst:
                    try:
                        self.process_client_message(get_message(client_with_message), client_with_message)
                    except:
                        LOGGER.info(f'Клиент {client_with_message.getpeername()} отключился от сервера.')
                        self.clients.remove(client_with_message)

            # Если есть сообщения, обрабатываем каждое.
            for message in self.messages:
                try:
                    self.process_message(message, send_data_lst)
                except Exception as e:
                    LOGGER.info(f'Связь с клиентом с именем '
                                f'{message["to"]} была потеряна, '
                                f' ошибка {e}')
                    self.clients.remove(self.names[message['to']])
                    del self.names[message['to']]
            self.messages.clear()

    # Функция адресной отправки сообщения определённому клиенту.
    # Принимает словарь сообщение, список зарегистрированных
    # пользователей и слушающие сокеты. Ничего не возвращает.
    def process_message(self, message, listen_socks):
        if message['to'] in self.names and \
                self.names[message['to']] in listen_socks:
            send_message(self.names[message['to']], message)
            LOGGER.info(f'Отправлено сообщение пользователю {message["to"]} '
                        f'от пользователя {message["from"]}.')
        elif message["to"] in self.names \
                and self.names[message["to"]] not in listen_socks:
            raise ConnectionError
        else:
            LOGGER.error(
                f'Пользователь {message["to"]} не зарегистрирован '
                f'на сервере, отправка сообщения невозможна.')

    # Обработчик сообщений от клиентов, принимает словарь - сообщение от клиента,
    # проверяет корректность, отправляет словарь-ответ в случае необходимости.
    def process_client_message(self, message, client):
        LOGGER.debug(f'Разбор сообщения от клиента : {message}')
        # Если это сообщение о присутствии, принимаем и отвечаем
        if 'action' in message and message['action'] == 'presence' \
                and 'time' in message and 'user' in message:
            # Если такой пользователь ещё не зарегистрирован, регистрируем,
            # иначе отправляем ответ и завершаем соединение.
            if message['user']['account_name'] not in self.names.keys():
                self.names[message['user']['account_name']] = client
                send_message(client, {'response': 200})
            else:
                response = {'response': 400, 'error': None}
                response['error'] = 'Имя пользователя уже занято.'
                send_message(client, response)
                self.clients.remove(client)
                client.close()
            return
        # Если это сообщение, то добавляем его в очередь сообщений. Ответ не требуется.
        elif 'action' in message \
                and message['action'] == 'message' \
                and 'to' in message \
                and 'time' in message \
                and 'from' in message \
                and 'mess_text' in message:
            self.messages.append(message)
            return
        # Если клиент выходит
        elif 'action' in message \
                and message['action'] == 'exit' \
                and 'account_name' in message:
            self.clients.remove(self.names['account_name'])
            self.names['account_name'].close()
            del self.names['account_name']
            return
        # Иначе отдаём Bad request
        else:
            response = {'response': 400, 'error': None}
            response['error'] = 'Запрос некорректен.'
            send_message(client, response)
            return


def main():
    # Загрузка параметров командной строки, если нет параметров,
    # то задаём значения по умолчанию.
    listen_address, listen_port = arg_parser()

    # Создание экземпляра класса - сервера.
    server = Server(listen_address, listen_port)
    server.main_loop()


if __name__ == '__main__':
    main()
