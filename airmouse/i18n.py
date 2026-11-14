"""Two languages: Russian and English («Язык / Language» in the window).

Texts are written in Russian in the code and shown through _(): in English it
looks the text up in EN below. Texts with numbers in them are format strings,
_("{} кадр/с").format(fps), so each language puts the numbers where it needs them.
tests/test_i18n.py checks that every Russian text in airmouse/ has its English line.
"""

import ctypes
import os
import sys

LANGUAGES = (("ru", "Русский"), ("en", "English"))
LANGUAGE_LABEL = "Язык · Language"     # in both, so it can be found whichever language is on
# Languages whose speakers mostly read Russian: Russian, Belarusian, Kazakh, Kyrgyz, Tajik, Uzbek
# (Windows language numbers, and the same as Linux locale names).
RUSSIAN_READERS = {0x19, 0x23, 0x3F, 0x40, 0x28, 0x43}
RUSSIAN_LOCALES = {"ru", "be", "kk", "ky", "tg", "uz"}

_language = "ru"


def set_language(code):
    global _language
    _language = code if code in dict(LANGUAGES) else "ru"


def language():
    return _language


def _(text):
    """text (Russian) in the language of the interface."""
    if _language == "en":
        return EN.get(text, text)
    return text


def system_language():
    """The first language for a new user: Russian if the system speaks it (or a neighbour of it), else English."""
    if sys.platform != "win32":       # Linux: the locale, e.g. LANG=ru_RU.UTF-8
        locale = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
        return "ru" if locale[:2].lower() in RUSSIAN_LOCALES else "en"
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return "en"
    return "ru" if primary in RUSSIAN_READERS else "en"


