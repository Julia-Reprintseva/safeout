from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from core.models import Language

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "welcome": (
            "👋 Привет! Я SafeOut — бот безопасности для свиданий с незнакомцами.\n\n"
            "Перед свиданием сохраню всё: имя, место, машину. "
            "Каждые 15 минут буду спрашивать как ты. "
            "Если не ответишь — напишу доверенным контактам.\n\n"
            "✨ Первые 3 свидания бесплатно.\n"
            "❤️ Дальше — 550 Stars (карта/Apple Pay) или 7 USDT через @CryptoBot.\n\n"
            "/newdate — создать свидание\n"
            "/contacts — доверенные контакты\n"
            "/tubiki — моя коллекция тюбиков 🙈\n"
            "/clear — удалить данные\n"
            "/language — сменить язык"
        ),
        "choose_language": "Выбери язык / Choose language / Dil seçin:",
        "language_set": "✅ Язык установлен: Русский",
        "new_date_start": "📋 Создаём новое свидание. Как зовут человека или его ник?",
        "ask_profile_url": "🔗 Ссылка на его профиль (Tinder, ВКонтакте, Instagram и т.д.)?",
        "ask_meeting_place": "📍 Где вы встречаетесь впервые? (адрес или название, например: кафе «Мята», ул. Ленина 5)",
        "ask_destination": "🗺 Куда поедете дальше или что ещё планируете? (кино, его место, другой ресторан и т.д.)",
        "ask_car": "🚗 Номер и описание машины (марка, цвет)?",
        "ask_extra": "📝 Любая другая важная информация?",
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
        "sos_triggered": "🆘 SOS активирован. Контакты уже получили сообщение со всеми данными о свидании.",
        "safe_return": "🏠 Рада, что ты дома и в безопасности! Ну как, довольна? Или очередной тюбик? 😄",
        "review_fire": "🔥 Огонь",
        "review_ok": "😐 Норм",
        "review_tubik": "🙈 Тюбик",
        "review_thanks_fire": "🔥 Вот это успех! Рада за тебя 🥂",
        "review_thanks_ok": "😐 Ну, не каждое свидание — история. Главное — дома и в безопасности 🏠",
        "review_thanks_tubik": "🙈 Понятно. Как его звали? Запишу в коллекцию.",
        "tubik_saved": "📝 Записала. Коллекция пополнена 😄",
        "tubik_list_empty": "Коллекция пока пуста — хороший знак! 🎉",
        "tubik_list_header": "🙈 Коллекция тюбиков:\n\n",
        "end_session_btn": "🏠 Я дома, всё хорошо",
        "already_active": "⚠️ У тебя уже есть активное свидание. Сначала заверши его — нажми «Я дома, всё хорошо».",
        "fallback_hint": (
            "Не знаю, что с этим делать 🙂\n\n"
            "Вот что я умею:\n"
            "/newdate — создать новое свидание\n"
            "/contacts — доверенные контакты\n"
            "/tubiki — коллекция тюбиков 🙈\n"
            "/clear — удалить данные\n"
            "/language — сменить язык\n"
            "/help — помощь"
        ),
        "no_contacts_warning": (
            "⚠️ У тебя нет доверенных контактов. "
            "Добавь хотя бы одного через /contacts, иначе некому будет сообщить об опасности."
        ),
        "contacts_list": "👥 Твои доверенные контакты:",
        "contacts_empty": "У тебя пока нет доверенных контактов.\nДобавь первого:",
        "add_contact_btn": "➕ Добавить контакт",
        "ask_contact_name": "Как зовут этого человека?",
        "ask_contact_phone": "Номер телефона (с кодом страны, например +79001234567)?",
        "ask_contact_email": "Email?",
        "ask_contact_username": "Ник в Telegram (@masha_example)?",
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
            "Before your date, I'll save all info: name, place, car. "
            "Every 15 minutes I'll check in with you. "
            "If you go silent — I'll alert your trusted contacts.\n\n"
            "✨ First 3 dates are free.\n"
            "❤️ Then — 550 Stars (card/Apple Pay) or 7 USDT via @CryptoBot.\n\n"
            "/newdate — create a new date\n"
            "/contacts — manage trusted contacts\n"
            "/language — change language\n"
            "/help — help"
        ),
        "choose_language": "Choose language / Выбери язык / Dil seçin:",
        "language_set": "✅ Language set: English",
        "new_date_start": "📋 Creating a new date. What's the person's name or username?",
        "ask_profile_url": "🔗 Link to their profile (Tinder, Instagram, etc.)?",
        "ask_meeting_place": "📍 Where are you meeting for the first time? (address or name, e.g.: Coffee House, 5 Main St)",
        "ask_destination": "🗺 Where will you go next or what else is planned? (cinema, their place, another restaurant, etc.)",
        "ask_car": "🚗 Car plate and description (make, colour)?",
        "ask_extra": "📝 Any other important information?",
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
        "sos_triggered": "🆘 SOS activated. Your contacts have been sent all your date details.",
        "safe_return": "🏠 So glad you're home! How did it go?",
        "review_fire": "🔥 Amazing",
        "review_ok": "😐 Meh",
        "review_tubik": "🙈 Total write-off",
        "review_thanks_fire": "🔥 That's a win! Happy for you 🥂",
        "review_thanks_ok": "😐 Not every date is a story. Home and safe — that's what counts 🏠",
        "review_thanks_tubik": "🙈 Got it. What was his name? Adding to the collection.",
        "tubik_saved": "📝 Added. The collection grows 😄",
        "tubik_list_empty": "Collection is empty — great sign! 🎉",
        "tubik_list_header": "🙈 The write-off collection:\n\n",
        "end_session_btn": "🏠 I'm home, I'm safe",
        "already_active": "⚠️ You already have an active date. End it first — press \"I'm home, I'm safe\".",
        "fallback_hint": (
            "Not sure what to do with that 🙂\n\n"
            "Here's what I can do:\n"
            "/newdate — start a new date session\n"
            "/contacts — manage trusted contacts\n"
            "/clear — delete your data\n"
            "/language — change language\n"
            "/help — help"
        ),
        "no_contacts_warning": (
            "⚠️ You have no trusted contacts. "
            "Add at least one via /contacts, otherwise no one will be notified in an emergency."
        ),
        "contacts_list": "👥 Your trusted contacts:",
        "contacts_empty": "You don't have any trusted contacts yet.\nAdd your first one:",
        "add_contact_btn": "➕ Add contact",
        "ask_contact_name": "What's this person's name?",
        "ask_contact_phone": "Phone number (with country code, e.g. +447911123456)?",
        "ask_contact_email": "Email?",
        "ask_contact_username": "Telegram username (@masha_example)?",
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
            "Buluşmadan önce her şeyi kaydederim: isim, yer, araba. "
            "Her 15 dakikada bir seni kontrol ederim. "
            "Cevap vermezsen — güvenilen kişileri uyarırım.\n\n"
            "✨ İlk 3 buluşma ücretsiz.\n"
            "❤️ Sonrası — 550 Stars (kart/Apple Pay) veya @CryptoBot ile 7 USDT.\n\n"
            "/newdate — yeni bir buluşma oluştur\n"
            "/contacts — güvenilen kişileri yönet\n"
            "/language — dil değiştir\n"
            "/help — yardım"
        ),
        "choose_language": "Dil seçin / Choose language / Выбери язык:",
        "language_set": "✅ Dil ayarlandı: Türkçe",
        "new_date_start": "📋 Yeni bir buluşma oluşturuyoruz. Kişinin adı veya kullanıcı adı nedir?",
        "ask_profile_url": "🔗 Profiline bağlantı (Tinder, Instagram vb.)?",
        "ask_meeting_place": "📍 İlk buluşma yeri nerede? (adres veya yer adı, örn: Merkez Kafe, Atatürk Cd. 5)",
        "ask_destination": "🗺 Sonra nereye gideceksiniz veya başka planlarınız var mı? (sinema, evi, başka restoran vb.)",
        "ask_car": "🚗 Araç plakası ve tanımı (marka, renk)?",
        "ask_extra": "📝 Başka önemli bilgi var mı?",
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
        "sos_triggered": "🆘 SOS etkinleştirildi. Kişilerinin tüm randevu bilgilerin gönderildi.",
        "safe_return": "🏠 Evde olduğuna sevindim! Nasıldı peki?",
        "review_fire": "🔥 Harikaydı",
        "review_ok": "😐 İdare eder",
        "review_tubik": "🙈 Berbattı",
        "review_thanks_fire": "🔥 Ne güzel! Mutluyum senin için 🥂",
        "review_thanks_ok": "😐 Her randevu bir hikaye olmak zorunda değil. Evde ve güvendesin — bu yeter 🏠",
        "review_thanks_tubik": "🙈 Anladım. Adı neydi? Koleksiyona ekleyeyim.",
        "tubik_saved": "📝 Eklendi. Koleksiyon büyüyor 😄",
        "tubik_list_empty": "Koleksiyon henüz boş — iyi işaret! 🎉",
        "tubik_list_header": "🙈 Berbat randevular koleksiyonu:\n\n",
        "already_active": "⚠️ Zaten aktif bir randevun var. Önce onu bitir — \"Evdeyim, güvendeyim\" düğmesine bas.",
        "fallback_hint": (
            "Bununla ne yapacağımı bilmiyorum 🙂\n\n"
            "Yapabileceklerim:\n"
            "/newdate — yeni randevu başlat\n"
            "/contacts — güvenilen kişileri yönet\n"
            "/clear — verilerini sil\n"
            "/language — dili değiştir\n"
            "/help — yardım"
        ),
        "end_session_btn": "🏠 Evdeyim, güvendeyim",
        "no_contacts_warning": (
            "⚠️ Güvenilen kişin yok. "
            "Acil durumda kimsenin bilgilendirilmemesi için /contacts üzerinden en az bir kişi ekle."
        ),
        "contacts_list": "👥 Güvenilen kişilerin:",
        "contacts_empty": "Henüz güvenilen kişin yok.\nİlkini ekle:",
        "add_contact_btn": "➕ Kişi ekle",
        "ask_contact_name": "Bu kişinin adı nedir?",
        "ask_contact_phone": "Telefon numarası (ülke koduyla, örn. +905001234567)?",
        "ask_contact_email": "E-posta?",
        "ask_contact_username": "Telegram kullanıcı adı (@masha_example)?",
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
