"""Программа-клиент"""

import sys
import json
import socket
import time
import argparse
import logging
import threading
import logs.client_log_config
from common.variables import default_port, default_ip_address
from common.utils import get_message, send_message
from errors import IncorrectDataRecivedError, ReqFieldMissingError, ServerError
from decorator import log
from metaclasses import ClientVerifier
from client_database import ClientDatabase

# Инициализация клиентского логера
LOGGER = logging.getLogger('client')

# Объект блокировки сокета и работы с базой данных
sock_lock = threading.Lock()
database_lock = threading.Lock()


# Класс формировки и отправки сообщений на сервер и взаимодействия с пользователем.
class ClientSender(threading.Thread, metaclass=ClientVerifier):
    def __init__(self, account_name, sock, database):
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    # Функция создаёт словарь с сообщением о выходе.
    def create_exit_message(self):
        return {
            'action': 'exit',
            'time': time.time(),
            'account_name': self.account_name
        }

    # Функция запрашивает кому отправить сообщение и само сообщение,
    # и отправляет полученные данные на сервер.
    def create_message(self):
        to = input('Введите получателя сообщения: ')
        message = input('Введите сообщение для отправки: ')

        # Проверим, что получатель существует
        with database_lock:
            if not self.database.check_user(to):
                LOGGER.error(f'Попытка отправить сообщение '
                             f'незарегистрированому получателю: {to}')
                return

        message_dict = {
            'action': 'message',
            'from': self.account_name,
            'to': to,
            'time': time.time(),
            'mess_text': message
        }
        LOGGER.debug(f'Сформирован словарь сообщения: {message_dict}')

        # Сохраняем сообщения для истории
        with database_lock:
            self.database.save_message(self.account_name, to, message)

        # Необходимо дождаться освобождения сокета для отправки сообщения
        with sock_lock:
            try:
                send_message(self.sock, message_dict)
                LOGGER.info(f'Отправлено сообщение для пользователя {to}')
            except OSError as err:
                if err.errno:
                    LOGGER.critical('Потеряно соединение с сервером.')
                    exit(1)
                else:
                    LOGGER.error('Не удалось передать сообщение. Таймаут соединения')

    # Функция взаимодействия с пользователем, запрашивает команды, отправляет сообщения
    def run(self):
        self.print_help()
        while True:
            command = input('Введите команду: ')
            # Если отправка сообщения - соответствующий метод
            if command == 'message':
                self.create_message()

            # Вывод помощи
            elif command == 'help':
                self.print_help()

            # Выход. Отправляем сообщение серверу о выходе.
            elif command == 'exit':
                with sock_lock:
                    try:
                        send_message(self.sock, self.create_exit_message())
                    except Exception as e:
                        print(e)
                        pass
                    print('Завершение соединения.')
                    LOGGER.info('Завершение работы по команде пользователя.')
                # Задержка неоходима, чтобы успело уйти сообщение о выходе
                time.sleep(0.5)
                break

            # Список контактов
            elif command == 'contacts':
                with database_lock:
                    contacts_list = self.database.get_contacts()
                for contact in contacts_list:
                    print(contact)

            # Редактирование контактов
            elif command == 'edit':
                self.edit_contacts()

            # история сообщений.
            elif command == 'history':
                self.print_history()

            else:
                print('Команда не распознана, попробойте снова. '
                      'help - вывести поддерживаемые команды.')

    # Функция, выводящяя справку по использованию.
    def print_help(self):
        print('Поддерживаемые команды:')
        print('message - отправить сообщение. Кому и текст будет запрошены отдельно.')
        print('history - история сообщений')
        print('contacts - список контактов')
        print('edit - редактирование списка контактов')
        print('help - вывести подсказки по командам')
        print('exit - выход из программы')

    # Функция выводящяя историю сообщений
    def print_history(self):
        ask = input('Показать входящие сообщения - in, исходящие - out, все - просто Enter: ')
        with database_lock:
            if ask == 'in':
                history_list = self.database.get_history(to_who=self.account_name)
                for message in history_list:
                    print(f'\nСообщение от пользователя: {message[0]} '
                          f'от {message[3]}:\n{message[2]}')
            elif ask == 'out':
                history_list = self.database.get_history(from_who=self.account_name)
                for message in history_list:
                    print(f'\nСообщение пользователю: {message[1]} '
                          f'от {message[3]}:\n{message[2]}')
            else:
                history_list = self.database.get_history()
                for message in history_list:
                    print(f'\nСообщение от пользователя: {message[0]},'
                          f' пользователю {message[1]} '
                          f'от {message[3]}\n{message[2]}')

    # Функция изменеия контактов
    def edit_contacts(self):
        ans = input('Для удаления введите del, для добавления add: ')
        if ans == 'del':
            edit = input('Введите имя удаляемного контакта: ')
            with database_lock:
                if self.database.check_contact(edit):
                    self.database.del_contact(edit)
                else:
                    LOGGER.error('Попытка удаления несуществующего контакта.')
        elif ans == 'add':
            # Проверка на возможность такого контакта
            edit = input('Введите имя создаваемого контакта: ')
            if self.database.check_user(edit):
                with database_lock:
                    self.database.add_contact(edit)
                with sock_lock:
                    try:
                        add_contact(self.sock, self.account_name, edit)
                    except ServerError:
                        LOGGER.error('Не удалось отправить информацию на сервер.')


