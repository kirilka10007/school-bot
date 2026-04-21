# Инструкция по запуску, мониторингу и передаче проекта

## 1. Что уже добавлено в проект

Ниже перечислено, что уже внедрено и зачем это нужно.

1. Автотесты (`pytest`) на критичные сценарии:
- проверка базового сценария анкеты и создания направления;
- проверка оплаты с защитой от повторного начисления;
- проверка записи действий администратора в журнал.

2. Мониторинг:
- логирование обоих ботов в файлы `logs/school_bot.log` и `logs/school_admin_bot.log`;
- `healthcheck`-скрипт, который проверяет доступность БД и наличие ключевых таблиц.

3. Удобные скрипты запуска:
- `run_school_bot.bat` для основного бота;
- `run_admin_bot.bat` для админ-бота;
- `run_healthcheck.bat` для быстрой проверки состояния.

4. Подготовка к сдаче:
- `requirements.txt` для установки зависимостей;
- `.env.example` с параметрами окружения;
- эта инструкция для запуска и передачи проекта.

## 2. Как это работает внутри

1. Основной бот (`school-bot`) и админ-бот (`school_admin_bot`) запускаются отдельно, но работают с общей БД в папке `shared`.
2. При старте каждого бота подключается логирование:
- сообщения пишутся в консоль;
- параллельно пишутся в файл в папке `logs/`;
- включена ротация логов, чтобы лог-файлы не росли бесконечно.
3. `scripts/healthcheck.py` проверяет:
- существует ли файл БД;
- есть ли в БД обязательные таблицы: `students`, `users`, `teachers`, `student_lessons`, `attendance`, `balance_history`, `payment_requests`, `admin_actions`.
4. Автотесты запускаются на временной тестовой БД, а не на боевой. Это безопасно: рабочие данные не затрагиваются.

## 3. Подготовка перед первым запуском

1. Установи Python 3.11 или выше.
2. Открой проект:

```text
C:\Users\Den\Desktop\School-system
```

3. Создай `.env` на основе `.env.example`.
4. Заполни реальные токены и ID чатов.

Важно:

- не отправляй `.env` никому;
- токены, которые когда-либо были показаны в переписке, лучше перевыпустить в BotFather.

## 4. Установка зависимостей

Выполни в PowerShell из корня проекта:

```powershell
py -3 -m venv school-bot/venv
school-bot/venv/Scripts/python.exe -m pip install -U pip
school-bot/venv/Scripts/python.exe -m pip install -r requirements.txt

py -3 -m venv school_admin_bot/venv
school_admin_bot/venv/Scripts/python.exe -m pip install -U pip
school_admin_bot/venv/Scripts/python.exe -m pip install -r requirements.txt
```

Если команда `py` недоступна, можно использовать `python` вместо неё.

## 5. Запуск ботов

1. Основной бот:

```powershell
.\run_school_bot.bat
```

2. Админ-бот:

```powershell
.\run_admin_bot.bat
```

Если всё запущено корректно:

- боты отвечают в Telegram;
- в папке `logs` появляются лог-файлы.

## 6. Проверка мониторинга

Запуск проверки:

```powershell
.\run_healthcheck.bat
```

Ожидаемый результат:

- `HEALTHCHECK_OK` - всё нормально;
- `HEALTHCHECK_FAIL` - есть проблема, например нет БД или таблиц.

## 7. Запуск автотестов

Из корня проекта:

```powershell
school-bot/venv/Scripts/python.exe -m pytest
```

Что проверяется:

1. Анкета и создание направления.
2. Платёж и невозможность повторного начисления при повторной обработке.
3. Запись админ-действия в `admin_actions`.

## 8. Автозапуск на Windows

Рекомендуется создать 3 задачи в Планировщике заданий.

1. `SchoolBotMain`
- Trigger: `At startup`
- Action: `Start a program`
- Program/script:

```text
C:\Users\Den\Desktop\School-system\run_school_bot.bat
```

2. `SchoolBotAdmin`
- Trigger: `At startup`
- Action: `Start a program`
- Program/script:

```text
C:\Users\Den\Desktop\School-system\run_admin_bot.bat
```

3. `SchoolBotHealthcheck`
- Trigger: каждые 5 минут
- Action: `Start a program`
- Program/script:

```text
C:\Users\Den\Desktop\School-system\run_healthcheck.bat
```

## 9. Что передавать заказчику

Есть 2 правильных варианта.

1. Передача через Git:
- передаёшь ссылку на репозиторий;
- в репозиторий не должны попадать `.env`, `venv`, `logs`, `__pycache__`, боевая БД.

2. Передача zip-архивом:
- включить:
  - `school-bot/`
  - `school_admin_bot/`
  - `shared/`
  - `scripts/`
  - `tests/`
  - `requirements.txt`
  - `.env.example`
  - `run_school_bot.bat`
  - `run_admin_bot.bat`
  - `run_healthcheck.bat`
  - `README.md`
  - `README_DEPLOY.md`
- не включать:
  - `.env`
  - `venv`
  - `logs`
  - `__pycache__`
  - локальные базы данных;
  - файлы с персональными данными и реальными токенами.

## 10. Финальный чек-лист перед сдачей

1. Перевыпустить токены ботов в BotFather и обновить `.env`.
2. Запустить оба бота и пройти ручной сценарий в Telegram.
3. Убедиться, что создаются логи в папке `logs`.
4. Выполнить `run_healthcheck.bat`.
5. Выполнить `pytest`.
6. Подготовить безопасный пакет передачи без секретов и мусора окружения.
