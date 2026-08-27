from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from core.models import Language

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "welcome": (
            "👋 Привет! Я SafeOut — бот безопасности для свиданий с незнакомцами.\n\n"
            "Перед свиданием я помогу сохранить всю информацию о человеке и месте встречи. "
            "Если ты не выйдешь на связь — оповещу доверенные контакты, которые подключились ко мне в Telegram.\n\n"
            "Команды:\n"
            "/newdate — создать новое свидание\n"
            "/contacts — управление доверенными контактами\n"
            "/language — сменить язык\n"
            "/help — помощь"
        ),
        "choose_language": "Выбери язык / Choose language / Dil seçin:",
        "language_set": "✅ Язык установлен: Русский",
        "new_date_start": "📋 Создаём новое свидание. Как зовут человека или его ник?",
        "ask_profile_url": "🔗 Ссылка на его профиль (Tinder, ВКонтакте, Instagram и т.д.)? Или нажми /skip",
        "ask_meeting_place": "📍 Где вы встречаетесь впервые? (адрес или название, например: кафе «Мята», ул. Ленина 5)",
        "ask_destination": "🗺 Куда поедете дальше или что ещё планируете? (кино, его место, другой ресторан и т.д.) Или /skip если нет планов после",
        "ask_car": "🚗 Номер и описание машины (марка, цвет)? Или /skip",
        "ask_extra": "📝 Любая другая важная информация? Или /skip",
        "ask_return_time": "⏰ Когда планируешь вернуться? (например: 23:00 или через 3 часа)",
        "ask_files": (
            "📎 Отправь фото, скриншоты переписки, голосовые — всё что есть.\n"
            "Файлы остаются на серверах Telegram, я храню только ссылку на них. "
            "Увидеть их сможет тот, у кого будет ссылка на страницу тревоги — она приходит только если сработает тревога.\n\n"
            "Когда закончишь, нажми кнопку ниже."
        ),
        "files_done": "Готово с файлами",
        "session_ready": (
            "✅ Всё сохранено!\n\n"
            "Когда будешь готова начать свидание — нажми кнопку ниже. "
            "Я буду проверять тебя каждые {interval} минут."
        ),
        "start_date_btn": "▶️ Начать свидание",
        "session_started": (
            "✅ Свидание начато. Буду пинговать тебя каждые {interval} минут.\n"
            "Если не ответишь — оповещу подключённые доверенные контакты.\n\n"
            "📍 Поделись живой геолокацией (скрепка → Геопозиция → Транслировать геопозицию) — тогда на странице тревоги контакты увидят, где ты.\n\n"
            "В любой момент нажми 🆘 SOS если нужна срочная помощь."
        ),
        "ping_message": "👋 Всё хорошо? Ответь, чтобы я знал(а) что ты в безопасности.",
        "ping_ok_btn": "✅ Всё хорошо",
        "ping_sos_btn": "🆘 SOS — нужна помощь",
        "ping_ok_response": "✅ Отлично! Следующая проверка через {interval} минут.",
        "sos_triggered": (
            "🆘 SOS активирован. Прямо сейчас оповещаю доверенные контакты, которые подключились в Telegram.\n"
            "Они получат ссылку со всеми твоими данными."
        ),
        "safe_return": "🏠 Рада, что ты дома! Ну как это было? Понравилось или очередной тюбик? 😄",
        "end_session_btn": "🏠 Я дома, всё хорошо",
        "no_contacts_warning": (
            "⚠️ У тебя нет доверенных контактов. "
            "Добавь хотя бы одного через /contacts, иначе некому будет сообщить об опасности."
        ),
        "contacts_list": "👥 Твои доверенные контакты:",
        "contacts_empty": "У тебя пока нет доверенных контактов.\nДобавь первого:",
        "add_contact_btn": "➕ Добавить контакт",
        "ask_contact_name": "Как зовут этого человека?",
        "ask_contact_phone": "Номер телефона (с кодом страны, например +79001234567)? Или /skip",
        "ask_contact_email": "Email? Или /skip",
        "ask_contact_username": "Ник в Telegram (@masha_example)? Или /skip",
        "contact_saved": "✅ Контакт {name} сохранён!",
        "contact_invite_link": (
            "Чтобы я могла написать {name} в Telegram, отправь ей эту ссылку — "
            "как только она нажмёт «Старт», я подключу её автоматически:\n{link}"
        ),
        "contact_pending": "⏳ ждём подключения в Telegram",
        "contact_connected": "✅ подключён(а) в Telegram",
        "no_reachable_contacts": (
            "⚠️ Ни один контакт не сможет получить оповещение — нет ни телефона, "
            "ни подключения в Telegram. Добавь телефон или дождись подключения в /contacts."
        ),
        "trust_link_connected": "✅ Готово! Теперь я напишу тебе сюда, если {name} не выйдет на связь во время свидания.",
        "trust_link_owner_notified": "✅ {name} подключилась как доверенный контакт в Telegram!",
        "trust_link_invalid": "Эта ссылка недействительна или уже использована.",
        "trust_link_self": "Это твоя собственная ссылка-приглашение — отправь её тому человеку, кого добавляешь в контакты.",
        "consent_notice": (
            "🔒 <b>Прежде чем начать</b>\n\n"
            "Для работы SafeOut я сохраняю:\n"
            "• Твой Telegram ID и имя\n"
            "• Данные о свидании: имя партнёра, место встречи, маршрут\n"
            "• Телефоны и Telegram доверенных контактов\n"
            "• Файлы, которые ты отправляешь (хранятся на серверах Telegram)\n\n"
            "Данные используются только для отправки тревожных оповещений. "
            "Я не передаю их третьим лицам.\n\n"
            "Нажав «Принимаю», ты даёшь согласие на обработку персональных данных "
            "в соответствии с <a href='https://reprintseva.ru/bots/safeout/privacy/'>Политикой конфиденциальности</a>."
        ),
        "consent_accept_btn": "✅ Принимаю",
        "consent_accepted": "✅ Отлично! Теперь можно начать.\n\n",
        "skip": "/skip",
        "cancel": "Отмена",
    },
    "en": {
        "welcome": (
            "👋 Hi! I'm SafeOut — a safety bot for dates with strangers.\n\n"
            "Before your date, I'll help you save all info about the person and meeting place. "
            "If you go silent — I'll alert the trusted contacts who've connected with me on Telegram.\n\n"
            "Commands:\n"
            "/newdate — create a new date\n"
            "/contacts — manage trusted contacts\n"
            "/language — change language\n"
            "/help — help"
        ),
        "choose_language": "Choose language / Выбери язык / Dil seçin:",
        "language_set": "✅ Language set: English",
        "new_date_start": "📋 Creating a new date. What's the person's name or username?",
        "ask_profile_url": "🔗 Link to their profile (Tinder, Instagram, etc.)? Or /skip",
        "ask_meeting_place": "📍 Where are you meeting for the first time? (address or name, e.g.: Coffee House, 5 Main St)",
        "ask_destination": "🗺 Where will you go next or what else is planned? (cinema, their place, another restaurant, etc.) Or /skip if no further plans",
        "ask_car": "🚗 Car plate and description (make, colour)? Or /skip",
        "ask_extra": "📝 Any other important information? Or /skip",
        "ask_return_time": "⏰ When do you plan to be back? (e.g. 23:00 or in 3 hours)",
        "ask_files": (
            "📎 Send photos, chat screenshots, voice messages — anything you have.\n"
            "Files stay on Telegram's servers, I only keep a link to them. "
            "They become visible to whoever holds the alert page link — which is only sent out if an alert actually fires.\n\n"
            "When done, press the button below."
        ),
        "files_done": "Done with files",
        "session_ready": (
            "✅ Everything saved!\n\n"
            "When you're ready to start your date, press the button below. "
            "I'll check in with you every {interval} minutes."
        ),
        "start_date_btn": "▶️ Start date",
        "session_started": (
            "✅ Date started. I'll ping you every {interval} minutes.\n"
            "If you don't respond — I'll alert your connected trusted contacts.\n\n"
            "📍 Share live location (paperclip → Location → Share Live Location) so contacts can see where you are on the alert page.\n\n"
            "Press 🆘 SOS at any time if you need urgent help."
        ),
        "ping_message": "👋 Are you okay? Reply to let me know you're safe.",
        "ping_ok_btn": "✅ I'm okay",
        "ping_sos_btn": "🆘 SOS — I need help",
        "ping_ok_response": "✅ Great! Next check-in in {interval} minutes.",
        "sos_triggered": (
            "🆘 SOS activated. Alerting the trusted contacts who've connected on Telegram right now.\n"
            "They'll receive a link with all your details."
        ),
        "safe_return": "🏠 So glad you're home! So — how did it go? A keeper or a total write-off? 😄",
        "end_session_btn": "🏠 I'm home, I'm safe",
        "no_contacts_warning": (
            "⚠️ You have no trusted contacts. "
            "Add at least one via /contacts, otherwise no one will be notified in an emergency."
        ),
        "contacts_list": "👥 Your trusted contacts:",
        "contacts_empty": "You don't have any trusted contacts yet.\nAdd your first one:",
        "add_contact_btn": "➕ Add contact",
        "ask_contact_name": "What's this person's name?",
        "ask_contact_phone": "Phone number (with country code, e.g. +447911123456)? Or /skip",
        "ask_contact_email": "Email? Or /skip",
        "ask_contact_username": "Telegram username (@masha_example)? Or /skip",
        "contact_saved": "✅ Contact {name} saved!",
        "contact_invite_link": (
            "So I can message {name} on Telegram, send them this link — "
            "once they press Start, I'll connect them automatically:\n{link}"
        ),
        "contact_pending": "⏳ waiting to connect on Telegram",
        "contact_connected": "✅ connected on Telegram",
        "no_reachable_contacts": (
            "⚠️ No contact can be reached — no phone number and none connected on "
            "Telegram yet. Add a phone or wait for a connection in /contacts."
        ),
        "trust_link_connected": "✅ All set! I'll message you here if {name} doesn't check in during a date.",
        "trust_link_owner_notified": "✅ {name} connected as a trusted contact on Telegram!",
        "trust_link_invalid": "This link is invalid or already used.",
        "trust_link_self": "This is your own invite link — send it to the person you're adding as a contact.",
        "consent_notice": (
            "🔒 <b>Before we start</b>\n\n"
            "To work, SafeOut stores:\n"
            "• Your Telegram ID and name\n"
            "• Date details: partner's name, meeting place, route\n"
            "• Trusted contacts' phone numbers and Telegram accounts\n"
            "• Files you send (stored on Telegram's servers)\n\n"
            "Your data is used solely to send emergency alerts. "
            "It is never shared with third parties.\n\n"
            "By tapping «I agree», you consent to the processing of your personal data "
            "under our <a href='https://reprintseva.ru/bots/safeout/privacy/en/'>Privacy Policy</a>."
        ),
        "consent_accept_btn": "✅ I agree",
        "consent_accepted": "✅ Great! You're all set.\n\n",
        "skip": "/skip",
        "cancel": "Cancel",
    },
    "tr": {
        "welcome": (
            "👋 Merhaba! Ben SafeOut — yabancılarla buluşmalar için güvenlik botuyum.\n\n"
            "Buluşmadan önce, kişi ve buluşma yeri hakkındaki tüm bilgileri kaydetmene yardımcı olacağım. "
            "Eğer haber vermezsen — Telegram'da benimle bağlantı kurmuş güvenilen kişileri uyaracağım.\n\n"
            "Komutlar:\n"
            "/newdate — yeni bir buluşma oluştur\n"
            "/contacts — güvenilen kişileri yönet\n"
            "/language — dil değiştir\n"
            "/help — yardım"
        ),
        "choose_language": "Dil seçin / Choose language / Выбери язык:",
        "language_set": "✅ Dil ayarlandı: Türkçe",
        "new_date_start": "📋 Yeni bir buluşma oluşturuyoruz. Kişinin adı veya kullanıcı adı nedir?",
        "ask_profile_url": "🔗 Profiline bağlantı (Tinder, Instagram vb.)? Veya /skip",
        "ask_meeting_place": "📍 İlk buluşma yeri nerede? (adres veya yer adı, örn: Merkez Kafe, Atatürk Cd. 5)",
        "ask_destination": "🗺 Sonra nereye gideceksiniz veya başka planlarınız var mı? (sinema, evi, başka restoran vb.) Plan yoksa /skip",
        "ask_car": "🚗 Araç plakası ve tanımı (marka, renk)? Veya /skip",
        "ask_extra": "📝 Başka önemli bilgi var mı? Veya /skip",
        "ask_return_time": "⏰ Ne zaman geri dönmeyi planlıyorsun? (örn: 23:00 veya 3 saat sonra)",
        "ask_files": (
            "📎 Fotoğraf, sohbet ekran görüntüsü, sesli mesaj — ne varsa gönder.\n"
            "Dosyalar Telegram sunucularında kalır, sadece bağlantısını saklarım. "
            "Sadece bir alarm tetiklenirse gönderilen tehlike sayfası bağlantısına sahip olan kişi görebilir.\n\n"
            "Bitirdiğinde aşağıdaki butona bas."
        ),
        "files_done": "Dosyalar tamam",
        "session_ready": (
            "✅ Her şey kaydedildi!\n\n"
            "Buluşmaya başlamaya hazır olduğunda aşağıdaki butona bas. "
            "Seni her {interval} dakikada bir kontrol edeceğim."
        ),
        "start_date_btn": "▶️ Buluşmayı başlat",
        "session_started": (
            "✅ Buluşma başladı. Seni her {interval} dakikada bir kontrol edeceğim.\n"
            "Cevap vermezsen — bağlı güvenilen kişileri uyaracağım.\n\n"
            "📍 Canlı konum paylaş (ataç → Konum → Canlı Konum Paylaş) — böylece kişiler tehlike sayfasında nerede olduğunu görebilir.\n\n"
            "Acil yardım gerekirse istediğin zaman 🆘 SOS'a bas."
        ),
        "ping_message": "👋 İyi misin? Güvende olduğunu bildirmek için cevap ver.",
        "ping_ok_btn": "✅ İyiyim",
        "ping_sos_btn": "🆘 SOS — Yardıma ihtiyacım var",
        "ping_ok_response": "✅ Harika! Bir sonraki kontrol {interval} dakika sonra.",
        "sos_triggered": (
            "🆘 SOS etkinleştirildi. Şu anda Telegram'da bağlı güvenilen kişilerin uyarılıyor.\n"
            "Tüm bilgilerini içeren bir bağlantı alacaklar."
        ),
        "safe_return": "🏠 Evde olduğuna sevindim! Nasıldı peki? Tekrar görecek misin yoksa silip attın mı? 😄",
        "end_session_btn": "🏠 Evdeyim, güvendeyim",
        "no_contacts_warning": (
            "⚠️ Güvenilen kişin yok. "
            "Acil durumda kimsenin bilgilendirilmemesi için /contacts üzerinden en az bir kişi ekle."
        ),
        "contacts_list": "👥 Güvenilen kişilerin:",
        "contacts_empty": "Henüz güvenilen kişin yok.\nİlkini ekle:",
        "add_contact_btn": "➕ Kişi ekle",
        "ask_contact_name": "Bu kişinin adı nedir?",
        "ask_contact_phone": "Telefon numarası (ülke koduyla, örn. +905001234567)? Veya /skip",
        "ask_contact_email": "E-posta? Veya /skip",
        "ask_contact_username": "Telegram kullanıcı adı (@masha_example)? Veya /skip",
        "contact_saved": "✅ {name} kişisi kaydedildi!",
        "contact_invite_link": (
            "{name} kişisine Telegram'dan yazabilmem için bu bağlantıyı gönder — "
            "Başlat'a bastığında otomatik olarak bağlanacağım:\n{link}"
        ),
        "contact_pending": "⏳ Telegram'da bağlanması bekleniyor",
        "contact_connected": "✅ Telegram'da bağlandı",
        "no_reachable_contacts": (
            "⚠️ Hiçbir kişiye ulaşılamıyor — telefon numarası yok ve henüz Telegram'a "
            "bağlanmadılar. /contacts üzerinden telefon ekle veya bağlanmalarını bekle."
        ),
        "trust_link_connected": "✅ Tamam! {name} buluşma sırasında haber vermezse sana buradan yazacağım.",
        "trust_link_owner_notified": "✅ {name} Telegram'da güvenilen kişi olarak bağlandı!",
        "trust_link_invalid": "Bu bağlantı geçersiz veya zaten kullanılmış.",
        "trust_link_self": "Bu senin kendi davet bağlantın — kişi olarak eklediğin kişiye gönder.",
        "consent_notice": (
            "🔒 <b>Başlamadan önce</b>\n\n"
            "SafeOut'un çalışması için şunları kaydediyorum:\n"
            "• Telegram kimliğin ve adın\n"
            "• Buluşma bilgilerin: kişinin adı, buluşma yeri, güzergah\n"
            "• Güvenilen kişilerin telefon numaraları ve Telegram hesapları\n"
            "• Gönderdiğin dosyalar (Telegram sunucularında saklanır)\n\n"
            "Veriler yalnızca acil durum uyarıları göndermek için kullanılır. "
            "Üçüncü taraflarla paylaşılmaz.\n\n"
            "«Kabul ediyorum» butonuna basarak, "
            "<a href='https://reprintseva.ru/bots/safeout/privacy/'>Gizlilik Politikası</a> "
            "kapsamında kişisel verilerinin işlenmesine onay vermiş olursun."
        ),
        "consent_accept_btn": "✅ Kabul ediyorum",
        "consent_accepted": "✅ Harika! Artık başlayabilirsin.\n\n",
        "skip": "/skip",
        "cancel": "İptal",
    },
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    text = TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(key, TRANSLATIONS["ru"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


class I18nMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        db_user = data.get("db_user")

        if db_user:
            lang = db_user.language.value
        elif user and user.language_code:
            lang = user.language_code[:2] if user.language_code[:2] in TRANSLATIONS else "ru"
        else:
            lang = "ru"

        data["lang"] = lang
        data["t"] = lambda key, **kw: t(key, lang=lang, **kw)
        return await handler(event, data)
