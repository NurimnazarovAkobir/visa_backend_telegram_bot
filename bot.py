import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import (
    answer_support_request,
    attach_payment_receipt,
    create_lead,
    create_support_request,
    ensure_user,
    get_referral_count,
    get_support_request,
    get_user,
    get_user_by_referral_code,
    init_db,
    set_support_admin_message,
    update_payment_method,
)


logging.basicConfig(level=logging.INFO)


user_sessions: dict[int, dict[str, Any]] = {}

TEXTS = {
    "uz": {
        "language_screen": (
            "🌐 <b>Выберите язык</b>\n\n"
            "Бот будет работать на выбранном вами языке на всех следующих этапах."
        ),
        "intro": (
            "🇬🇧 <b>UK Seasonal Work</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "🤖 <b>Бу TelegramBot нима қилади?</b>\n"
            "Бот 🇰🇬 KG 🇺🇿 UZB 🇹🇯 TJK фуқароларига 🇬🇧 Буюк Британиядаги мавсумий ишлар учун рўйхатдан ўтишни осонлаштиради:\n"
            "маълумотларни тўлдиради ва интервью босқичигача етказади.\n\n"
            "🎯 <b>Нима учун яратилган?</b>\n"
            "❌ Ўзи рўйхатдан ўта олмаганлар\n"
            "❌ Қабулга улгурмаганлар\n"
            "❌ Жараённи тушунмаганлар учун\n\n"
            "🤝 <b>Бот биздаги ёпиқ алоқа каналлари орқали номзодга имкониятларни очиб беради.</b>\n\n"
            "👥 <b>Кимлар учун?</b>\n"
            "— Англияга ишлашга боришни истаганлар\n"
            "— Уринишлардан чарчаганлар\n"
            "— Натижага тайёрлар\n\n"
            "💥 <b>Асосий ғоя:</b>\n"
            "90% одамлар рўйхатдан ўта олмаётган пайтда —\n"
            "сиз @seasonalworkUK_bot орқали осон йўл билан имконият оласиз."
        ),
        "intro_button": "📘 Танишиш",
        "terms": (
            "📜 <b>Фойдаланиш шартлари / Согласие с условиями</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "«Розиман» тугмасини босиш орқали сиз қуйидагиларни тасдиқлайсиз:\n"
            "— ишончли шахсий маълумотларни тақдим этасиз\n"
            "— бот ариза топшириш жараёнида ёпиқ каналлар орқали ёрдам кўрсатишини тушунасиз\n"
            "— ўзаро алоқа конфиденциал форматда амалга оширилишини англайсиз\n"
            "— рус тилининг базавий билимларига эгасиз\n"
            "— интервью санаси ва кейинги босқичлар визавий операторлар томонидан белгиланишини тушунасиз\n"
            "— бот хизматларидан ихтиёрий равишда фойдаланасиз ва барча шартларни қабул қиласиз\n"
            "— ушбу бот орқали координаторлар жамоаси билан тўғридан-тўғри алоқа амалга оширилишини тушунасиз\n"
            "— бот орқали рўйхатдан ўтиш ‼️ПУЛЛИК\n\n"
            "⚠️ <b>Муҳим:</b>\n"
            "Бот давлат органи эмас.\n"
            "Ботдан фойдаланиш жараёнида олинган барча маълумотлар конфиденциал сақланиши керак.\n"
            "Конфиденциалликни бузиш сизнинг аризангизни кейинги кўриб чиқишга таъсир қилиши мумкин.\n\n"
            "✅ Тугмани босиш орқали сиз шартларга розилик билдириб, жараённи давом эттирасиз"
        ),
        "agree": "✅ Розиман",
        "back": "⬅️ Орқага",
        "change_language": "🌐 Тилни алмаштириш",
        "go_payment": "💳 Тўловга ўтиш",
        "payment_title": (
            "💳 <b>Тўлов усулини танланг</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "Қуйидаги тўлов тизимларидан бирини танланг."
        ),
        "payment_selected": "Тўлов усули танланди.",
        "payment_saved_note": "Карта реквизитлари чиқарилди. Энди квитанцияни юкланг.",
        "payment_details": (
            "💳 <b>{payment_method}</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "Барча тўлов тизимлари учун бир хил карта ишлатилади:\n\n"
            "💳 <b>Карта рақами:</b>\n<code>4073420063643757</code>\n\n"
            "👤 <b>Эгаси:</b>\nHasanov B"
        ),
        "upload_receipt_button": "📎 Квитанцияни юклаш",
        "payment_receipt_prompt": "📎 Шу ерда квитанцияни юкланг.",
        "payment_receipt_uploaded": "Тўловингиз текшириш учун админга юборилди. Жавобини кутинг.",
        "payment_receipt_invalid": "Квитанцияни расм ёки файл кўринишида юборинг.",
        "payment_receipt_pending": "Аввал тўлов усулини танланг, кейин квитанцияни юкланг.",
        "prompt_nationality": (
            "🪪 <b>1/8 Фуқаролигингизни танланг</b>\n\n"
            "Қуйидаги давлатлардан бирини танланг:"
        ),
        "prompt_full_name": (
            "👤 <b>2/8 Исм-фамилия</b>\n\n"
            "Исм ва фамилиянгизни passport'дагидек киритинг.\n\n"
            "<i>Масалан: ABDULLAYEV AZIZBEK</i>"
        ),
        "prompt_birth_date": (
            "🎂 <b>3/8 Туғилган сана</b>\n\n"
            "Туғилган санангизни <b>КУН.ОЙ.ЙИЛ</b> форматида киритинг.\n\n"
            "<i>Масалан: 07.11.1998</i>"
        ),
        "prompt_russian_level": (
            "🗣 <b>4/8 Рус тили даражаси</b>\n\n"
            "Рус тили даражангизни 0 дан 5 гача баҳоланг:"
        ),
        "prompt_experience": (
            "🌾 <b>5/8 Тажриба</b>\n\n"
            "Қишлоқ хўжалигида тажрибангиз борми?"
        ),
        "yes": "✅ Ҳа",
        "no": "❌ Йўқ",
        "prompt_phone_primary": (
            "📱 <b>6/8 Асосий телефон рақам</b>\n\n"
            "Асосий телефон рақамингизни киритинг.\n\n"
            "<i>Масалан: +998901234567</i>"
        ),
        "prompt_phone_secondary": (
            "☎️ <b>6/8 Қўшимча телефон рақам</b>\n\n"
            "Иккинчи телефон рақамингизни киритинг ёки ўтказиб юборинг."
        ),
        "skip": "⏭ Ўтказиб юбориш",
        "prompt_email": (
            "✉️ <b>7/8 Email address</b>\n\n"
            "Фаол электрон почта манзилингизни киритинг."
        ),
        "prompt_passport": (
            "🛂 <b>8/8 Хорижга чиқиш паспорти</b>\n\n"
            "Паспорт суратини ёки скан нусхасини юборинг.\n\n"
            "Талаблар:\n"
            "• JPG yoki PNG format\n"
            "• аниқ ва ўқиладиган сифат\n"
            "• барча муҳим маълумотлар кўриниб туриши керак"
        ),
        "summary": (
            "💳 <b>Тўловлар босқичи</b>\n\n"
            "💵 <b>$169</b>\n"
            "💰 <code>2.066.000 сўм</code>\n\n"
            "🛡 Тўлов номзод файлини давом эттириш учун кафолат бўлади.\n\n"
            "📎 Тўловни амалга ошириб, чек расмини юборинг."
        ),
        "invalid_full_name": "Исм-фамилия камида исм ва фамилиядан иборат бўлиши керак.",
        "invalid_birth_date": "Сана формати нотўғри. Илтимос, КУН.ОЙ.ЙИЛ форматида юборинг.",
        "invalid_phone": "Телефон рақами нотўғри. Илтимос, <code>+998901234567</code> каби форматда қайтадан юборинг.",
        "invalid_email": "Email манзил нотўғри. Илтимос, тўғри email манзилни қайтадан юборинг.",
        "invalid_passport": "Фақат JPG ёки PNG форматдаги расм юборинг.",
        "saved": "Қабул қилинди.",
        "select_value": "Қуйидагилардан бирини танланг.",
        "language_changed": "Тил ўзгартирилди.",
        "help_button": "💬 Ёрдам",
        "cabinet_button": "👤 Кабинет",
        "help_prompt": "Шу ерда саволингизни қолдиринг.",
        "help_sent": "Саволингиз админга юборилди.",
        "help_admin_header": "Янги ёрдам сўрови",
        "help_admin_reply": "Жавоб ёзиш",
        "help_admin_prompt": "Жавобингизни шу ерга ёзинг. У фақат шу фойдаланувчига юборилади.",
        "help_admin_sent": "Жавоб фойдаланувчига юборилди.",
        "help_answer_prefix": "Админ жавоби:",
        "help_admin_missing": "Админ chat ID созланмаган. .env га ADMIN_TELEGRAM_ID қўшинг.",
        "cabinet_title": (
            "<b>Кабинет</b>\n\n"
            "Реферал ҳаволангиз:\n{referral_link}\n\n"
            "Таклиф қилган фойдаланувчилар: {referral_count}"
        ),
        "referral_applied": "Реферал боғланди.",
    },
    "ru": {
        "language_screen": (
            "🌐 <b>Выберите язык</b>\n\n"
            "Бот будет работать на выбранном вами языке на всех следующих этапах."
        ),
        "intro": (
            "🇬🇧 <b>UK Seasonal Work</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "🤖 <b>Что делает бот?</b>\n"
            "Бот берет на себя весь сложный процесс регистрации на сезонные работы в Англии:\n"
            "заполняет данные, помогает пройти отбор и доводит кандидата до этапа приглашения на интервью.\n\n"
            "🎯 <b>Для чего создан бот?</b>\n"
            "Чтобы дать реальный шанс попасть на сезонную работу тем, кто:\n"
            "❌ не смог зарегистрироваться сам\n"
            "❌ не успел попасть в набор\n"
            "❌ не понимает процесс подачи\n\n"
            "Бот решает эту проблему и открывает доступ к возможностям, которые недоступны большинству.\n\n"
            "👥 <b>Кому полезен этот бот?</b>\n"
            "— Тем, кто реально хочет уехать на работу в Англию 🇬🇧\n"
            "— Тем, кто устал пытаться зарегистрироваться и получать ошибки\n"
            "— Тем, кто готов действовать и получить результат\n\n"
            "💥 <b>Главная идея:</b>\n"
            "Пока 90% людей не могут даже зарегистрироваться —\n"
            "ты просто заходишь в бот и получаешь шанс пройти дальше."
        ),
        "intro_button": "📘 Ознакомиться",
        "terms": (
            "📜 <b>Согласие с условиями / Фойдаланиш шартлари</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "Нажимая «Согласен», вы подтверждаете, что:\n"
            "— предоставляете достоверные личные данные\n"
            "— понимаете, что бот оказывает помощь в процессе подачи заявки через закрытые каналы\n"
            "— осознаёте, что взаимодействие осуществляется в конфиденциальном формате\n"
            "— обладаете базовыми знаниями русского языка\n"
            "— даты интервью и дальнейшие этапы определяются визовыми операторами\n"
            "— добровольно пользуетесь услугами бота и принимаете все условия\n"
            "— через данный бот осуществляется связь напрямую с командой координаторов\n"
            "— регистрация через бот ‼️ПЛАТНАЯ\n\n"
            "⚠️ <b>Важно:</b>\n"
            "Бот не является государственным органом.\n"
            "Вся информация, полученная в процессе использования бота, должна оставаться конфиденциальной.\n"
            "Нарушение конфиденциальности может повлиять на дальнейшее рассмотрение вашей заявки.\n\n"
            "✅ Нажимая кнопку, вы соглашаетесь с условиями и продолжаете процесс"
        ),
        "agree": "✅ Согласен",
        "back": "⬅️ Назад",
        "change_language": "🌐 Сменить язык",
        "go_payment": "💳 Перейти к оплате",
        "payment_title": (
            "💳 <b>Выберите способ оплаты</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "Выберите одну из платежных систем ниже."
        ),
        "payment_selected": "Способ оплаты выбран.",
        "payment_saved_note": "Реквизиты карты показаны. Теперь загрузите квитанцию.",
        "payment_details": (
            "💳 <b>{payment_method}</b>\n"
            "━━━━━━━━━━━━━━\n\n"
            "Для всех платежных систем используются одинаковые реквизиты:\n\n"
            "💳 <b>Номер карты:</b>\n<code>4073420063643757</code>\n\n"
            "👤 <b>Владелец:</b>\nHasanov B"
        ),
        "upload_receipt_button": "📎 Загрузить квитанцию",
        "payment_receipt_prompt": "📎 Загрузите квитанцию сюда.",
        "payment_receipt_uploaded": "Ваш платеж отправлен администратору на проверку. Ожидайте ответа.",
        "payment_receipt_invalid": "Отправьте квитанцию в виде изображения или файла.",
        "payment_receipt_pending": "Сначала выберите способ оплаты, затем загрузите квитанцию.",
        "prompt_nationality": (
            "🪪 <b>1/8 Гражданство</b>\n\n"
            "Выберите одну из стран ниже:"
        ),
        "prompt_full_name": (
            "👤 <b>2/8 Имя и фамилия</b>\n\n"
            "Введите имя и фамилию точно как в загранпаспорте.\n\n"
            "<i>Например: ABDULLAYEV AZIZBEK</i>"
        ),
        "prompt_birth_date": (
            "🎂 <b>3/8 Дата рождения</b>\n\n"
            "Введите дату рождения в формате <b>ДД.ММ.ГГГГ</b>.\n\n"
            "<i>Например: 07.11.1998</i>"
        ),
        "prompt_russian_level": (
            "🗣 <b>4/8 Уровень русского языка</b>\n\n"
            "Оцените свой уровень русского языка от 0 до 5:"
        ),
        "prompt_experience": (
            "🌾 <b>5/8 Опыт</b>\n\n"
            "Есть ли у вас опыт работы в сельском хозяйстве?"
        ),
        "yes": "✅ Да",
        "no": "❌ Нет",
        "prompt_phone_primary": (
            "📱 <b>6/8 Основной номер телефона</b>\n\n"
            "Введите ваш основной номер телефона.\n\n"
            "<i>Например: +998901234567</i>"
        ),
        "prompt_phone_secondary": (
            "☎️ <b>6/8 Дополнительный номер</b>\n\n"
            "Введите второй номер телефона."
        ),
        "skip": "⏭ Пропустить",
        "prompt_email": (
            "✉️ <b>7/8 Email address</b>\n\n"
            "Введите ваш активный адрес электронной почты."
        ),
        "prompt_passport": (
            "🛂 <b>8/8 Загранпаспорт</b>\n\n"
            "Загрузите фото или скан загранпаспорта.\n\n"
            "Требования:\n"
            "• формат JPG или PNG\n"
            "• четкое и читаемое качество\n"
            "• все важные данные должны быть видны"
        ),
        "summary": (
            "💳 <b>Этап оплаты</b>\n\n"
            "💵 <b>$169</b>\n"
            "💰 <code>2.066.000 сум</code>\n\n"
            "🛡 Этот платеж служит гарантией продолжения работы по анкете кандидата.\n\n"
            "📎 После оплаты отправьте фото или скриншот чека."
        ),
        "invalid_full_name": "Имя и фамилия должны содержать как минимум два слова.",
        "invalid_birth_date": "Неверный формат даты. Пожалуйста, используйте ДД.ММ.ГГГГ.",
        "invalid_phone": "Неверный номер телефона. Отправьте заново в формате <code>+998901234567</code>.",
        "invalid_email": "Неверный email. Пожалуйста, отправьте корректный адрес заново.",
        "invalid_passport": "Отправьте изображение только в формате JPG или PNG.",
        "saved": "Принято.",
        "select_value": "Выберите один из вариантов ниже.",
        "language_changed": "Язык изменен.",
        "help_button": "💬 Помощь",
        "cabinet_button": "👤 Кабинет",
        "help_prompt": "Оставьте здесь ваш вопрос.",
        "help_sent": "Ваш вопрос отправлен администратору.",
        "help_admin_header": "Новый запрос в поддержку",
        "help_admin_reply": "Ответить",
        "help_admin_prompt": "Напишите ответ сюда. Он уйдет только этому пользователю.",
        "help_admin_sent": "Ответ отправлен пользователю.",
        "help_answer_prefix": "Ответ администратора:",
        "help_admin_missing": "Не настроен ADMIN_TELEGRAM_ID. Добавьте его в .env.",
        "cabinet_title": (
            "<b>Кабинет</b>\n\n"
            "Ваша referral ссылка:\n{referral_link}\n\n"
            "Приглашено пользователей: {referral_count}"
        ),
        "referral_applied": "Referral привязан.",
    },
}

