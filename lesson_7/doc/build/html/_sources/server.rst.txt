Server module documentation
=================================================

Серверное приложение для обмена сообщениями. Поддерживает
отправку сообщений пользователям которые находятся в сети, сообщения шифруются
с помощью алгоритма RSA с длинной ключа 2048 bit.

Поддерживает аргументы коммандной строки:

``python server.py -p {порт} -a {имя сервера}``

1. {имя сервера} - адрес сервера сообщений.
2. {порт} - порт по которому принимаются подключения

Все опции командной строки являются необязательными.

Примеры использования:

* ``python server.py``

*Запуск приложения с параметрами по умолчанию.*

* ``python server.py -p 7774 -a 127.0.0.1``

*Запуск сервера с портом и адресом*

server.py
~~~~~~~~~


add_user.py
~~~~~~~~~~~~~~

.. autoclass:: server.add_user.RegisterUser
	:members:

config_window.py
~~~~~~~~~~~~~~

.. autoclass:: server.config_window.ConfigWindow
	:members:

core.py
~~~~~~~~~~~~~~

.. autoclass:: server.core.MessageProcessor
	:members:

database.py
~~~~~~~~~~~~~~

.. autoclass:: server.database.ServerStorage
	:members:

main_window.py
~~~~~~~~~~~~~~

.. autoclass:: server.main_window.MainWindow
	:members:

remove_user.py
~~~~~~~~~~~~~~

.. autoclass:: server.remove_user.DelUserDialog
	:members:

stat_window.py
~~~~~~~~~~~~~~

.. autoclass:: server.stat_window.StatWindow
	:members:
