"""Шуточный фейковый «деанон» для команды /ip. Пулы ~×2 от первой версии."""

from __future__ import annotations

import random


_FIRST_M = (
    "Артём",
    "Богдан",
    "Валера",
    "Гоша",
    "Дима",
    "Егор",
    "Жека",
    "Коля",
    "Лёха",
    "Макс",
    "Никита",
    "Олег",
    "Паша",
    "Саша",
    "Тарас",
    "Фёдор",
    "Ярик",
    "Кибер-Вася",
    "Пикми-Витя",
    "Игорь",
    "Степан",
    "Руслан",
    "Вадим",
    "Глеб",
    "Тимофей",
    "Лёня Тапок",
    "Дед Гриша",
    "Вован",
    "Жека Ржавый",
    "Санёк",
    "Дима Бедный",
    "Костыль",
    "Захар",
    "Мирон",
    "Альберт",
    "Роман",
)
_FIRST_F = (
    "Алина",
    "Валя",
    "Даша",
    "Карина",
    "Лера",
    "Маша",
    "Настя",
    "Оля",
    "Света",
    "Таня",
    "Уля",
    "Фрося",
    "Хлоя",
    "Ангеліна",
    "Ксеня",
    "Рита",
    "Квінтішка",
    "Аніме-діва Міла",
    "Юля",
    "Лиза",
    "Катя",
    "Ника",
    "Вика",
    "Полина",
    "Жанна",
    "Инга",
    "Эля",
    "Оксана",
    "Ира",
    "Лиля",
    "Зоя",
    "Ханна",
    "Дуня",
    "Бусинка",
    "Нюша",
    "Лола",
)
_LAST = (
    "Толстой",
    "Котов",
    "Зойкин",
    "Бездельников",
    "Пельменев",
    "Бабаев",
    "Непейвода",
    "Криптокид",
    "Мемозавр",
    "Лаговский",
    "Шредингер",
    "Макароныч",
    "Вайберович",
    "Тиктокидзе",
    "Темщик",
    "Душнилав",
    "Пукич",
    "Салоедов",
    "Пупкин",
    "Лопухин",
    "Грустный",
    "Радостный",
    "Овернайт",
    "Дримкетчер",
    "Лагодром",
    "Рилсомэн",
    "Шитпостер",
    "Флексович",
    "Крашитель",
    "Ойвей",
    "Ошибка502",
    "Тильтаник",
    "Рофлан",
    "Пивозавр",
    "Фантомас",
    "Гусь",
)
_EPIC_FULL = (
    "Лев Толстой",
    "Вінні-Пух Батьович",
    "Гаррі Поттер",
    "Баба Яга (переоформлена)",
    "Кенні без шапки",
    "Капітан Очевидність",
    "Дед Інсайд",
    "Альтушка №{n}",
    "Кібер-Гопнік 3000",
    "Містер Жмот з 9-го під'їзду",
    "Ілон Маск (репліка)",
    "Шиза Тудей",
    "Дурка №{n}",
    "NPC з підвалу",
    "Головний герой фінансової піраміди",
    "Тінь від роутера",
    "Біткойн-Мойша",
    "Тітка з базару №{n}",
    "Заяц європейський",
    "Дух розетки",
)

