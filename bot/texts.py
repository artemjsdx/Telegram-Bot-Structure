"""
i18n strings (ru/en) and the t() helper.
Usage:  from texts import t;  t(lang, "menu_title")
Missing key in a language falls back to ru, then to the key name itself.
"""
from __future__ import annotations

from config import DEFAULT_LANG

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        # --- common ---
        "btn_back": "◀️ Назад",
        "btn_home": "🏠 Меню",
        "btn_cancel": "✖️ Отмена",
        "btn_yes": "✅ Да",
        "btn_no": "❌ Нет",
        "cancelled": "Отменено.",
        "loading": "⏳ Обрабатываю…",
        "error_generic": "⚠️ Что-то пошло не так. Попробуйте ещё раз.",
        "banned_msg": "🚫 Доступ к боту ограничен.",
        "admin_only": "🚫 Раздел доступен только администраторам.",
        "post_failed_dm": "⚠️ Не удалось структурировать пост в «{channel}».\nПричина: {error}",

        # --- main menu ---
        "menu_title": "<b>🤖 Channel AI Bot</b>\n\nПереписываю посты в ваших каналах через ИИ.\nВыберите раздел:",
        "menu_settings": "⚙️ Настройки",
        "menu_channels": "📣 Каналы",
        "menu_stats": "📊 Статистика",
        "menu_provider": "🤖 Провайдер",
        "menu_prompt": "✏️ Промпт",
        "menu_help": "❓ Помощь",
        "menu_admin": "🛠 Админка",

        # --- start / help ---
        "start_welcome": "👋 Добро пожаловать! Давайте настроим бота.",
        "help_text": (
            "<b>❓ Помощь</b>\n\n"
            "Бот переписывает посты в ваших каналах через ИИ. Вы создаёте «агента» — связку "
            "ИИ + стиль — и привязываете к нему канал. Каждый новый пост канала бот "
            "автоматически переписывает в заданном стиле.\n\n"

            "<b>🏠 Главный экран — агенты</b>\n"
            "Это список ваших агентов. <b>🤖 Имя</b> — открыть карточку агента. "
            "<b>➕ Создать агента</b> — мастер настройки.\n"
            "Агент = провайдер ИИ + ключ + модель + промпт (стиль) + привязанные каналы. "
            "Можно держать несколько агентов под разные каналы и стили.\n\n"

            "<b>🛠 Создание агента (мастер)</b>\n"
            "По шагам: имя → провайдер → API-ключ → модель → промпт → сис.промпт → канал. "
            "На каждом шаге есть подсказка; <b>/cancel</b> прерывает мастер.\n\n"

            "<b>🗂 Карточка агента</b>\n"
            "• <b>✏️ Имя</b> — переименовать.\n"
            "• <b>🤖 Провайдер</b> / <b>🔑 Ключ</b> / <b>📚 Модель</b> — какой ИИ и под каким "
            "ключом работает агент.\n"
            "• <b>✏️ Промпт</b> — инструкция, КАК переписывать пост (стиль, структура, "
            "форматирование).\n"
            "• <b>🎨 Сис.промпт</b> — передавать промпт как «системный». Обычно ВКЛ: модель "
            "строже держит стиль.\n"
            "• <b>📣 Каналы</b> — привязать/отвязать каналы агента.\n"
            "• <b>🗑 Удалить</b> — удалить агента.\n\n"

            "<b>✏️ Промпт и библиотека пресетов</b>\n"
            "Промпт — самое важное, именно он задаёт стиль. В библиотеке: <b>⭐</b> — ваши "
            "пресеты, <b>📄</b> — готовые. <b>➕ Создать</b> — ввести свой вручную.\n"
            "Тап по пресету открывает карточку: <b>✅ Применить</b>, "
            "<b>📨 Поделиться</b>, <b>🗑 Удалить</b>.\n"
            "<b>🔮 Из поста</b> — ИИ сам соберёт промпт по вашим постам:\n"
            "1. Перешлите от 1 до 20 реальных постов канала (можно пачкой). Чем больше — тем "
            "точнее ИИ поймёт стиль.\n"
            "2. Нажмите <b>⚡️ Создать промпт</b> и выберите режим:\n"
            "  ▫️ <b>🎭 Характер:</b> <b>Единый</b> — один общий стиль на все посты; "
            "<b>🎬 Сценарии</b> — разные правила под разные типы постов плюс стиль по "
            "умолчанию (берите, если постов много и они разные).\n"
            "3. ИИ предложит промпт: <b>✅ Применить</b>, <b>💾 Сохранить и применить</b> "
            "(добавит в ваши пресеты) или <b>❌ Отклонить</b>.\n\n"

            "<b>📨 Предложка пресетов</b>\n"
            "Своим пресетом можно поделиться с другим пользователем. Откройте пресет и "
            "нажмите <b>📨 Поделиться</b>, затем укажите <b>ID</b> или <b>@username</b> "
            "получателя — он должен пользоваться этим ботом.\n"
            "Получателю придёт предложение, где он сам выберет: <b>✅ Применить</b> к "
            "своему агенту, <b>💾 В библиотеку</b>, <b>👁 Осмотреть</b> или "
            "<b>❌ Отклонить</b>.\n"
            "<i>Не хотите получать чужие пресеты — выключите «📨 Предложка пресетов» "
            "в Настройках.</i>\n\n"

            "<b>📣 Каналы</b>\n"
            "Привязка: перешлите в бота любой пост из нужного канала. Бот должен быть "
            "<b>администратором</b> этого канала. ⏹ рядом с каналом — отвязать.\n\n"

            "<b>🤖 Провайдер</b>\n"
            "Выбор ИИ-сервиса (⭐ FavoriteAPI / 🔀 OpenRouter / 🆓 FreeModel) и модели. "
            "<b>🧪 Тест</b> — проверить ключ, <b>🔑 Ключ</b> / <b>🌐 База</b> / "
            "<b>📚 Модель</b> — параметры доступа.\n\n"

            "<b>⚙️ Настройки</b>\n"
            "• <b>🎨 Сис.промпт</b> — как промпт передаётся модели.\n"
            "• <b>👁 Предпросмотр</b> — если ВКЛ, переписанный пост сначала приходит вам в ЛС "
            "на проверку и публикуется только после подтверждения.\n"
            "• <b>📨 Предложка пресетов</b> — принимать ли пресеты, которыми делятся "
            "с вами другие пользователи.\n"
            "• <b>🌐 Язык</b>, <b>🗑 Сбросить статистику</b>.\n\n"

            "<b>📊 Статистика</b> — сколько постов переписано и расход по запросам.\n\n"

            "<b>Команды:</b> /start — запуск, /menu — главный экран, /help — эта справка, "
            "/cancel — отменить текущий шаг.\n\n"
            "🆘 Поддержка / владелец: {support}"
        ),

        # --- settings ---
        "settings_title": "<b>⚙️ Настройки</b>",
        "settings_lang": "🌐 Язык: {code}",
        "settings_preview_on": "👁 Предпросмотр: ВКЛ",
        "settings_preview_off": "👁 Предпросмотр: ВЫКЛ",
        "settings_sys_on": "🎨 Сис.промпт: ВКЛ",
        "settings_sys_off": "🎨 Сис.промпт: ВЫКЛ",
        "settings_shares_on": "📨 Предложка пресетов: ВКЛ",
        "settings_shares_off": "📨 Предложка пресетов: ВЫКЛ",
        "settings_reset_ctx": "♻️ Сбросить контекст",
        "settings_reset_stats": "🗑 Сбросить статистику",
        "settings_saved": "✅ Сохранено.",
        "settings_ctx_reset": "♻️ Контекст сброшен.",
        "settings_stats_reset": "🗑 Статистика сброшена.",

        # --- provider ---
        "provider_title": "<b>🤖 Провайдер</b>\n\nАктивный: <b>{active}</b>\nВыберите провайдера:",
        "provider_test": "🧪 Тест соединения",
        "provider_set_key": "🔑 Сменить ключ",
        "provider_set_base": "🌐 Сменить базу",
        "provider_set_model": "📚 Сменить модель",
        "provider_switched": "✅ Активный провайдер: <b>{name}</b>",
        "provider_need_creds": "🔑 Для <b>{name}</b> нет сохранённых ключей. Введите ключ:",
        "provider_test_ok": "✅ Соединение успешно.\n{info}",
        "provider_test_fail": "❌ Ошибка соединения:\n{error}",
        "provider_enter_base": "🌐 Введите базовый URL API:",
        "provider_enter_key": "🔑 Введите API-ключ:",
        "provider_verifying": "⏳ Проверяю ключ…",
        "provider_key_ok": "✅ Ключ принят.",
        "provider_key_fail": "❌ Ключ не прошёл проверку:\n{error}",
        "provider_choose_model": "📚 Выберите модель:",
        "provider_model_set": "✅ Модель: <code>{model}</code>",
        "provider_freemodel_warn": "ℹ️ FreeModel: бесплатные GPT-модели (gpt-5.4-mini и др.). Есть дневной лимит запросов.",

        # --- prompt ---
        "prompt_title": "<b>✏️ Промпт</b>",
        "prompt_current": "Текущий промпт:\n<blockquote>{prompt}</blockquote>",
        "prompt_empty": "Промпт не задан.",
        "prompt_view": "👁 Показать",
        "prompt_edit": "✏️ Изменить",
        "prompt_presets": "📚 Пресеты",
        "prompt_enter": "✏️ Пришлите новый промпт текстом:",
        "prompt_saved": "✅ Промпт сохранён.",
        "prompt_presets_title": "📚 Выберите пресет:",
        "prompt_preset_applied": "✅ Пресет применён.",
        "preset_lib_btn": "📚 Библиотека пресетов",
        "preset_lib_title": (
            "📚 <b>Библиотека пресетов</b>\n\n"
            "⭐ — ваши пресеты (вверху), 📄 — готовые.\n"
            "Тапните пресет, чтобы посмотреть и применить его к агенту.\n\n"
            "➕ <b>Создать</b> — добавить свой пресет вручную.\n"
            "🔮 <b>Из поста</b> — перешлите пост, и ИИ соберёт пресет по его структуре, "
            "форматированию и стилю."
        ),
        "preset_detail": "📄 <b>{name}</b>\n\n{body}",
        "preset_apply": "✅ Применить пресет",
        "preset_back": "◀️ К списку пресетов",
        # --- user presets (create / delete) ---
        "preset_new_btn": "➕ Создать",
        "preset_fwd_btn": "🔮 Из поста",
        "preset_new_name": (
            "✏️ <b>Новый пресет</b>\n\n"
            "Пришлите <b>название</b> пресета (коротко, например «Деловой стиль»)."
        ),
        "preset_new_body": (
            "📝 Теперь пришлите <b>текст пресета</b> — инструкцию для ИИ: как переписывать посты "
            "(структура, тон, форматирование и т.д.)."
        ),
        "preset_created": "✅ Пресет «{name}» сохранён и добавлен в избранное (вверху списка).",
        "preset_delete_btn": "🗑 Удалить пресет",
        "preset_delete_confirm": "🗑 Удалить пресет «{name}»? Действие необратимо.",
        "preset_deleted": "🗑 Пресет удалён.",
        # --- preset sharing (sender side) ---
        "preset_share_btn": "📨 Поделиться",
        "preset_share_ask": (
            "📨 <b>Поделиться пресетом «{name}»</b>\n\n"
            "Пришлите <b>ID</b> или <b>@username</b> получателя.\n"
            "<i>Получатель должен пользоваться этим ботом</i> — иначе доставить пресет не выйдет."
        ),
        "preset_share_notfound": (
            "🤷 Не нашёл такого пользователя среди тех, кто запускал бота.\n"
            "Проверьте ID/@username и пришлите ещё раз, либо нажмите «Назад»."
        ),
        "preset_share_self": "🙂 Это вы сами. Укажите другого получателя.",
        "preset_share_blocked": (
            "🚫 Этот пользователь не принимает предложку пресетов.\n"
            "Укажите другого получателя или нажмите «Назад»."
        ),
        "preset_share_confirm": (
            "📨 <b>Отправить пресет?</b>\n\n"
            "Пресет: <b>{name}</b>\n"
            "Получатель: {who}\n\n"
            "Он получит уведомление и сам решит — применить, сохранить или отклонить."
        ),
        "preset_share_send_btn": "📤 Отправить",
        "preset_share_sent": "✅ Пресет «{name}» отправлен пользователю {who}.",
        "preset_share_fail": (
            "⚠️ Не удалось доставить — похоже, пользователь остановил бота. "
            "Попробуйте другого получателя."
        ),
        # --- preset sharing (recipient side) ---
        "preset_share_recv": (
            "📨 <b>Вам прислали пресет</b>\n\n"
            "{sender} делится с вами пресетом <b>«{name}»</b>.\n\n"
            "Осмотрите его, примените к своему агенту или сохраните в библиотеку."
        ),
        "pshare_view_btn": "👁 Осмотреть",
        "pshare_apply_btn": "✅ Применить",
        "pshare_save_btn": "💾 В библиотеку",
        "pshare_reject_btn": "❌ Отклонить",
        "pshare_back_btn": "◀️ Назад",
        "pshare_body": "📨 <b>{name}</b>\nот {sender}\n\n{body}",
        "pshare_pick_agent": "✅ <b>К какому агенту применить пресет «{name}»?</b>\nЭто заменит промпт выбранного агента.",
        "pshare_no_agents": (
            "🤖 У вас пока нет агентов. Пресет «{name}» сохранён в вашу библиотеку — "
            "примените его при создании агента."
        ),
        "pshare_applied": "✅ Пресет «{name}» применён к агенту «{agent}».",
        "pshare_saved": "💾 Пресет «{name}» добавлен в вашу библиотеку.",
        "pshare_rejected": "❌ Вы отклонили пресет «{name}».",
        "pshare_stale": "⚠️ Это предложение уже неактуально (обработано или отозвано).",
        # --- AI preset suggestion from a forwarded post ---
        "preset_fwd_howto": (
            "🔮 <b>Пресет из постов</b>\n\n"
            "Перешлите сюда от 1 до 20 постов канала (можно сразу несколько за раз). "
            "Чем больше реальных постов — тем точнее ИИ поймёт ваш стиль.\n\n"
            "После каждого поста я покажу, сколько принято. Когда хватит — нажмите "
            "«⚡️ Создать промпт». ИИ разберёт структуру, форматирование (жирный, курсив, "
            "спойлеры и т.д.) и характер, и предложит готовый пресет.\n\n"
            "Подойдёт пост с текстом или подписью к медиа."
        ),
        "preset_fwd_no_text": (
            "⚠️ В этом посте нет текста для анализа — пропускаю. Перешлите пост с текстом или подписью."
        ),
        "preset_collect_count": (
            "📥 Принято постов: <b>{n}/{max}</b>.\n\n"
            "Перешлите ещё (можно сразу несколько) или нажмите «⚡️ Создать промпт»."
        ),
        "preset_collect_capped": (
            "📥 Набрано максимум — <b>{max}</b> постов. Лишние не добавляю.\n\n"
            "Нажмите «⚡️ Создать промпт» или отмените."
        ),
        "preset_collect_gen_btn": "⚡️ Создать промпт",
        "preset_collect_empty": "Сначала перешлите хотя бы один пост.",
        # --- AI generation mode picker (two toggles) ---
        "preset_mode_char_unified": "🎭 Единый",
        "preset_mode_char_scenarios": "🎬 Сценарии",
        "preset_mode_gen_btn": "⚡️ Сгенерировать",
        "preset_mode_title": (
            "⚙️ <b>Настройка генерации</b>\n"
            "Собрано постов: <b>{n}</b>. Выберите, как ИИ соберёт пресет.\n\n"
            "<b>🎭 Характер</b> — насколько единым будет стиль:\n"
            "• <b>🎭 Единый</b> — ИИ найдёт одну общую форму подачи и опишет её как цельный "
            "стиль. Все посты будут оформляться одинаково. Лучше всего, когда канал ведётся "
            "в одном узнаваемом стиле.\n"
            "• <b>🎬 Сценарии</b> — ИИ заметит, что посты бывают РАЗНЫЕ (новость, рассуждение, "
            "реклама, анонс…), и пропишет правила «если пост такой — оформляй так», плюс стиль "
            "по умолчанию. Лучше всего, когда вы прислали много постов РАЗНЫХ типов.\n\n"
            "💡 <b>Совет.</b> Прислали 10+ постов разных типов — берите <b>🎬 Сценарии</b>; "
            "стиль ровный и однотипный — <b>🎭 Единый</b>.\n\n"
            "Когда выберете — нажмите «⚡️ Сгенерировать»."
        ),
        "preset_analyzing": "🔮 Анализирую пост… это займёт несколько секунд.",
        "preset_analyzing_n": "🔮 Анализирую посты ({n})… это займёт несколько секунд.",
        "preset_suggested_title": (
            "🔮 <b>Предложенный пресет</b>\n\n{body}\n\n"
            "Примените его сразу или сохраните в избранное и примените."
        ),
        "preset_suggest_apply_btn": "✅ Применить",
        "preset_suggest_save_btn": "💾 Сохранить и применить",
        "preset_suggest_discard_btn": "❌ Отклонить",
        "preset_suggest_save_name": (
            "💾 Пришлите <b>название</b> для этого пресета — он сохранится в избранном и применится к агенту."
        ),
        "preset_suggest_discarded": "❌ Предложение отклонено.",
        "preset_suggest_fail": (
            "😕 Не удалось проанализировать пост: {error}\n\nПопробуйте ещё раз или создайте пресет вручную."
        ),
        "preset_session_stale": "⚠️ Сессия устарела (бот перезапускался). Откройте «✏️ Промпт» → библиотеку и повторите.",

        # --- channels ---
        "channels_title": "<b>📣 Каналы</b>",
        "channels_empty": "Каналов нет. Нажмите ➕, чтобы привязать.",
        "channel_add": "➕ Привязать канал",
        "channel_add_howto": (
            "➕ <b>Привязка канала</b>\n\n"
            "Перешлите сюда любой пост из нужного канала.\n"
            "Бот должен быть администратором канала."
        ),
        "channel_added": "✅ Канал «{title}» привязан.",
        "channel_not_forwarded": "❌ Это не пересланный пост из канала. Попробуйте ещё раз.",
        "channel_removed": "✅ Канал отвязан.",
        "channel_confirm_remove": "Отвязать канал «{title}»?",
        "channel_toggle_on": "▶️ Включить",
        "channel_toggle_off": "⏸ Выключить",
        "channel_toggled": "✅ Статус канала обновлён.",
        "channel_set_active": "⭐ Сделать активным",
        "channel_active_set": "✅ Активный канал обновлён.",
        "channel_remove": "⏹ Отвязать",

        # --- agents (multi-agent home + wizard + card) ---
        "agents_title": (
            "<b>🤖 Мои агенты</b>\n\n"
            "Каждый агент переписывает посты в своих каналах по своему провайдеру и промпту.\n"
            "Выберите агента или создайте нового:"
        ),
        "agents_empty": (
            "<b>🤖 Мои агенты</b>\n\n"
            "У вас пока нет агентов. Создайте первого — он будет переписывать посты в выбранных каналах."
        ),
        "agent_create": "➕ Создать агента",
        "agent_card": (
            "<b>🤖 {name}</b>\n\n"
            "Провайдер: <b>{provider}</b>\n"
            "Модель: <code>{model}</code>\n"
            "Промпт: <blockquote>{prompt}</blockquote>\n"
            "Режим: {mode}\n"
            "Форварды: {forwarded}\n"
            "Каналы: {channels}\n\n"
            "<blockquote>✏️ <b>Правка</b> — бот редактирует пост на месте. "
            "🔁 <b>Переотправка</b> — удаляет оригинал и шлёт новый, сохраняя медиа "
            "(фото/видео/файлы). Форварды редактировать нельзя — для них всегда переотправка.</blockquote>"
        ),
        "agent_mode_edit": "✏️ Режим: правка",
        "agent_mode_resend": "🔁 Режим: переотправка",
        "agent_mode_edit_v": "✏️ правка на месте",
        "agent_mode_resend_v": "🔁 переотправка (удалить + отправить заново)",
        "agent_fwd_on": "↪️ Форварды: ВКЛ",
        "agent_fwd_off": "↪️ Форварды: ВЫКЛ",
        "agent_fwd_on_v": "реагирует (переотправкой)",
        "agent_fwd_off_v": "пропускает",
        "agent_web_btn": "🌐 Веб-поиск",
        "agent_web_title": (
            "🌐 <b>Веб-поиск</b>\n\n"
            "Состояние: <b>{state}</b>\n"
            "Сайтов на запрос: <b>{results}</b>\n"
            "Длина фрагмента сайта: <b>{snippet}</b> симв.\n"
            "Раундов поиска: <b>{rounds}</b>\n"
            "API-ключ: <b>{key}</b>\n\n"
            "<blockquote>Когда модели не хватает данных для точного поста (актуальные "
            "лимиты сервиса, детали новости, проверка фактов), она сама ищет в интернете "
            "через DuckDuckGo, видит дату источников и может раскрыть полную версию "
            "нужного результата. API-ключ не обязателен.</blockquote>"
        ),
        "agent_web_on": "🌐 Веб-поиск: ВКЛ",
        "agent_web_off": "🌐 Веб-поиск: ВЫКЛ",
        "agent_web_state_on": "включён",
        "agent_web_state_off": "выключен",
        "agent_web_results": "🔎 Сайтов на запрос: {n}",
        "agent_web_snippet": "📄 Длина фрагмента: {n}",
        "agent_web_rounds": "🔁 Раундов поиска: {n}",
        "agent_web_key": "🔑 API-ключ (опц.)",
        "agent_web_key_set": "🔑 API-ключ: задан ✅",
        "agent_web_key_none": "не задан (DuckDuckGo бесплатно)",
        "agent_web_key_yes": "задан",
        "agent_web_key_ask": (
            "🔑 Пришлите API-ключ поискового сервиса (Brave/Serper/Tavily) одним сообщением.\n\n"
            "<blockquote>Это <b>не обязательно</b>: без ключа поиск работает через "
            "DuckDuckGo бесплатно. Чтобы очистить ключ — пришлите «-».</blockquote>"
        ),
        "agent_web_key_saved": "✅ Готово.",
        "agent_edit_name": "✏️ Имя",
        "agent_edit_provider": "🤖 Провайдер",
        "agent_edit_key": "🔑 Ключ",
        "agent_edit_model": "📚 Модель",
        "agent_edit_prompt": "✏️ Промпт",
        "agent_channels": "📣 Каналы",
        "agent_delete": "🗑 Удалить агента",
        "agent_add_channel": "➕ Привязать канал",
        "agent_ask_name": "✏️ <b>Новый агент</b>\n\nКак назовём агента? Пришлите имя текстом:",
        "agent_ask_provider": "🤖 Выберите провайдера для агента:",
        "agent_next": "Готово",
        "agent_sys_title": (
            "🎨 <b>Системный промпт</b>\n\n"
            "Добавляет к вашему промпту служебные правила оформления. Включить?"
        ),
        "agent_bind_howto": (
            "➕ <b>Привязка канала к агенту</b>\n\n"
            "Чтобы агент переписывал посты, привяжите к нему канал:\n\n"
            "<b>1.</b> Добавьте бота в канал <b>администратором</b> "
            "(право <i>«Публикация сообщений»</i> обязательно).\n"
            "<b>2.</b> Перешлите сюда <b>любой пост</b> из этого канала.\n\n"
            "<blockquote>Бот определит канал из пересланного поста сам — "
            "вводить ID вручную не нужно.</blockquote>\n\n"
            "<i>Можно нажать «Пропустить» — привяжете позже из карточки агента.</i>"
        ),
        "agent_bind_skip": "⏭ Пропустить",
        "agent_skip_setup": "⏭ Пропустить настройку",
        "agent_ready": "✅ Агент готов! Канал «{title}» привязан.",
        "agent_ready_nochan": "✅ Агент готов! Канал можно привязать позже из его карточки.",
        "agent_gone": "⚠️ Этот агент уже удалён, привязывать канал не к чему. Откройте меню и выберите агента заново.",
        "agent_addchan_howto": (
            "➕ <b>Привязка канала к агенту</b>\n\n"
            "<b>1.</b> Добавьте бота в канал <b>администратором</b> "
            "(право <i>«Публикация сообщений»</i>).\n"
            "<b>2.</b> Перешлите сюда <b>любой пост</b> из этого канала.\n\n"
            "<blockquote>Канал определится из пересланного поста — "
            "ID вручную вводить не нужно.</blockquote>"
        ),
        "agent_chan_added": "✅ Канал «{title}» привязан.",
        "agent_channels_title": "<b>📣 Каналы агента</b>\n\nНажмите ⏹, чтобы отвязать канал.",
        "agent_channels_empty": "<b>📣 Каналы агента</b>\n\nПока ни одного канала. Нажмите ➕, чтобы привязать.",
        "agent_confirm_delete": "Удалить агента «{name}»? Его каналы перестанут обрабатываться.",
        "model_search": "🔎 Поиск",
        "model_search_prompt": "🔎 Введите часть названия модели:",
        "model_search_none": "❌ Ничего не найдено. Показываю полный список.",

        # --- stats ---
        "stats_title": "<b>📊 Статистика</b>",
        "stats_body": (
            "Обработано: <b>{processed}</b>\n"
            "Ошибок: <b>{failed}</b>\n"
            "Среднее время: <b>{avg_ms} мс</b>\n"
            "Последняя активность: {last}"
        ),
        "stats_none": "Пока нет данных.",
        "stats_caption": (
            "<b>📊 Ваша статистика</b>\n\n"
            "Обработано: <b>{processed}</b> · Ошибок: <b>{failed}</b>\n"
            "Успешность: <b>{rate}%</b>\n"
            "Скорость: ср <b>{avg} мс</b> · медиана <b>{median} мс</b>\n"
            "За 24ч: <b>{c24}</b> · 7д: <b>{c7}</b> · 30д: <b>{c30}</b>\n"
            "Каналов: <b>{channels}</b> · Агентов: <b>{agents}</b>\n"
            "Первая активность: {first}\n"
            "Последняя активность: {last}"
        ),
        "stats_chart_title": "Статистика постов",
        "stats_legend_proc": "Обработано",
        "stats_legend_fail": "Ошибки",
        "chart_sub_days": "за {n} дн.",
        "period_1d": "1д",
        "period_7d": "7д",
        "period_30d": "30д",

        # --- preview ---
        "preview_caption": (
            "<b>👁 Предпросмотр</b>\n\n"
            "Канал: {chan}\n\n"
            "<blockquote>{text}</blockquote>\n\n"
            "Опубликовать?"
        ),
        "preview_publish": "✅ Опубликовать",
        "preview_reject": "❌ Отклонить",
        "preview_edit": "✏️ Правка",
        "preview_published": "✅ Опубликовано.",
        "preview_rejected": "❌ Отклонено.",
        "preview_edit_prompt": (
            "✏️ <b>Правка</b>\n\n"
            "Текущий вариант ниже — тапните по нему, чтобы скопировать, отредактируйте и пришлите "
            "новый текст в ответ. Можно использовать HTML-теги (&lt;b&gt;, &lt;i&gt; и т.д.).\n\n"
            "<code>{text}</code>"
        ),

        # --- admin ---
        "admin_title": "<b>🛠 Админ-панель</b>",
        "admin_users": "👥 Пользователи",
        "admin_stats": "📊 Глобальная статистика",
        "admin_broadcast": "📢 Рассылка",
        "admin_logs": "📜 Логи",
        "admin_banner": "🖼 Баннер меню",
        "admin_desc": "📝 Описание бота",
        "admin_support": "🆘 Поддержка",
        "admin_menuchan": "📰 Канал в меню",
        "admin_users_title": "<b>👥 Пользователи</b> ({count})",
        "admin_user_search": "🔎 Поиск",
        "admin_user_search_prompt": "🔎 Введите @username, имя или ID пользователя:",
        "admin_user_search_none": "❌ Никого не найдено по запросу «{q}».",
        "admin_user_search_title": "<b>🔎 Результаты: «{q}»</b> ({count})",
        "admin_user_ban": "🚫 Забанить",
        "admin_user_unban": "✅ Разбанить",
        "admin_user_banned": "🚫 Пользователь забанен.",
        "admin_user_unbanned": "✅ Пользователь разбанен.",
        "admin_user_none": "Пользователь не найден.",
        "admin_user_status_banned": "🚫 бан",
        "admin_user_status_blocked": "⛔ заблокировал бота",
        "admin_user_status_deleted": "👻 удалил / недоступен",
        "admin_user_status_ok": "🟢 активен",
        "admin_user_card": (
            "<b>👤 {name}</b>\n"
            "ID: <code>{id}</code> · {status}\n\n"
            "Обработано: <b>{processed}</b> · Ошибок: <b>{failed}</b>\n"
            "Успешность: <b>{rate}%</b>\n"
            "Скорость: ср <b>{avg}</b> · мед <b>{median}</b> · макс <b>{max}</b> мс\n"
            "За 24ч: <b>{c24}</b> · 7д: <b>{c7}</b> · 30д: <b>{c30}</b>\n"
            "Каналов: <b>{channels}</b> · Агентов: <b>{agents}</b>\n"
            "Провайдер: {provider} · Язык: {ulang}\n"
            "Регистрация: {created}\n"
            "Последняя активность: {last}"
        ),
        "admin_user_channels": "\n\n<b>📎 Привязанные каналы:</b>\n{list}",
        "admin_user_channels_more": "\n…и ещё {n}",
        "admin_user_channels_none": "\n\n<i>📎 Нет привязанных каналов</i>",
        "admin_user_channels_link": "🔗 ссылка",
        "admin_gstats": (
            "<b>📊 Глобальная статистика</b>\n\n"
            "Пользователей: <b>{users}</b>\n"
            "Активных: <b>{active}</b>\n"
            "⛔ Заблокировали: <b>{blocked}</b> · 👻 Удалили: <b>{deleted}</b>\n"
            "🚫 Бан: <b>{banned}</b>\n"
            "Обработано постов: <b>{processed}</b>\n"
            "Ошибок: <b>{failed}</b>"
        ),
        "admin_gstats_chart_title": "Пользователи",
        "admin_gstats_legend_join": "Новые",
        "admin_gstats_legend_left": "Ушедшие",
        # --- support contact ---
        "admin_support_title": (
            "<b>🆘 Контакт поддержки</b>\n\n"
            "Текущий: {handle}\n"
            "ID: <code>{id}</code>\n\n"
            "Показывается в разделе «Помощь»."
        ),
        "admin_support_set": "✏️ Изменить ID",
        "admin_support_prompt": "✏️ Пришлите числовой Telegram ID нового контакта поддержки:",
        "admin_support_bad": "❌ Это не похоже на ID. Пришлите число (например 8149203573).",
        "admin_support_saved": "✅ Контакт поддержки обновлён: {handle}",
        # --- bot channel line in main menu ---
        "admin_menuchan_title": (
            "<b>📰 Канал бота в меню</b>\n\n"
            "Статус: {status}\n"
            "Ссылка: {link}\n\n"
            "Когда включено, в главном меню появляется строка со ссылкой на канал."
        ),
        "admin_menuchan_on": "включён ✅",
        "admin_menuchan_off": "выключен ⛔",
        "admin_menuchan_none": "не задана",
        "admin_menuchan_setup": "🔗 Указать канал",
        "admin_menuchan_toggle_on": "✅ Включить строку",
        "admin_menuchan_toggle_off": "⛔ Выключить строку",
        "admin_menuchan_clear": "🗑 Сбросить",
        "admin_menuchan_ask_id": (
            "🔗 <b>Канал в меню</b>\n\n"
            "Перешлите любой пост из канала, либо пришлите @username, ссылку t.me или ID (-100…).\n"
            "Для публичного канала бот сам соберёт ссылку; для приватного попросит ссылку-инвайт."
        ),
        "admin_menuchan_ask_link": (
            "🔒 У канала нет публичного @username.\n"
            "Пришлите ссылку-приглашение вручную (https://t.me/+…):"
        ),
        "admin_menuchan_bad_id": (
            "❌ Не удалось распознать канал. Пришлите @username, ссылку или ID, либо перешлите пост."
        ),
        "admin_menuchan_bad_link": "❌ Это не похоже на ссылку. Пришлите URL вида https://t.me/…",
        "admin_menuchan_saved": "✅ Канал сохранён, строка в меню включена.",
        "admin_menuchan_cleared": "✅ Настройка канала сброшена.",
        "admin_menuchan_toggled_on": "✅ Строка канала включена.",
        "admin_menuchan_toggled_off": "⛔ Строка канала выключена.",
        "menu_channel_line": (
            "📰 <a href=\"{link}\">Telegram-канал бота</a> — обновления, отзывы и раздачи"
        ),
        "admin_broadcast_prompt": "📢 Пришлите текст рассылки:",
        "admin_broadcast_sent": "✅ Рассылка отправлена: {ok}/{total}",
        "admin_logs_title": "<b>📜 Последние запросы</b>",
        "admin_logs_empty": "Логи пусты.",
        "admin_banner_title": (
            "<b>🖼 Баннер меню</b>\n\nТекущий: {current}\n\n"
            "Баннер показывается над кнопками главного меню."
        ),
        "admin_banner_photo": "📷 Задать фото",
        "admin_banner_video": "🎬 Задать видео",
        "admin_banner_remove": "🗑 Убрать баннер",
        "admin_banner_send_photo": "📷 Пришлите фото для баннера:",
        "admin_banner_send_video": "🎬 Пришлите видео для баннера:",
        "admin_banner_saved": "✅ Баннер обновлён.",
        "admin_banner_removed": "✅ Баннер убран.",
        "admin_banner_wrong": "❌ Ожидалось {kind}. Попробуйте ещё раз.",
        "admin_desc_title": (
            "<b>📝 Описание бота</b>\n\n"
            "Длинное (экран «Что умеет этот бот»):\n<blockquote>{long}</blockquote>\n\n"
            "Короткое (в профиле):\n<blockquote>{short}</blockquote>"
        ),
        "admin_desc_edit_long": "✏️ Длинное описание",
        "admin_desc_edit_short": "✏️ Короткое описание",
        "admin_desc_enter_long": "✏️ Пришлите длинное описание (до 512 симв.):",
        "admin_desc_enter_short": "✏️ Пришлите короткое описание (до 120 симв.):",
        "admin_desc_saved": "✅ Описание обновлено.",

        # --- bot profile defaults (set via Bot API) ---
        "bot_desc_long": (
            "Я переписываю посты в ваших Telegram-каналах через ИИ. "
            "Поддерживаю несколько провайдеров, предпросмотр перед публикацией "
            "и гибкие промпты. Нажмите «Start», чтобы настроить."
        ),
        "bot_desc_short": "ИИ переписывает посты в ваших каналах.",
    },

    "en": {
        "btn_back": "◀️ Back",
        "btn_home": "🏠 Menu",
        "btn_cancel": "✖️ Cancel",
        "btn_yes": "✅ Yes",
        "btn_no": "❌ No",
        "cancelled": "Cancelled.",
        "loading": "⏳ Working…",
        "error_generic": "⚠️ Something went wrong. Please try again.",
        "banned_msg": "🚫 Access to the bot is restricted.",
        "admin_only": "🚫 Admins only.",
        "post_failed_dm": "⚠️ Couldn't rewrite a post in “{channel}”.\nReason: {error}",

        "menu_title": "<b>🤖 Channel AI Bot</b>\n\nI rewrite posts in your channels with AI.\nChoose a section:",
        "menu_settings": "⚙️ Settings",
        "menu_channels": "📣 Channels",
        "menu_stats": "📊 Stats",
        "menu_provider": "🤖 Provider",
        "menu_prompt": "✏️ Prompt",
        "menu_help": "❓ Help",
        "menu_admin": "🛠 Admin",

        "start_welcome": "👋 Welcome! Let's set up the bot.",
        "help_text": (
            "<b>❓ Help</b>\n\n"
            "The bot rewrites your channel posts with AI. You create an “agent” — an "
            "AI + style bundle — and link a channel to it. Every new post in that channel "
            "is automatically rewritten in the chosen style.\n\n"

            "<b>🏠 Home screen — agents</b>\n"
            "A list of your agents. <b>🤖 Name</b> opens the agent card. "
            "<b>➕ Create agent</b> starts the setup wizard.\n"
            "An agent = AI provider + key + model + prompt (style) + linked channels. "
            "You can keep several agents for different channels and styles.\n\n"

            "<b>🛠 Creating an agent (wizard)</b>\n"
            "Step by step: name → provider → API key → model → prompt → system prompt → "
            "channel. Each step has a hint; <b>/cancel</b> aborts the wizard.\n\n"

            "<b>🗂 Agent card</b>\n"
            "• <b>✏️ Name</b> — rename.\n"
            "• <b>🤖 Provider</b> / <b>🔑 Key</b> / <b>📚 Model</b> — which AI runs the agent "
            "and with which key.\n"
            "• <b>✏️ Prompt</b> — the instruction for HOW to rewrite a post (style, "
            "structure, formatting).\n"
            "• <b>🎨 System prompt</b> — send the prompt as a “system” one. Usually ON: the "
            "model keeps the style more strictly.\n"
            "• <b>📣 Channels</b> — link/unlink the agent's channels.\n"
            "• <b>🗑 Delete</b> — remove the agent.\n\n"

            "<b>✏️ Prompt and preset library</b>\n"
            "The prompt is the most important part — it sets the style. In the library: "
            "<b>⭐</b> — your presets, <b>📄</b> — ready-made. <b>➕ Create</b> — enter your "
            "own manually.\n"
            "Tapping a preset opens its card: <b>✅ Apply</b>, <b>📨 Share</b>, "
            "<b>🗑 Delete</b>.\n"
            "<b>🔮 From posts</b> — the AI builds a prompt from your posts:\n"
            "1. Forward 1 to 20 real channel posts (a batch is fine). The more, the better "
            "the AI captures the style.\n"
            "2. Tap <b>⚡️ Generate prompt</b> and choose the mode:\n"
            "  ▫️ <b>🎭 Character:</b> <b>Unified</b> — one common style for all posts; "
            "<b>🎬 Scenarios</b> — different rules for different post types plus a default "
            "style (use it when you sent many, varied posts).\n"
            "3. The AI suggests a prompt: <b>✅ Apply</b>, <b>💾 Save &amp; apply</b> "
            "(adds it to your presets) or <b>❌ Discard</b>.\n\n"

            "<b>📨 Sharing presets</b>\n"
            "You can share one of your presets with another user. Open the preset and tap "
            "<b>📨 Share</b>, then enter the recipient's <b>ID</b> or <b>@username</b> — "
            "they must already use this bot.\n"
            "They get an offer and decide for themselves: <b>✅ Apply</b> to one of their "
            "agents, <b>💾 To library</b>, <b>👁 View</b> or <b>❌ Reject</b>.\n"
            "<i>Don't want to receive others' presets — turn off “📨 Shared presets” "
            "in Settings.</i>\n\n"

            "<b>📣 Channels</b>\n"
            "To link: forward any post from the channel to the bot. The bot must be an "
            "<b>administrator</b> of that channel. ⏹ next to a channel unlinks it.\n\n"

            "<b>🤖 Provider</b>\n"
            "Pick the AI service (⭐ FavoriteAPI / 🔀 OpenRouter / 🆓 FreeModel) and model. "
            "<b>🧪 Test</b> checks the key; <b>🔑 Key</b> / <b>🌐 Base</b> / <b>📚 Model</b> "
            "are access settings.\n\n"

            "<b>⚙️ Settings</b>\n"
            "• <b>🎨 System prompt</b> — how the prompt is passed to the model.\n"
            "• <b>👁 Preview</b> — when ON, the rewritten post first arrives in your DM for "
            "review and is published only after you confirm.\n"
            "• <b>📨 Shared presets</b> — whether to accept presets other users share "
            "with you.\n"
            "• <b>🌐 Language</b>, <b>🗑 Reset stats</b>.\n\n"

            "<b>📊 Stats</b> — how many posts were rewritten and request usage.\n\n"

            "<b>Commands:</b> /start — launch, /menu — home screen, /help — this help, "
            "/cancel — cancel the current step.\n\n"
            "🆘 Support / owner: {support}"
        ),

        "settings_title": "<b>⚙️ Settings</b>",
        "settings_lang": "🌐 Language: {code}",
        "settings_preview_on": "👁 Preview: ON",
        "settings_preview_off": "👁 Preview: OFF",
        "settings_sys_on": "🎨 System prompt: ON",
        "settings_sys_off": "🎨 System prompt: OFF",
        "settings_shares_on": "📨 Shared presets: ON",
        "settings_shares_off": "📨 Shared presets: OFF",
        "settings_reset_ctx": "♻️ Reset context",
        "settings_reset_stats": "🗑 Reset stats",
        "settings_saved": "✅ Saved.",
        "settings_ctx_reset": "♻️ Context reset.",
        "settings_stats_reset": "🗑 Stats reset.",

        "provider_title": "<b>🤖 Provider</b>\n\nActive: <b>{active}</b>\nChoose a provider:",
        "provider_test": "🧪 Test connection",
        "provider_set_key": "🔑 Change key",
        "provider_set_base": "🌐 Change base",
        "provider_set_model": "📚 Change model",
        "provider_switched": "✅ Active provider: <b>{name}</b>",
        "provider_need_creds": "🔑 No saved key for <b>{name}</b>. Enter the key:",
        "provider_test_ok": "✅ Connection OK.\n{info}",
        "provider_test_fail": "❌ Connection error:\n{error}",
        "provider_enter_base": "🌐 Enter the API base URL:",
        "provider_enter_key": "🔑 Enter the API key:",
        "provider_verifying": "⏳ Verifying key…",
        "provider_key_ok": "✅ Key accepted.",
        "provider_key_fail": "❌ Key verification failed:\n{error}",
        "provider_choose_model": "📚 Choose a model:",
        "provider_model_set": "✅ Model: <code>{model}</code>",
        "provider_freemodel_warn": "ℹ️ FreeModel: free GPT models (gpt-5.4-mini etc). A daily request limit applies.",

        "prompt_title": "<b>✏️ Prompt</b>",
        "prompt_current": "Current prompt:\n<blockquote>{prompt}</blockquote>",
        "prompt_empty": "No prompt set.",
        "prompt_view": "👁 Show",
        "prompt_edit": "✏️ Edit",
        "prompt_presets": "📚 Presets",
        "prompt_enter": "✏️ Send the new prompt as text:",
        "prompt_saved": "✅ Prompt saved.",
        "prompt_presets_title": "📚 Choose a preset:",
        "prompt_preset_applied": "✅ Preset applied.",
        "preset_lib_btn": "📚 Preset library",
        "preset_lib_title": (
            "📚 <b>Preset library</b>\n\n"
            "⭐ — your presets (on top), 📄 — built-in.\n"
            "Tap a preset to view it and apply it to the agent.\n\n"
            "➕ <b>Create</b> — add your own preset manually.\n"
            "🔮 <b>From post</b> — forward a post and the AI will build a preset from its "
            "structure, formatting and tone."
        ),
        "preset_detail": "📄 <b>{name}</b>\n\n{body}",
        "preset_apply": "✅ Apply preset",
        "preset_back": "◀️ To preset list",
        # --- user presets (create / delete) ---
        "preset_new_btn": "➕ Create",
        "preset_fwd_btn": "🔮 From post",
        "preset_new_name": (
            "✏️ <b>New preset</b>\n\n"
            "Send the preset <b>name</b> (short, e.g. “Business style”)."
        ),
        "preset_new_body": (
            "📝 Now send the <b>preset text</b> — the instruction for the AI on how to rewrite "
            "posts (structure, tone, formatting, etc.)."
        ),
        "preset_created": "✅ Preset “{name}” saved and pinned to favorites (top of the list).",
        "preset_delete_btn": "🗑 Delete preset",
        "preset_delete_confirm": "🗑 Delete preset “{name}”? This cannot be undone.",
        "preset_deleted": "🗑 Preset deleted.",
        # --- preset sharing (sender side) ---
        "preset_share_btn": "📨 Share",
        "preset_share_ask": (
            "📨 <b>Share preset “{name}”</b>\n\n"
            "Send the recipient's <b>ID</b> or <b>@username</b>.\n"
            "<i>The recipient must already use this bot</i> — otherwise the preset can't be delivered."
        ),
        "preset_share_notfound": (
            "🤷 Couldn't find that user among those who started the bot.\n"
            "Check the ID/@username and send again, or tap “Back”."
        ),
        "preset_share_self": "🙂 That's you. Pick a different recipient.",
        "preset_share_blocked": (
            "🚫 This user isn't accepting shared presets.\n"
            "Pick a different recipient or tap “Back”."
        ),
        "preset_share_confirm": (
            "📨 <b>Send the preset?</b>\n\n"
            "Preset: <b>{name}</b>\n"
            "Recipient: {who}\n\n"
            "They'll get a notification and decide for themselves — apply, save or reject."
        ),
        "preset_share_send_btn": "📤 Send",
        "preset_share_sent": "✅ Preset “{name}” sent to {who}.",
        "preset_share_fail": (
            "⚠️ Couldn't deliver — looks like the user stopped the bot. "
            "Try another recipient."
        ),
        # --- preset sharing (recipient side) ---
        "preset_share_recv": (
            "📨 <b>Someone shared a preset with you</b>\n\n"
            "{sender} is sharing the preset <b>“{name}”</b> with you.\n\n"
            "Take a look, apply it to one of your agents, or save it to your library."
        ),
        "pshare_view_btn": "👁 View",
        "pshare_apply_btn": "✅ Apply",
        "pshare_save_btn": "💾 To library",
        "pshare_reject_btn": "❌ Reject",
        "pshare_back_btn": "◀️ Back",
        "pshare_body": "📨 <b>{name}</b>\nfrom {sender}\n\n{body}",
        "pshare_pick_agent": "✅ <b>Which agent should the preset “{name}” apply to?</b>\nThis will replace that agent's prompt.",
        "pshare_no_agents": (
            "🤖 You don't have any agents yet. The preset “{name}” has been saved to your "
            "library — apply it when you create an agent."
        ),
        "pshare_applied": "✅ Preset “{name}” applied to agent “{agent}”.",
        "pshare_saved": "💾 Preset “{name}” added to your library.",
        "pshare_rejected": "❌ You rejected the preset “{name}”.",
        "pshare_stale": "⚠️ This offer is no longer valid (already handled or withdrawn).",
        # --- AI preset suggestion from a forwarded post ---
        "preset_fwd_howto": (
            "🔮 <b>Preset from posts</b>\n\n"
            "Forward 1 to 20 channel posts here (you can send several at once). "
            "The more real posts, the better the AI captures your style.\n\n"
            "After each post I'll show how many were collected. When you're ready, tap "
            "“⚡️ Generate prompt”. The AI will analyze the structure, formatting (bold, "
            "italic, spoilers, etc.) and tone, and suggest a ready preset.\n\n"
            "A post with text or a media caption works."
        ),
        "preset_fwd_no_text": (
            "⚠️ This post has no text to analyze — skipping it. Forward a post with text or a caption."
        ),
        "preset_collect_count": (
            "📥 Posts collected: <b>{n}/{max}</b>.\n\n"
            "Forward more (several at once is fine) or tap “⚡️ Generate prompt”."
        ),
        "preset_collect_capped": (
            "📥 Maximum reached — <b>{max}</b> posts. Extra ones are ignored.\n\n"
            "Tap “⚡️ Generate prompt” or cancel."
        ),
        "preset_collect_gen_btn": "⚡️ Generate prompt",
        "preset_collect_empty": "Forward at least one post first.",
        # --- AI generation mode picker (two toggles) ---
        "preset_mode_char_unified": "🎭 Unified",
        "preset_mode_char_scenarios": "🎬 Scenarios",
        "preset_mode_gen_btn": "⚡️ Generate",
        "preset_mode_title": (
            "⚙️ <b>Generation setup</b>\n"
            "Posts collected: <b>{n}</b>. Choose how the AI builds the preset.\n\n"
            "<b>🎭 Character</b> — how unified the style is:\n"
            "• <b>🎭 Unified</b> — the AI finds one common form and describes it as a single "
            "style. Every post is formatted the same way. Best when the channel has one "
            "recognizable style.\n"
            "• <b>🎬 Scenarios</b> — the AI notices that posts DIFFER (news, reflection, ad, "
            "announcement…) and writes “if the post is like this — format it that way” rules "
            "plus a default style. Best when you sent many posts of DIFFERENT types.\n\n"
            "💡 <b>Tip.</b> 10+ posts of different types — pick <b>🎬 Scenarios</b>; "
            "a steady, uniform style — <b>🎭 Unified</b>.\n\n"
            "When ready, tap “⚡️ Generate”."
        ),
        "preset_analyzing": "🔮 Analyzing the post… this takes a few seconds.",
        "preset_analyzing_n": "🔮 Analyzing posts ({n})… this takes a few seconds.",
        "preset_suggested_title": (
            "🔮 <b>Suggested preset</b>\n\n{body}\n\n"
            "Apply it now, or save it to favorites and apply."
        ),
        "preset_suggest_apply_btn": "✅ Apply",
        "preset_suggest_save_btn": "💾 Save & apply",
        "preset_suggest_discard_btn": "❌ Discard",
        "preset_suggest_save_name": (
            "💾 Send a <b>name</b> for this preset — it will be saved to favorites and applied to the agent."
        ),
        "preset_suggest_discarded": "❌ Suggestion discarded.",
        "preset_suggest_fail": (
            "😕 Couldn't analyze the post: {error}\n\nTry again or create a preset manually."
        ),
        "preset_session_stale": "⚠️ Session expired (the bot restarted). Open “✏️ Prompt” → library and try again.",

        "channels_title": "<b>📣 Channels</b>",
        "channels_empty": "No channels. Tap ➕ to link one.",
        "channel_add": "➕ Link channel",
        "channel_add_howto": (
            "➕ <b>Link a channel</b>\n\n"
            "Forward any post from the target channel here.\n"
            "The bot must be an admin of that channel."
        ),
        "channel_added": "✅ Channel \"{title}\" linked.",
        "channel_not_forwarded": "❌ That's not a forwarded channel post. Try again.",
        "channel_removed": "✅ Channel unlinked.",
        "channel_confirm_remove": "Unlink channel \"{title}\"?",
        "channel_toggle_on": "▶️ Enable",
        "channel_toggle_off": "⏸ Disable",
        "channel_toggled": "✅ Channel status updated.",
        "channel_set_active": "⭐ Make active",
        "channel_active_set": "✅ Active channel updated.",
        "channel_remove": "⏹ Unlink",

        # --- agents (multi-agent home + wizard + card) ---
        "agents_title": (
            "<b>🤖 My agents</b>\n\n"
            "Each agent rewrites posts in its own channels using its own provider and prompt.\n"
            "Pick an agent or create a new one:"
        ),
        "agents_empty": (
            "<b>🤖 My agents</b>\n\n"
            "You don't have any agents yet. Create your first one — it will rewrite posts in the channels you link."
        ),
        "agent_create": "➕ Create agent",
        "agent_card": (
            "<b>🤖 {name}</b>\n\n"
            "Provider: <b>{provider}</b>\n"
            "Model: <code>{model}</code>\n"
            "Prompt: <blockquote>{prompt}</blockquote>\n"
            "Mode: {mode}\n"
            "Forwards: {forwarded}\n"
            "Channels: {channels}\n\n"
            "<blockquote>✏️ <b>Edit</b> — the bot edits the post in place. "
            "🔁 <b>Resend</b> — deletes the original and sends a new one, keeping media "
            "(photos/videos/files). Forwards can't be edited — they always use resend.</blockquote>"
        ),
        "agent_mode_edit": "✏️ Mode: edit",
        "agent_mode_resend": "🔁 Mode: resend",
        "agent_mode_edit_v": "✏️ edit in place",
        "agent_mode_resend_v": "🔁 resend (delete + send again)",
        "agent_fwd_on": "↪️ Forwards: ON",
        "agent_fwd_off": "↪️ Forwards: OFF",
        "agent_fwd_on_v": "reacts (via resend)",
        "agent_fwd_off_v": "skips",
        "agent_web_btn": "🌐 Web search",
        "agent_web_title": (
            "🌐 <b>Web search</b>\n\n"
            "State: <b>{state}</b>\n"
            "Sites per query: <b>{results}</b>\n"
            "Site snippet length: <b>{snippet}</b> chars\n"
            "Search rounds: <b>{rounds}</b>\n"
            "API key: <b>{key}</b>\n\n"
            "<blockquote>When the model lacks data for an accurate post (current "
            "service limits, news details, fact-checking), it searches the web via "
            "DuckDuckGo, sees source dates, and can expand the full version of a "
            "result. The API key is optional.</blockquote>"
        ),
        "agent_web_on": "🌐 Web search: ON",
        "agent_web_off": "🌐 Web search: OFF",
        "agent_web_state_on": "on",
        "agent_web_state_off": "off",
        "agent_web_results": "🔎 Sites per query: {n}",
        "agent_web_snippet": "📄 Snippet length: {n}",
        "agent_web_rounds": "🔁 Search rounds: {n}",
        "agent_web_key": "🔑 API key (opt.)",
        "agent_web_key_set": "🔑 API key: set ✅",
        "agent_web_key_none": "none (DuckDuckGo, free)",
        "agent_web_key_yes": "set",
        "agent_web_key_ask": (
            "🔑 Send a search-service API key (Brave/Serper/Tavily) in one message.\n\n"
            "<blockquote>This is <b>optional</b>: without a key, search works via "
            "DuckDuckGo for free. Send «-» to clear the key.</blockquote>"
        ),
        "agent_web_key_saved": "✅ Done.",
        "agent_edit_name": "✏️ Name",
        "agent_edit_provider": "🤖 Provider",
        "agent_edit_key": "🔑 Key",
        "agent_edit_model": "📚 Model",
        "agent_edit_prompt": "✏️ Prompt",
        "agent_channels": "📣 Channels",
        "agent_delete": "🗑 Delete agent",
        "agent_add_channel": "➕ Link channel",
        "agent_ask_name": "✏️ <b>New agent</b>\n\nWhat should we call this agent? Send a name:",
        "agent_ask_provider": "🤖 Choose a provider for the agent:",
        "agent_next": "Done",
        "agent_sys_title": (
            "🎨 <b>System prompt</b>\n\n"
            "Adds built-in formatting rules on top of your prompt. Enable it?"
        ),
        "agent_bind_howto": (
            "➕ <b>Link a channel to the agent</b>\n\n"
            "For the agent to rewrite posts, link it to a channel:\n\n"
            "<b>1.</b> Add the bot to the channel as an <b>administrator</b> "
            "(the <i>“Post messages”</i> right is required).\n"
            "<b>2.</b> Forward <b>any post</b> from that channel here.\n\n"
            "<blockquote>The bot detects the channel from the forwarded post "
            "automatically — no need to type an ID.</blockquote>\n\n"
            "<i>You can tap “Skip” and link one later from the agent's card.</i>"
        ),
        "agent_bind_skip": "⏭ Skip",
        "agent_skip_setup": "⏭ Skip setup",
        "agent_ready": "✅ Agent ready! Channel \"{title}\" linked.",
        "agent_ready_nochan": "✅ Agent ready! You can link a channel later from its card.",
        "agent_gone": "⚠️ This agent was already deleted — there's nothing to link the channel to. Open the menu and pick an agent again.",
        "agent_addchan_howto": (
            "➕ <b>Link a channel to the agent</b>\n\n"
            "<b>1.</b> Add the bot to the channel as an <b>administrator</b> "
            "(the <i>“Post messages”</i> right).\n"
            "<b>2.</b> Forward <b>any post</b> from that channel here.\n\n"
            "<blockquote>The channel is detected from the forwarded post — "
            "no manual ID needed.</blockquote>"
        ),
        "agent_chan_added": "✅ Channel \"{title}\" linked.",
        "agent_channels_title": "<b>📣 Agent channels</b>\n\nTap ⏹ to unlink a channel.",
        "agent_channels_empty": "<b>📣 Agent channels</b>\n\nNo channels yet. Tap ➕ to link one.",
        "agent_confirm_delete": "Delete agent \"{name}\"? Its channels will stop being processed.",
        "model_search": "🔎 Search",
        "model_search_prompt": "🔎 Type part of a model name:",
        "model_search_none": "❌ Nothing found. Showing the full list.",

        "stats_title": "<b>📊 Statistics</b>",
        "stats_body": (
            "Processed: <b>{processed}</b>\n"
            "Errors: <b>{failed}</b>\n"
            "Avg time: <b>{avg_ms} ms</b>\n"
            "Last activity: {last}"
        ),
        "stats_none": "No data yet.",
        "stats_caption": (
            "<b>📊 Your statistics</b>\n\n"
            "Processed: <b>{processed}</b> · Errors: <b>{failed}</b>\n"
            "Success rate: <b>{rate}%</b>\n"
            "Speed: avg <b>{avg} ms</b> · median <b>{median} ms</b>\n"
            "24h: <b>{c24}</b> · 7d: <b>{c7}</b> · 30d: <b>{c30}</b>\n"
            "Channels: <b>{channels}</b> · Agents: <b>{agents}</b>\n"
            "First activity: {first}\n"
            "Last activity: {last}"
        ),
        "stats_chart_title": "Posts statistics",
        "stats_legend_proc": "Processed",
        "stats_legend_fail": "Errors",
        "chart_sub_days": "last {n} days",
        "period_1d": "1d",
        "period_7d": "7d",
        "period_30d": "30d",

        "preview_caption": (
            "<b>👁 Preview</b>\n\n"
            "Channel: {chan}\n\n"
            "<blockquote>{text}</blockquote>\n\n"
            "Publish?"
        ),
        "preview_publish": "✅ Publish",
        "preview_reject": "❌ Reject",
        "preview_edit": "✏️ Edit",
        "preview_published": "✅ Published.",
        "preview_rejected": "❌ Rejected.",
        "preview_edit_prompt": (
            "✏️ <b>Edit</b>\n\n"
            "The current version is below — tap it to copy, edit it and send the new text back. "
            "You can use HTML tags (&lt;b&gt;, &lt;i&gt;, etc.).\n\n"
            "<code>{text}</code>"
        ),

        "admin_title": "<b>🛠 Admin panel</b>",
        "admin_users": "👥 Users",
        "admin_stats": "📊 Global stats",
        "admin_broadcast": "📢 Broadcast",
        "admin_logs": "📜 Logs",
        "admin_banner": "🖼 Menu banner",
        "admin_desc": "📝 Bot description",
        "admin_support": "🆘 Support",
        "admin_menuchan": "📰 Menu channel",
        "admin_users_title": "<b>👥 Users</b> ({count})",
        "admin_user_search": "🔎 Search",
        "admin_user_search_prompt": "🔎 Enter a @username, name or user ID:",
        "admin_user_search_none": "❌ Nobody found for \"{q}\".",
        "admin_user_search_title": "<b>🔎 Results: \"{q}\"</b> ({count})",
        "admin_user_ban": "🚫 Ban",
        "admin_user_unban": "✅ Unban",
        "admin_user_banned": "🚫 User banned.",
        "admin_user_unbanned": "✅ User unbanned.",
        "admin_user_none": "User not found.",
        "admin_user_status_banned": "🚫 banned",
        "admin_user_status_blocked": "⛔ blocked the bot",
        "admin_user_status_deleted": "👻 removed / unreachable",
        "admin_user_status_ok": "🟢 active",
        "admin_user_card": (
            "<b>👤 {name}</b>\n"
            "ID: <code>{id}</code> · {status}\n\n"
            "Processed: <b>{processed}</b> · Errors: <b>{failed}</b>\n"
            "Success rate: <b>{rate}%</b>\n"
            "Speed: avg <b>{avg}</b> · med <b>{median}</b> · max <b>{max}</b> ms\n"
            "24h: <b>{c24}</b> · 7d: <b>{c7}</b> · 30d: <b>{c30}</b>\n"
            "Channels: <b>{channels}</b> · Agents: <b>{agents}</b>\n"
            "Provider: {provider} · Lang: {ulang}\n"
            "Registered: {created}\n"
            "Last activity: {last}"
        ),
        "admin_user_channels": "\n\n<b>📎 Bound channels:</b>\n{list}",
        "admin_user_channels_more": "\n…and {n} more",
        "admin_user_channels_none": "\n\n<i>📎 No bound channels</i>",
        "admin_user_channels_link": "🔗 link",
        "admin_gstats": (
            "<b>📊 Global statistics</b>\n\n"
            "Users: <b>{users}</b>\n"
            "Active: <b>{active}</b>\n"
            "⛔ Blocked: <b>{blocked}</b> · 👻 Removed: <b>{deleted}</b>\n"
            "🚫 Banned: <b>{banned}</b>\n"
            "Posts processed: <b>{processed}</b>\n"
            "Errors: <b>{failed}</b>"
        ),
        "admin_gstats_chart_title": "Users",
        "admin_gstats_legend_join": "Joined",
        "admin_gstats_legend_left": "Left",
        "admin_support_title": (
            "<b>🆘 Support contact</b>\n\n"
            "Current: {handle}\n"
            "ID: <code>{id}</code>\n\n"
            "Shown in the Help section."
        ),
        "admin_support_set": "✏️ Change ID",
        "admin_support_prompt": "✏️ Send the numeric Telegram ID of the new support contact:",
        "admin_support_bad": "❌ That doesn't look like an ID. Send a number (e.g. 8149203573).",
        "admin_support_saved": "✅ Support contact updated: {handle}",
        "admin_menuchan_title": (
            "<b>📰 Bot channel in the menu</b>\n\n"
            "Status: {status}\n"
            "Link: {link}\n\n"
            "When enabled, the main menu shows a line linking to the channel."
        ),
        "admin_menuchan_on": "enabled ✅",
        "admin_menuchan_off": "disabled ⛔",
        "admin_menuchan_none": "not set",
        "admin_menuchan_setup": "🔗 Set channel",
        "admin_menuchan_toggle_on": "✅ Enable line",
        "admin_menuchan_toggle_off": "⛔ Disable line",
        "admin_menuchan_clear": "🗑 Reset",
        "admin_menuchan_ask_id": (
            "🔗 <b>Menu channel</b>\n\n"
            "Forward any post from the channel, or send a @username, t.me link or ID (-100…).\n"
            "For a public channel I'll build the link; for a private one I'll ask for the invite link."
        ),
        "admin_menuchan_ask_link": (
            "🔒 The channel has no public @username.\n"
            "Send the invite link manually (https://t.me/+…):"
        ),
        "admin_menuchan_bad_id": (
            "❌ Couldn't recognize the channel. Send a @username, link or ID, or forward a post."
        ),
        "admin_menuchan_bad_link": "❌ That doesn't look like a link. Send a URL like https://t.me/…",
        "admin_menuchan_saved": "✅ Channel saved, the menu line is enabled.",
        "admin_menuchan_cleared": "✅ Channel setting reset.",
        "admin_menuchan_toggled_on": "✅ Channel line enabled.",
        "admin_menuchan_toggled_off": "⛔ Channel line disabled.",
        "menu_channel_line": (
            "📰 <a href=\"{link}\">Bot's Telegram channel</a> — updates, reviews & giveaways"
        ),
        "admin_broadcast_prompt": "📢 Send the broadcast text:",
        "admin_broadcast_sent": "✅ Broadcast sent: {ok}/{total}",
        "admin_logs_title": "<b>📜 Recent requests</b>",
        "admin_logs_empty": "No logs.",
        "admin_banner_title": (
            "<b>🖼 Menu banner</b>\n\nCurrent: {current}\n\n"
            "The banner is shown above the main menu buttons."
        ),
        "admin_banner_photo": "📷 Set photo",
        "admin_banner_video": "🎬 Set video",
        "admin_banner_remove": "🗑 Remove banner",
        "admin_banner_send_photo": "📷 Send a photo for the banner:",
        "admin_banner_send_video": "🎬 Send a video for the banner:",
        "admin_banner_saved": "✅ Banner updated.",
        "admin_banner_removed": "✅ Banner removed.",
        "admin_banner_wrong": "❌ Expected {kind}. Try again.",
        "admin_desc_title": (
            "<b>📝 Bot description</b>\n\n"
            "Long (\"What can this bot do?\"):\n<blockquote>{long}</blockquote>\n\n"
            "Short (profile):\n<blockquote>{short}</blockquote>"
        ),
        "admin_desc_edit_long": "✏️ Long description",
        "admin_desc_edit_short": "✏️ Short description",
        "admin_desc_enter_long": "✏️ Send the long description (max 512 chars):",
        "admin_desc_enter_short": "✏️ Send the short description (max 120 chars):",
        "admin_desc_saved": "✅ Description updated.",

        "bot_desc_long": (
            "I rewrite posts in your Telegram channels with AI. "
            "I support multiple providers, preview before publishing, and "
            "flexible prompts. Tap \"Start\" to set up."
        ),
        "bot_desc_short": "AI rewrites posts in your channels.",
    },
}


def t(lang: str, key: str, **fmt) -> str:
    """Return localized string for key; fall back ru → key. Format with **fmt."""
    lang = lang if lang in TEXTS else DEFAULT_LANG
    s = TEXTS.get(lang, {}).get(key)
    if s is None:
        s = TEXTS.get("ru", {}).get(key, key)
    if fmt:
        try:
            return s.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return s
    return s
