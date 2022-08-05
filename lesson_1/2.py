from ipaddress import ip_address
from tabulate import tabulate
from lesson_1.ping import host_ping


def host_range_ping():
    ip_for_testing = input('Введите начальный адрес:')  # '192.168.0.1'
    ipv_4 = ip_address(ip_for_testing)
    quantity = int(input('Введите колличество адресов:'))
    list_2 = [ipv_4]
    address = str(ipv_4).split('.')[:3]

    for i in range(1, quantity + 1):
        if address == str(ipv_4 + i).split('.')[:3]:
            list_2.append(ipv_4 + i)
        else:
            print('Можем менять только последний октет')
            break
    return host_ping(list_2)


def host_range_ping_tab():
    tuple_1 = host_range_ping()
    list_reachable = []
    list_unreachable = []
    for i in tuple_1:
        if i[0]:
            list_reachable.append(i[1])
        else:
            list_unreachable.append(i[1])
    print(tabulate(list_reachable, 'Reachable', 'plain'))
    print(tabulate(list_unreachable, 'Unreachable', 'plain'))


host_range_ping_tab()