_STREET_RU = (
    "Остров Эпштейна, ул. Скорострельная, д. 69А",
    "г. Нью-Васюки, пер. Тихий, кв. 404",
    "пос. Нижние Пуканы, ул. Мемная, 1488",
    "станция Лосиноостровская, ящик у ларька №3",
    "Берлин, район Неопределённость, д. б/н",
    "Каир, пирамида запасного выхода",
    "Лондон, Бейкер-стрит, подвал с роутером",
    "Нью-Йорк, Таймс-сквер, люк люка",
    "Детройт, заброшенный серверный шкаф",
    "Токио, комната с неоном и тоской",
    "Варшава, подъезд с запахом пирогов",
    "Одесса, двор с котом и мудростью",
    "Харьков, салют из окна напротив",
    "Киев, трамвайная остановка «Надежда»",
    "Москва, кольцевая линия в сердце",
    "СПб, канал с Wi‑Fi от соседа",
    "ОАЭ, квартира с видом на Excel",
    "Исландия, бункер от уведомлений",
    "Норвегия, фьорд Wi‑Fi",
    "Чернобыль-2, корпус «Маминых чатов»",
    "Амстердам, канал грехов и VPN",
    "Пекин, хутун с лапшой и ping",
    "Сиэтл, кофе и дождь TCP",
    "Рим, Колизей (Wi‑Fi пароль: SPQR)",
    "Афины, подъезд философов",
    "Мумбаи, даха с голубями и 5G",
    "Сеул, неон и депривация сна",
    "Хельсинки, сауна и сервер",
    "Рейkjavik, гейзер и модем",
    "Дубай, этаж с карманом во времени",
    "Лиссабон, трамвай на горку мемов",
    "Барселона, балкон с соседским торрентом",
    "Прага, мост с замком от тильды",
    "Вена, оперный туалет с эхом",
    "Женева, банк шуток и депозит иронии",
)
_STREET_UK = (
    "Острів Епштейна, вул. Скорострільна, буд. 69А",
    "м. Нью-Васюки, пров. Тихий, кв. 404",
    "селище Нижні Пукани, вул. Мемна, 1488",
    "станція Лосиноострівська, ящик біля ларька №3",
    "Берлін, район Невизначеність, буд. без номера",
    "Каїр, піраміда запасного виходу",
    "Лондон, Бейкер-стріт, підвал з роутером",
    "Нью-Йорк, Таймс-сквер, люк у люку",
    "Детройт, покинутий серверний шаф",
    "Токіо, кімната з неоном і журбою",
    "Варшава, під'їзд із запахом пирогів",
    "Одеса, двір з котом і мудрістю",
    "Харків, салют з вікна навпроти",
    "Київ, трамвайна зупинка «Надія»",
    "Москва, кільцева в серці",
    "СПб, канал з Wi‑Fi від сусіда",
    "ОАЕ, квартира з видом на Excel",
    "Ісландія, бункер від сповіщень",
    "Норвегія, фіорд Wi‑Fi",
    "Чорнобиль-2, корпус «Маминих чатів»",
    "Амстердам, канал гріхів і VPN",
    "Пекін, хутун з локшою і ping",
    "Сіетл, кава і дощ TCP",
    "Рим, Колізей (Wi‑Fi: SPQR)",
    "Афіни, під'їзд філософів",
    "Мумбаї, дах з голубами і 5G",
    "Сеул, неон і депривація сну",
    "Гельсінкі, сауна і сервер",
    "Рейк'явік, гейзер і модем",
    "Дубай, поверх з кишенею в часі",
    "Лісабон, трамвай на гору мемів",
    "Барселона, балкон із сусідським торрентом",
    "Прага, міст із замком від тильди",
    "Відень, оперний туалет з луною",
    "Женева, банк жартів і депозит іронії",
)

_JOB_RU = (
    "алкоголик, наркоман и бездельник (по совместительству поэт)",
    "фрилансер по жизни, специализация — «потом»",
    "стример нулевого онлайна",
    "дегустатор пельменей и драм",
    "админ чата в душе, в реальности — курьер",
    "инженер по нажатию кнопки «далее»",
    "аналитик мемов без выходных",
    "оператор позитива (Ошибка 404)",
    "крипто-гуру без кошелька",
    "продавец воздуха оптом",
    "тестировщик кровати, стаж 25 лет",
    "нейросеть на батарейках",
    "шеф-мемолог полуфабрикатов",
    "специалист по перекладыванию ответственности",
    "агент влияния на себя",
    "руководитель отдела «завтра»",
    "младший сомелье по энергетикам",
    "оператор чата с собой в голове",
    "инвестор в чувство вины",
    "фудфотограф на тапке",
    "клоун по совместительству HR",
    "инженер по перегреву роутера",
    "аналитик Big Mood Data",
    "дегустатор чужих проблем",
    "менеджер по отмазкам бригады «никак»",
)
_JOB_UK = (
    "алкоголік, наркоман і бездільник (за сумісництвом поет)",
    "фрілансер у житті, спеціалізація — «потім»",
    "стрімер нульового онлайну",
    "дегустатор пельменів і драм",
    "адмін чату в душі, у реальності — кур'єр",
    "інженер з натискання «далі»",
    "аналітик мемів без вихідних",
    "оператор позитиву (Помилка 404)",
    "кріпто-гуру без гаманця",
    "продавець повітря оптом",
    "тестувальник ліжка, стаж 25 років",
    "нейромережа на батарейках",
    "шеф-мемолог напівфабрикатів",
    "спеціаліст із перекладання відповідальності",
    "агент впливу на себе",
    "керівник відділу «завтра»",
    "молодший сомельє енергетиків",
    "оператор чату з собою в голові",
    "інвестор у почуття провини",
    "фудфотограф на капці",
    "клоун за сумісництвом HR",
    "інженер з перегріву роутера",
    "аналітик Big Mood Data",
    "дегустатор чужих проблем",
    "менеджер з відмовок бригади «нікуди»",
)

