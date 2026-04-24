# Подготовка Проекта: Полный Сброс + PostgreSQL

## 1) Что сделано в коде

- Добавлена полноценная поддержка PostgreSQL через `DATABASE_URL` в `shared/database.py`.
- Добавлен полный сброс данных: `scripts/reset_all_data.py` и `run_reset_all_data.bat`.
- Служебные скрипты переведены на универсальное подключение (SQLite/PostgreSQL):
  - `scripts/healthcheck.py`
  - `scripts/check_db_state.py`
  - `scripts/db_admin.py`
  - `scripts/soft_cleanup.py`
  - `scripts/cleanup_known_users_without_username.py`
- В `requirements.txt` добавлен `psycopg2-binary`.
- В `.env.example` добавлен пример `DATABASE_URL`.

## 2) Как перейти на PostgreSQL

1. Создайте БД PostgreSQL (пример: `school_system`).
2. В `.env` укажите:

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/school_system
```

3. Установите зависимости:

```powershell
school-bot/venv/Scripts/python.exe -m pip install -r requirements.txt
school_admin_bot/venv/Scripts/python.exe -m pip install -r requirements.txt
```

4. Выполните полную очистку (если нужно начать с нуля):

```powershell
.\run_reset_all_data.bat
```

5. Проверьте состояние:

```powershell
.\run_healthcheck.bat
.\run_check_db_state.bat
```

6. Запустите ботов:

```powershell
.\run_school_bot.bat
.\run_admin_bot.bat
```

## 3) Зачем нужны .bat файлы

- `run_school_bot.bat` — запуск основного бота (ученики/заявки/оплаты).
- `run_admin_bot.bat` — запуск админ-бота.
- `run_healthcheck.bat` — проверка, что БД доступна и нужные таблицы существуют.
- `run_check_db_state.bat` — вывод текущего состояния таблиц и ключевых записей.
- `run_db_admin.bat` — точечные операции с БД (например, операции с преподавателями через `scripts/db_admin.py`).
- `run_reset_db.bat` — сброс данных с пересевом преподавателей из каталога `school-bot/data.py`.
- `run_reset_keep_teachers.bat` — мягкий сброс: чистит операционные данные, сохраняет текущих преподавателей.
- `run_reset_all_data.bat` — полный сброс всех данных во всех рабочих таблицах.
- `run_soft_cleanup.bat` — регулярная мягкая очистка и нормализация служебных данных.
- `run_cleanup_known_users.bat` — удаление из `known_telegram_users` записей без `@username`.
- `run_setup_weekly_cleanup.bat` — установка задания планировщика на еженедельный soft-cleanup.
- `run_remove_weekly_cleanup.bat` — удаление задания планировщика soft-cleanup.

## 4) Рекомендуемый порядок для боевого старта

1. Заполнить `.env` и `DATABASE_URL`.
2. `run_reset_all_data.bat` (если стартуете полностью с чистого листа).
3. Добавить супер-админов в `.env` (`SCHOOL_ADMIN_SUPERADMINS`).
4. `run_healthcheck.bat`.
5. Запустить оба бота.
6. Через админ-бота завести админов, преподавателей и учеников.