NATIONALITIES = {
    "UZ": "🇺🇿 UZB",
    "KG": "🇰🇬 KG",
    "TJ": "🇹🇯 TJ",
}

FORM_STEPS = [
    "nationality",
    "full_name",
    "birth_date",
    "russian_level",
    "experience",
    "phone_primary",
    "phone_secondary",
    "email",
    "passport",
]

PAYMENT_METHODS = {
    "payme": "💠 Payme",
    "click": "🔷 Click",
    "uzum": "🟣 Uzum Bank",
    "paynet": "🟨 Paynet",
    "humo_uzcard": "💳 Humo / Uzcard",
    "visa_mastercard": "🌐 Visa / Mastercard",
}


def get_bot_token() -> str:
    env_path = Path(".env")
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            os.environ.setdefault(key.strip(), value.strip())

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")
    return token


def get_session(user_id: int) -> dict[str, Any]:
    return user_sessions.setdefault(
        user_id,
        {
            "language": None,
            "screen": "language",
            "step": None,
            "data": {},
            "bot_message_id": None,
            "lead_id": None,
            "telegram_user_id": user_id,
            "payment_method": None,
            "awaiting_support": False,
            "admin_reply_user_id": None,
            "admin_reply_request_id": None,
        },
    )


def reset_form(session: dict[str, Any]) -> None:
    session["step"] = None
    session["data"] = {}
    session["lead_id"] = None
    session["payment_method"] = None