# Портреты людей: не пейзажи с picsum. Мелкие превью — в ленте меньше «на весь экран».
# randomuser.me — стабильные ~128×128, только лица. Wikimedia — часть известных портретов (thumb).
_WIKI_FACE_THUMB_URLS: tuple[str, ...] = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9c/Volodymyr_Zelensky_Official_portrait.jpg/220px-Volodymyr_Zelensky_Official_portrait.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Volodymyr_Zelensky_2022_official_portrait.jpg/220px-Volodymyr_Zelensky_2022_official_portrait.jpg",
    # у файла на Commons есть превью 250px (см. страницу файла)
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/Cristiano_Ronaldo_2018.jpg/250px-Cristiano_Ronaldo_2018.jpg",
)


def _random_stock_face_portrait_url() -> str:
    """Случайное лицо с randomuser (муж/жен, индекс 0–99), маленький файл."""
    kind = random.choice(("men", "women"))
    return f"https://randomuser.me/api/portraits/{kind}/{random.randint(0, 99)}.jpg"


def random_ip_scan_photo_url(exclude: str | None = None) -> str:
    """URL портрета человека для досье. Telegram подтягивает картинку по ссылке."""
    for _ in range(48):
        if random.random() < 0.35 and _WIKI_FACE_THUMB_URLS:
            u = random.choice(_WIKI_FACE_THUMB_URLS)
        else:
            u = _random_stock_face_portrait_url()
        if exclude is None or u != exclude:
            return u
    return _random_stock_face_portrait_url()


def _gender(lang: str) -> str:
    if lang == "uk":
        return random.choice(("чоловічий", "жіночий", "не вказано"))
    return random.choice(("мужской", "женский", "не указан"))


# Внешняя картинка с ERROR (Telegram тянет по URL). Не хранить локальные файлы.
OWNER_CLASSIFIED_PHOTO_URL = (
    "https://placehold.co/220x220/101010/ff3333/png?font=roboto&text=ERROR"
)


def normalize_username(u: str | None) -> str:
    if not u:
        return ""
    return u.strip().lstrip("@").lower()


def ip_target_is_bot_owner(target_username: str | None, owner_username: str) -> bool:
    """Цель /ip — аккаунт владельца из BOT_OWNER_USERNAME (.env)."""
    tu, ou = normalize_username(target_username), normalize_username(owner_username)
    return bool(tu) and bool(ou) and tu == ou


def owner_classified_dossier_v2(lang: str) -> dict[str, object]:
    """«Засекречено» для владельца бота: красный ERROR, поля-заглушки."""
    if lang == "uk":
        first_name = "████████"
        last_name = "████████"
        gender = "не підлягає розголошенню"
        address = "СПЕЦСЛУЖБИ · доступ заборонено"
        job = "CLASSIFIED · запис вилучено з реєстру"
    else:
        first_name = "████████"
        last_name = "████████"
        gender = "не подлежит раскрытию"
        address = "СПЕЦСЛУЖБЫ · доступ запрещён"
        job = "CLASSIFIED · запись изъята из реестра"
    return {
        "v": 2,
        "owner_classified": True,
        "first_name": first_name,
        "last_name": last_name,
        "age": -1,
        "gender": gender,
        "address": address,
        "job": job,
        "photo_url": OWNER_CLASSIFIED_PHOTO_URL,
    }


