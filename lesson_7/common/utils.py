import json
import os
import sys
from .variables import max_package_length, encoding
from .decorator import log


@log
def get_message(client):
    """
    Утилита приема и декодирования сообщения.
    Принимает байты, возвращает словарь, если принято что-то
    другое возвращает ValueError (ошибку значения).
    """
    encoded_response = client.recv(max_package_length)
    if isinstance(encoded_response, bytes):
        json_response = encoded_response.decode(encoding)
        if isinstance(json_response, str):
            response = json.loads(json_response)
            if isinstance(response, dict):
                return response
            raise ValueError
        raise ValueError
    raise ValueError


@log
def send_message(sock, message):
    """
    Утилита кодирования и отправки сообщения.
    Принимает для отправки словарь, получает из него строку,
    далее превращает строку в байты и оправляет.
    """
    if not isinstance(message, dict):
        raise TypeError
    is_message = json.dumps(message)
    encoded_message = is_message.encode(encoding)
    sock.send(encoded_message)
