"""The words of the AirMouse website, in Russian and English: key -> (ru, en).

Used by tools/build_site.py. <em>word</em> is shown in the accent colour.
The numbers come from docs/KPI.md and README.md; when they change there, change them here.
"""

T = {
    # -- head ---------------------------------------------------------------------------------
    "title": ("AirMouse — управление компьютером рукой через веб-камеру",
              "AirMouse — control your computer with a hand in the air"),
    "description": (
        "AirMouse превращает обычную веб-камеру в мышь: жесты рукой, две руки, взгляд и поворот головы. "
        "Windows 10/11 и Linux. Видео с камеры не покидает компьютер.",
        "AirMouse turns an ordinary webcam into a mouse: hand gestures, two hands, eyes and head. "
        "Windows 10/11 and Linux. Camera video never leaves your computer."),
    "skip": ("К содержимому", "Skip to content"),

    # -- header -------------------------------------------------------------------------------
    "nav_start": ("Как начать", "Get started"),
    "nav_gestures": ("Жесты", "Gestures"),
    "nav_features": ("Возможности", "Features"),
    "nav_numbers": ("Цифры", "Numbers"),
    "nav_faq": ("Вопросы", "FAQ"),
    "nav_download": ("Скачать", "Download"),
    "menu": ("Меню", "Menu"),
    "lang_label": ("Язык", "Language"),

    # -- hero ---------------------------------------------------------------------------------
    "hero_kicker": ("Мышь, которой не нужно касаться", "A mouse you control without touching"),
    "hero_h1": ("Веб-камера становится <em>мышью.</em>", "Your webcam becomes <em>the mouse.</em>"),
    "hero_sub": (
        "Двигайте курсор ладонью, нажимайте щипком в воздухе. Руки заняты — управляйте взглядом или поворотом головы.",
        "Move the cursor with your palm, click with a pinch in the air. Hands busy? Use your eyes or a turn of the head."),
    "chips": (("Без датчиков", "Без перчаток", "Без установки"), ("No sensors", "No gloves", "No installer")),
    "btn_win": ("Скачать для Windows", "Download for Windows"),
    "btn_win_note": ("zip · 83 МБ", "zip · 83 MB"),
    "btn_linux": ("Скачать для Linux", "Download for Linux"),
    "btn_linux_note": ("tar.gz · 155 МБ", "tar.gz · 155 MB"),
    "hero_note_free": ("Бесплатно", "Free"),
    "hero_note": ("Windows 10 и 11 · Linux · нужна только веб-камера",
                  "Windows 10 & 11 · Linux · all you need is a webcam"),
    "phone_hint": ("AirMouse работает на компьютере. Откройте эту страницу на ПК или отправьте себе ссылку.",
                   "AirMouse runs on a computer. Open this page on your PC, or send yourself the link."),
    "copy_link": ("Скопировать ссылку", "Copy the link"),
    "copied": ("Ссылка скопирована", "Link copied"),
    "video_play": ("Смотреть ролик", "Watch the film"),
    "video_note": ("60 секунд: что это, как начать и что умеет", "60 seconds: what it is, how to start, what it can do"),
    "video_alt": ("Рекламный ролик AirMouse", "The AirMouse commercial"),

    # -- problem ------------------------------------------------------------------------------
    "pain_title": ("Знакомо?", "Sound familiar?"),
    "pain": (
        (("Руки заняты", "Готовите, чините, рисуете — а надо нажать «дальше»."),
         ("Мышь далеко", "Презентация, телевизор, экран на стене."),
         ("Рука устаёт", "Запястье болит, пальцы дрожат, клик мимо.")),
        (("Hands are busy", "Cooking, fixing, sketching — and you need to click “next”."),
         ("Mouse out of reach", "A presentation, a TV, a screen on the wall."),
         ("Hand gets tired", "A sore wrist, shaky fingers, clicks that miss."))),
    "pain_end": ("Мышь не всегда под рукой.", "A mouse is not always at hand."),

    # -- three steps --------------------------------------------------------------------------
    "steps_title": ("Начать — три шага", "Three steps to start"),
    "steps": (
        (("Скачайте и распакуйте",
          "Архив 83 МБ. Установка и Python не нужны: распакуйте архив целиком и запустите AirMouse.exe."),
         ("Нажмите «Старт»", "Камера включится, и программа увидит руку."),
         ("Покажите ладонь", "Курсор пойдёт за рукой. Рамка в кадре — это весь экран.")),
        (("Download and unzip",
          "An 83 MB archive. No installer and no Python needed: extract the whole archive and run AirMouse.exe."),
         ("Press “Start”", "The camera turns on and AirMouse sees your hand."),
         ("Show your palm", "The cursor follows your hand. The frame in the picture is the whole screen."))),
    "checks": (("40–70 см от камеры", "Ладонь к камере", "Свет спереди"),
               ("40–70 cm from the camera", "Palm to the camera", "Light from the front")),
    "steps_linux": (
        "В Linux: распакуйте архив и запустите <code>./install.sh</code> — он добавит AirMouse в меню приложений "
        "и даст доступ к виртуальной мыши.",
        "On Linux: extract the archive and run <code>./install.sh</code> — it adds AirMouse to the applications "
        "menu and gives access to the virtual mouse."),
    "steps_linux_link": ("Инструкция для Linux", "Linux instructions"),
    "guide_link": ("Гайд с картинками", "Illustrated guide"),

    # -- gestures -----------------------------------------------------------------------------
    "g_title": ("Четыре жеста — и вы умеете всё", "Four gestures cover everything"),
    "g_sub": ("Как с мышью, только в воздухе. Кольцо у курсора показывает, какой жест видит AirMouse.",
              "Like a mouse, only in the air. The ring around the cursor shows which gesture AirMouse sees."),
    "gestures": (
        (("Ладонь", "Курсор",
          "Двигайте раскрытой ладонью. Курсор идёт за центром ладони, а не за пальцем, поэтому щипок его не сдвигает."),
         ("Щипок", "Клик", "Большой палец к указательному. Два раза подряд — двойной клик."),
         ("Два пальца", "Прокрутка", "Указательный и средний вверх, остальные согнуты. Ведите руку вверх или вниз."),
         ("Сжать и вести", "Перенос", "Щипок, держать и двигать рукой. Разжали пальцы — отпустили.")),
        (("Palm", "Cursor",
          "Move your open palm. The cursor follows the centre of the palm, not a fingertip, so a pinch does not move it."),
         ("Pinch", "Click", "Thumb to the index finger. Twice in a row is a double click."),
         ("Two fingers", "Scroll", "Index and middle fingers up, the rest folded. Move your hand up or down."),
         ("Pinch and move", "Drag", "Pinch, hold and move your hand. Open the fingers to let go."))),
    "g_more": (("Большой к двум пальцам — правый клик", "Палец вверх — виджеты", "Палец вниз на секунду — пауза"),
               ("Thumb to two fingers — right click", "Thumbs up — widgets", "Thumbs down for a second — pause")),
    "g_all": ("Все жесты — в гайде", "All gestures are in the guide"),
    "g_demo": ("Показ жеста", "Gesture demo"),

    # -- more features ------------------------------------------------------------------------
    "f_title": ("Не только курсор", "More than a cursor"),
    "f_sub": ("Виджеты, блокнот, глаза и голова, две руки — всё в одной программе.",
              "Widgets, a notebook, eyes and head, two hands — all in one program."),
    "features": (
        (("Виджеты прямо на экране",
          "Громкость, музыка, часы, нагрузка компьютера и панель со своими кнопками плавают поверх всех окон. "
          "Нажимайте их щипком, как любую программу.",
          ("Палец вверх или Ctrl+Alt+W — показать и спрятать",
           "Свои кнопки: сочетания клавиш, программы, сайты, файлы",
           "Не забирают фокус: клавиши уходят в вашу программу"),
          "Виджеты AirMouse поверх рабочего стола"),
         ("Блокнот: рисуйте в воздухе",
          "Черновик поверх всех окон, как Paint. Щипок на бумаге — и ведите руку: получится линия.",
          ("Ручка, маркер, ластик и пять цветов",
           "Страницы сохраняются сами",
           "«Копировать» — и Ctrl+V в чат или документ"),
          "Блокнот AirMouse с рисунком"),
         ("Руки заняты? Глазами и головой",
          "Курсор идёт за взглядом или за поворотом головы. Обычное моргание — не клик.",
          ("Закрыть глаза на полсекунды — клик",
           "Подмигнуть — правый клик",
           "Открыть рот — держать и тащить",
           "Брови вверх и наклон головы — прокрутка"),
          ""),
         ("Две руки — ещё точнее",
          "Одна рука ведёт курсор, другая нажимает. Целится одна, кликает другая — курсор не съезжает в момент клика.",
          ("Жест «L» — точный курсор: в 3 раза медленнее руки, для мелких кнопок и ячеек",
           "Обе руки «V» развести или свести — масштаб",
           "Ладони в стороны — все окна, вместе — рабочий стол"),
          "Вкладка «Две руки» в настройках AirMouse"),
         ("Клик задержкой: без щипка и без рук",
          "Наведите курсор и подержите на месте: через секунду он нажмёт сам. Работает с рукой, взглядом и головой — "
          "компьютером можно пользоваться совсем без рук.",
          ("Панель выбирает следующий клик: обычный, двойной, правый или «тащить»",
           "Пауза одной рукой: большой палец вниз на секунду",
           "Время задержки и допуск настраиваются"),
          "Вкладка «Доступность» в настройках AirMouse")),
        (("Widgets right on the screen",
          "Volume, music, a clock, computer load and a panel with your own buttons float above all windows. "
          "Press them with a pinch, like any program.",
          ("Thumbs up or Ctrl+Alt+W shows and hides them",
           "Your own buttons: key combinations, programs, websites, files",
           "They never take the focus: keys go to your program"),
          "AirMouse widgets above the desktop"),
         ("Notebook: draw in the air",
          "A scratch pad above all windows, like Paint. Pinch on the paper and move your hand to draw a line.",
          ("Pen, marker, eraser and five colours",
           "Pages save themselves",
           "“Copy”, then Ctrl+V into a chat or a document"),
          "The AirMouse notebook with a drawing"),
         ("Hands busy? Use your eyes and head",
          "The cursor follows your gaze or the turn of your head. An ordinary blink is not a click.",
          ("Close your eyes for half a second — click",
           "Wink — right click",
           "Open your mouth — hold and drag",
           "Brows up and a head tilt — scroll"),
          ""),
         ("Two hands, even more precise",
          "One hand moves the cursor, the other presses. Aim with one, click with the other — the cursor does not slip "
          "at the moment of the click.",
          ("The “L” gesture is a precise cursor: 3 times slower than the hand, for small buttons and cells",
           "Both hands “V”, apart or together — zoom",
           "Palms apart — all windows, together — the desktop"),
          "The “Two hands” tab of the AirMouse settings"),
         ("Dwell click: no pinch, no hands",
          "Point the cursor and hold it still: after a second it clicks by itself. It works with the hand, the eyes and "
          "the head — the computer can be used with no hands at all.",
          ("A panel picks the next click: plain, double, right or drag",
           "One-hand pause: thumbs down for a second",
           "The dwell time and the tolerance can be set"),
          "The “Accessibility” tab of the AirMouse settings"))),
    "f_face_note": (
        "Веб-камера видит взгляд примерно, в пределах 100–200 px, поэтому лёгкий поворот головы доводит курсор до цели. "
        "Режим «Голова» — самый точный способ без рук.",
        "A webcam sees the gaze only roughly, within 100–200 px, so a slight turn of the head brings the cursor onto "
        "the target. The “Head” mode is the most precise way without hands."),
    "f_access": (
        "AirMouse сделан и для тех, кому мышь даётся с трудом: после травмы, при слабых или дрожащих руках, "
        "с одной рабочей рукой.",
        "AirMouse is also made for people who find a mouse hard to use: after an injury, with weak or shaking hands, "
        "with one working hand."),
    "extras": (
        (("Три дизайна", "Стекло, Природа и Классика. Меняются сразу, камера не выключается."),
         ("33 настройки", "Восемь вкладок в «Подробнее». Всё применяется сразу, «По умолчанию» вернёт как было."),
         ("До 60 кадров в секунду", "Курсор точнее и отзывчивее, если камера это умеет."),
         ("Русский и английский", "Переключатель RU | EN прямо в окне программы.")),
        (("Three designs", "Glass, Nature and Classic. They switch at once, and the camera keeps running."),
         ("33 settings", "Eight tabs in “More”. Everything applies at once, “Defaults” puts it all back."),
         ("Up to 60 frames per second", "A more precise and responsive cursor, if the camera can do it."),
         ("English and Russian", "The RU | EN switch is right in the program window."))),
    "designs": (("Стекло", "Природа", "Классика"), ("Glass", "Nature", "Classic")),
    "designs_alt": ("Окно AirMouse, дизайн «{}»", "The AirMouse window, the “{}” design"),
    "face_alt": ("Лицо и девять точек калибровки взгляда", "A face and the nine gaze calibration dots"),

    # -- numbers ------------------------------------------------------------------------------
    "p_title": ("Рука дрожит — <em>курсор нет</em>", "Your hand shakes. <em>The cursor doesn’t</em>"),
    "p_sub": ("Точность AirMouse не обещана, а измерена. Вот числа из замеров и автотестов.",
              "AirMouse precision is measured, not promised. These numbers come from benchmarks and automated tests."),
    "stats": (
        (("20 из 20", "щипков дали ровно по одному клику"),
         ("0", "ложных действий за минуту дрожащей руки"),
         ("0 px", "от места, где стоял курсор, до клика"),
         ("0", "сдвигов курсора за минуту, пока рука неподвижна"),
         ("0,3 с", "до окна при повторном запуске"),
         ("8,5 мс", "на кадр уходит у трекинга руки"),
         ("83 МБ", "архив для скачивания"),
         ("223", "автотеста на каждое изменение кода")),
        (("20 of 20", "pinches made exactly one click each"),
         ("0", "false actions in a minute of a shaking hand"),
         ("0 px", "between where the cursor stood and the click"),
         ("0", "cursor moves in a minute while the hand is still"),
         ("0.3 s", "until the window on a repeated start"),
         ("8.5 ms", "per frame for hand tracking"),
         ("83 MB", "the archive to download"),
         ("223", "automated tests on every code change"))),
    "p_note": (
        "Замерено на одном компьютере: Intel Core i7-13650HX, 24 ГБ ОЗУ, Windows 11. Точность курсора и кликов "
        "проверяет искусственная рука с шумом трекинга, которая проходит через настоящий движок жестов. "
        "На вашем компьютере числа будут другими — замерьте сами: <code>AirMouse.exe --bench report.json</code>.",
        "Measured on one computer: Intel Core i7-13650HX, 24 GB RAM, Windows 11. Cursor and click precision is checked "
        "by an artificial hand with tracking noise that goes through the real gesture engine. On your computer the "
        "numbers will differ — measure them yourself: <code>AirMouse.exe --bench report.json</code>."),
    "p_kpi": ("Все замеры — в docs/KPI.md", "All measurements are in docs/KPI.md (in Russian)"),
    "how_title": ("Как курсор остаётся спокойным", "How the cursor stays calm"),
    "how": (
        ("Курсор идёт за центром ладони, а не за кончиком пальца.",
         "Медиана трёх кадров отбрасывает одиночные сбои трекинга.",
         "Фильтр One Euro сильно сглаживает медленные движения и почти не тормозит быстрые.",
         "«Поводок»: дрожь короче поводка до экрана не доходит.",
         "Пока пальцы сомкнуты, курсор стоит: клик попадает туда, куда целились."),
        ("The cursor follows the centre of the palm, not a fingertip.",
         "A median of three frames drops single tracking glitches.",
         "A One Euro filter smooths slow movements hard and barely holds back fast ones.",
         "A “leash”: shaking shorter than the leash never reaches the screen.",
         "While the fingers touch, the cursor stays still: the click lands where you aimed.")),

    # -- privacy ------------------------------------------------------------------------------
    "priv_title": ("Видео с камеры не покидает компьютер", "Camera video never leaves your computer"),
    "priv_sub": (
        "AirMouse находит руку и лицо прямо на вашем компьютере. Кадры никуда не отправляются и не сохраняются.",
        "AirMouse finds your hand and face right on your computer. Frames are not sent anywhere and are not saved."),
    "priv": (
        (("Работает без интернета", "Камера, жесты и курсор — всё локально."),
         ("Без аккаунта", "Ни регистрации, ни входа, ни ключей."),
         ("Нет сетевого кода", "В программе нечему выходить в сеть. Исходники лежат на GitHub — можно проверить."),
         ("Данные у вас", "Настройки и страницы блокнота хранятся в папке на вашем компьютере.")),
        (("Works offline", "The camera, the gestures and the cursor are all local."),
         ("No account", "No sign-up, no sign-in, no keys."),
         ("No network code", "Nothing in the program goes online. The source is on GitHub — you can check."),
         ("Your data stays with you", "Settings and notebook pages are kept in a folder on your computer."))),

    # -- platforms / download -----------------------------------------------------------------
    "dl_title": ("Скачайте AirMouse", "Download AirMouse"),
    "dl_sub": ("Нужна только веб-камера — встроенная в ноутбук тоже подходит.",
               "All you need is a webcam — the one built into a laptop works too."),
    "dl_win_name": ("Windows 10 и 11", "Windows 10 & 11"),
    "dl_win_text": ("64-разрядная. Распакуйте архив целиком и запустите <code>AirMouse\\AirMouse.exe</code>.",
                    "64-bit. Extract the whole archive and run <code>AirMouse\\AirMouse.exe</code>."),
    "dl_linux_name": ("Linux", "Linux"),
    "dl_linux_text": (
        "x86-64: Ubuntu 22.04, Debian 12, Fedora 36 и новее. X11 и Wayland. После распаковки — <code>./install.sh</code>.",
        "x86-64: Ubuntu 22.04, Debian 12, Fedora 36 or newer. X11 and Wayland. After extracting, run "
        "<code>./install.sh</code>."),
    "dl_linux_new": (
        "Версия для Linux новая: её проверяют автотесты на Ubuntu, а на живых рабочих столах она только начинает путь. "
        "Что-то не работает — напишите, пожалуйста.",
        "The Linux version is new: automated tests check it on Ubuntu, and on real desktops it is only starting out. "
        "If something does not work, please tell us."),
    "dl_version": ("Версия {}", "Version {}"),
    "dl_all": ("Все версии", "All versions"),
    "dl_source": ("Исходный код", "Source code"),
    "dl_report": ("Сообщить об ошибке", "Report a problem"),

    # -- FAQ ----------------------------------------------------------------------------------
    "faq_title": ("Частые вопросы", "Questions and answers"),
    "faq": (
        (("Нужна особая камера?",
          "Нет. Подойдёт обычная веб-камера, в том числе встроенная в ноутбук. Если камера умеет 60 кадров в секунду, "
          "курсор будет ещё точнее: «Подробнее» → «Камера»."),
         ("Нужен ли интернет?",
          "Нет. AirMouse работает без сети: рука и лицо распознаются на вашем компьютере."),
         ("Куда уходит видео с камеры?",
          "Никуда. Кадры обрабатываются в памяти программы, не сохраняются и не отправляются. В программе нет сетевого кода."),
         ("Нужно ли что-то устанавливать?",
          "В Windows — нет: распакуйте архив целиком и запустите AirMouse.exe, Python не нужен. В Linux скрипт "
          "install.sh добавляет программу в меню и даёт доступ к виртуальной мыши."),
         ("Как быстро остановить управление?",
          "Ctrl+Alt+M или большой палец вниз на секунду — пауза. Так же управление возвращается."),
         ("Рука быстро устанет?",
          "Кнопка «Центр зоны по моей руке» переносит рабочую зону туда, где руке удобно, — её не нужно держать высоко. "
          "А если руки заняты или устали, есть режимы «Глаза» и «Голова» и клик задержкой."),
         ("Что делать, если курсор дрожит или клики срабатывают сами?",
          "Курсор дрожит — прибавьте «Стабилизацию». Клики срабатывают сами — убавьте «Чувствительность клика». "
          "Помогает и свет: в полутьме камера даёт всего 15 кадров в секунду."),
         ("Работает ли с несколькими мониторами?",
          "В Windows управление идёт на основном мониторе. В Linux под X11 — на всём экране, все мониторы вместе."),
         ("Почему не управляются некоторые окна?",
          "Windows не даёт обычным программам управлять окнами, запущенными от имени администратора, — например, "
          "диспетчером задач. Чтобы управлять и ими, запустите AirMouse от имени администратора."),
         ("Есть ли версия для macOS?",
          "Пока нет. AirMouse работает в Windows 10 и 11 и в Linux.")),
        (("Do I need a special camera?",
          "No. An ordinary webcam will do, including the one built into a laptop. If the camera can give 60 frames "
          "per second, the cursor is even more precise: “More” → “Camera”."),
         ("Do I need the internet?",
          "No. AirMouse works offline: the hand and the face are recognised on your computer."),
         ("Where does the camera video go?",
          "Nowhere. Frames are processed in the program's memory; they are not saved and not sent. The program has "
          "no network code."),
         ("Do I have to install anything?",
          "On Windows, no: extract the whole archive and run AirMouse.exe, no Python needed. On Linux the install.sh "
          "script adds the program to the menu and gives access to the virtual mouse."),
         ("How do I stop the control quickly?",
          "Ctrl+Alt+M or a thumbs down held for a second pauses it. The same brings the control back."),
         ("Will my hand get tired?",
          "The “Center the zone on my hand” button moves the working zone to where your hand is comfortable, so you "
          "do not have to hold it high. And when your hands are busy or tired, there are the “Eyes” and “Head” modes "
          "and the dwell click."),
         ("The cursor shakes, or clicks happen by themselves. What now?",
          "The cursor shakes — raise “Stabilization”. Clicks happen by themselves — lower “Click sensitivity”. "
          "Light helps too: in poor light the camera gives only 15 frames per second."),
         ("Does it work with several monitors?",
          "On Windows the control works on the main monitor. On Linux under X11 it covers the whole screen, "
          "all monitors together."),
         ("Why can't I control some windows?",
          "Windows does not let ordinary programs control windows run as administrator, the Task Manager for example. "
          "To control them too, run AirMouse as administrator."),
         ("Is there a macOS version?",
          "Not yet. AirMouse runs on Windows 10 and 11 and on Linux."))),
    "faq_free": (
        ("Это бесплатно?", "Да. AirMouse можно скачать и пользоваться им бесплатно."),
        ("Is it free?", "Yes. AirMouse is free to download and use.")),
    "faq_pro": (
        " Позже появится версия Pro с дополнительными функциями; всё необходимое для управления останется бесплатным.",
        " A Pro edition with extra features will come later; everything needed for the control stays free."),

    # -- free and Pro -------------------------------------------------------------------------
    "pro_title": ("AirMouse — бесплатный", "AirMouse is free"),
    "pro_sub": ("А для тех, кто захочет больше, готовится версия Pro.",
                "And for those who want more, a Pro edition is on the way."),
    "pro_free_name": ("Бесплатно", "Free"),
    "pro_free_text": ("Всё необходимое, чтобы управлять компьютером без мыши.",
                      "Everything you need to control a computer without a mouse."),
    "pro_free_points": (
        ("Жесты одной и двумя руками", "Глаза, голова и клик задержкой", "Windows и Linux, без регистрации"),
        ("Gestures with one hand and with two", "Eyes, head and the dwell click", "Windows and Linux, no sign-up")),
    "pro_name": ("Pro", "Pro"),
    "pro_badge": ("В разработке", "In development"),
    "pro_text": (
        "Дополнительные функции: без них можно обойтись, но с ними удобнее. Список и цену объявим, когда Pro будет готова.",
        "Extra features: you can do without them, but they make things more comfortable. The list and the price "
        "will be announced when Pro is ready."),
    "pro_news": ("Новости — в Telegram", "News in Telegram (in Russian)"),
    "pro_support": ("Поддержать разработку", "Support the development"),
    "pro_support_text": ("Каждый перевод приближает новые версии.", "Every contribution brings new versions closer."),
    "foot_telegram": ("Telegram-канал", "Telegram channel (in Russian)"),

    # -- gallery (Russian page only: the carousel is in Russian) ---------------------------------
    "gal_title": ("Коротко в картинках", "In pictures"),
    "gal_alt": ("Обложка", "Жесты рукой", "Глаза и голова", "Виджеты", "Блокнот", "Точность в цифрах",
                "Тонкая настройка", "Как скачать"),

    # -- final call and footer ----------------------------------------------------------------
    "cta_title": ("Попробуйте сами", "Try it yourself"),
    "cta_title_free": ("Попробуйте бесплатно", "Try it free"),
    "cta_sub": ("Скачайте, нажмите «Старт», покажите ладонь.", "Download, press “Start”, show your palm."),
    "foot_tag": ("Управляйте компьютером рукой в воздухе.", "Control your computer with a hand in the air."),
    "foot_product": ("Программа", "Product"),
    "foot_help": ("Помощь", "Help"),
    "foot_guide": ("Гайд с картинками", "Illustrated guide"),
    "foot_video_guide": ("Видео-гайд", "Video guide (in Russian)"),
    "foot_releases": ("Все версии", "All versions"),
    "foot_issues": ("Сообщить об ошибке", "Report a problem"),
    "foot_github": ("Исходный код на GitHub", "Source code on GitHub"),
    "foot_top": ("Наверх", "Back to top"),
}