def clear_support_flags(session: dict[str, Any]) -> None:
    session["awaiting_support"] = False
    session["admin_reply_user_id"] = None
    session["admin_reply_request_id"] = None


def text(session: dict[str, Any], key: str) -> str:
    language = session.get("language") or "uz"
    return TEXTS[language][key]


def get_admin_telegram_id() -> int | None:
    raw_value = os.getenv("ADMIN_TELEGRAM_ID")
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        logging.warning("ADMIN_TELEGRAM_ID is invalid.")
        return None


def parse_start_payload(message: Message) -> str | None:
    if not message.text:
        return None
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()

def build_inline_main_actions(session: dict[str, Any]) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(text=text(session, "help_button"), callback_data="nav:help"),
            InlineKeyboardButton(text=text(session, "cabinet_button"), callback_data="nav:cabinet"),
        ]
    ]


def with_inline_main_actions(
    session: dict[str, Any],
    rows: list[list[InlineKeyboardButton]],
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[*rows, *build_inline_main_actions(session)])


def build_support_admin_keyboard(language: str, request_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=TEXTS[language]["help_admin_reply"],
                    callback_data=f"support_reply:{request_id}:{user_id}",
                )
            ]
        ]
    )


def build_referral_link(bot_username: str, referral_code: str) -> str:
    return f"https://t.me/{bot_username}?start=ref_{referral_code}"


