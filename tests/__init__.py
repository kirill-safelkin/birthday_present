"""Автоматические проверки. Запуск из папки проекта:

    ./.venv/bin/python -m unittest discover -s tests -v

Каждый модуль тестов сам включает драйвер SDL dummy: при запуске через
discover -s tests этот файл не импортируется.
"""