# Класс-приёмник сообщений с сервера.
# Принимает сообщения, выводит в консоль, сохраняет в базу.
class ClientReader(threading.Thread, metaclass=ClientVerifier):
    def __init__(self, account_name, sock, database):
        self.account_name = account_name
        self.sock = sock
        self.database = database
        super().__init__()

    # Основной цикл приёмника сообщений, принимает сообщения, выводит в консоль.
    # Завершается при потере соединения.
    def run(self):
        while True:
            # Отдыхаем секунду и снова пробуем захватить сокет.
            # Если не сделать тут задержку,
            # то второй поток может достаточно долго ждать освобождения сокета.
            time.sleep(1)
            with sock_lock:
                try:
                    message = get_message(self.sock)

                # Принято некорректное сообщение
                except IncorrectDataRecivedError:
                    LOGGER.error(f'Не удалось декодировать полученное сообщение.')
                # Вышел таймаут соединения если errno = None, иначе обрыв соединения.
                except OSError as err:
                    if err.errno:
                        LOGGER.critical(f'Потеряно соединение с сервером.')
                        break
                # Проблемы с соединением
                except (ConnectionError,
                        ConnectionAbortedError,
                        ConnectionResetError,
                        json.JSONDecodeError):
                    LOGGER.critical(f'Потеряно соединение с сервером.')
                    break
                # Если пакет корретно получен выводим в консоль и записываем в базу.
                else:
                    if 'action' in message and message['action'] == 'message' \
                            and 'from' in message \
                            and 'to' in message \
                            and 'mess_text' in message \
                            and message['to'] == self.account_name:
                        print(f'\n Получено сообщение от пользователя '
                              f'{message["from"]}:\n{message["mess_text"]}')
                        # Захватываем работу с базой данных и сохраняем в неё сообщение
                        with database_lock:
                            try:
                                self.database.save_message(message['from'],
                                                           self.account_name,
                                                           message['mess_text'])
                            except Exception as e:
                                print(e)
                                LOGGER.error('Ошибка взаимодействия с базой данных')

                        LOGGER.info(f'Получено сообщение от пользователя '
                                    f'{message["from"]}:\n{message["mess_text"]}')
                    else:
                        LOGGER.error(f'Получено некорректное сообщение с сервера: {message}')


# Функция генерирует запрос о присутствии клиента
@log
def create_presence(account_name):
    out = {
        'action': 'presence',
        'time': time.time(),
        'user': {
            'account_name': account_name
        }
    }
    LOGGER.debug(f'Сформировано {"presence"} сообщение для пользователя {account_name}')
    return out


# Функция разбирает ответ сервера на сообщение о присутствии,
# возвращает 200 если все ОК или генерирует исключение при ошибке.
@log
def process_response_ans(message):
    LOGGER.debug(f'Разбор приветственного сообщения от сервера: {message}')
    if 'response' in message:
        if message['response'] == 200:
            return '200 : OK'
        elif message['response'] == 400:
            raise ServerError(f'400 : {message["error"]}')
    raise ReqFieldMissingError('response')