def is_admin_user(user_id: int) -> bool:
    admin_id = get_admin_telegram_id()
    return admin_id is not None and user_id == admin_id


def extract_referral_code(payload: str | None) -> str | None:
    if not payload or not payload.startswith("ref_"):
        return None
    return payload[4:].strip().upper()


def user_identity_payload(message: Message, session: dict[str, Any], referrer_user_id: int | None = None) -> dict[str, Any]:
    return {
        "telegram_user_id": message.from_user.id,
        "telegram_chat_id": message.chat.id,
        "language": session.get("language"),
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "referrer_user_id": referrer_user_id,
    }


def build_language_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    if session.get("language") == "ru":
        first = InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")
        second = InlineKeyboardButton(text="🇺🇿 Ўзбекча", callback_data="lang:uz")
    else:
        first = InlineKeyboardButton(text="🇺🇿 Ўзбекча", callback_data="lang:uz")
        second = InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")

    return InlineKeyboardMarkup(inline_keyboard=[[first, second]])


def build_intro_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(session, "intro_button"), callback_data="nav:terms")],
            [InlineKeyboardButton(text=text(session, "change_language"), callback_data="nav:language")],
        ]
    )


def build_terms_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(session, "agree"), callback_data="form:start")],
            [InlineKeyboardButton(text=text(session, "back"), callback_data="nav:intro")],
        ]
    )