def is_v2_ip_dossier(d: object) -> bool:
    if not isinstance(d, dict):
        return False
    if int(d.get("v") or 0) == 2:
        return True
    return bool(d.get("photo_url")) and "first_name" in d and "age" in d


def _random_ip_dossier_fields(lang: str) -> dict[str, object]:
    """Случайные текстовые поля v2 без URL фото."""
    is_uk = lang == "uk"
    age = random.randint(0, 77)
    gender = _gender("uk" if is_uk else "ru")
    addr = random.choice(_STREET_UK if is_uk else _STREET_RU)
    job = random.choice(_JOB_UK if is_uk else _JOB_RU)

    if random.random() < 0.12:
        epic = random.choice(_EPIC_FULL)
        if "{n}" in epic:
            epic = epic.format(n=random.randint(1, 999))
        first_name = epic
        last_name = ""
    elif random.random() < 0.55:
        first_name, last_name = random.choice(_FIRST_M), random.choice(_LAST)
    else:
        first_name, last_name = random.choice(_FIRST_F), random.choice(_LAST)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "age": age,
        "gender": gender,
        "address": addr,
        "job": job,
    }


def build_ip_dossier_v2(lang: str) -> dict[str, object]:
    """Компактное досье для карточки: имя, фамилия, возраст (от 0 лет), пол, адрес, сфера, фото."""
    fields = _random_ip_dossier_fields(lang)
    return {
        "v": 2,
        **fields,
        "photo_url": random_ip_scan_photo_url(),
    }


def regenerate_ip_dossier_fields_keep_photo(lang: str, photo_url: str) -> dict[str, object]:
    """Новые случайные поля, портрет оставляем (для /newip)."""
    fields = _random_ip_dossier_fields(lang)
    return {
        "v": 2,
        **fields,
        "photo_url": str(photo_url).strip(),
    }


def format_ip_dossier_caption(target_display: str, dossier: dict[str, object], lang: str) -> str:
    """Короткая подпись к фото /ip (одно сообщение)."""
    is_uk = lang == "uk"
    t = target_display.strip()
    fn = str(dossier.get("first_name") or "").strip()
    ln = str(dossier.get("last_name") or "").strip()
    age = dossier.get("age")
    if isinstance(age, int) and age >= 0:
        age_s = str(age)
    else:
        age_s = "—"
    g = str(dossier.get("gender") or "—")
    addr = str(dossier.get("address") or "—")
    job = str(dossier.get("job") or "—")
    if is_uk:
        lines = [
            f"Об'єкт: {t}",
            f"Ім'я: {fn}",
            f"Прізвище: {ln}" if ln else f"Прізвище: —",
            f"Вік: {age_s}",
            f"Стать: {g}",
            f"Адреса: {addr}",
            f"Сфера діяльності: {job}",
        ]
    else:
        lines = [
            f"Объект: {t}",
            f"Имя: {fn}",
            f"Фамилия: {ln}" if ln else "Фамилия: —",
            f"Возраст: {age_s}",
            f"Пол: {g}",
            f"Адрес: {addr}",
            f"Сфера деятельности: {job}",
        ]
    if dossier.get("owner_classified"):
        if is_uk:
            lines.append("⚠️ ERROR: дані спецслужбами вилучено з реєстру.")
        else:
            lines.append("⚠️ ERROR: данные спецслужбами изъяты из реестра.")
    return "\n".join(lines)[:1024]


def format_ip_dossier_profile_block(lang: str, dossier: dict[str, object], user_display: str) -> str:
    """Компактная карточка досье в профиле (текст /mystat): поля без строки «Фото: URL»."""
    return format_ip_dossier_caption(user_display.strip(), dossier, lang)


def format_legacy_ip_dossier_caption(target_display: str, lang: str) -> str:
    """Старое досье с полем text — только уведомление, без длинной справки."""
    t = target_display.strip()
    if lang == "uk":
        return (
            f"Об'єкт: {t}\n"
            f"Застарілий формат досьє (довга довідка). Власник бота може скинути: /ip_reset"
        )[:1024]
    return (
        f"Объект: {t}\n"
        f"Устаревший формат досье (длинная справка). Владелец бота может сбросить: /ip_reset"
    )[:1024]