EN = {
    # main window (ui.py, ui_classic.py, app_base.py)
    "Мышь, которой управляете вы": "A mouse you control without touching",
    "Старт": "Start",
    "Стоп": "Stop",
    "Рука": "Hand",
    "Глаза": "Eyes",
    "Голова": "Head",
    "Управлять мышью": "Control the mouse",
    "Управлять мышью   Ctrl+Alt+M": "Control the mouse   Ctrl+Alt+M",
    "Ctrl+Alt+M — пауза": "Ctrl+Alt+M: pause",
    "НАСТРОЙКИ": "SETTINGS",
    "Настройки": "Settings",
    "Камера": "Camera",
    "Стабилизация": "Stabilization",
    "Скорость курсора": "Cursor speed",
    "Чувствительность клика": "Click sensitivity",
    "Моргание для клика": "Blink to click",
    "Скорость прокрутки": "Scroll speed",
    "{:.2f} с": "{:.2f} s",
    "Обратная прокрутка": "Reverse scrolling",
    "Поверх всех окон": "Always on top",
    "Виджеты на экране (палец вверх, Ctrl+Alt+W)": "On-screen widgets (thumbs up, Ctrl+Alt+W)",
    "Кольцо у курсора": "Ring around the cursor",
    "Дизайн": "Design",
    "Стекло": "Glass",
    "Природа": "Nature",
    "Классика": "Classic",
    "Природа (запотевшее стекло)": "Nature (fogged glass)",
    "Классический": "Classic",
    "Виджеты": "Widgets",
    "Виджеты…": "Widgets…",
    "Блокнот": "Notebook",
    "Подробнее": "More",
    "Подробнее…": "More…",
    "СЕАНС": "SESSION",
    "Сеанс": "Session",
    "ЖЕСТЫ": "GESTURES",
    "Жесты": "Gestures",
    "ЛИЦО": "FACE",
    "Лицо": "Face",
    "Левый глаз": "Left eye",
    "Правый глаз": "Right eye",
    "Рот": "Mouth",
    "Брови": "Brows",
    "Включаю камеру…": "Starting the camera…",
    "Это займёт пару секунд": "This takes a couple of seconds",
    "Камера выключена": "Camera off",
    "Нажмите «Старт»": "Press “Start”",
    "Камера выключена\nНажмите «Старт»": "Camera off\nPress “Start”",
    "Центр зоны по руке": "Center the zone on my hand",
    "Калибровка взгляда": "Gaze calibration",
    "Центр по положению головы": "Center on my head position",
    "Держите руку удобно… {}": "Hold your hand comfortably… {}",
    "Смотрите в центр экрана… {}": "Look at the center of the screen… {}",
    "Сначала нажмите «Старт».": "Press “Start” first.",
    "Рука не видна. Поднимите руку перед камерой и попробуйте ещё раз.":
        "No hand in view. Raise your hand in front of the camera and try again.",
    "Точность взгляда ≈ {:.0f} px": "Gaze accuracy ≈ {:.0f} px",
    "Калибровки ещё нет": "Not calibrated yet",
    "{:.0f} кадр/с": "{:.0f} fps",
    "процессор {:.0f}%": "CPU {:.0f}%",
    "клики {}  ·  правые {}  ·  прокрутка {}": "clicks {}  ·  right {}  ·  scroll {}",
    "AirMouse уже запущен.": "AirMouse is already running.",

    # status
    "Остановлено": "Stopped",
    "Калибровка…": "Calibrating…",
    "Запуск…": "Starting…",
    "Нужна калибровка взгляда": "Gaze calibration needed",
    "Пауза": "Paused",
    "Рука не видна": "No hand in view",
    "Лицо не видно": "No face in view",
    "Курсор": "Cursor",
    "Клик": "Click",
    "Кнопка нажата": "Button down",
    "Глаза закрыты": "Eyes closed",
    "Перетаскивание": "Dragging",
    "Правый клик": "Right click",
    "Прокрутка": "Scrolling",
    "Точный курсор": "Precise cursor",
    "Масштаб": "Zoom",

    # the gestures card
    "Ладонь": "Palm",
    "двигает курсор": "moves the cursor",
    "Большой + указательный": "Thumb + index",
    "левый клик, дважды — двойной": "left click, twice: double click",
    "Сжать, держать и вести": "Pinch, hold and move",
    "перетаскивание": "drag",
    "Большой + два пальца": "Thumb + two fingers",
    "правый клик": "right click",
    "Два пальца вверх / вниз": "Two fingers up / down",
    "прокрутка": "scroll",
    "Большой палец вверх": "Thumbs up",
    "показать / скрыть виджеты": "show / hide the widgets",
    "Большой палец вниз, 1 с": "Thumbs down, 1 s",
    "пауза / продолжить": "pause / resume",
    "Вторая рука: щипок": "Second hand: pinch",
    "клик; держать — перетащить": "click; hold to drag",
    "Вторая рука: «L»": "Second hand: “L”",
    "точный медленный курсор": "slow, precise cursor",
    "Вторая рука: взмах ← / →": "Second hand: swipe ← / →",
    "вперёд / назад": "forward / back",
    "слайды → / ←": "slides → / ←",
    "рабочие столы": "desktops",
    "трек вперёд / назад": "next / previous track",
    "Обе руки «V»: развести": "Both hands “V”: spread",
    "масштаб крупнее / мельче": "zoom in / out",
    "экранная лупа + / −": "screen magnifier + / −",
    "Развести / свести ладони": "Palms apart / together",
    "все окна / свернуть все": "all windows / show desktop",
    "Взгляд": "Gaze",
    "переносит курсор, куда смотрите": "puts the cursor where you look",
    "Лёгкий поворот головы": "Slight head turn",
    "точно доводит курсор": "fine-tunes the cursor",
    "Поворот головы": "Head turn",
    "Долго моргнуть": "Long blink",
    "Подмигнуть": "Wink",
    "Открыть рот": "Open the mouth",
    "зажать кнопку (перетаскивание)": "hold the button (drag)",
    "Брови вверх + наклон": "Brows up + tilt",

    # gaze calibration (calibration.py)
    "Калибровка взгляда\nСмотрите на точки, пока они не исчезнут. Esc — отмена.":
        "Gaze calibration\nLook at the dots until they disappear. Esc cancels.",
    "Смотрите на точку и медленно поворачивайте голову:\nвлево — вправо, потом вверх — вниз":
        "Look at the dot and slowly turn your head:\nleft and right, then up and down",
    "Смотрите на точку. Голову держите ровно.": "Look at the dot. Keep your head still.",
    "Не получилось: глаза плохо видны.\nПроверьте освещение и попробуйте ещё раз.":
        "That did not work: the eyes are hard to see.\nCheck the lighting and try again.",
    "Готово!\nСредняя ошибка ≈ {:.0f} px": "Done!\nAverage error ≈ {:.0f} px",

    # the camera (tracker.py)
    "Не удалось открыть камеру №{}.\nПроверьте, что она подключена и не занята другой программой.":
        "Could not open camera #{}.\nCheck that it is connected and not used by another program.",
    "Камера перестала отдавать изображение.": "The camera stopped sending pictures.",
    "Нет доступа к /dev/uinput, поэтому AirMouse не может двигать мышь.\n"
    "Добавьте себя в группу input и правило udev (см. README), затем войдите в систему заново.":
        "No access to /dev/uinput, so AirMouse cannot move the mouse.\n"
        "Add yourself to the input group and the udev rule (see the README), then log in again.",

    # on-screen widgets (onscreen.py)
    "AirMouse: камера и жест": "AirMouse: camera and gesture",
    "Часы": "Clock",
    "Громкость": "Volume",
    "Музыка и видео": "Music and video",
    "Нагрузка компьютера": "Computer load",
    "Панель кнопок": "Button panel",
    "Блокнот: рисовать рукой": "Notebook: draw by hand",
    "Клик задержкой: какой клик": "Dwell click: which click",
    "Ctrl+Alt+M — пауза   ·   палец вверх — скрыть": "Ctrl+Alt+M: pause   ·   thumbs up: hide",
    "Камера включается…": "Camera starting…",
    "{weekday}, {day} {month}": "{weekday}, {month} {day}",
    "понедельник": "Monday",
    "вторник": "Tuesday",
    "среда": "Wednesday",
    "четверг": "Thursday",
    "пятница": "Friday",
    "суббота": "Saturday",
    "воскресенье": "Sunday",
    "января": "January",
    "февраля": "February",
    "марта": "March",
    "апреля": "April",
    "мая": "May",
    "июня": "June",
    "июля": "July",
    "августа": "August",
    "сентября": "September",
    "октября": "October",
    "ноября": "November",
    "декабря": "December",
    "Нет звукового устройства": "No audio device",
    "Процессор": "CPU",
    "Память": "Memory",
    "Батарея": "Battery",
    "Заряжается": "Charging",
    "Быстрые действия": "Quick actions",
    "Копировать": "Copy",
    "Вставить": "Paste",
    "Отменить": "Undo",
    "Рабочий стол": "Desktop",
    "Все окна": "All windows",
    "Скриншот": "Screenshot",
    "Голосовой ввод": "Voice typing",
    "Клавиатура": "Keyboard",
    "Кнопка": "Button",
    "Добавьте кнопки в настройках": "Add buttons in the settings",
    "Скопировано: вставьте Ctrl+V": "Copied: paste with Ctrl+V",
    "Не удалось скопировать": "Could not copy",
    "КЛИК ЗАДЕРЖКОЙ": "DWELL CLICK",
    "Двойной": "Double",
    "Правый": "Right",
    "Тащить": "Drag",
    "Отпустить": "Release",
    "кнопка зажата": "button held",

    # what the buttons do (system.py)
    "Неизвестная клавиша: «{}»": "Unknown key: “{}”",
    "Пустая клавиша в сочетании": "An empty key in the combination",
    "Не указано, что открыть": "Nothing to open is given",
    "Не удалось открыть «{}»": "Could not open “{}”",
    "Неизвестное действие": "Unknown action",

    # the widget editor (widget_editor.py)
    "Виджеты на экране — AirMouse": "On-screen widgets — AirMouse",
    "Показывать виджеты, пока AirMouse управляет мышью": "Show the widgets while AirMouse controls the mouse",
    "Показать или скрыть: подержите большой палец вверх или нажмите Ctrl+Alt+W.\n"
    "Блокнот для рисования открывают Ctrl+Alt+N и карандаш на мини-панели AirMouse.\n"
    "Виджеты не забирают фокус: их кнопки нажимают клавиши в той программе, где вы работаете.\n"
    "Чтобы передвинуть виджет, потяните его за фон (щипок, подержать и вести).":
        "To show or hide them, hold a thumbs up or press Ctrl+Alt+W.\n"
        "Ctrl+Alt+N or the pen on the AirMouse mini panel opens the notebook for drawing.\n"
        "Widgets never take the focus: their buttons press keys in the program you are working in.\n"
        "To move a widget, drag it by its background (pinch, hold and move).",
    "Кольцо у курсора: показывает щипок, клик и прокрутку": "Ring around the cursor: shows the pinch, clicks and scrolling",
    "Виджет": "Widget",
    "На экране": "Shown",
    "да": "yes",
    "Показать / скрыть": "Show / hide",
    "Расставить заново": "Arrange again",
    "Новая панель кнопок": "New button panel",
    "Удалить панель": "Delete panel",
    "Название": "Title",
    "без названия": "untitled",
    "Мои кнопки": "My buttons",
    "Удалить «{}»?": "Delete “{}”?",
    "Что делает": "What it does",
    "Добавить": "Add",
    "Изменить": "Edit",
    "Удалить": "Delete",
    "Выберите слева панель кнопок.": "Pick a button panel on the left.",
    "Выберите слева панель кнопок или создайте новую.": "Pick a button panel on the left or make a new one.",
    "открыть {}": "open {}",
    "Можно добавить ещё {}.": "{} more can be added.",
    "Кнопок уже максимум.": "This panel is full.",
    "Готово": "Done",
    "Надпись на кнопке": "Button label",
    "Нажать клавиши": "Press keys",
    "Открыть программу, файл или сайт": "Open a program, file or website",
    "Клавиши": "Keys",
    "Что открыть": "What to open",
    "Например: ctrl+c, win+d, alt+tab, ctrl+shift+esc, f5, playpause, volumeup":
        "For example: ctrl+c, win+d, alt+tab, ctrl+shift+esc, f5, playpause, volumeup",
    "Например: notepad, calc, osk, https://youtube.com или путь к файлу":
        "For example: notepad, calc, osk, https://youtube.com or a file path",
    "Напишите надпись для кнопки.": "Write a label for the button.",
    "Сохранить": "Save",
    "Отмена": "Cancel",

    # «Подробнее» (advanced.py, tuning.py)
    "Подробные настройки — AirMouse": "Advanced settings — AirMouse",
    "Всё применяется сразу. Настройки камеры перезапускают её сами.\n"
    "«По умолчанию» возвращает значения, с которыми AirMouse работает из коробки.":
        "Everything applies at once. Camera settings restart the camera by themselves.\n"
        "“Defaults” brings back the values AirMouse works with out of the box.",
    "По умолчанию": "Defaults",
    "мс": "ms",
    "Клики": "Clicks",
    "Окно и виджеты": "Window and widgets",
    "Две руки": "Two hands",
    "Доступность": "Accessibility",
    "Частота кадров камеры": "Camera frame rate",
    "30 кадр/с": "30 fps",
    "60 кадр/с — точнее и быстрее": "60 fps: more precise and faster",
    "60 кадр/с: курсор отзывчивее и точнее, процессора нужно больше. Не всякая камера умеет 60.":
        "60 fps: a quicker, more precise cursor, but more CPU. Not every camera can do 60.",
    "Разрешение камеры": "Camera resolution",
    "Больше разрешение — точнее точки руки вдали от камеры, но больше нагрузка.":
        "A higher resolution tracks a hand far from the camera more precisely, at a higher load.",
    "Зеркальное изображение": "Mirror the picture",
    "нет": "no",
    "Как в зеркале: руку вправо — курсор вправо.": "Like a mirror: hand to the right, cursor to the right.",
    "Уверенность распознавания руки": "Hand detection confidence",
    "Ниже — рука находится легче, но чаще ошибочно; выше — надёжнее, но может теряться.":
        "Lower finds the hand more easily but makes more mistakes; higher is more reliable but may lose it.",
    "Мёртвая зона курсора": "Cursor dead zone",
    "Дрожь меньше этой зоны не двигает курсор. 0 — курсор ловит каждое движение.":
        "Shaking smaller than this zone does not move the cursor. 0: the cursor follows every movement.",
    "Отзывчивость к быстрым движениям": "Response to fast movements",
    "Больше — быстрые движения почти без задержки, меньше — плавнее.":
        "Higher: fast movements with almost no lag; lower: smoother.",
    "Отбрасывать одиночные сбои камеры": "Drop single-frame camera glitches",
    "Медиана из трёх кадров: убирает рывки, добавляет задержку в один кадр.":
        "A median of three frames: removes jumps, adds one frame of delay.",
    "Плавный перелёт курсора": "Smooth cursor glide",
    "Когда рука появляется, курсор не прыгает, а перелетает за это время.":
        "When the hand appears, the cursor glides over in this time instead of jumping.",
    "Подтверждение щипка": "Pinch confirmation",
    "Сколько пальцы должны касаться (и потом разжаться), чтобы это засчиталось. Больше — меньше случайных кликов.":
        "How long the fingers must touch (and then part) to count. Longer: fewer accidental clicks.",
    "Разжать пальцы для отпускания": "Open the fingers to release",
    "Во сколько раз дальше порога касания нужно развести пальцы, чтобы отпустить кнопку.":
        "How many times farther than the touch threshold the fingers must part to release the button.",
    "Время на правый клик": "Time for a right click",
    "Сколько ждать, не присоединится ли средний палец (тогда клик правый).":
        "How long to wait for the middle finger to join (then it is a right click).",
    "Курсор стоит после клика": "Cursor stays still after a click",
    "Чтобы второй щипок двойного клика попал в то же место.":
        "So that the second pinch of a double click lands on the same spot.",
    "Сдвиг для начала перетаскивания": "Movement that starts a drag",
    "Насколько сдвинуть руку с зажатыми пальцами, чтобы началось перетаскивание.":
        "How far to move the pinching hand to start a drag.",
    "Шаг прокрутки": "Scroll step",
    "Мельче — плавнее прокрутка, крупнее — быстрее (120 = одно деление колеса).":
        "Smaller: smoother scrolling; larger: faster (120 = one wheel notch).",
    "Удерживать «палец вверх»": "Hold the thumbs up",
    "Сколько держать большой палец вверх, чтобы показать или скрыть виджеты.":
        "How long to hold a thumbs up to show or hide the widgets.",
    "Ждать пропавшую руку": "Wait for a lost hand",
    "Если рука на миг пропала из кадра, нажатая кнопка не отпускается это время.":
        "If the hand leaves the picture for a moment, a held button stays down this long.",
    "Глаз считается закрытым при": "An eye counts as closed at",
    "Порог по шкале «Левый / правый глаз» под превью.": "The threshold on the “Left / Right eye” meters under the preview.",
    "Подмигнуть для правого клика": "Wink for a right click",
    "Рот открыт при": "The mouth counts as open at",
    "Порог по шкале «Рот»: открыть рот — зажать кнопку.":
        "The threshold on the “Mouth” meter: open the mouth to hold the button.",
    "Брови подняты при": "The brows count as raised at",
    "Порог по шкале «Брови»: поднять брови — прокрутка.": "The threshold on the “Brows” meter: raise the brows to scroll.",
    "Частота окна AirMouse": "AirMouse window frame rate",
    "60 кадр/с — плавнее, нагрузка выше": "60 fps: smoother, higher load",
    "Размер виджетов на экране": "On-screen widget size",
    "Виджеты на экране, даже когда камера выключена": "Widgets on screen even with the camera off",
    "нет, только во время работы": "no, only while running",
    "да, всегда": "yes, always",
    "Вторая рука — кнопки мыши и окна": "Second hand: mouse buttons and windows",
    "нет, только одна рука": "no, one hand only",
    "Одна рука ведёт курсор, другая щипком нажимает кнопку: целиться и нажимать можно разными руками.":
        "One hand moves the cursor, the other presses the button with a pinch: aim with one hand, click with the other.",
    "Курсор ведёт рука": "Hand that moves the cursor",
    "правая": "right",
    "левая": "left",
    "Когда в кадре одна рука, курсор ведёт она, какая бы ни была.":
        "With one hand in view, that hand moves the cursor, whichever it is.",
    "Жесты двумя руками: окна и пауза": "Two-hand gestures: windows and pause",
    "Развести ладони — все окна, свести — свернуть все, оба больших пальца вверх — пауза.":
        "Palms apart: all windows; together: show the desktop; both thumbs up: pause.",
    "Обе руки «V»: развести — крупнее, свести — мельче": "Both hands “V”: apart zooms in, together zooms out",
    "масштаб в программе (Ctrl + колесо)": "zoom in the program (Ctrl + wheel)",
    "экранная лупа Windows (Win + «+» / «−»)": "Windows Magnifier (Win + “+” / “−”)",
    "выключено": "off",
    "Покажите обеими руками два пальца и разведите руки. Браузер, документы, карты, графики. "
    "Лупа Windows закрывается Win+Esc.":
        "Show two fingers with both hands and move the hands apart. Browsers, documents, maps, charts. "
        "Win+Esc closes the Windows Magnifier.",
    "Точный курсор: скорость": "Precise cursor: speed",
    "Вторая рука буквой «L» (указательный вверх, большой в сторону): курсор идёт медленнее — "
    "для мелких кнопок, ячеек таблиц, чертежей. 1 — выключено.":
        "Second hand in an “L” (index up, thumb out): the cursor moves slower, "
        "for small buttons, table cells, drawings. 1: off.",
    "Взмах второй рукой влево / вправо": "Second hand swipe left / right",
    "ничего": "nothing",
    "вперёд / назад (браузер, проводник)": "forward / back (browser, Explorer)",
    "слайды и страницы (→ / ←)": "slides and pages (→ / ←)",
    "рабочие столы Windows": "Windows desktops",
    "следующий / предыдущий трек": "next / previous track",
    "Быстрый взмах открытой ладонью: влево — вперёд, следующий; вправо — назад, предыдущий. "
    "Удобно показывать презентацию, не подходя к ноутбуку.":
        "A quick swipe of the open palm: left for forward or next, right for back or previous. "
        "Handy for presenting slides from across the room.",
    "Пауза одной рукой: большой палец вниз": "One-hand pause: thumbs down",
    "да, подержать секунду": "yes, hold for a second",
    "Палец вниз ведущей рукой на секунду — пауза, ещё раз — управление снова. "
    "Для тех, у кого работает одна рука.":
        "Thumbs down with the cursor hand for a second: pause; again: control is back. "
        "For people who use one hand.",
    "Клик задержкой: навести и подождать": "Dwell click: point and wait",
    "Курсор постоял на месте — и щёлкнул. Не нужно сводить пальцы; работает и в режимах лица. "
    "Двойной, правый клик и перетаскивание — на панели «Клик задержкой».":
        "Hold the cursor still and it clicks. No pinching needed; works in the face modes too. "
        "Double click, right click and drag are on the “Dwell click” panel.",
    "Сколько ждать до клика": "Wait before the click",
    "Кольцо у курсора заполняется, пока идёт время.": "The ring around the cursor fills up as the time passes.",
    "Курсор стоит, если не уходит дальше": "The cursor counts as still within",
    "Больше — легче, если рука или голова дрожат.": "Larger is easier if the hand or head shakes.",
}
