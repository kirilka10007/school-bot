# School System

Проект содержит два Telegram-бота для учебного центра:

- `school-bot` для учеников и заявок;
- `school_admin_bot` для администратора;
- `shared` с общей SQLite-базой и общими утилитами;
- `scripts/healthcheck.py` для быстрой проверки состояния проекта.

## Структура

- `school-bot/` основной бот
- `school_admin_bot/` админ-бот
- `shared/` общая база данных и логирование
- `scripts/` служебные скрипты
- `tests/` автотесты на критичные сценарии

## Быстрый старт

1. Создай файл `.env` на основе `.env.example`.
2. Заполни реальные токены и идентификаторы чатов.
3. Создай виртуальные окружения и установи зависимости:

```powershell
py -3 -m venv school-bot/venv
school-bot/venv/Scripts/python.exe -m pip install -U pip
school-bot/venv/Scripts/python.exe -m pip install -r requirements.txt

py -3 -m venv school_admin_bot/venv
school_admin_bot/venv/Scripts/python.exe -m pip install -U pip
school_admin_bot/venv/Scripts/python.exe -m pip install -r requirements.txt
```

## Запуск

```powershell
.\run_school_bot.bat
.\run_admin_bot.bat
.\run_healthcheck.bat
```

## Тесты

```powershell
school-bot/venv/Scripts/python.exe -m pytest
```

## Что не должно попадать в GitHub

В репозиторий не нужно загружать:

- `.env`
- `venv`
- `logs`
- `__pycache__`
- локальные файлы базы данных

## Документация по развёртыванию

Подробная инструкция по запуску, мониторингу и передаче проекта находится в `README_DEPLOY.md`.