# Парсер аргументов коммандной строки
@log
def arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('addr', default=default_ip_address, nargs='?')
    parser.add_argument('port', default=default_port, type=int, nargs='?')
    parser.add_argument('-n', '--name', default=None, nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    server_address = namespace.addr
    server_port = namespace.port
    client_name = namespace.name

    # проверим подходящий номер порта
    if not 1023 < server_port < 65536:
        LOGGER.critical(
            f'Попытка запуска клиента с неподходящим номером порта: {server_port}. '
            f'Допустимы адреса с 1024 до 65535. Клиент завершается.')
        exit(1)

    return server_address, server_port, client_name


# Функция запрос контакт листа
def contacts_list_request(sock, name):
    LOGGER.debug(f'Запрос контакт листа для пользователя {name}')
    req = {
        'action': 'get_contacts',
        'time': time.time(),
        'user': name
    }
    LOGGER.debug(f'Сформирован запрос {req}')
    send_message(sock, req)
    ans = get_message(sock)
    LOGGER.debug(f'Получен ответ {ans}')
    if 'response' in ans and ans['response'] == 202:
        return ans['data_list']
    else:
        raise ServerError


# Функция добавления пользователя в контакт лист
def add_contact(sock, username, contact):
    LOGGER.debug(f'Создание контакта {contact}')
    req = {
        'action': 'add',
        'time': time.time(),
        'user': username,
        'account_name': contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if 'response' in ans and ans['response'] == 200:
        pass
    else:
        raise ServerError('Ошибка создания контакта')
    print('Удачное создание контакта.')


# Функция запроса списка известных пользователей
def user_list_request(sock, username):
    LOGGER.debug(f'Запрос списка известных пользователей {username}')
    req = {
        'action': 'get_users',
        'time': time.time(),
        'account_name': username
    }
    send_message(sock, req)
    ans = get_message(sock)
    if 'response' in ans and ans['response'] == 202:
        return ans['data_list']
    else:
        raise ServerError


# Функция удаления пользователя из списка контактов
def remove_contact(sock, username, contact):
    LOGGER.debug(f'Создание контакта {contact}')
    req = {
        'action': 'remove',
        'time': time.time(),
        'user': username,
        'account_name': contact
    }
    send_message(sock, req)
    ans = get_message(sock)
    if 'response' in ans and ans['response'] == 200:
        pass
    else:
        raise ServerError('Ошибка удаления клиента')
    print('Удачное удаление')


# Функция инициализатор базы данных.
# Запускается при запуске, загружает данные в базу с сервера.
def database_load(sock, database, username):
    # Загружаем список известных пользователей
    try:
        users_list = user_list_request(sock, username)
    except ServerError:
        LOGGER.error('Ошибка запроса списка известных пользователей.')
    else:
        database.add_users(users_list)

    # Загружаем список контактов
    try:
        contacts_list = contacts_list_request(sock, username)
    except ServerError:
        LOGGER.error('Ошибка запроса списка контактов.')
    else:
        for contact in contacts_list:
            database.add_contact(contact)


def main():
    # Сообщаем о запуске
    print('Консольный месседжер. Клиентский модуль.')

    # Загружаем параметры коммандной строки
    server_address, server_port, client_name = arg_parser()

    # Если имя пользователя не было задано, необходимо запросить пользователя.
    if not client_name:
        client_name = input('Введите имя пользователя: ')
    else:
        print(f'Клиентский модуль запущен с именем: {client_name}')

    LOGGER.info(
        f'Запущен клиент с параметрами: '
        f'адрес сервера: {server_address} , порт: {server_port}, '
        f'имя пользователя: {client_name}')

    # Инициализация сокета и сообщение серверу о нашем появлении
    try:
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Таймаут 1 секунда, необходим для освобождения сокета.
        transport.settimeout(1)

        transport.connect((server_address, server_port))
        send_message(transport, create_presence(client_name))
        answer = process_response_ans(get_message(transport))
        LOGGER.info(f'Установлено соединение с сервером. Ответ сервера: {answer}')
        print(f'Установлено соединение с сервером.')
    except json.JSONDecodeError:
        LOGGER.error('Не удалось декодировать полученную Json строку.')
        exit(1)
    except ServerError as error:
        LOGGER.error(f'При установке соединения сервер вернул ошибку: {error.text}')
        exit(1)
    except ReqFieldMissingError as missing_error:
        LOGGER.error(f'В ответе сервера отсутствует необходимое поле '
                     f'{missing_error.missing_field}')
        exit(1)
    except (ConnectionRefusedError, ConnectionError):
        LOGGER.critical(
            f'Не удалось подключиться к серверу {server_address}:{server_port}, '
            f'конечный компьютер отверг запрос на подключение.')
        exit(1)
    else:

        # Инициализация БД
        database = ClientDatabase(client_name)
        database_load(transport, database, client_name)

        # Если соединение с сервером установлено корректно,
        # запускаем поток взаимодействия с пользователем
        module_sender = ClientSender(client_name, transport, database)
        module_sender.daemon = True
        module_sender.start()
        LOGGER.debug('Запущены процессы')

        # затем запускаем поток - приёмник сообщений.
        module_receiver = ClientReader(client_name, transport, database)
        module_receiver.daemon = True
        module_receiver.start()

        # Watchdog основной цикл, если один из потоков завершён,
        # то значит или потеряно соединение, или пользователь ввёл exit.
        # Поскольку все события обработываются в потоках,
        # то достаточно просто завершить цикл.
        while True:
            time.sleep(1)
            if module_receiver.is_alive() and module_sender.is_alive():
                continue
            break


if __name__ == '__main__':
    main()

