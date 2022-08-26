from setuptools import setup, find_packages

setup(name="s_messenger",
      version="1.0",
      description="Mess Server",
      author="daas",
      author_email="derevanko@yandex.ru",
      packages=find_packages(),
      install_requires=['PyQt5', 'sqlalchemy', 'pycryptodome', 'pycryptodomex'],
      )