def build_step_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup | None:
    step = session.get("step")
    if step == "nationality":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=NATIONALITIES["KG"], callback_data="set:nationality:KG")],
                [InlineKeyboardButton(text=NATIONALITIES["UZ"], callback_data="set:nationality:UZ")],
                [InlineKeyboardButton(text=NATIONALITIES["TJ"], callback_data="set:nationality:TJ")],
                [InlineKeyboardButton(text=text(session, "back"), callback_data="back:terms")],
            ],
        )
    if step == "russian_level":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=str(value), callback_data=f"set:russian_level:{value}") for value in range(0, 3)],
                [InlineKeyboardButton(text=str(value), callback_data=f"set:russian_level:{value}") for value in range(3, 6)],
                [InlineKeyboardButton(text=text(session, "back"), callback_data="back:step")],
            ],
        )
    if step == "experience":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=text(session, "yes"), callback_data="set:experience:yes"),
                    InlineKeyboardButton(text=text(session, "no"), callback_data="set:experience:no"),
                ],
                [InlineKeyboardButton(text=text(session, "back"), callback_data="back:step")],
            ],
        )
    if step == "phone_secondary":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=text(session, "skip"), callback_data="set:phone_secondary:skip")],
                [InlineKeyboardButton(text=text(session, "back"), callback_data="back:step")],
            ],
        )
    if step in {"full_name", "birth_date", "phone_primary", "email", "passport"}:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=text(session, "back"), callback_data="back:step")]],
        )
    return None


def build_summary_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text(session, "go_payment"), callback_data="nav:payment")],
            [InlineKeyboardButton(text=text(session, "back"), callback_data="nav:intro")],
        ]
    )


def build_payment_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return with_inline_main_actions(
        session,
        [
            [
                InlineKeyboardButton(text=PAYMENT_METHODS["payme"], callback_data="payment:payme"),
                InlineKeyboardButton(text=PAYMENT_METHODS["click"], callback_data="payment:click"),
            ],
            [
                InlineKeyboardButton(text=PAYMENT_METHODS["uzum"], callback_data="payment:uzum"),
                InlineKeyboardButton(text=PAYMENT_METHODS["paynet"], callback_data="payment:paynet"),
            ],
            [
                InlineKeyboardButton(text=PAYMENT_METHODS["humo_uzcard"], callback_data="payment:humo_uzcard"),
                InlineKeyboardButton(text=PAYMENT_METHODS["visa_mastercard"], callback_data="payment:visa_mastercard"),
            ],
            [InlineKeyboardButton(text=text(session, "back"), callback_data="nav:summary")],
        ],
    )


def build_payment_receipt_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return with_inline_main_actions(
        session,
        [
            [InlineKeyboardButton(text=text(session, "upload_receipt_button"), callback_data="nav:receipt_upload")],
            [InlineKeyboardButton(text=text(session, "back"), callback_data="nav:payment")],
        ],
    )


def build_payment_upload_keyboard(session: dict[str, Any]) -> InlineKeyboardMarkup:
    return with_inline_main_actions(
        session,
        [[InlineKeyboardButton(text=text(session, "back"), callback_data="nav:payment_receipt")]],
    )


def current_screen_content(session: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup | None]:
    screen = session["screen"]
    if screen == "language":
        return text(session, "language_screen"), build_language_keyboard(session)
    if screen == "intro":
        return text(session, "intro"), build_intro_keyboard(session)
    if screen == "terms":
        return text(session, "terms"), build_terms_keyboard(session)
    if screen == "form":
        prompt_key = {
            "nationality": "prompt_nationality",
            "full_name": "prompt_full_name",
            "birth_date": "prompt_birth_date",
            "russian_level": "prompt_russian_level",
            "experience": "prompt_experience",
            "phone_primary": "prompt_phone_primary",
            "phone_secondary": "prompt_phone_secondary",
            "email": "prompt_email",
            "passport": "prompt_passport",
        }[session["step"]]
        return text(session, prompt_key), build_step_keyboard(session)
    if screen == "payment":
        return text(session, "payment_title"), build_payment_keyboard(session)
    if screen == "payment_receipt":
        payment_method = PAYMENT_METHODS.get(session.get("payment_method"), "")
        return (
            text(session, "payment_details").format(payment_method=payment_method),
            build_payment_receipt_keyboard(session),
        )
    if screen == "payment_upload":
        return text(session, "payment_receipt_prompt"), build_payment_upload_keyboard(session)
    return text(session, "summary"), build_summary_keyboard(session)


async def delete_message_safe(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        return


async def answer_callback_safe(callback: CallbackQuery, text_value: str | None = None) -> None:
    try:
        await callback.answer(text_value)
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if "query is too old" in error_text or "query id is invalid" in error_text:
            return
        raise


async def render(session: dict[str, Any], chat_id: int, bot: Bot) -> None:
    content, keyboard = current_screen_content(session)
    message_id = session.get("bot_message_id")

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=content,
                reply_markup=keyboard,
            )
            return
        except Exception:
            session["bot_message_id"] = None

    sent = await bot.send_message(chat_id=chat_id, text=content, reply_markup=keyboard)
    session["bot_message_id"] = sent.message_id


