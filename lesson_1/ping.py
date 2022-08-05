import locale
import platform
from subprocess import Popen, PIPE
from ipaddress import ip_address

ENCODING = locale.getpreferredencoding()


def host_ping(ip_add):
    """
    Ping IP address and return tuple:
    On success:
        * True
        * command output (stdout)
    On failure:
        * False
        * error output (stderr)
    """
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    list_1 = []
    for ip_1 in ip_add:
        args = ['ping', param, '5', str(ip_1)]
        reply = Popen(args, stdout=PIPE, stderr=PIPE)

        code = reply.wait()
        if code == 0:
            list_1.append((True, reply.args[3], reply.stdout.read().decode(ENCODING)))
        else:
            list_1.append((False, reply.args[3], reply.stderr.read().decode(ENCODING)))
    return list_1


if __name__ == '__main__':
    IPV4 = ip_address('18.8.8.8')
    print([IPV4])

    print(host_ping('18.8.8.8'))
    print(host_ping('yandex.ru'))
