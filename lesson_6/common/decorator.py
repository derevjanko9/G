import sys
import logging
import logs.client_log_config
import logs.server_log_config
import traceback


def log(func_to_log):
    """Функция-декоратор"""

    def log_saver(*args, **kwargs):
        logger_name = 'server' if 'server.py' in sys.argv[0] else 'client'
        logger = logging.getLogger(logger_name)

        ret = func_to_log(*args, **kwargs)
        logger.debug(f'Была вызвана функция {func_to_log.__name__} c параметрами {args}, {kwargs}.')
        logger.debug(f'Функция {func_to_log.__name__} вызвана из функции '
                     f'{traceback.format_stack()[0].strip().split()[-1]}.')
        return ret

    return log_saver