def validate_full_name(value: str) -> bool:
    cleaned = " ".join(value.split())
    return len(cleaned.split()) >= 2


def validate_birth_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%d.%m.%Y")
        return True
    except ValueError:
        return False


def validate_phone(value: str) -> bool:
    normalized = re.sub(r"[\s\-()]", "", value.strip())
    return bool(re.fullmatch(r"\+?\d{9,15}", normalized))


def validate_email(value: str) -> bool:
    cleaned = value.strip()
    if ".." in cleaned:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", cleaned))


def normalize_phone(value: str) -> str:
    return re.sub(r"[\s\-()]", "", value.strip())


def normalize_email(value: str) -> str:
    return value.strip().lower()


def previous_state(session: dict[str, Any]) -> None:
    step = session.get("step")
    if session["screen"] == "terms":
        session["screen"] = "intro"
        return
    if session["screen"] != "form" or step is None:
        session["screen"] = "intro"
        return
    if step == "nationality":
        session["screen"] = "terms"
        session["step"] = None
        return
    index = FORM_STEPS.index(step)
    session["step"] = FORM_STEPS[index - 1]


async def start_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    session["telegram_user_id"] = message.from_user.id
    clear_support_flags(session)
    referral_code = extract_referral_code(parse_start_payload(message))
    referrer_user_id = None
    if referral_code:
        referrer = get_user_by_referral_code(referral_code)
        if referrer and referrer["telegram_user_id"] != message.from_user.id:
            referrer_user_id = int(referrer["telegram_user_id"])
    session["language"] = None
    session["screen"] = "language"
    reset_form(session)
    ensure_user(user_identity_payload(message, session, referrer_user_id))
    await render(session, message.chat.id, bot)
    await delete_message_safe(message)


async def language_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    session["telegram_user_id"] = callback.from_user.id
    session["language"] = callback.data.split(":")[1]
    session["screen"] = "intro"
    reset_form(session)
    user_row = get_user(callback.from_user.id)
    if user_row:
        ensure_user(
            {
                "telegram_user_id": callback.from_user.id,
                "telegram_chat_id": callback.message.chat.id,
                "language": session["language"],
                "username": callback.from_user.username,
                "first_name": callback.from_user.first_name,
                "last_name": callback.from_user.last_name,
                "referrer_user_id": user_row.get("referrer_user_id"),
            }
        )
    await answer_callback_safe(callback, text(session, "language_changed"))
    await render(session, callback.message.chat.id, bot)


async def navigation_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    target = callback.data.split(":")[1]
    if target == "language":
        session["screen"] = "language"
        session["step"] = None
    elif target == "intro":
        session["screen"] = "intro"
    elif target == "terms":
        session["screen"] = "terms"
    elif target == "payment":
        session["screen"] = "payment"
    elif target == "payment_receipt":
        session["screen"] = "payment_receipt"
    elif target == "receipt_upload":
        session["screen"] = "payment_upload"
    elif target == "summary":
        session["screen"] = "summary"
    elif target == "help":
        session["awaiting_support"] = True
        session["admin_reply_user_id"] = None
        session["admin_reply_request_id"] = None
        await answer_callback_safe(callback)
        await callback.message.answer(text(session, "help_prompt"))
        return
    elif target == "cabinet":
        await answer_callback_safe(callback)
        await send_cabinet_message(callback.message.chat.id, callback.from_user.id, bot, session)
        return
    await answer_callback_safe(callback)
    await render(session, callback.message.chat.id, bot)


async def form_start_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    session["screen"] = "form"
    session["step"] = "nationality"
    session["data"] = {}
    await answer_callback_safe(callback)
    await render(session, callback.message.chat.id, bot)


async def set_value_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    _, field, value = callback.data.split(":", maxsplit=2)

    if field == "nationality":
        session["data"]["nationality"] = value
        session["step"] = "full_name"
    elif field == "russian_level":
        session["data"]["russian_level"] = int(value)
        session["step"] = "experience"
    elif field == "experience":
        session["data"]["experience"] = value
        session["step"] = "phone_primary"
    elif field == "phone_secondary":
        session["data"]["phone_secondary"] = None if value == "skip" else value
        session["step"] = "email"

    await answer_callback_safe(callback, text(session, "saved"))
    await render(session, callback.message.chat.id, bot)


async def back_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    target = callback.data.split(":", maxsplit=1)[1]
    if target == "terms":
        session["screen"] = "terms"
        session["step"] = None
    else:
        previous_state(session)
    await answer_callback_safe(callback)
    await render(session, callback.message.chat.id, bot)


