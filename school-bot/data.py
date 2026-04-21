from pathlib import Path

TEACHERS_DATA = {
    "Математика": [
        {
            "name": "Даша",
            "description": "Преподает математику для 7-11 классов: помогает закрыть пробелы в базе, "
            "разобраться со сложными задачами и уверенно подготовиться к ОГЭ и ЕГЭ.",
            "telegram_id": None,
            "photo": "assets/teachers/dasha_card.jpg",
        },
        {
            "name": "Соня",
            "description": "Специализируется на олимпиадной математике: развивает нестандартное мышление, "
            "учит видеть идею задачи и уверенно решать задания повышенной сложности.",
            "telegram_id": None,
            "photo": "assets/teachers/sonya_olymp_card.jpg",
        },
        {
            "name": "Таня",
            "description": "Помогает выстроить крепкую математическую базу, спокойно разбирает сложные темы "
            "и системно готовит к контрольным, ОГЭ и ЕГЭ.",
            "telegram_id": None,
            "photo": "assets/teachers/tanya_card.jpg",
        },
    ],
    "Русский язык": [
        {
            "name": "Ангелина",
            "description": "Преподает русский язык для 5-11 классов и готовит к ОГЭ. Объясняет сложные темы простым "
            "языком, помогает стабильно повышать результат и уверенно писать изложение и сочинение.",
            "telegram_id": None,
            "photo": "assets/teachers/angelina_card.jpg",
        },
        {
            "name": "Тая",
            "description": "Ведет русский язык для средней и старшей школы: помогает подтянуть грамотность, "
            "уверенно писать сочинения и готовиться к экзаменам без перегруза.",
            "telegram_id": None,
            "photo": "assets/teachers/taya_card.jpg",
        },
        {
            "name": "София",
            "description": "Готовит к ОГЭ и ЕГЭ по русскому языку, учит четко формулировать мысли и грамотно "
            "выполнять тестовую и письменную часть.",
            "telegram_id": None,
            "photo": "assets/teachers/sofia_card.jpg",
        },
        {
            "name": "Элина",
            "description": "Помогает повысить успеваемость по русскому языку, системно отрабатывает правила "
            "и закрепляет их на практике.",
            "telegram_id": None,
            "photo": "assets/teachers/elina_card.jpg",
        },
    ],
    "Информатика": [
        {
            "name": "Галина Ефимовна",
            "description": "Преподает информатику для 9-11 классов, готовит к ОГЭ и ЕГЭ, помогает с Python. "
            "Учитель высшей категории с большим стажем и сильными результатами учеников.",
            "telegram_id": None,
            "photo": "assets/teachers/galina_card.jpg",
        },
    ],
    "Физика": [
        {
            "name": "Даша",
            "description": "Ведет физику с акцентом на понимание, а не заучивание: объясняет темы простым "
            "языком, тренирует решение задач и готовит к контрольным, ОГЭ и ЕГЭ.",
            "telegram_id": None,
            "photo": "assets/teachers/dasha_card.jpg",
        },
    ],
    "Обществознание": [
        {
            "name": "Екатерина",
            "description": "Готовит к ОГЭ и ЕГЭ по обществознанию, выстраивает понятную систему тем и "
            "тренирует формат экзамена. Среди достижений ученицы: призер регионального этапа ВСОШ, "
            "победитель «Высшей пробы», призер олимпиад РАНХиГС, Business Skills и «Звезда».",
            "telegram_id": None,
            "photo": "assets/teachers/ekaterina_card.jpg",
        },
    ],
    "Литература": [
        {
            "name": "София",
            "description": "Объясняет литературу доступно и помогает лучше понимать произведения и писать сочинения.",
            "telegram_id": None,
            "photo": "assets/teachers/sofia_card.jpg",
        },
        {
            "name": "Элина",
            "description": "Преподает литературу через смысл и структуру текста: помогает глубже понимать "
            "произведения, аргументированно рассуждать и уверенно писать сочинения.",
            "telegram_id": None,
            "photo": "assets/teachers/elina_card.jpg",
        },
    ],
}

# Ensure all teacher cards have optional fields for future integrations.
for _subject_teachers in TEACHERS_DATA.values():
    for _teacher in _subject_teachers:
        _teacher.setdefault("telegram_id", None)
        _teacher.setdefault("photo", None)


def load_reviews_from_folder(folder: str = "assets/reviews") -> list[dict]:
    reviews_path = Path(folder)

    if not reviews_path.exists():
        return []

    allowed_extensions = {".png", ".jpg", ".jpeg", ".webp"}

    files = [
        file
        for file in reviews_path.iterdir()
        if file.is_file() and file.suffix.lower() in allowed_extensions
    ]

    def extract_number(file_path: Path):
        name = file_path.stem.lower()
        digits = "".join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 999999

    files.sort(key=lambda x: (extract_number(x), x.name.lower()))

    return [{"image": str(file).replace("\\", "/")} for file in files]


REVIEWS_DATA = load_reviews_from_folder()
