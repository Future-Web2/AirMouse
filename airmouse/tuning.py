"""Fine-tuning: the numbers behind the camera, the cursor, clicks and the window («Подробнее»).

Every parameter has a default that matches how AirMouse behaves without tuning;
settings.advanced keeps only what the user changed. The tracking thread reads
values each frame, so changes apply at once (those marked restart: on the next
start of the camera, which the settings window does by itself).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Param:
    key: str
    group: str
    label: str
    default: float
    lo: float = 0.0
    hi: float = 1.0
    step: float = 1.0
    unit: str = ""
    hint: str = ""
    choices: tuple = ()      # ((value, label), ...) to pick from instead of a slider
    restart: bool = False    # the camera must start again for this to apply


GROUPS = ("Камера", "Курсор", "Клики", "Жесты", "Лицо", "Окно и виджеты")

PARAMS = (
    Param("camera_fps", "Камера", "Частота кадров камеры", 30,
          choices=((30, "30 кадр/с"), (60, "60 кадр/с — точнее и быстрее")), restart=True,
          hint="60 кадр/с: курсор отзывчивее и точнее, процессора нужно больше. Не всякая камера умеет 60."),
    Param("camera_width", "Камера", "Разрешение камеры", 640,
          choices=((640, "640 × 480"), (1280, "1280 × 720")), restart=True,
          hint="Больше разрешение — точнее точки руки вдали от камеры, но больше нагрузка."),
    Param("mirror", "Камера", "Зеркальное изображение", 1, choices=((1, "да"), (0, "нет")),
          hint="Как в зеркале: руку вправо — курсор вправо."),
    Param("hand_confidence", "Камера", "Уверенность распознавания руки", 0.6, 0.3, 0.9, 0.05, restart=True,
          hint="Ниже — рука находится легче, но чаще ошибочно; выше — надёжнее, но может теряться."),
    Param("deadzone", "Курсор", "Мёртвая зона курсора", 1.0, 0.0, 3.0, 0.1, "×",
          hint="Дрожь меньше этой зоны не двигает курсор. 0 — курсор ловит каждое движение."),
    Param("fast_response", "Курсор", "Отзывчивость к быстрым движениям", 1.0, 0.25, 3.0, 0.05, "×",
          hint="Больше — быстрые движения почти без задержки, меньше — плавнее."),
    Param("outlier_filter", "Курсор", "Отбрасывать одиночные сбои камеры", 1, choices=((1, "да"), (0, "нет")),
          hint="Медиана из трёх кадров: убирает рывки, добавляет задержку в один кадр."),
    Param("glide_ms", "Курсор", "Плавный перелёт курсора", 150, 0, 500, 10, "мс",
          hint="Когда рука появляется, курсор не прыгает, а перелетает за это время."),
    Param("pinch_confirm_ms", "Клики", "Подтверждение щипка", 30, 0, 250, 5, "мс",
          hint="Сколько пальцы должны касаться (и потом разжаться), чтобы это засчиталось. Больше — меньше случайных кликов."),
    Param("release_factor", "Клики", "Разжать пальцы для отпускания", 1.5, 1.1, 2.5, 0.05, "×",
          hint="Во сколько раз дальше порога касания нужно развести пальцы, чтобы отпустить кнопку."),
    Param("right_click_ms", "Клики", "Время на правый клик", 120, 40, 400, 10, "мс",
          hint="Сколько ждать, не присоединится ли средний палец (тогда клик правый)."),
    Param("post_click_ms", "Клики", "Курсор стоит после клика", 500, 0, 1500, 50, "мс",
          hint="Чтобы второй щипок двойного клика попал в то же место."),
    Param("drag_start_px", "Клики", "Сдвиг для начала перетаскивания", 30, 5, 120, 5, "px",
          hint="Насколько сдвинуть руку с зажатыми пальцами, чтобы началось перетаскивание."),
    Param("wheel_step", "Жесты", "Шаг прокрутки", 30, 10, 120, 10,
          hint="Мельче — плавнее прокрутка, крупнее — быстрее (120 = одно деление колеса)."),
    Param("thumb_ms", "Жесты", "Удерживать «палец вверх»", 500, 200, 1500, 50, "мс",
          hint="Сколько держать большой палец вверх, чтобы показать или скрыть виджеты."),
    Param("hand_lost_ms", "Жесты", "Ждать пропавшую руку", 300, 100, 1500, 50, "мс",
          hint="Если рука на миг пропала из кадра, нажатая кнопка не отпускается это время."),
    Param("eye_closed", "Лицо", "Глаз считается закрытым при", 0.55, 0.3, 0.9, 0.05,
          hint="Порог по шкале «Левый / правый глаз» под превью."),
    Param("wink_ms", "Лицо", "Подмигнуть для правого клика", 300, 150, 800, 25, "мс"),
    Param("mouth_open", "Лицо", "Рот открыт при", 0.45, 0.2, 0.8, 0.05,
          hint="Порог по шкале «Рот»: открыть рот — зажать кнопку."),
    Param("brows_up", "Лицо", "Брови подняты при", 0.5, 0.2, 0.9, 0.05,
          hint="Порог по шкале «Брови»: поднять брови — прокрутка."),
    Param("window_fps", "Окно и виджеты", "Частота окна AirMouse", 30,
          choices=((30, "30 кадр/с"), (60, "60 кадр/с — плавнее, нагрузка выше"))),
    Param("widget_scale", "Окно и виджеты", "Размер виджетов на экране", 1.0, 0.75, 1.5, 0.05, "×"),
    Param("widgets_always", "Окно и виджеты", "Виджеты на экране, даже когда камера выключена", 0,
          choices=((0, "нет, только во время работы"), (1, "да, всегда"))),
)
BY_KEY = {p.key: p for p in PARAMS}


def get(settings, key):
    """The value of a parameter: the user's, if valid, otherwise the default."""
    param = BY_KEY[key]
    value = getattr(settings, "advanced", {}).get(key, param.default)
    return clean(param, value)


def seconds(settings, key):
    """A parameter given in milliseconds, in seconds."""
    return get(settings, key) / 1000.0


def clean(param, value):
    """value made valid for param: one of its choices, or a number within its range."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return param.default
    if param.choices:
        values = [v for v, _label in param.choices]
        return value if value in values else param.default
    return min(max(value, param.lo), param.hi)


def set_value(settings, key, value):
    """Store a parameter (or forget it when it equals the default)."""
    param = BY_KEY[key]
    value = clean(param, value)
    if value == param.default:
        settings.advanced.pop(key, None)
    else:
        settings.advanced[key] = value
    return value


def changed(settings):
    """Keys the user has changed from their defaults."""
    return [p.key for p in PARAMS if get(settings, p.key) != p.default]