async def finalize_form(session: dict[str, Any], chat_id: int, bot: Bot) -> None:
    session["lead_id"] = create_lead(
        {
            "telegram_user_id": session["telegram_user_id"],
            "telegram_chat_id": chat_id,
            "language": session["language"],
            "nationality": session["data"]["nationality"],
            "full_name": session["data"]["full_name"],
            "birth_date": session["data"]["birth_date"],
            "russian_level": session["data"]["russian_level"],
            "agriculture_experience": session["data"]["experience"],
            "phone_primary": session["data"]["phone_primary"],
            "phone_secondary": session["data"].get("phone_secondary"),
            "email": session["data"]["email"],
            "passport_file_id": session["data"]["passport_file_id"],
            "passport_kind": session["data"]["passport_kind"],
        }
    )
    session["screen"] = "summary"
    session["step"] = None
    await render(session, chat_id, bot)


async def payment_handler(callback: CallbackQuery, bot: Bot) -> None:
    session = get_session(callback.from_user.id)
    method = callback.data.split(":", maxsplit=1)[1]
    if session.get("lead_id"):
        update_payment_method(session["lead_id"], method)
    session["payment_method"] = method
    session["screen"] = "payment_receipt"
    await answer_callback_safe(callback, text(session, "payment_selected"))
    await render(session, callback.message.chat.id, bot)


async def send_receipt_to_admin(
    bot: Bot,
    session: dict[str, Any],
    user_id: int,
    chat_id: int,
    receipt_file_id: str,
    receipt_kind: str,
) -> None:
    admin_chat_id = get_admin_telegram_id()
    if admin_chat_id is None:
        return

    payment_method = PAYMENT_METHODS.get(session.get("payment_method"), session.get("payment_method", ""))
    caption = (
        "💸 <b>Янги тўлов квитанцияси</b>\n\n"
        f"Lead ID: <code>{session.get('lead_id')}</code>\n"
        f"User ID: <code>{user_id}</code>\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Тўлов усули: <b>{payment_method}</b>\n"
        "Ҳолат: <b>pending</b>"
    )

    if receipt_kind == "photo":
        await bot.send_photo(chat_id=admin_chat_id, photo=receipt_file_id, caption=caption)
    else:
        await bot.send_document(chat_id=admin_chat_id, document=receipt_file_id, caption=caption)


async def send_cabinet_message(chat_id: int, user_id: int, bot: Bot, session: dict[str, Any]) -> None:
    user_stub = {
        "telegram_user_id": user_id,
        "telegram_chat_id": chat_id,
        "language": session.get("language"),
        "username": None,
        "first_name": None,
        "last_name": None,
        "referrer_user_id": None,
    }
    user_row = ensure_user(user_stub)
    me = await bot.get_me()
    referral_link = build_referral_link(me.username, user_row["referral_code"])
    referral_count = get_referral_count(user_id)
    await bot.send_message(
        chat_id=chat_id,
        text=text(session, "cabinet_title").format(
            referral_link=referral_link,
            referral_count=referral_count,
        ),
    )


async def cabinet_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    ensure_user(user_identity_payload(message, session))
    await send_cabinet_message(message.chat.id, message.from_user.id, bot, session)


async def help_button_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    session["awaiting_support"] = True
    session["admin_reply_user_id"] = None
    session["admin_reply_request_id"] = None
    await message.answer(text(session, "help_prompt"))


async def support_reply_callback_handler(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin_user(callback.from_user.id):
        await answer_callback_safe(callback)
        return

    _, request_id, user_id = callback.data.split(":")
    support_request = get_support_request(int(request_id))
    if not support_request:
        await answer_callback_safe(callback)
        return
    admin_session = get_session(callback.from_user.id)
    admin_session["admin_reply_request_id"] = int(request_id)
    admin_session["admin_reply_user_id"] = int(user_id)
    admin_session["awaiting_support"] = False
    await answer_callback_safe(callback)
    await callback.message.answer(text(admin_session, "help_admin_prompt"))


async def support_message_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)

    if is_admin_user(message.from_user.id) and session.get("admin_reply_user_id"):
        request_id = session["admin_reply_request_id"]
        user_id = session["admin_reply_user_id"]
        answer_text = (message.text or "").strip()
        if not answer_text:
            return

        target_session = get_session(user_id)
        answer_support_request(request_id, answer_text)
        await bot.send_message(
            chat_id=user_id,
            text=f"{text(target_session, 'help_answer_prefix')}\n{answer_text}",
        )
        clear_support_flags(session)
        await message.answer(text(session, "help_admin_sent"))
        return

    if not session.get("awaiting_support"):
        return

    question_text = (message.text or "").strip()
    if not question_text:
        return

    session["awaiting_support"] = False
    request_id = create_support_request(message.from_user.id, question_text)
    admin_chat_id = get_admin_telegram_id()
    if admin_chat_id is None:
        await message.answer(text(session, "help_admin_missing"))
        return

    admin_text = (
        f"<b>{text(session, 'help_admin_header')}</b>\n\n"
        f"User ID: <code>{message.from_user.id}</code>\n"
        f"Username: @{message.from_user.username or '-'}\n"
        f"Name: {message.from_user.full_name}\n\n"
        f"Question:\n{question_text}"
    )
    admin_message = await bot.send_message(
        chat_id=admin_chat_id,
        text=admin_text,
        reply_markup=build_support_admin_keyboard(session.get("language") or "uz", request_id, message.from_user.id),
    )
    set_support_admin_message(request_id, admin_message.message_id)
    await message.answer(text(session, "help_sent"))


async def process_form_message(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    if session.get("screen") != "form" or not session.get("step"):
        return

    step = session["step"]
    value = (message.text or "").strip()

    if step in {"nationality", "russian_level", "experience", "passport"}:
        await message.answer(text(session, "select_value"))
        await delete_message_safe(message)
        return

    if step == "full_name":
        if not validate_full_name(value):
            await message.answer(text(session, "invalid_full_name"))
            await delete_message_safe(message)
            return
        session["data"]["full_name"] = " ".join(value.split())
        session["step"] = "birth_date"
    elif step == "birth_date":
        if not validate_birth_date(value):
            await message.answer(text(session, "invalid_birth_date"))
            await delete_message_safe(message)
            return
        session["data"]["birth_date"] = value
        session["step"] = "russian_level"
    elif step == "phone_primary":
        if not validate_phone(value):
            await message.answer(text(session, "invalid_phone"))
            await delete_message_safe(message)
            return
        session["data"]["phone_primary"] = normalize_phone(value)
        session["step"] = "phone_secondary"
    elif step == "phone_secondary":
        if not validate_phone(value):
            await message.answer(text(session, "invalid_phone"))
            await delete_message_safe(message)
            return
        session["data"]["phone_secondary"] = normalize_phone(value)
        session["step"] = "email"
    elif step == "email":
        if not validate_email(value):
            await message.answer(text(session, "invalid_email"))
            await delete_message_safe(message)
            return
        session["data"]["email"] = normalize_email(value)
        session["step"] = "passport"
    else:
        return

    await delete_message_safe(message)
    await render(session, message.chat.id, bot)


def valid_document_name(file_name: str | None, mime_type: str | None) -> bool:
    lower_name = (file_name or "").lower()
    allowed_extension = lower_name.endswith((".jpg", ".jpeg", ".png", ".pdf", ".heic", ".heif"))
    allowed_mime = mime_type in {
        "image/jpeg",
        "image/png",
        "application/pdf",
        "image/heic",
        "image/heif",
    }
    return allowed_extension or allowed_mime


async def passport_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    if session.get("screen") == "payment_upload":
        if not session.get("lead_id") or not session.get("payment_method"):
            await message.answer(text(session, "payment_receipt_pending"))
            await delete_message_safe(message)
            return

        is_valid = False
        file_id = None
        file_kind = None

        if message.document and valid_document_name(message.document.file_name, message.document.mime_type):
            is_valid = True
            file_id = message.document.file_id
            file_kind = "document"
        elif message.photo:
            is_valid = True
            file_id = message.photo[-1].file_id
            file_kind = "photo"

        if not is_valid:
            await message.answer(text(session, "payment_receipt_invalid"))
            await delete_message_safe(message)
            return

        attach_payment_receipt(session["lead_id"], file_id, file_kind)
        await send_receipt_to_admin(
            bot=bot,
            session=session,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            receipt_file_id=file_id,
            receipt_kind=file_kind,
        )
        await message.answer(text(session, "payment_receipt_uploaded"))
        await delete_message_safe(message)
        return

    if session.get("screen") != "form" or session.get("step") != "passport":
        return

    is_valid = False
    file_id = None
    file_kind = None

    if message.document and valid_document_name(message.document.file_name, message.document.mime_type):
        is_valid = True
        file_id = message.document.file_id
        file_kind = "document"
    elif message.photo:
        is_valid = True
        file_id = message.photo[-1].file_id
        file_kind = "photo"

    if not is_valid:
        await message.answer(text(session, "invalid_passport"))
        await delete_message_safe(message)
        return

    session["data"]["passport_file_id"] = file_id
    session["data"]["passport_kind"] = file_kind
    await delete_message_safe(message)
    await finalize_form(session, message.chat.id, bot)


async def unknown_handler(message: Message, bot: Bot) -> None:
    session = get_session(message.from_user.id)
    if not session.get("language"):
        session["screen"] = "language"
        await render(session, message.chat.id, bot)
    elif session.get("screen") == "form":
        await message.answer(text(session, "select_value"))
    elif session.get("screen") == "payment_upload":
        await message.answer(text(session, "payment_receipt_invalid"))
    else:
        await render(session, message.chat.id, bot)
    await delete_message_safe(message)


async def main() -> None:
    init_db()
    bot = Bot(
        token=get_bot_token(),
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(language_handler, F.data.startswith("lang:"))
    dp.callback_query.register(navigation_handler, F.data.startswith("nav:"))
    dp.callback_query.register(form_start_handler, F.data == "form:start")
    dp.callback_query.register(set_value_handler, F.data.startswith("set:"))
    dp.callback_query.register(back_handler, F.data.startswith("back:"))
    dp.callback_query.register(payment_handler, F.data.startswith("payment:"))
    dp.callback_query.register(support_reply_callback_handler, F.data.startswith("support_reply:"))
    dp.message.register(passport_handler, F.document | F.photo)
    dp.message.register(
        support_message_handler,
        lambda message: (
            get_session(message.from_user.id).get("awaiting_support")
            or (
                is_admin_user(message.from_user.id)
                and get_session(message.from_user.id).get("admin_reply_user_id") is not None
            )
        ),
    )
    dp.message.register(process_form_message, F.text)
    dp.message.register(unknown_handler)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
