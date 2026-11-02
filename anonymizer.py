#!/usr/bin/env python3
"""
anonymizer.py -- обезличивание КОДОМ до любого ИИ (роль Аналитика, шаг 1), версия 2.

Порядок: (1) правила для данных с жёстким форматом (e-mail, IBAN, номера, телефон, адрес, даты) -- на исходном тексте;
(2) spaCy NER (лица, фирмы, места); (3) правила для имён (обращения, подписи, имена из адреса почты);
(4) повторные упоминания (фамилия отдельно, родительный падеж); (5) суммы -> округлённые.
Таблица соответствия остаётся локально. guard() -- контроль исходящего текста.
review()/confirm() -- подтверждение человеком: наружу уходит только текст, который человек увидел и одобрил
(одобрение привязано к контрольной сумме текста и пишется в журнал).
learn() -- обучение на проверке человеком: всё, что человек отметил как пропущенное, запоминается локально
(~/.config/leckermath/anonymizer_learned.json, вне проектов) и со следующего запуска убирается всегда; те же отметки
копятся как размеченные примеры (…/anonymizer_corrections.jsonl) для будущего дообучения модели распознавания имён.

Уровень строгости (решение владельца проекта 02.10.2026: в работе -- необходимый минимум, строгий -- по настройке):
  1 «минимум»  -- только то, что указывает на человека или фирму: имена, названия, адреса, контакты, все номера
                  (налоговые, банковские, дел, договоров, автомобиля), дата рождения. Суммы, даты, годы остаются.
  2 «обычный»  -- плюс: суммы округляются, даты -> год, марка автомобиля убирается, числа вне налогового контекста убираются.
  3 «строгий»  -- плюс: убираются все числа и годы, кроме ссылок на нормы и процентов; суммы -> порядок величины.
Проверка: python3 eval_anonymize.py run --v2
"""
import re
from pathlib import Path

_NLP = None
NAME = r"[A-ZÄÖÜ][a-zäöüßıćčšžğşéèáóñ]+(?:-[A-ZÄÖÜ][a-zäöüßıćčšžğşéèáóñ]+)*"
STREET_END = r"(?:[Ss]traße|[Ss]tr\.|[Ww]eg|[Aa]llee|[Pp]latz|[Dd]amm|[Rr]ing|[Gg]asse|[Uu]fer|[Hh]ellweg|[Cc]haussee|[Ww]all|[Mm]arkt|[Ss]tieg|[Bb]usch|[Tt]eich|[Ww]eide)"
PREP = r"(?:Am|An der|An den|Auf der|Auf dem|Im|In der|In den|Zum|Zur|Hinter dem|Vor dem|Unter den)"
MONTH = r"(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)"
# жёсткие форматы: (шаблон, метка). Порядок важен: длинные номера раньше коротких.
HARD = [
    (r"(?:https?://|www\. ?)[^\s<>\"\]\)]+", "Link"),                                      # ссылки -- целиком (в них бывают имена, ключи доступа к облачным папкам)
    # адрес сайта без http/www («habermehl-sanitaer.de/rechnung») -- атака 19.10.2026; адреса ведомств и судов -- публичные, остаются
    (r"(?<![\w@./-])(?!(?:[\w-]+\.)*(?:bund|bundesfinanzministerium|bzst|bundesbank|bafin|bundesfinanzhof|bverfg|gesetze-im-internet|"
     r"elster|europa|curia|finanzamt|justiz|nrw|bayern|niedersachsen|sachsen|hessen|berlin|hamburg|bremen|saarland|thueringen|"
     r"brandenburg|sachsen-anhalt|rlp|schleswig-holstein|mv-regierung|baden-wuerttemberg|destatis|dejure|openjur)\.(?:de|eu)\b)"
     r"[a-z0-9][\w-]*(?:\.[\w-]+)*\.(?:de|com|net|org|eu|info|biz|at|ch|io|ru|nl|pl|tr|it|fr|uk|online|shop|gmbh)\b(?:/[^\s<>\"\]\)]*)?", "Link"),
    # учётная запись сотрудника в подвале распечатки («Währung: EUR vorname.nachname Seite 1») и после слов «Benutzer», «Bearbeiter» -- остаток Салона 08.10.2026
    (r"(?<=Währung: EUR )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}", "Kennung"),
    (r"(?<![\w@/.])[A-Za-zÄÖÜäöüß]{2,}\.[a-zäöüß]{3,}(?= Seite \d)", "Kennung"),
    (r"(?<=Benutzer: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Benutzer )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Bearbeiter: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Kennung: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}", "Kennung"),
    (r"[\w.+-]+ ?@ ?[\w-]+(?: ?\. ?[\w-]+)+", "E-Mail"),                                 # с пробелами распознавания вокруг «@» и точек
    (r"\b[A-ZА-Я]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b", "IBAN"),       # 19.10: и с кириллическим кодом страны («ДЕ44…»)
    # IBAN и другие номера словами («IBAN DE vier vier fünf null …») -- атака 19.10.2026: шесть и больше цифр словами подряд
    (r"(?i)(?:\b[A-Z]{2}[ ]+)?(?:\b(?:null|eins|zwei|drei|vier|fünf|fuenf|sechs|sieben|acht|neun|zehn|elf|zwölf)\b[ ,-]*){6,}", "Kennung"),
    (r"\b(?:AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK)[ ]?[A-Z0-9]{8,12}\b(?<=\d)", "USt-IdNr"),
    (r"(?<=BIC[: ])\s*[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b|(?<=BIC: )\s*[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", "BIC"),
    (r"\b\d{2,3}/\d{3,4}/\d{4,5}\b|\b\d{13}\b", "Steuernummer"),
    (r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b", "Steuer-ID"),
    (r"(?<![\w/+])(?:\+49[ ]?(?:\(0\))?[ ]?|0049[ ]?|\(0\d{2,5}\)[ ]?|0)\d{2,5}(?:[ /-]{0,2}\d{2,9}){1,4}(?![\w/])", "Telefon"),
    (r"\b[A-ZÄÖÜ]{1,3}-[A-Z]{1,2}[ ]?\d{1,4}[EH]?\b|\b(?![IVX]+ )[A-ZÄÖÜ]{1,3} (?!R |B |S |ZR |AR )[A-Z]{1,2} \d{1,4}[EH]?\b(?![/.]\d)", "Kennzeichen"),
    (r"(?<![\w/-])\b(?!\d[\d.]*-[A-ZÄÖÜ][A-Za-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)*\b)(?!\d{2,4}/\d+/(?:EG|EU|EWG|EGV|Euratom)\b)(?![CT]-\d+/\d{2}\b)(?=[\w/.-]*\d)(?=[\w/.-]*[A-ZÄÖÜ])\w+(?:[-/]\w+)+\b", "Kennung"),
    (r"\b[A-Z][ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b|\b[A-Z]\d{5}[ ]\d{4}\b", "Versichertennr"),
    # 19.10.2026 (остатки набора wild: номера с подписью, поземельная книга, номер кузова, таможня, USt-IdNr. вне ЕС)
    (r"(?<=Grundbuch )[^.\n]{0,60}?\bBlatt\s+\d{1,6}\b|\bBlatt\s+\d{1,6}(?=[^.\n]{0,40}Grundbuch)|(?<![\w-])Flurst(?:ück|ücke|\.)?\s+(?:Nr\.\s*)?\d{1,5}(?:/\d{1,4})?|\bFlur\s+\d{1,4}\b", "Grundbuch"),
    (r"(?<![A-Za-z0-9])(?=[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9]))(?=[A-HJ-NPR-Z0-9]*\d)(?=[A-HJ-NPR-Z0-9]*[A-HJ-NPR-Z])[A-HJ-NPR-Z0-9]{17}", "Fahrgestellnr"),
    (r"\b\d{2}[A-Z]{2}[A-Z0-9]{14}\b", "MRN"),
    (r"(?:(?<=USt-IdNr\. )|(?<=USt-IdNr\.: )|(?<=UST-ID )|(?<=USt-ID )|(?<=Ust-Id )|(?<=UST-ID: )|(?<=USt-ID: )|(?<=VAT ID )|(?<=VAT ID: )|(?<=lautet ))"
     r"[A-Z]{2}(?=[A-Z0-9]{8,12}\b)(?=[A-Z0-9]*\d{6})[A-Z0-9]{8,12}\b", "USt-IdNr"),
    (r"\bPostfach\s+\d[\d ]{2,10}\d\b", "Adresse"),
    (r"(?:[A-ZÄÖÜ][\wäöüß.-]+ ){1,3}\d{1,4} ?[a-z]?(?=,?\s+(?:in\s+)?\d{5}\b)", "Adresse"),
    (rf"\b(?:{PREP}[ \t]+)?(?:[A-ZÄÖÜ][\wäöüß.-]*[ \t]+){{0,2}}[A-ZÄÖÜ]?[\wäöüß.-]*{STREET_END}[ \t]*\d{{1,4}}[ \t]?[a-zA-Z]?\b", "Adresse"),   # в пределах одной строки
    (rf"\b{PREP}\s+(?!{MONTH}\b|Jahr\b|Jahre\b|Monat\b|Zeitraum\b|Höhe\b|Umfang\b)[A-ZÄÖÜ][\wäöüß-]+\s+(?!(?:19|20)\d{{2}}\b)\d{{1,4}}\s?[a-zA-Z]?\b", "Adresse"),
]
# номер с подписью («Beleg-Nr. 9931», «Mandanten-Nr. 1234»): подпись остаётся, номер -- под метку (19.10.2026, остатки набора wild);
# группа 1 -- подпись, группа 2 -- номер
HARD_LABEL = [(r"\b((?:Beleg|Mandanten|Kunden|Berater|Vertrags|Auftrags|Vorgangs|Mitglieds|Versicherungsschein|Kassenzeichen)"
               r"(?:-Nr\.|-Nummer|nummer|nr\.)\s*:?\s*)([A-Z0-9][\w/-]{2,})", "Kennung")]
KEEP = re.compile(r"^(Inh\.?|Tatzeit|Tatort|Tatzeitraum|Geschädigte[rn]?|Anzeigenerstatter(?:in)?|Formularerstellung|Sachbearbeitung|Amtsbezeichnung|Bescheinigung|Strafanzeige|Aktenzeichen|Vorgangsnummer|Dienststelle|Inhaber\w*|Kontakt\w*|Betriebs-?Nr\.?|[\w-]*-Nr\.?|SGB\b.*|BGB|HGB|AO|EStG|UStG|KStG|GewStG|StBerG|ZPO|SGG|FGO|Der|Die|Das|Den|Dem|Des|Ein|Eine|Einer|Einem|Wir|Sie|Ich|Er|Es|Im|In|Am|An|Auf|Für|Von|Zu|Nach|Bei|Aus|Wenn|Dies\w*|"
                  r"West|Ost|Nord|Süd|Rechtskreis|Team|Abteilung|Sachgebiet|Referat|EuGH|EuG|BFH|BGH|BVerfG|BSG|BMF|Summe\w*|Saldo|Gesamt\w*|Zwischensumme|Betrag|Beträge|Konto|Datum|Seite|Monat|Jahr|Übertrag|Vortrag|Buchwert|Teilwert|Marktwert|Steuernummer|Vorsteuer|Umsatzsteuer|Finanzamt|Betriebsprüfung|Kleinunternehmer\w*|"
                  r"Einzelunternehmer\w*|Gesellschafter\S*|Geschäftsführer\w*|Tantieme|Jahresüberschuss\w*|Eigentumswohnung|Eheleute|"
                  r"Ehefrau|Ehemann|Bemessungsgrundlage|Großauftrag|Übersetzerin|EUR|Euro|Mandant\w*|Kanzlei|Steuerberater\w*|"
                  r"Sehr|Mit|Guten|Hallo|Betreff|Telefonnotiz|Aktenvermerk|Reverse-Charge|Investitionsabzugsbetrag|Rückstellung\w*|"
                  r"\w*[Nn]r\.?|\w*nummer|Az\.?|Datum|Betreff|Bearbeiter\w*|Sitz|Geburtsdatum|Firma|Heute|Hierbei|Mitarbeiter\w*|Ihr|Ihre|Unser\w*|Anlage\w*|Aktenzeichen|Lohnsteuer\S*|Umsatzsteuer\S*|Schenkung\w*|Erbschaft\w*|GmbH\S*|E-Mail|Telefon|IBAN|Kennzeichen|Adresse|Steuer-ID)$")
LEGAL_FORM = re.compile(r"\s+((?:GmbH\s*&\s*Co\.?\s*KG|GmbH|AG|KG|OHG|UG(?:\s*\(haftungsbeschränkt\))?|GbR|e\.\s?K\.|eG|SE|PartG)\b\.?)\s*$")


def _nlp():
    global _NLP
    if _NLP is None:
        import spacy
        try:
            _NLP = spacy.load("de_core_news_lg")
        except OSError:
            _NLP = spacy.load("de_core_news_sm")
    return _NLP


LEVEL = 1          # уровень по умолчанию
LEARNED = __import__("os").path.expanduser("~/.config/leckermath/anonymizer_learned.json")
CORRECTIONS = __import__("os").path.expanduser("~/.config/leckermath/anonymizer_corrections.jsonl")


def load_learned():
    import json
    import os
    return json.load(open(LEARNED, encoding="utf-8")) if os.path.exists(LEARNED) else []


def learn(terms, kind="Person", context=""):
    """Запомнить пропущенное, отмеченное человеком. terms -- строки ровно так, как они стоят в тексте."""
    import json
    import os
    import time
    cur = load_learned()
    have = {(x["text"].lower(), x["kind"]) for x in cur}
    new = [{"text": t.strip(), "kind": kind} for t in terms if len(t.strip()) > 2 and (t.strip().lower(), kind) not in have]
    if not new:
        return 0
    os.makedirs(os.path.dirname(LEARNED), exist_ok=True)
    json.dump(cur + new, open(LEARNED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.chmod(LEARNED, 0o600)
    with open(CORRECTIONS, "a", encoding="utf-8") as f:      # размеченные примеры для дообучения
        for x in new:
            i = context.find(x["text"])
            f.write(json.dumps({"time": time.strftime("%F %T"), "text": x["text"], "kind": kind,
                                "context": context[max(0, i - 80):i + len(x["text"]) + 80] if i >= 0 else ""}, ensure_ascii=False) + "\n")
    os.chmod(CORRECTIONS, 0o600)
    return len(new)


# ---------------------------------------------------------------- русский и английский текст (08.10.2026)
# Владелец проекта: «работать буду однозначно с русскими, английскими и немецкими источниками». Немецкая модель имён русских и английских имён
# не видит; для них -- свои модели (локальные, spaCy) и свои правила. Отключить: LM_ANON_MEHRSPRACHIG=0 (для сравнения в замерах).
_NLP_X = {}
_KYR = re.compile(r"[А-Яа-яЁё]")
RU_NAME = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
EN_NAME = r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)?"
_EN_STOP = re.compile(r"\b(the|and|of|to|is|are|was|were|for|with|that|this|your|our|please|have|has|been|will|from|you|we|not|by|on|as|at)\b", re.I)
_DE_STOP = re.compile(r"\b(der|die|das|und|ist|nicht|mit|für|von|den|dem|des|wir|Sie|ein|eine|wird|sind|zu|auf|im|bei|nach|oder|auch)\b")
RU_ENDE = r"(?:ого|его|ому|ему|ыми|ими|ой|ей|ою|ею|ым|им|ом|ем|ах|ях|ам|ям|ов|ев|ью|ая|яя|ую|юю|а|я|у|ю|ы|и|е|о|ь|й)$"
RU_KEEP = re.compile(r"^(Господин\w*|Госпож\w*|Белег\w*|Кляйн\w*|Унтернемер\w*|Рехнунг\w*|Бухунг\w*|Умзац\w*|Форштойер\w*|Гевербе\w*|Мандант\w*|Мельдунг\w*|Анмельдунг\w*|"
                     r"Айншпрух\w*|Видершпрух\w*|Манунг\w*|Ферзихерунг\w*|Байтраг\w*|Айнкоммен\w*|Эрклерунг\w*|Прюфунг\w*|Бетрибспрюфунг\w*|Што[её]?бератор\w*|Штойербератор\w*|Бератор\w*|Финан[цз]амт\w*|Кранкенкасс\w*|Бешайд\w*|Штойер\w*|Амт\w*|Арбайтсагентур\w*|Соцамт\w*|Джобцентр\w*|"
                     r"Икк|ИКК|Датев\w*|Лексвар\w*|Бухгалтер\w*|Консультант\w*|Клиент\w*|Салон\w*|Касс\w*|Налогов\w*|Деклараци\w*|Уважаем\w*|Здравствуйте|Добрый|Доброе|Спасибо|Пожалуйста|Германи\w*|Росси\w*|Европ\w*|Финансов\w*|Налогов\w*|Больничн\w*|Касс\w*|Январ\w*|Феврал\w*|Март\w*|Апрел\w*|"
                     r"Ма[йяе]|Июн\w*|Июл\w*|Август\w*|Сентябр\w*|Октябр\w*|Ноябр\w*|Декабр\w*|Понедельник|Вторник|Сред[ау]|Четверг|Пятниц\w*|Суббот\w*|Воскресень\w*|Евро|Рубл\w*)$")
EN_KEEP = re.compile(r"^(Mr|Mrs|Ms|Miss|Dr|Prof|Sir|Madam|Dear|Sincerely|Regards|Best|Kind|Yours|Thank|Thanks|Please|Hello|Hi|Germany|German|Europe|European|EU|VAT|Tax|Invoice|Monday|Tuesday|Wednesday|Thursday|Friday|"
                     r"Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December|Euro|EUR|USD|GBP)$")
HARD_X = [
    # бланки ведомств (справка полиции, 09.10.2026): имя в полях «…durch», «Name, Amtsbezeichnung»; «Фамилия, сокращение должности»;
    # город в строке «Город, дата» и в названии подразделения; адрес через запятые «индекс город, район, улица, номер»
    (r"(?:Sachbearbeitung durch|Formularerstellung durch|aufgenommen durch|Sachbearbeiter(?:in)?|Name, ?Amtsbezeichnung\)?)[^\n:]{0,45}:[ \t]*([A-ZÄÖÜ][a-zäöüß-]{2,}(?: [A-ZÄÖÜ][a-zäöüß-]{2,})?)(?![\w:])", "Person"),
    (r"(?:Sachbearbeitung durch|Formularerstellung durch|aufgenommen durch|Sachbearbeiter(?:in)?|Name, ?Amtsbezeichnung\)?)[^\n:]{0,45}:?[ \t]*\n[ \t]*([A-ZÄÖÜ][a-zäöüß-]{2,}(?: [A-ZÄÖÜ][a-zäöüß-]{2,})?)(?=[ \t]*(?:,|\n|$))", "Person"),
    (r"(?<![\w\[])([A-ZÄÖÜ][a-zäöüß-]{2,}), ?(?:PK|POK|PHK|EPHK|KK|KOK|KHK|EKHK|PM|POM|PHM|PKin|POKin|PHKin|KKin|KOKin|KHKin|PMin|POMin|PHMin|PKA|KKA|ROI|RAR|RR|ORR|StI|StOI|StAR|StAF|VA|RI|ROS)\b", "Person"),
    (r"(?m)^[ \t]*([A-ZÄÖÜ][a-zäöüß-]{2,}(?:[ -][A-ZÄÖÜ][a-zäöüß-]{2,})?), (?:den )?\d{1,2}\.\d{1,2}\.\d{4}[ \t]*$", "Ort"),
    (r"(?:Polizeiinspektion|Polizeiwache|Polizeistation|Polizeipräsidium|Polizeidirektion|Polizeirevier|Kriminalkommissariat|Kriminalinspektion|Kreispolizeibehörde|Polizeikommissariat)[ \t]+([A-ZÄÖÜ][a-zäöüß-]{2,}(?:[ -][A-ZÄÖÜ][a-zäöüß-]{2,})?)", "Ort"),
    (r"\b\d{5} [A-ZÄÖÜ][\wäöüß-]+((?:, ?[A-ZÄÖÜ][\wäöüß. -]{2,30}){1,2}, ?\d{1,4} ?[a-z]?\b)", "Adresse"),

    (r"(?<![\d+])(?:\+7|8)[ (\-]{0,2}\d{3}[ )\-]{0,2}\d{3}[ \-]?\d{2}[ \-]?\d{2}(?!\d)", "Telefon"),
    (r"(?<![\w+])\+(?!49)\d{1,3}[ \-]?\(?\d{1,4}\)?(?:[ \-]?\d{2,4}){2,4}(?!\d)", "Telefon"),
    (r"(?<=ИНН)[:№ ]{0,3}\d{10,12}\b", "Steuernummer"),
    (r"(?<=СНИЛС)[:№ ]{0,3}\d{3}-\d{3}-\d{3}[ -]\d{2}\b", "Versichertennr"),
    (r"(?i:паспорт\w*|passport)(?:[^\d\n]{0,25})(\d{2} ?\d{2} ?\d{6}|[A-Z]{1,2}\d{6,8})", "Ausweis"),
    (r"(?:ул\.|улица|пр\.|просп\.|проспект|пер\.|переулок|наб\.|бульвар|шоссе)\s+[А-ЯЁ0-9][\wа-яё.\- ]{2,40}?,?\s+(?:д\.|дом)\s*\d+[а-яА-Я]?(?:[,\s]+(?:кв\.|корп\.|стр\.)\s*\d+)*", "Adresse"),
    (r"\b\d{1,5} [A-Z][a-z]+(?: [A-Z][a-z]+)? (?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Drive|Square|Way|Close|Court|Place)\b", "Adresse"),
]


def _nlp_x(lang):
    if lang not in _NLP_X:
        import spacy
        try:
            _NLP_X[lang] = spacy.load({"ru": "ru_core_news_lg", "en": "en_core_web_md"}[lang])
        except OSError:
            _NLP_X[lang] = None
    return _NLP_X[lang]


_MORPH = None
GLOSSAR = ("Steuerberater Finanzamt Krankenkasse Bescheid Beleg Belege Kleinunternehmer Rechnung Buchung Buchhaltung Umsatz Umsatzsteuer Vorsteuer Gewerbe Gewerbesteuer Mandant "
           "Meldung Anmeldung Einspruch Widerspruch Mahnung Versicherung Beitrag Einkommen Einkommensteuer Erklärung Steuererklärung Prüfung Betriebsprüfung Lohn Lohnsteuer Kasse "
           "Kassenbuch Jahresabschluss Bilanz Gewinn Verlust Vollmacht Zahlung Ratenzahlung Stundung Pfändung Zoll Hauptzollamt Jobcenter Arbeitsagentur Sozialamt Ausländerbehörde "
           "Termin Unterlagen Dokumente Vertrag Kündigung Miete Vermieter Konto Überweisung Dauerauftrag Lastschrift Fahrtenbuch Firmenwagen Salon Kosmetik Studio").split()
_TRANS = dict(zip("абвгдезийклмнопрстуфхцчшщыэюяёьъж", ["a", "b", "w", "g", "d", "e", "s", "i", "j", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "ch", "z", "tsch", "sch", "sch", "y", "e", "ju", "ja", "jo", "", "", "sch"]))


def _deutsch_kyrillisch(w):
    """«Белеги», «кляйнунтернемер», «штоебератор» -- немецкое слово русскими буквами?"""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False
    lat = "".join(_TRANS.get(c, c) for c in w.lower())
    lat = lat.replace("schto", "steu").replace("schte", "ste").replace("schp", "sp").replace("ai", "ei").replace("oi", "eu").replace("ljai", "lei").replace("jai", "ei")
    return len(lat) >= 5 and any(fuzz.ratio(lat[:len(t) + 2], t.lower()) >= 74 for t in GLOSSAR)


def _ru_namensteile(t, kind):
    """Из найденного моделью русского «имени» оставить только слова, похожие на имя: с заглавной буквы, не из списка обычных слов;
    известное словарю слово -- только если словарь знает его как имя, фамилию, отчество (для мест и фирм -- как название).
    Смешанные «Нашла Steuerberater» и глаголы в начале предложения («Хотела») так отсекаются."""
    global _MORPH
    if _MORPH is None:
        try:
            import pymorphy3
            _MORPH = pymorphy3.MorphAnalyzer()
        except Exception:
            _MORPH = False
    gut = []
    for w in t.split():
        kern = w.strip("«»\"',.;:()")
        if not kern or not re.fullmatch(r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?|[А-ЯЁ]\.|[А-ЯЁ]{2,6}", kern) or RU_KEEP.match(kern) \
                or kern.casefold() in RU_GEMEIN:                  # 31.10, итерация 3: «Приват Аня» -> только «Аня» (вид занятия -- не часть имени)
            if kind == "Firma" and gut and re.fullmatch(r"[«»\"А-ЯЁа-яё-]+", w):      # «ООО „Северный ветер“»: внутри названия допускаются любые слова
                gut.append(w)
            continue
        if _MORPH and len(kern) > 2 and kern[1:].islower():
            ps = _MORPH.parse(kern)
            bekannt = any(p_.is_known for p_ in ps)
            eigen = any(g in p_.tag for p_ in ps for g in ("Name", "Surn", "Patr", "Geox", "Orgn"))
            if bekannt and not eigen and kind != "Firma":
                continue
            if not bekannt and _deutsch_kyrillisch(kern):
                continue
        gut.append(w)
    return " ".join(gut).strip(" «»\"',.;:()")


def _en_abs(out):
    """Границы английских абзацев. Короткий абзац без немецких служебных слов считается английским, если весь текст в основном английский."""
    en_all, de_all = len(_EN_STOP.findall(out)), len(_DE_STOP.findall(out))
    doc_en = en_all >= 5 and en_all > 2 * de_all
    spans, pos = [], 0
    for para in re.split(r"(\n\s*\n)", out):
        en, de = len(_EN_STOP.findall(para)), len(_DE_STOP.findall(para))
        if (en >= 3 and en > de) or (doc_en and de == 0 and para.strip()):
            spans.append((pos, pos + len(para)))
        pos += len(para)
    return spans


def _ersetze(out, val, ph):
    return re.sub(rf"(?<![\[\wа-яёА-ЯЁ]){re.escape(val)}(?![\wа-яёА-ЯЁ\]])", ph, out)


def _zellen(t):
    """Строки таблицы (CSV: от трёх запятых) -- запятые и кавычки заменены переводом строки той же длины, чтобы модель распознавания
    видела ячейки по отдельности: иначе «Q3 2024,,Yes,,Yes» и «Datum,Datum,Generalkonsulat Der» становятся «лицами» (имитация дела B 16.10.2026).
    Смещения символов не меняются."""
    return re.sub(r"(?m)^[^\n]*(?:,(?! )[^\n]*){3,}$", lambda m: re.sub(r'[,"]', "\n", m.group(0)), t)      # в таблице после запятой нет пробела, в связном тексте -- есть


def _de_wort(p):
    """Слово есть в словаре базы права (de_wortliste.txt.gz)."""
    if not _DE_WORT:
        import gzip
        f = Path(__file__).parent / "de_wortliste.txt.gz"
        _DE_WORT.append(set(gzip.open(f, "rt", encoding="utf-8").read().split("\n")) if f.exists() else set())
    return p.lower() in _DE_WORT[0]


def _mehrsprachig(out, tag, ner):
    """Русский и английский текст: жёсткие форматы, имена по правилам, модели имён, повторные упоминания с падежами."""
    import os
    if os.environ.get("LM_ANON_MEHRSPRACHIG", "1") == "0":
        return out
    for rx, kind in HARD_X:
        out = re.sub(rx, lambda m, kind=kind: (m.group(0)[:m.start(1) - m.start(0)] + tag(kind, m.group(1))) if m.groups() else tag(kind, m.group(0)), out)
    found = []                                                        # (значение, вид)
    hat_ru = len(_KYR.findall(out)) >= 20
    if hat_ru:
        for rx in (rf"(?:г-н|г-жа|господин\w*|госпож\w*|[Уу]важаем\w+)\s+((?:{RU_NAME}\s+){{0,2}}{RU_NAME})",
                   rf"(?:[Сс] уважением|[Сс] наилучшими пожеланиями|[Вв]сего доброго)[,!.]?\s+((?:{RU_NAME}\s+){{1,2}}{RU_NAME})",
                   rf"((?:{RU_NAME}\s+)?{RU_NAME}\s+[А-ЯЁ][а-яё]+(?:ович|евич|ьич|овна|евна|ична|инична))",
                   rf"((?:{RU_NAME})\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)", rf"([А-ЯЁ]\.\s?[А-ЯЁ]\.\s?{RU_NAME})"):
            for m in re.finditer(rx, out):
                v = m.group(1).strip()
                if "[" not in v and not RU_KEEP.match(v.split()[0]):
                    found.append((v, "Person"))
        nlp = _nlp_x("ru")
        if nlp is not None:
            for ent in nlp(out).ents:
                t = ent.text.strip(" «»\"',.;:()")
                if len(t) <= 2 or not _KYR.search(t) or "[" in t or "]" in t or "\n" in t or RU_KEEP.match(t.split()[0]):
                    continue
                kind = {"PER": "Person", "ORG": "Firma", "LOC": "Ort"}.get(ent.label_)
                if kind == "Person" and " " not in t and (t[:1].islower() or t.casefold() in RU_GEMEIN):
                    continue                # 31.10.2026: одно слово строчными или из учётной таблицы («приват», «аренда») -- не лицо (имена строчными ловит список)
                if kind and (ner != "per" or kind == "Person"):
                    t = _ru_namensteile(t, kind)
                    if len(t) > 2:
                        found.append((t, kind))
    latin = re.sub(r"\[[^\[\]]+\]", " ", out)
    if len(_EN_STOP.findall(latin)) >= 5:
        for rx in (rf"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+((?:{EN_NAME}\s+){{0,2}}{EN_NAME})", rf"\bDear\s+((?:{EN_NAME}\s+){{0,1}}{EN_NAME})\b",
                   rf"(?:Sincerely|Regards|Best regards|Kind regards|Best wishes|Yours faithfully|Yours sincerely|Cheers)[,!.]?\s+((?:{EN_NAME}\s+){{1,2}}{EN_NAME})"):
            for m in re.finditer(rx, out):
                v = m.group(1).strip()
                if "[" not in v and not EN_KEEP.match(v.split()[0]) and not KEEP.match(v.split()[0]):
                    found.append((v, "Person"))
        nlp = _nlp_x("en")
        if nlp is not None:
            for a_, b_ in _en_abs(out):                               # модель -- только на английских абзацах: на немецком тексте она шумит
                para = out[a_:b_]
                if True:
                    _mp = _zellen(para)
                    for ent in nlp(_mp).ents:
                        t = para[ent.start_char:ent.end_char].strip(" \"',.;:()")
                        if re.search(r"\d", t) and ent.label_ == "PERSON" or "\n" in _mp[ent.start_char:ent.end_char].strip() or (ent.label_ == "ORG" and " " not in t and _de_wort(t)):
                            continue
                        if len(t) <= 2 or "[" in t or "]" in t or "\n" in t or _KYR.search(t) or EN_KEEP.match(t.split()[0]) or KEEP.match(t.split()[0]) or all(w in FACHWORT for w in t.split()):
                            continue
                        kind = {"PERSON": "Person", "ORG": "Firma", "GPE": "Ort", "LOC": "Ort", "FAC": "Ort"}.get(ent.label_)
                        if kind and re.search(r"(?i)\b(?:name|number|date|amount|item|account|holder|client|supplier|total|vat|code|type|status|price|quantity|description)\b", t):
                            continue                # заголовок столбца таблицы («Item Name» -> «лицо», затем слово «Name» закрывалось во всех заголовках; имитация дела B 16.10.2026)
                        if kind and (ner != "per" or (kind == "Person" and " " in t)):
                            found.append((re.sub(r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+", "", t), kind))
    for v, kind in sorted(set(found), key=lambda x: -len(x[0])):
        if v and v in out:
            ph = tag(kind, v)
            out = _ersetze(out, v, ph)
            if _KYR.search(v):                                         # падежи: основа каждого слова имени + до четырёх букв окончания
                for part in v.split():
                    part = part.strip("«»\"',.;:()")
                    stem = re.sub(RU_ENDE, "", part)
                    if len(part) > 3 and len(stem) >= 3 and part[0].isupper() and not RU_KEEP.match(part):
                        out = re.sub(rf"(?<![\[\wа-яёА-ЯЁ]){re.escape(stem)}[а-яё]{{0,4}}(?![\wа-яёА-ЯЁ\]])", ph, out)
            elif kind == "Person":
                for part in v.split():
                    if len(part) > 3 and re.search(r"[A-Za-z]{3}", part) and not EN_KEEP.match(part) and not KEEP.match(part) and not _de_wort(part):     # обычное слово и число («2023» из «Q4 2023») -- не часть имени
                        out = _ersetze(out, part, ph)
                        out = _ersetze(out, part + "'s", ph)
    return out


AZ_GERICHT = (r"(?<![\w/.-])(?:[IVX]{1,4}|\d{1,3}) ?(?:K|V|R|B|S|E|U|Ko|BvR|BvL|BvF|BvE|BvQ|BvC|ZR|ZB|StR|AZR|AZB|LB|LC|LA|KR|AL|AS|AY|KA|BS)\b"
              r" ?\d{1,5}/\d{2,4}(?: [A-Z]{1,3}(?![\wäöü]))?")
GERICHT_NAME = (r"\b(?:BFH|BVerfG|BGH|BSG|BAG|BVerwG|EuGH|Bundesfinanzhof|Bundesverfassungsgericht|Bundesgerichtshof|Bundessozialgericht|"
                r"(?:FG|Finanzgericht|LSG|Landessozialgericht|SG|Sozialgericht|OLG|Oberlandesgericht|LG|Landgericht|VG|OVG|VGH|Verwaltungsgericht)"
                r"(?:\s+(?:des\s+Landes\s+|für\s+das\s+Land\s+)?[A-ZÄÖÜ][\wäöüß]+(?:[- ][A-ZÄÖÜ][\wäöüß]+)?)?)")
HOMOGLYPH_LOG = []                                  # (было, стало) по всем вызовам anonymize; сборка обнуляет и пишет протокол в папку дела
_UNSICHTBAR = re.compile("[\u00ad\u200b-\u200f\u2060-\u2064\ufeff\u034f\u180e]")
_KYR_LAT = str.maketrans("АВЕКМНОРСТХаеорсухіјѕ", "ABEKMHOPCTXaeopcyxijs")
_LAT_KYR = str.maketrans("ABEKMHOPCTXaeopcyx", "АВЕКМНОРСТХаеорсух")
# 31.10.2026, итерация 4: двойники распознавания (OCR), которых нет среди одинаковых по виду букв: «Ьis» = «bis», «Befбrderung» = «Beförderung»,
# «zurйckgelegten» = «zurückgelegten», «giЫ» = «gibt»? -- такие пары не однозначны, поэтому замена принимается только если слово
# целиком стало словарным (de_wortliste, служебные слова spaCy, немецкое сложное слово). Таблица UTS #39 (confusables) в venv нет
# (пакета confusable_homoglyphs нет); одинаковые по виду буквы -- _KYR_LAT, двойники распознавания -- здесь.
_OCR_KYR = {"Ь": "b", "ь": "b", "Ъ": "b", "ъ": "b", "б": "ö6b", "Б": "B6", "Ы": ["bl", "bI", "Bl", "bt"], "ы": ["bl", "bi"], "ё": "äöëe", "Ё": "ÄÖË",
            "й": "üu", "Й": "ÜU", "и": "un", "И": "UN", "п": "n", "П": "n", "л": "nl", "Л": "JI", "н": "nh", "щ": ["m", "w", "ш"], "ш": "w", "Ш": "W",
            "г": "r", "Г": "r", "к": "k", "т": "mt", "Т": "T", "д": "gd", "Д": "D", "в": "Bb", "З": "3", "з": "3", "ц": "u", "ч": "4", "я": "a", "Я": "R",
            "ю": "io", "ж": "x", "ф": "o", "у": "y", "ч": "y"}
_STOP_DE = []


def _dt_wort(w):
    """Немецкое слово: словарь базы права, служебное слово spaCy, сложное слово из двух слов словаря."""
    if not _STOP_DE:
        try:
            from spacy.lang.de.stop_words import STOP_WORDS
            _STOP_DE.append({x.casefold() for x in STOP_WORDS})
        except Exception:
            _STOP_DE.append(set())
    wl = w.casefold()
    return wl in _STOP_DE[0] or (len(wl) >= 4 and (_de_wort(wl) or _de_kompositum(wl)))


def homoglyph_wort(w):
    """Слово из букв обоих алфавитов -> одним алфавитом. Чисто кириллическое и чисто латинское не трогается.
    1) одинаковые по виду буквы -- в сторону алфавита, которого в слове больше (как с 19.10.2026);
    2) если в латинском по большинству слове остались кириллические буквы -- двойники распознавания (_OCR_KYR), только если всё слово
       стало немецким словом; 3) кириллическое по большинству слово, которое целиком латиницей -- немецкое слово («ипd» -> «und»), -- латиницей."""
    import itertools
    kyr = sum("\u0400" <= c <= "\u04ff" for c in w)
    lat = sum(c.isalpha() and not ("\u0400" <= c <= "\u04ff") for c in w)
    if not kyr or not lat:
        return w
    if lat >= kyr:
        v = w.translate(_KYR_LAT)
    else:
        v = w.translate(_LAT_KYR)
        if not any("a" <= c.lower() <= "z" for c in v):
            return v
    rest = [i for i, c in enumerate(v) if "\u0400" <= c <= "\u04ff"]
    if not rest or len(rest) > 4:
        return v
    if lat < kyr:                                   # кириллица по большинству: латинское прочтение принимается только как немецкое слово
        v = w.translate(_KYR_LAT)
        rest = [i for i, c in enumerate(v) if "\u0400" <= c <= "\u04ff"]
    wahl = [list(_OCR_KYR.get(v[i], "")) if isinstance(_OCR_KYR.get(v[i], ""), str) else _OCR_KYR[v[i]] for i in rest]
    if not all(wahl):
        return w.translate(_KYR_LAT) if lat >= kyr else w.translate(_LAT_KYR)
    for komb in itertools.islice(itertools.product(*wahl), 256):
        z = list(v)
        for i, r in zip(rest, komb):
            z[i] = r
        kand = "".join(z)
        if not re.search("[\u0400-\u04ff]", kand) and _dt_wort(kand):
            return kand
    return w.translate(_KYR_LAT) if lat >= kyr else w.translate(_LAT_KYR)


def vorbereiten(text, log=None):
    """19.10.2026 (атаки на обезличиватель, замечания DeepSeek/Gemini): привести текст к одному виду ДО всех правил, чтобы имя
    нельзя было спрятать от них: NFKC (полноширинные и составные знаки), без невидимых знаков (U+200B…, мягкий перенос),
    слова из смеси латиницы и кириллицы -> одним письмом (буквы-двойники -- по большинству букв слова),
    перенос строки внутри слова склеивается, разрядка («H a b e r m e h l») склеивается."""
    import unicodedata
    # NFKC по знакам, кроме степеней и дробей («m²», «½» -- смысл, а не маскировка)
    t = "".join(c if unicodedata.category(c) == "No" else unicodedata.normalize("NFKC", c) for c in unicodedata.normalize("NFC", text))
    t = _UNSICHTBAR.sub("", t)

    def _schrift(m):
        w = m.group(0)
        neu = homoglyph_wort(w)
        if neu != w and log is not None:
            log.append((w, neu))
        return neu
    t = re.sub(r"[\w\u0400-\u04ff]+", _schrift, t)
    t = re.sub(r"(?<=[a-zäöüß])-[ \t]*\n[ \t]*(?!(?:und|oder|bzw|sowie|bis)\b)(?=[a-zäöüß])", "", t)
    t = re.sub(r"(?<![\w.])(?:[A-Za-zÄÖÜäöüß] ){3,}[A-Za-zÄÖÜäöüß](?![\w])",
               lambda m: re.sub(r" (?=[A-ZÄÖÜ])", "  ", m.group(0)).replace("  ", "\x00").replace(" ", "").replace("\x00", " "), t)
    return t


# 31.10.2026 (имитация дела A, прогон 29.10: 211 текстов, контроль остановил, но четыре класса утечек он не назвал) — отдельная ступень
# после повторных упоминаний, на всех уровнях: (а) имена кириллицей в немецком документе и в ячейках таблиц (xlsx -> CSV: «Катя», «Даша»),
# (б) склейка распознавания «ИмяФамилия» без пробела, (в) обрывки IBAN («DE48D», «DE9610» — номер разорван переносом), (г) школы и учреждения
# («…-Grundschule» указывает на место). Ложные тревоги того же прогона — термины спорта и балета (FACHWORT).
RU_VORNAMEN = set("""Александр Саша Шура Алексей Лёша Леша Анатолий Толя Андрей Андрюша Антон Тоша Аркадий Артём Артем Тёма Борис Боря Вадим Валентин Валя
Валерий Валера Василий Вася Виктор Витя Виталий Владимир Володя Вова Владислав Влад Вячеслав Слава Геннадий Гена Георгий Жора Гоша Глеб Григорий Гриша
Даниил Даня Денис Дмитрий Дима Евгений Женя Егор Иван Ваня Игорь Илья Кирилл Константин Костя Леонид Лёня Максим Макс Матвей Михаил Миша Никита Николай Коля
Олег Павел Паша Пётр Петр Петя Роман Рома Руслан Сергей Серёжа Сережа Станислав Стас Степан Тимофей Тимур Фёдор Федор Федя Юрий Юра Ярослав
Александра Алёна Алена Алиса Алина Алла Анастасия Настя Ангелина Анна Аня Анюта Арина Ариша Валентина Валерия Лера Варвара Варя Вера Вероника Ника Виктория Вика
Галина Галя Дарья Даша Диана Ева Евгения Екатерина Катя Катюша Елена Лена Леночка Елизавета Лиза Жанна Злата Зоя Инна Ирина Ира Карина Кира Кристина Ксения Ксюша
Лариса Лара Лидия Лида Любовь Люба Людмила Люда Мила Маргарита Рита Марго Марина Мария Маша Машенька Милана Надежда Надя Наталья Наталия Наташа Нина Оксана Ольга Оля
Полина Поля Раиса Света Светлана Снежана София Софья Соня Тамара Татьяна Таня Ульяна Уля Эвелина Юлия Юля Яна Янка Ясмина Валюша Олеся Василиса Мирослава Милена
Богдана Майя Вита Агата Есения Эмилия Нелли Инга Регина Эльвира Ярослава Ярина Таисия Тая Аришка Дашенька Катенька Сонечка Варенька Анечка Ариночка Алисочка
Маргоша Кристя Эмили Ева Стефания Стеша Таисья Мирра Амелия Аделина Ульянка Лерочка Викуся Настенька Лизонька""".split())
# совпадают с обычными словами (вера, надежда, любовь, слава, роман, майя/мая, ника…) -- только с заглавной буквы и не в начале предложения
RU_VORNAMEN_MEHRDEUTIG = {"Вера", "Надежда", "Любовь", "Слава", "Роман", "Майя", "Ника", "Мила", "Лада", "Ева", "Влад", "Макс", "Злата", "Вита", "Агата",
                          "Марина", "Регина", "Инна", "Лера", "Рита", "Нина", "Лида", "Люба", "Тая", "Мирра", "Кира", "Поля"}
LAT_VORNAMEN = set("""Lena Katja Katia Dasha Dascha Jana Yana Lara Arisha Alisa Valja Uljana Ulyana Olga Olja Irina Ira Natascha Natasha Tanja Tatjana Swetlana
Svetlana Svitlana Oksana Mascha Masha Marija Anja Sonja Polina Nastja Nastia Ksenia Xenia Wika Vika Julia Julija Alina Arina Vera Nina Galina Ljuba Ljudmila
Sascha Sasha Dima Dmitri Mischa Misha Kolja Wanja Vanja Serjoscha Andrej Alexej Sergej Sergei Juri Jurij Igor Oleg Pawel Pavel Maxim Kirill Stanislaw Stanislav
Taisia Emilia Margo Kristina Warja Varya Varja Liza Lisa Alisa Uljana""".split())
# частые немецкие фамилии, которые не совпадают с обычными словами (Müller, Koch, Richter, Klein … — совпадают, их здесь нет)
DE_NACHNAMEN = {"Schmidt", "Schmitt", "Schulz", "Schulze", "Meyer", "Meier", "Mayer", "Maier", "Hoffmann", "Schröder", "Neumann", "Zimmermann", "Krüger",
                "Hartmann", "Krause", "Lehmann", "Köhler", "Kowalski", "Kowalska", "Nowak", "Lewandowski"}
# слова учётных таблиц и разговорные -- не имена (31.10, второй прогон имитации дела A: русская модель имён закрывала их как лиц)
RU_GEMEIN = set("""приват интенсив индив индивидуально аренда тикет малышка малышки новенькая новенький сестрички сестры подарок лимит доп суббота воскресенье
понедельник вторник среда четверг пятница январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь января февраля марта апреля мая июня
июля августа сентября октября ноября декабря конечно единственное спасибо привет хорошо оплата оплачено долг группа занятие занятия тренировка тренер
итого сумма наличные перевод скидка абонемент пробное""".split())
FACHWORT = set("""Spagat Pirouette Pirouetten Passé Passe Chainé Chaine Chainés Plié Plie Relevé Releve Tendu Jeté Jete Arabesque Attitude Battement Fouetté Fouette
Grand Petit Port Bras Sauté Saute Glissade Assemblé Assemble Échappé Echappe Rond Jambe Keule Keulen Reifen Band Ball Seil Barre Pointe Spitze Berliner
Sport Turnen Gymnastik Rhythmische Akrobatik Flickflack Radschlag Rolle Brücke Kerze Handstand Choreografie Choreographie Kür Pflicht""".split())
_TYP = (r"(?:Grundschule|Gesamtschule|Realschule|Hauptschule|Sekundarschule|Förderschule|Gemeinschaftsschule|Gymnasium|Berufskolleg|Berufsschule|Schule|"
        r"Kita|KiTa|Kindergarten|Kindertagesstätte|Familienzentrum|Sporthalle|Turnhalle|Schwimmhalle|Mehrzweckhalle|Halle|Ballettschule|Tanzschule|Musikschule|"
        r"Grundschulverbund|Hochschule|Universität|Klinik|Krankenhaus|Seniorenheim|Pflegeheim|Sportverein|Verein|Studio|Sportzentrum|Zentrum|"
        r"School|Academy|Akademie|College|Club)")   # 31.10: английские виды («… RG School» -- имя школы, вид остаётся)
# видовые части слитного названия учреждения («Leistungssportschule» -- вид, важен для § 4 Nr. 21 UStG; не маскируется)
TYP_VORSILBE = re.compile(r"(?i)^(?:leistungssport|sport|musik|tanz|ballett|volkshoch|berufs|fach|grund|haupt|real|gesamt|förder|sekundar|gemeinschafts|hoch|"
                          r"fahr|abend|privat|sprach|kunst|ganztags|gesundheits|kranken|pflege|alten|ausbildungs|fortbildungs|wirtschafts|kinder|jugend|"
                          r"turn|schwimm|mehrzweck|stadt|kreis|landes|bundes|gemeinde|europa|international|tages|kampfsport)+$")
RX_IBAN_REST = (r"(?<![\w\[])(?:DE|AT|CH|NL|BE|LU|FR|IT|ES|PL|CZ|UA|LT|LV|EE|ДЕ)\d{2}[A-Z0-9]{0,4}"
                r"(?:[ ](?=[A-Z0-9]*\d)[A-Z0-9]{1,4}){0,7}(?![\w\]])")
_RU_ENDUNG = ("", "а", "я", "у", "ю", "е", "и", "ы", "ой", "ей", "ою", "ею", "ом", "ем", "ам", "ям", "ами", "ями", "ах", "ях", "ке", "ки", "ку", "кой")


def _ru_vorname(tok):
    """Слово -- русское имя из списка: в любом регистре («яна», «ВАря»), с падежным окончанием, со склеенными заглавными («КатяРР»).
    Имена, совпадающие с обычными словами, -- только с заглавной первой буквой. -> имя из списка или None"""
    kern = re.sub(r"[А-ЯЁ]{1,4}$", "", tok) if re.search(r"[а-яё][А-ЯЁ]{1,4}$", tok) else tok          # «КатяРР» -> «Катя»
    k = kern.casefold()
    for n in RU_VORNAMEN:
        nf = n.casefold()
        stamm = nf[:-1] if nf[-1] in "аяйь" else nf
        if k == nf or (k.startswith(stamm) and k[len(stamm):] in _RU_ENDUNG and len(k) > len(stamm)):
            if n in RU_VORNAMEN_MEHRDEUTIG and not kern[:1].isupper():
                continue
            return n
    return None


# 31.10.2026, итерация 3 (имитация дела A: «geboren am [Geburtsdatum] in <город>» -- место рождения открыто во всех трёх прогонах, 31 место):
# место рождения -- всегда Ort, по слову-признаку перед ним (немецкий, русский, английский), а не по списку городов
_ORT_WORT = r"[A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,}(?:-[A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,})?"
_GEBURTSORT = [
    r"(?i:\bgeboren|\bgeb\.|\bborn)(?:(?!\bin\b)[^\n;]){0,45}?\bin\s+(?:der\s+Stadt\s+)?",     # «geboren am [Geburtsdatum A] in X», «geb. 1975 in X» (первое «in»)
    r"(?i:\bGeburtsort|\bplace of birth|\bbirthplace)\s*(?:[:\-–]\s*|\s)",           # «Geburtsort: X»
    r"(?i:\bродил(?:ся|ась|ись))(?:(?!(?<!\w)в\s)[^\n;]){0,40}?(?<!\w)в\s+(?:г\.\s*|городе\s+)?",     # «родилась 13.12.1975 в X» (первое «в»)
    r"(?i:\bместо\s+рождения)\s*(?:[:\-–]\s*|\s)(?:г\.\s*|город\s+)?",              # «место рождения: X»
]


def geburtsort(out, tag):
    """Место рождения после слова-признака -> [Ort]. Уже поставленная метка и слово со строчной буквы («in der Ukraine») не трогаются."""
    for rx in _GEBURTSORT:
        out = re.sub(rf"({rx})({_ORT_WORT})(?![\w\]])", lambda m: m.group(1) + (m.group(2) if KEEP.match(m.group(2)) else tag("Ort", m.group(2))), out)
    return out


# 31.10.2026, итерация 3: равнозначность написаний латиницей и кириллицей («Hannover» = «Ганновер», «Elena» = «Елена», «Musterowa» = «Мустеровой»).
# Не таблица готовых пар, а образец: каждая буква -- все принятые передачи (немецкая, английская, украинская транслитерация).
_L2K = [("tsch", "ч"), ("shch", "щ"), ("sch", "ш"), ("sh", "ш"), ("ch", "(?:х|ш|ч|к)"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("tz", "ц"), ("ck", "к"), ("ph", "ф"),
        ("th", "т"), ("ei", "(?:ай|ей)"), ("eu", "(?:ой|ей)"), ("ie", "(?:и|ие)"), ("ja", "(?:я|ья|йа)"), ("ju", "(?:ю|ью)"), ("jo", "(?:ё|йо|е|ьо)"), ("ya", "(?:я|ья)"),
        ("yu", "(?:ю|ью)"), ("yo", "(?:ё|йо)"), ("ia", "(?:ия|иа|я)"), ("iu", "(?:ию|ю)"), ("ii", "(?:ий|ии|и)"),
        ("a", "а"), ("b", "б"), ("c", "(?:к|ц)"), ("d", "д"), ("e", "(?:е|э)"), ("f", "ф"), ("g", "г"), ("h", "(?:г|х)?"), ("i", "(?:и|й|і)"), ("j", "(?:й|ж|дж)"),
        ("k", "к"), ("l", "ль?"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"), ("s", "(?:с|з)"), ("t", "т"), ("u", "(?:у|ю)"),
        ("v", "(?:в|ф)"), ("w", "в"), ("x", "кс"), ("y", "(?:и|й|ы)"), ("z", "(?:ц|з)"), ("ä", "(?:е|э|а)"), ("ö", "(?:е|ё|о)"), ("ü", "(?:ю|у|и)"), ("ß", "с")]
_K2L = {"а": "a", "б": "b", "в": "(?:v|w)", "г": "(?:g|h)", "д": "d", "е": "(?:e|je|ye)", "ё": "(?:jo|yo|e|o)", "ж": "(?:zh|sch|j|g|s)", "з": "(?:z|s)",
        "и": "(?:i|y|ij)", "й": "(?:j|y|i)?", "к": "(?:k|c|ck)", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "(?:s|ss|z)", "т": "t",
        "у": "(?:u|ou)", "ф": "(?:f|ph|v)", "х": "(?:ch|kh|h)", "ц": "(?:ts|tz|z|c)", "ч": "(?:ch|tsch|tch|cz)", "ш": "(?:sch|sh|ch|sz)", "щ": "(?:sch|shch|sh)",
        "ъ": "", "ы": "(?:y|i)", "ь": "", "э": "e", "ю": "(?:ju|yu|iu|u)", "я": "(?:ja|ya|ia|a)", "і": "i", "ї": "(?:ji|yi|i)", "є": "(?:je|ye|e)"}


def translit_muster(w):
    """Образец того же слова в другом алфавите (без границ слова, без окончаний), или None. Удвоенные согласные -- одна или две."""
    w = w.casefold()
    if re.fullmatch(r"[a-zäöüß]{3,}", w):
        w = re.sub(r"([bcdfgklmnprstz])\1", r"\1", w)
        out, i = [], 0
        while i < len(w):
            for lat, kyr in _L2K:
                if w.startswith(lat, i):
                    out.append(f"(?:{kyr})+" if lat in ("n", "l", "m", "r", "s", "t", "k", "p", "f", "b", "d", "g") else kyr)
                    i += len(lat)
                    break
            else:
                return None
        return "".join(out)
    if re.fullmatch(r"[а-яёіїє]{3,}", w):
        out = []
        for c in w:
            lat = _K2L.get(c)
            if lat is None:
                return None
            out.append(f"(?:{lat})+" if c in "нлмрстпкфбдг" else lat)
        return "".join(out)
    return None


def _luecken_31_10(out, tag, mapping):
    """Ступень 31.10.2026 (см. комментарий выше; вторая итерация того же дня). Возвращает текст."""
    # учреждение, уже закрытое моделью целиком («[Ort A]» = «Muster-Gymnasium», «[Firma A]» = «Private Muster-Sportschule»):
    # вид возвращается в текст, закрывается только собственное имя; если собственного имени нет -- метка снимается
    allg = {"private", "privat", "staatliche", "staatlich", "städtische", "städtisch", "und", "der", "die", "das", "des", "für", "freie", "evangelische", "katholische"}
    for ph, val in list(mapping.items()):
        if not str(ph).startswith(("[Ort", "[Firma")) or not isinstance(val, str) or ph not in out:
            continue
        m = re.match(rf"^(.*?)(-?)({_TYP}|[A-ZÄÖÜ][a-zäöüß]*(?:schule|gymnasium|kita|halle))$", val.strip())
        if not m:
            continue
        vor, typ = m.group(1).strip(" -"), m.group(3)
        typ_vor = re.match(r"^([A-ZÄÖÜ][a-zäöüß]*?)(schule|gymnasium|kita|halle)$", typ)
        typ_allg = not typ_vor or TYP_VORSILBE.match(typ_vor.group(1)) or _de_wort(typ)
        teile = [w for w in re.split(r"[\s]+", vor) if w]
        if typ_allg and all(w.strip("-").casefold() in allg or TYP_VORSILBE.match(w.strip("-")) or _de_wort(w.strip("-")) for w in teile):
            out = out.replace(ph, val)                                  # всё -- видовые слова: метку снять
            del mapping[ph]
        elif typ_allg and vor:
            out = out.replace(ph, tag("Ort", vor) + (m.group(2) or " ") + typ)
    # 31.10 (прогон 4): модель закрыла сам вид («School» -> [Person]), а имя школы перед ним осталось открытым -- вид вернуть,
    # затем закрыть имя перед видом через пробел («A-B RG School» -> «[Ort] School»); общие слова перед видом не закрываются
    for ph, val in list(mapping.items()):
        if str(ph).startswith("[Person") and isinstance(val, str) and re.fullmatch(_TYP, val.strip()) and ph in out:
            out = out.replace(ph, val.strip())
            del mapping[ph]
    allg_en = {"rhythmic", "gymnastics", "sport", "sports", "dance", "music", "ballet", "art", "arts", "private", "international", "the", "of", "and", "for", "high", "primary"}
    def _vor_typ(m):
        teile = m.group(1).split()
        while teile and (teile[0].casefold() in allg | allg_en or _de_wort(teile[0]) or TYP_VORSILBE.match(teile[0])):
            teile.pop(0)
        if not teile or all(w.casefold() in allg_en or _de_wort(w) or TYP_VORSILBE.match(w) for w in teile):
            return m.group(0)
        name = " ".join(teile)
        return m.group(1)[:m.group(1).find(name)] + tag("Ort", name) + " " + m.group(2)
    out = re.sub(r"(?<![\w\[\]])((?:[A-ZÄÖÜ0-9][\w&.-]*\s+){1,4}?)(School|Academy|Akademie|College|Club)\b", _vor_typ, out)
    out = re.sub(RX_IBAN_REST, lambda m: tag("IBAN", m.group(0)), out)                              # (в) обрывки IBAN
    # (г) учреждения: маскируется только собственное имя, вид остаётся («[Ort A]-Grundschule», «Grundschule am [Ort B]», «Sporthalle „[Ort C]“»)
    out = re.sub(rf"(?<![\w\[])((?:[A-ZÄÖÜ][\wäöüß]+-)+)({_TYP})\b",
                 lambda m: m.group(0) if TYP_VORSILBE.match(m.group(1).replace("-", "")) else tag("Ort", m.group(1).rstrip("-")) + "-" + m.group(2), out)
    out = re.sub(rf"\b({_TYP})(\s+(?:am|an der|an den|im|in der|auf dem|Am|An der|Im)\s+)([A-ZÄÖÜ][\wäöüß-]+)",
                 lambda m: m.group(1) + m.group(2) + tag("Ort", m.group(3)), out)
    out = re.sub(rf"\b({_TYP})(\s*)([„\"«‚])([^“”\"»‘’\n\[\]]{{2,40}})([“”\"»‘’])", lambda m: m.group(1) + m.group(2) + m.group(3) + tag("Ort", m.group(4)) + m.group(5), out)
    def _wort(m):
        vor, typ = m.group(1), m.group(2)
        if TYP_VORSILBE.match(vor) or _de_wort(m.group(0)) or _de_wort(vor):
            return m.group(0)
        return tag("Ort", vor) + typ
    out = re.sub(r"(?<![\w\[-])([A-ZÄÖÜ][a-zäöüß]{3,}?)(grundschule|gesamtschule|realschule|hauptschule|schule|gymnasium|kita|halle)\b", _wort, out)
    # (а) русские имена: по списку, в любом регистре, с падежами и склейками -- в любой строке
    def _tok(m):
        t = m.group(0)
        return tag("Person", t) if _ru_vorname(t) else t
    out = re.sub(r"(?<![\w\[])[А-ЯЁа-яё]{2,20}(?![\w\]])", _tok, out)
    # фамилия рядом с найденным именем: слово с заглавной сразу после метки лица; перед меткой -- только с фамильным окончанием
    def _nach(m):
        w = m.group(2)
        if w.casefold() in RU_GEMEIN or RU_KEEP.match(w) or str(mapping.get(m.group(1), "")).rstrip().endswith(".") \
                or re.search(r"(?:ли|ла|ло|ть|ться|ет|ит|ут|ют|ят|ем|им|ешь|ишь|сь|ся|те)$", w):     # инициалы с точкой -- конец фразы; глагол -- не фамилия
            return m.group(0)
        return m.group(1) + " " + tag("Person", w)
    out = re.sub(r"(\[Person [^\]\n]{1,6}\])[ \t]+([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]+)?)(?![\w\]])", _nach, out)
    out = re.sub(r"(?<![\w\[])([А-ЯЁ][а-яё]+(?:ова|ева|ина|ская|цкая|ов|ев|ин|ский|цкий|енко|ук|юк|ич|ян))[ \t]+(?=\[Person )",
                 lambda m: tag("Person", m.group(1)) + " ", out)
    # кириллическое слово с заглавной внутри НЕМЕЦКОЙ строки (кириллицы в строке < 30 % букв) -- имя (вставка в немецкий текст)
    def _zeile(z):
        zl = z.group(0)
        b = re.findall(r"[A-Za-zÄÖÜäöüßА-Яа-яЁё]", zl)
        if not b or sum(1 for c in b if _KYR.match(c)) >= 0.3 * len(b):
            return zl
        return re.sub(r"(?<![\w\[])[А-ЯЁ][а-яё]{1,14}(?:-[А-ЯЁ][а-яё]+)?(?![\w\]])",
                      lambda m: m.group(0) if RU_KEEP.match(m.group(0)) or m.group(0).casefold() in RU_GEMEIN else tag("Person", m.group(0)), zl)
    out = re.sub(r"(?m)^[^\n]+$", _zeile, out)
    # падежи уже найденных лиц (кириллица): основа каждого слова имени + до четырёх букв окончания, в т.ч. ПРОПИСНЫМИ
    for ph, val in list(mapping.items()):
        if not str(ph).startswith("[Person") or not isinstance(val, str):
            continue
        for w in val.split():
            if re.fullmatch(r"[А-ЯЁ][а-яё]{3,}", w):
                st = re.sub(RU_ENDE, "", w)
                if len(st) >= 4:
                    out = re.sub(rf"(?<![\w\[]){re.escape(st)}[а-яё]{{0,4}}(?![\w\]])", ph, out)
                    out = re.sub(rf"(?<![\w\[]){re.escape(st.upper())}[А-ЯЁ]{{0,4}}(?![\w\]])", ph, out) if len(st) >= 5 else out
    # латинские: имена из списка и частые фамилии, не совпадающие с обычными словами
    out = re.sub(r"(?<![\w\[])[A-ZÄÖÜ][a-zäöüß]{2,}(?![\w\]])", lambda m: tag("Person", m.group(0)) if m.group(0) in LAT_VORNAMEN or m.group(0) in DE_NACHNAMEN else m.group(0), out)
    # (б) склейка «ИмяФамилия» / «ФамилияИмя»: часть -- уже найденное имя лица или имя из списка
    teile = {p.strip(",.;:()").casefold() for k, v in mapping.items() if k.startswith("[Person") and isinstance(v, str) for p in v.split() if len(p.strip(",.;:()")) > 2}
    teile |= {v.casefold() for v in LAT_VORNAMEN | RU_VORNAMEN}
    def _klebe(m):
        a, b = m.group(1), m.group(2)
        return tag("Person", m.group(0)) if a.casefold() in teile or b.casefold() in teile else m.group(0)
    out = re.sub(r"(?<![\w\[])([A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,})([A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,})(?![\w\]])", _klebe, out)
    return out


def anonymize(text, level=None, ner="all"):
    """ner: "all" -- лица, фирмы, места (связный текст); "per" -- только лица (распознанные сканы и бланки:
    на шуме распознавания модель принимает обычные слова за фирмы и места)."""
    level = level or LEVEL
    text = vorbereiten(text, HOMOGLYPH_LOG)
    mapping, counters = {}, {}
    label = {"PER": "Person", "ORG": "Firma", "LOC": "Ort", "GPE": "Ort"}

    def tag(kind, value):
        for k, v in mapping.items():
            if v == value and k.startswith("[" + kind):
                return k
        counters[kind] = counters.get(kind, 0) + 1
        n = counters[kind]
        ph = f"[{kind} {chr(64 + n) if n <= 26 else n}]"
        mapping[ph] = value
        return ph

    # имена из адреса почты (vorname.nachname@...) -- запомнить до удаления адреса
    mail_names = [p for m in re.finditer(r"([\w.+-]+)@", text) for p in re.split(r"[._+-]", m.group(1)) if len(p) > 3 and p.isalpha()]
    out = text
    # суммы защищаются до правил о номерах (08.10.2026: на реальном деле целые части сумм становились «налоговым номером» и «телефоном»,
    # а прибыль и база взноса -- «[Zahl]»): «1.234,56», «615,02», «32.000» остаются как есть на уровне 1
    schutz = []

    def _halt(m):
        schutz.append(m.group(0))
        return f"\x01{len(schutz) - 1}\x02"
    if level == 1:
        out = re.sub(r"(?<![\w.,/-])\d{1,3}(?:\.\d{3})+(?:,\d{2})?(?![\w/]|[.,]\d)|(?<![\w.,/-])\d{1,6},\d{2}(?![\w/]|[.,]\d)", _halt, out)
    out = re.sub(r"((?:\bat |_at_)\d{1,2})\.(\d{2})\.(\d{2})(?=\.\w{2,4}\b|\b)", r"\1:\2:\3", out)       # «… at 11.54.49.ogg» -- время, не дата
    # 19.10.2026 (замечания DeepSeek/Gemini: номер дела суда сразу указывает на дело): номер дела суда («3 K 1234/21», «IX R 7/24», «2 BvR 123/19»).
    # Ссылка на опубликованное решение («vgl. BFH, Urteil vom … – VI R 5/18», «BStBl», «EFG») -- публичный источник: остаётся целиком вместе
    # с названием суда; иначе (Az., Klageverfahren, anhängig, Ihr/unser Zeichen, без признака ссылки) -- собственное дело: номер целиком под метку.
    for m in reversed(list(re.finditer(AZ_GERICHT, out))):
        vor, nach = out[max(0, m.start() - 120):m.start()], out[m.end():m.end() + 40]
        eigen = re.search(r"(?i)\b(?:Az\.?|Aktenzeichen|Klageverfahren|Klage|Verfahren des|Verfahren der|unser\w*|Ihr\w*|Mandant\w*|Revisionsverfahren|"
                          r"Beschwerdeverfahren|Gz\.?|Geschäftszeichen)\b[^.;\n]{0,40}$", vor) or re.match(r"[^.;\n]{0,25}\banhängig", nach)
        oeffentlich = re.search(r"(?:Urteil|Beschluss|Gerichtsbescheid|Entscheidung|Vorlagebeschluss)\s+vom\b[^;\n]{0,40}$|\bvgl\.|\bsiehe\b|\bBStBl\b|"
                                r"BFH/NV|\bEFG\b|\bjuris\b|\bDStR[E]?\b|\bNJW\b|\bHFR\b|\bZfZ\b", vor + " " + nach[:25])
        if oeffentlich and not eigen:
            g = re.search(GERICHT_NAME + r"[^;\n]{0,70}$", vor)
            a = m.start() - (len(vor) - g.start()) if g else m.start()
            out = out[:a] + _halt(re.match(r".*", out[a:m.end()], re.S)) + out[m.end():]
        else:
            out = out[:m.start()] + tag("Aktenzeichen", m.group(0)) + out[m.end():]
    # (1) жёсткие форматы
    out = re.sub(rf"((?i:\bgeb\.|\bgeboren\w*|\bGeburts\w*|\bJahrgang)[^\n\d]{{0,60}}?|(?<!\*)\*(?!\*)\s?)(\d{{1,2}}\.\s?(?:\d{{1,2}}\.|{MONTH})\s?\d{{2,4}})\b",
                 lambda m: m.group(0) if m.group(1).startswith("*") and re.search(r"(?:20[1-9]\d)$", m.group(2))      # «**09.07.2024» -- жирный шрифт, не «*» рождения
                 else m.group(1) + tag("Geburtsdatum", m.group(2)), out)
    # полная дата с годом до 2010 (или двузначным годом 30–99) без пояснения -- скорее всего дата рождения: оставить только год
    out = re.sub(rf"\b\d{{1,2}}\.\s?(?:\d{{1,2}}\.|{MONTH})\s?(19\d{{2}}|200\d)\b", r"im Jahr \1", out)
    out = re.sub(r"\b\d{1,2}\.\d{1,2}\.([3-9]\d)\b", r"im Jahr 19\1", out)
    out = geburtsort(out, tag)
    for rx, kind in HARD:
        out = re.sub(rx, lambda m, kind=kind: tag(kind, m.group(0)), out)
    for rx, kind in HARD_LABEL:
        out = re.sub(rx, lambda m, kind=kind: m.group(1) + tag(kind, m.group(2)), out)
    # выученное на проверках человеком: убирается всегда (пробелы гибкие -- распознавание текста их ломает)
    for x in sorted(load_learned(), key=lambda x: -len(x["text"])):
        rx = r"\s*".join(re.escape(c) for c in x["text"] if not c.isspace()) if len(x["text"]) <= 40 else re.escape(x["text"])
        out = re.sub(rf"(?<![\w\[]){rx}(?![\w\]])", lambda m, k=x["kind"]: tag(k, m.group(0)), out, flags=re.I)
        core = re.sub(r"\s+", "", x["text"])
        if len(core) >= 8 and core.isalpha():        # длинное имя: допускаем до двух ошибок распознавания (l/I, b/Ь, пропуск буквы)
            try:
                import regex
                out = regex.sub(rf"(?<![\w\[])(?:{regex.escape(core)}){{e<=2}}(?![\w\]])", lambda m, k=x["kind"]: tag(k, m.group(0)), out, flags=regex.I)
            except ImportError:
                pass
    # почтовый индекс + место: место запомнить, чтобы убрать и отдельные упоминания
    for m in list(re.finditer(rf"\b(\d{{5}})\s*((?:Bad |St\. |Sankt )?{NAME})", out)):
        if KEEP.match(m.group(2)):                  # «12345 Summe», «40000 Betrag» -- не место
            continue
        ph = tag("Ort", m.group(2))
        out = out.replace(m.group(0), ph).replace(m.group(2), ph)
    if level >= 2:
        out = re.sub(rf"\b\d{{1,2}}\.\s?(?:\d{{1,2}}\.|{MONTH})\s?(\d{{4}})\b", r"im Jahr \1", out)
        out = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2}\b", lambda m: tag("Datum", m.group(0)), out)
    # фирма по правовой форме: «Слово(а) + GmbH / OHG / Sp. z o.o. …» -- название убрать, форму оставить
    form = r"(Aktiengesellschaft|Kommanditgesellschaft|Gesellschaft mit beschränkter Haftung|GmbH\s*&\s*Co\.?\s*KG|GmbH|gGmbH|AG|KG|OHG|UG(?:\s*\(haftungsbeschränkt\))?|GbR|e\.\s?K\.|e\.\s?V\.|eG|SE|PartG(?:\s*mbB)?|Sp\.\s?z\s?o\.\s?o\.|B\.\s?V\.|Ltd\.?|S\.\s?A\.|S\.\s?r\.\s?l\.|Inc\.?|LLC)"
    tok = r"(?!(?:GmbH|gGmbH|AG|KG|OHG|UG|GbR|Co|SE|eG|Aktiengesellschaft)\b)(?:[A-ZÄÖÜ]\.|[A-ZÄÖÜ][\wäöüßÄÖÜ\-]*)"      # «W. Muster GmbH»: инициал с точкой (имитация дела B 16.10.2026)
    for m in list(re.finditer(rf"({tok}(?:\s+(?:{tok}|&|und|\+|mehr)){{0,4}})\s+{form}(?![\w])", out)):
        name_part = re.sub(r"^(?:(?:Die|Der|Das|Den|Dem|Firma|Fa|Bei|Von|Mit|Für|An|Eine|Einer)\s+)+", "", m.group(1))
        if name_part and name_part not in ("Die", "Der", "Das", "Eine", "Firma") and not KEEP.match(name_part.split()[0]) and "[" not in name_part:
            out = out.replace(name_part + " " + m.group(2), tag("Firma", name_part) + " " + m.group(2))
    # название в кавычках перед правовой формой («MUSTER-IMPORT» LLC, „Muster“ GmbH) -- имитация дела B 16.10.2026: правило выше требует заглавную букву в начале
    for m in list(re.finditer(rf"([«„“\"])([^«»„“”\"\n\[\]]{{2,40}})([»“”\"])\s*{form}(?![\w])", out)):
        out = out.replace(m.group(0), tag("Firma", m.group(1) + m.group(2) + m.group(3)) + " " + m.group(4))
    # (2) NER
    out = _mehrsprachig(out, tag, ner)                  # русский и английский текст -- до немецкой модели: на чужом языке она шумит
    res, last = "", 0
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[[^\[\]]+\]", out)]
    fremd = _en_abs(out)                                # английские абзацы и строки с кириллицей немецкой моделью не размечаются
    for m in re.finditer(r"[^\n]*[А-Яа-яЁё]{3,}[^\n]*", out):
        if len(_KYR.findall(m.group(0))) > len(re.findall(r"[A-Za-zÄÖÜäöüß]", m.group(0))):
            fremd.append((m.start(), m.end()))
    _maske = _zellen(out)
    for ent in _nlp()(_maske).ents:
        t = out[ent.start_char:ent.end_char].strip()
        if "\n" in _maske[ent.start_char:ent.end_char].strip() or (ent.label_ == "ORG" and " " not in t and _de_wort(t)):     # через ячейки таблицы; одно обычное слово («Leasing», «Name») -- не имя (имитация дела B 16.10.2026)
            continue
        if ent.label_ not in label or len(t) <= 2 or KEEP.match(t) or all(w.strip(",.;:()") in FACHWORT for w in t.split()) or "[" in t or "]" in t:
            continue
        if _KYR.search(t) or any(a <= ent.start_char < b for a, b in fremd):
            continue
        if ner == "per" and (ent.label_ != "PER" or "\n" in t or not re.fullmatch(rf"(?:{NAME})(?:\s+(?:{NAME})){{1,3}}", t)):
            continue
        if any(a < ent.end_char and ent.start_char < b for a, b in spans):     # не трогать уже поставленные метки
            continue
        if t.startswith("Finanzamt"):
            res += out[last:ent.start_char] + "[Finanzamt]"
            mapping.setdefault("[Finanzamt]", t)
            last = ent.end_char
            continue
        val, suffix = ent.text, ""
        m = LEGAL_FORM.search(val)
        if m:                                   # правовая форма важна для налогового анализа -- оставить
            val, suffix = val[:m.start()], " " + m.group(1)
        res += out[last:ent.start_char] + tag(label[ent.label_], val) + suffix
        last = ent.end_char
    out = res + out[last:]
    # (3) имена по правилам: обращения, подписи, «… und Имя Фамилия», имена из адреса почты
    for rx in (rf"\b(?:Herrn?|Frau|Eheleute|Familie|Dr\.|Prof\.|gez\.|StB|RA|WP|Hr\.|Fr\.)\s+((?:{NAME}\s+){{0,2}}{NAME})",
               rf"\b((?:[A-Z]\.\s?){{1,2}}{NAME})\b",
               rf"(?:Grüßen?|Gruß|LG|VG|MfG)[,!.]?\s+((?:{NAME}\s+){{1,2}}{NAME})",
               rf"\]\s+und\s+({NAME}\s+{NAME})", rf"\[Person [A-Z]\]\s+({NAME})\b",
               # 19.10.2026 (остатки wild): «Kanzlei-MA: Stefanie Müller», «Prüfer hr. schuster» (строчными в переписке)
               rf"(?:\b[\w-]*-MA|Mitarbeiter(?:in)?|Sachbearbeiter(?:in)?|Bearbeiter(?:in)?|Ansprechpartner(?:in)?|Gesprächspartner(?:in)?|Prüfer(?:in)?)\s*:\s*((?:{NAME}\s+){{0,2}}{NAME})",
               r"\b(?:[Hh]r|[Ff]r)\.\s+([a-zäöü][a-zäöüß]{3,})\b"):
        for m in list(re.finditer(rx, out)):
            val = m.group(1)
            if re.search(r"(?:SGB|Buch|Teil|Abschnitt|Kapitel|Anlage|Nr\.|Art\.) $", out[max(0, m.start(1) - 9):m.start(1)]) and re.match(r"[IVX]\.", val):
                continue
            if "[" not in val and not KEEP.match(val.split()[0]) and val not in ("und", "aus"):
                out = re.sub(rf"(?<![\[\w]){re.escape(val)}(?![\w\]])", tag("Person", val), out)
    for p in mail_names:
        for m in set(re.findall(rf"\b{re.escape(p)}\w*\b", out, re.I)):
            if m[0].isupper() and not KEEP.match(m):
                out = out.replace(m, tag("Person", m))
    if level >= 2:
        out = re.sub(r"\b(BMW|Mercedes(?:-Benz)?|Audi|Volkswagen|VW|Porsche|Tesla|Opel|Ford|Toyota|Skoda|Škoda|Renault|Peugeot|Volvo|"
                     r"Hyundai|Kia|Mazda|Nissan|Fiat|Seat|Mini|Smart)\b(\s+[A-Z]?\d\w*|\s+[A-Z][a-z]+\b)?", "[Fahrzeug]", out)
    # (4) повторные упоминания: каждая часть имени/названия, в т.ч. с окончанием родительного падежа
    for ph, val in list(mapping.items()):
        if not ph.startswith(("[Person", "[Firma", "[Ort")):
            continue
        for part in re.split(r"[\s]+", val):
            part = part.strip(",.;:()")
            if len(part) > 3 and part[0].isupper() and not KEEP.match(part) and not re.fullmatch(r"(Bäckerei|Autohaus|Praxis|Friseursalon|Ristorante|"
                                                                                                r"Consulting|Logistik|Haustechnik|Immobilienverwaltung|Söhne|Bau)", part) \
                    and not (ph.startswith(("[Firma", "[Ort")) and _de_wort(part)):     # обычное слово из названия фирмы («Leasing» из «VW Leasing») -- не по всему тексту (имитация дела B 16.10.2026); у лиц фамилия-слово закрывается по-прежнему
                out = re.sub(rf"(?<!\[)\b{re.escape(part)}(?:s|'s|’s)?\b(?! [A-Z0-9]+\])", ph, out)
                out = re.sub(rf"(?<!\[)\b{re.escape(part.upper())}(?:S)?\b(?! [A-Z0-9]+\])", ph, out) if ph.startswith("[Person") and len(part) > 3 else out   # 19.10: «HABERMEHL»
    out = _luecken_31_10(out, tag, mapping)
    # 19.10.2026 (атаки, «одна маска = одно лицо»): если распознавание имён раньше дало части имени лица другую метку
    # («der Mandant HABERMEHL» -> [Ort A]), эта метка заменяется меткой лица; значение остаётся в таблице под служебным ключом для контроля
    teile = {}
    for ph, val in mapping.items():
        if ph.startswith("[Person"):
            for part in val.split():
                if len(part.strip(",.;:()")) > 3:
                    teile[part.strip(",.;:()").casefold()] = ph
    for ph, val in list(mapping.items()):
        if ph.startswith(("[Ort", "[Firma")) and isinstance(val, str) and re.sub(r"(?:s|'s|’s)$", "", val.strip()).casefold() in teile:
            person = teile[re.sub(r"(?:s|'s|’s)$", "", val.strip()).casefold()]
            out = out.replace(ph, person)
            mapping[person + "#" + ph.strip("[]")] = mapping.pop(ph)
    out = re.sub(r"(\[Person [A-Z0-9]+\])(?:\s+\1)+", r"\1", out)
    if level == 1:                               # минимум: суммы и даты остаются, длинные номера без пояснения -- нет
        for m in reversed(list(re.finditer(r"(?<![\w\[.,])(?<!\d[.,] )\d(?:\d|[ /-]{1,3}(?=\d))*\d(?![\w]|,\d|\.\d)", out))):
            t = m.group(0)
            # год и час в строке письма («2. Dezember 2024 10:41», «Gesendet: … 2024 10:41»): дата, а не длинный номер (стенд на имитации C 12.10.2026: год терялся в 28 письмах)
            if re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", t):      # месяц «2022-10» -- период, не номер (имитация дела B 16.10.2026)
                continue
            if re.fullmatch(r"(?:19|20)\d{2} {1,2}\d{1,2}", t) and re.match(r"[:.]\d{2}", out[m.end():m.end() + 3]):
                continue
            t = m.group(0)
            # официальные номера актов ЕС («2006/112/EG», «(EU) 2016/679») и дел EuGH («C-726/23») -- публичные ссылки, не данные клиента
            if re.match(r"^/(EG|EU|EWG|EGV|Euratom)\b", out[m.end():m.end() + 9]) or re.search(r"\b[CT]-$", out[max(0, m.start() - 2):m.start()]) \
                    or re.search(r"\((EU|EG|EWG)\)\s*(Nr\.\s*)?$", out[max(0, m.start() - 12):m.start()]):
                continue
            if len(re.sub(r"\D", "", t)) >= 5 and not re.match(r"\s*(€|EUR|Euro|T€|km|qm|евро|руб|тыс|млн)", out[m.end():m.end() + 8]) \
                    and not re.search(r"(EUR|€)\s*$", out[max(0, m.start() - 5):m.start()]) and not any(a <= m.start() < b for a, b in
                                                                                                    [(x.start(), x.end()) for x in re.finditer(r"\[[^\[\]]+\]", out)]):
                out = out[:m.start()] + tag("Zahl", t) + out[m.end():]
        out = re.sub(r"\x01(\d+)\x02", lambda m: schutz[int(m.group(1))], out)
        if "@" in out:                                                   # всё, что осталось перед «@», -- часть адреса почты
            out = re.sub(r"[\w.+-]{2,} ?@ ?[\w.-]*", lambda m: tag("E-Mail", m.group(0)), out)
        return out, mapping
    # (5) точные суммы -> округлённые
    def _round(m):
        v = int(m.group(1).replace(".", ""))
        if v < 1000:
            return m.group(0)
        mag = 10 ** (len(str(v)) - 2)
        txt = f"rund {round(v / mag) * mag:,} {m.group(2)}".replace(",", ".")
        mapping.setdefault(txt, m.group(0))
        return txt
    out = re.sub(r"\b(\d{1,3}(?:\.\d{3})+|\d{4,})(?:,\d+)?\s*(EUR|Euro|€)", _round, out)
    out = re.sub(r"\b(EUR|€)\s*(\d{1,3}(?:\.\d{3})+|\d{4,})(?:,\d+)?", lambda m: _round(_Swap(m)), out)

    def _round_k(m):                             # «34 T€», «1,2 Mio. €» -> одна значащая цифра
        v = float(m.group(1).replace(".", "").replace(",", "."))
        mag = 10 ** max(len(str(int(v))) - 1, 0)
        txt = f"rund {int(round(v / mag) * mag)} {m.group(2)}"
        mapping.setdefault(txt, m.group(0))
        return txt
    out = re.sub(r"\b(\d{1,3}(?:[.,]\d+)?)\s*(T€|TEUR|Tsd\.?\s*(?:€|EUR|Euro)|Mio\.?\s*(?:€|EUR|Euro))", _round_k, out)
    # (6) остаточные числа: всё, что не похоже на ссылку на норму, год, процент или округлённую сумму, -- убрать.
    #     Это страховка от форматов, которых нет в правилах (телефон в непривычной записи, дата, номер договора).
    if level >= 3:                               # суммы -> порядок величины; годы и все прочие числа убрать
        out = re.sub(r"rund (\d[\d.]*) (EUR|Euro|€|T€|TEUR)", lambda m: "ein " + {4: "vier", 5: "fünf", 6: "sechs", 7: "sieben", 8: "acht"}.get(
                         len(m.group(1).replace(".", "")) + (3 if m.group(2) in ("T€", "TEUR") else 0), "mehr") + "stelliger Betrag", out)
    for m in reversed(residual_numbers(out, strict=level >= 3)):
        out = out[:m.start()] + tag("Zahl", m.group(0)) + out[m.end():]
    out = re.sub(r"\x01(\d+)\x02", lambda m: schutz[int(m.group(1))], out)
    return out, mapping


class _Swap:
    """Сумма в записи «EUR 311.924,74»: подать в _round как (число, валюта)."""
    def __init__(self, m):
        self.m = m

    def group(self, i):
        return self.m.group(0) if i == 0 else self.m.group(2) if i == 1 else self.m.group(1)


_NUM_OK_BEFORE = re.compile(r"(§+|Abs\.|Absatz|Nr\.|Nummer|Satz|S\.|Art\.|Artikel|Buchst\.|Tz\.|Rz\.|Rn\.|R|H|Abschn\.|Abschnitt|Anlage|Zeile|Kz\.?|Kennzahl|"
                            r"SKR|Konto|Konten|rund|ca\.|etwa|Jahr|Jahre|Jahren|VZ|seit|bis|ab|von|vor|nach|in|im|für|und|oder|Quelle|BStBl|BGBl|[IVX]+)\s*$")
_NUM_OK_AFTER = re.compile(r"^\s*(%|Prozent|v\.\s?H\.|Jahre?n?|Monate?n?|Wochen?|Tage?n?|Stunden?|km|qm|m²|kW|Abs\.|Nr\.|Satz|EStG|UStG|AO|KStG|GewStG|HGB|BGB|"
                           r"ErbStG|GrEStG|UStAE|EStR|EStH|LStR|Mitarbeiter\w*|Gesellschafter\w*|Personen|Fahrzeuge?n?|Wohnungen|Kinder\w*|Fälle\w*|Rechnungen|"
                           r"€|EUR|Euro|T€|TEUR|Mio|евро|руб\w*|тыс\.?|млн\.?|[a-z]?\s*(EStG|UStG|AO|KStG|HGB))")


def residual_numbers(text, strict=False):
    """Числа, которые не объяснены налоговым контекстом (норма, год, процент, срок, количество, округлённая сумма)."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[[^\[\]]+\]", text)]
    out = []
    for m in re.finditer(r"(?<![\w\[])\(\d[\d ./()-]*\d\)?(?!\w)|(?<![\w\[])\d[\d ./-]*\d(?!\w)|(?<![\w\[])\d(?!\w)", text):
        t = m.group(0)
        if any(a <= m.start() < b for a, b in spans):
            continue
        digits = re.sub(r"\D", "", t)
        before, after = text[max(0, m.start() - 14):m.start()], text[m.end():m.end() + 16]
        # официальные номера актов ЕС («Richtlinie 2006/112/EG», «VO (EU) 2016/679») и дел EuGH/EuG («C-726/23») -- не данные клиента
        if not strict and (re.match(r"^/(EG|EU|EWG|EGV|Euratom)\b", after) or re.search(r"\b[CT]-$", before)
                           or re.search(r"\((EU|EG|EWG)\)\s*(Nr\.\s*)?$", before)):
            continue
        simple = re.fullmatch(r"\d{1,4}(?:[.,]\d{1,2})?", t)        # длинные и составные номера контекст не оправдывает
        if strict:
            if simple and (re.search(r"(§+|Abs\.|Nr\.|Satz|Art\.|Buchst\.)\s*$", before) or re.match(r"^\s*(%|Prozent|[a-z]?\s*(Abs\.|EStG|UStG|AO|KStG|HGB))", after)):
                continue
            out.append(m)
            continue
        if re.fullmatch(r"(19|20)\d{2}", t) or (simple and (_NUM_OK_BEFORE.search(before) or _NUM_OK_AFTER.match(after))):
            continue
        if len(digits) <= 2 and re.fullmatch(r"\d{1,2}", t):          # одиночное малое число («3 Fahrzeuge», «zum 1.»)
            continue
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t) and text[max(0, m.start() - 5):m.start()].strip().endswith("rund"):
            continue
        out.append(m)
    return out


_DE_WORT = []


def _gemeinwort_im_text(p, text):
    """Часть ложного «имени» («B. Lohn», «Schreiben Mustermann») -- обычное слово, а не остаток имени (стенд на имитации C 12.10.2026: 15 остановок контроля
    на словах «Lohn», «Krankengeld», «Satz»). Условия все сразу: слово есть в словаре базы права; в тексте нигде не стоит после «Herr/Frau/Familie»;
    там, где оно стоит отдельно, немецкая модель видит нарицательное, а не имя собственное (до восьми мест); там, где оно начало более длинного
    слова, это слово тоже словарное («Kreditinstitut»). Иначе -- остаток, контроль останавливает."""
    if not _DE_WORT:
        import gzip
        f = Path(__file__).parent / "de_wortliste.txt.gz"
        _DE_WORT.append(set(gzip.open(f, "rt", encoding="utf-8").read().split("\n")) if f.exists() else set())
    W = _DE_WORT[0]
    p = p.strip(".,;:()")
    if len(p) < 4 or p.lower() not in W or re.search(rf"\b(?:Herrn?|Frau|Hr\.|Fr\.|Familie|Eheleute)\s+{re.escape(p)}\b", text):
        return False
    for m in re.finditer(rf"\b{re.escape(p)}([A-Za-zÄÖÜäöüß-]+)", text):          # начало более длинного слова
        if (p + m.group(1)).lower().strip("-") not in W and (p + m.group(1)).lower().rstrip("sne") not in W:
            return False
    nlp = _nlp()
    for k, m in enumerate(re.finditer(rf"(?<![\w\[]){re.escape(p)}(?![\w\]-])", text)):
        if k >= 8:
            break
        a, b = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
        zeile = re.sub(r"\[[^\]\n]{1,40}\]", "Herr Mustermann", text[max(a, m.start() - 120): (b if b >= 0 else len(text))][:260])
        if any(t.text == p and t.pos_ == "PROPN" for t in nlp(zeile)):
            return False
    return True


def _wort_bekannt(tok):
    """Целое слово -- обычное слово языка: немецкое из словаря базы права или русское, известное словарю не как имя/фамилия."""
    if re.fullmatch(r"[A-Za-zÄÖÜäöüß]+", tok):
        return _de_wort(tok) or _de_kompositum(tok)
    if re.fullmatch(r"[А-Яа-яЁё]+", tok):
        global _MORPH
        if _MORPH is None:
            try:
                import pymorphy3
                _MORPH = pymorphy3.MorphAnalyzer()
            except Exception:
                _MORPH = False
        if _MORPH:
            ps = [x for x in _MORPH.parse(tok.casefold()) if x.is_known]
            return bool(ps) and not any(g in x.tag for x in ps for g in ("Name", "Surn", "Patr"))
    return False


def _de_kompositum(w):
    """Немецкое сложное слово из двух слов словаря, в том числе с соединительным «s» и оборванным распознаванием концом
    («Veranstaltungs|charakter», «Veranlagungs|zeitr»: вторая часть -- начало слова словаря от четырёх букв)."""
    import bisect
    wl = w.casefold()
    if len(wl) < 9 or not re.fullmatch(r"[a-zäöüß]+", wl):
        return False
    if not _DE_WORT:
        _de_wort("x")
    if not hasattr(_de_kompositum, "sl"):
        _de_kompositum.sl = sorted(_DE_WORT[0])
    sl = _de_kompositum.sl

    def anfang(b):
        i = bisect.bisect_left(sl, b)
        return i < len(sl) and sl[i].startswith(b)
    for i in range(4, len(wl) - 3):
        a, b = wl[:i], wl[i:]
        if _de_wort(a) or (a.endswith("s") and _de_wort(a[:-1])) or ("graf" in a and _de_wort(a.replace("graf", "graph"))):     # Choreografie = Choreographie
            if _de_wort(b) or (len(b) >= 4 and anfang(b)):
                return True
    return False


def _gemein_kontext(p, text):
    """31.10.2026, итерация 3: часть ложного «имени» («Araup Senior») -- слово словаря, которое в этом же тексте стоит со строчной буквы
    или частью составного через дефис («Senior-innen»): обычное слово. Имя из списков (LAT_VORNAMEN, DE_NACHNAMEN) так не снимается."""
    p = p.strip(".,;:()")
    if not re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß]{3,}", p) or p in LAT_VORNAMEN or p in DE_NACHNAMEN or not _de_wort(p):
        return False
    return bool(re.search(rf"(?<![\w\[]){re.escape(p.lower())}(?![\w\]])|(?<![\w\[]){re.escape(p)}-[a-zäöü]|-{re.escape(p)}(?![\w\]])", text))


def _teil_treffer(p, text):
    """Часть имени лица стоит в тексте: отдельным словом или началом слова («Habermehls», «Мустерманной»). 31.10.2026, итерация 3:
    начало слова, которое целиком -- обычное слово («Vera» в «Veranstaltung», «Верн» в «вернула»), остатком не считается."""
    if not p[:1].isupper():
        return bool(re.search(rf"\b{re.escape(p)}(?![a-zäöüß])", text))
    for m in re.finditer(rf"\b{re.escape(p)}([\w]*)", text):
        if not m.group(1) or not _wort_bekannt(m.group(0)):
            return True
    return False


def guard(text, mapping, level=None):
    """Контроль исходящего текста: ничего из таблицы соответствия и никаких данных жёсткого формата. Возвращает нарушения."""
    # 19.10.2026: невидимые знаки внутри слова и слова из смеси латиницы с кириллицей в исходящем тексте -- сами по себе нарушение
    # (мягкий перенос и перенос строки в текстах норм из базы -- обычное дело, нарушением не считаются); проверка идёт по нормализованному тексту
    bad_vor = (["невидимый знак внутри слова"] if re.search("\\w[\u200b-\u200f\u2060-\u2064\ufeff\u034f\u180e]\\w", text) else []) + \
              (["слово из смеси латиницы и кириллицы"] if re.search(r"[A-Za-z][\u0400-\u04ff]|[\u0400-\u04ff][A-Za-z]", text) else [])
    text = vorbereiten(text)
    low = text.lower()
    mapping = {k: (v.strip() if isinstance(v, str) else v) for k, v in mapping.items()}
    mapping = {k: v for k, v in mapping.items() if not (isinstance(v, str) and v and all(w in FACHWORT for w in v.split()))}   # 31.10: Spagat, Pirouette …      # значение с пробелом по краям не совпадало с текстом (BIC в начале строки, 08.10.2026)
    bad = [v for k, v in mapping.items() if not k.startswith("rund") and len(v) > 3 and not (" " not in v.strip() and KEEP.match(v.strip())) and
           (re.search(rf"(?<![\wäöüÄÖÜß\[]){re.escape(v.strip())}(?![\wäöüÄÖÜß\]])", text, 0 if any(len(w) < 3 for w in v.split()) else re.I) if " " in v.strip()     # 17.10, имитация дела А: «A Ba» не в «da balance» и (короткие части -- с учётом регистра) не в «nach a ba»
            else re.search(rf"(?<![\wäöüÄÖÜß\[]){re.escape(v.strip())}(?![\wäöüÄÖÜß\]])", text))]
    # номера (шесть цифр и больше) ищутся и вплотную к буквам: распознавание склеивает «KVNR» с номером (остаток Салона 08.10.2026)
    bad += [v for k, v in mapping.items() if not k.startswith(("rund", "[Zahl", "[Betrag", "[Datum")) and " " not in v.strip() and len(v.strip()) >= 7
            and sum(c.isdigit() for c in v) >= 6 and v not in bad and v.strip().lower() in low]
    for k, v in mapping.items():                       # отдельные части имён
        if k.startswith("[Person"):
            # 31.10.2026, итерация 3: термины гимнастики (FACHWORT) не считались остатком только как целое значение; часть ложного «имени»
            # («B. Spagat», «Li Keule») останавливала контроль -- теперь и часть
            bad += [p for p in v.split() if len(p) > 3 and not KEEP.match(p) and p.strip(".,;:()") not in FACHWORT and _teil_treffer(p, text) and not _gemeinwort_im_text(p, text) and not _gemein_kontext(p, text)]   # обычное слово в ложном «имени» -- не остаток; строчная часть («anna») -- только отдельным словом, не в «annahme» (17.10)
    for rx, kind in HARD_LABEL:                      # 19.10.2026
        if any("[" not in m_.group(2) for m_ in re.finditer(rx, text)):
            bad.append(kind)
    for rx, kind in HARD:
        for m_ in re.finditer(rx, text):
            if kind == "Kennzeichen" and re.match(r",\s?(\[|\d)", text[m_.end():m_.end() + 3]):      # «LV 200,53» в выписке -- сумма, не номер автомобиля
                continue
            if kind == "Telefon" and (re.match(r",\d{2}(?!\d)", text[m_.end():m_.end() + 4]) or re.search(r" \d{1,6}$", m_.group(0)) and re.match(r",\d{2}", text[m_.end():m_.end() + 3])):
                continue                                                 # «0500 35,40» в ведомости -- код строки и сумма, не телефон
            bad.append(kind)
            break
    level = level or LEVEL
    if level >= 2 and re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", text):
        bad.append("точная дата")
    if re.search(r"\b\d{5}\s+[A-ZÄÖÜ]", text):
        bad.append("PLZ")
    if level >= 2:
        bad += ["число вне налогового контекста: " + m.group(0) for m in residual_numbers(text, strict=level >= 3)]
    try:                                              # 19.10.2026: указания для модели внутри материалов (инъекция) -- только с явного одобрения человека
        import versteckt
        bad += [f"указание для модели в материалах дела: «{h}»" for _, h in versteckt.injektion(text)[:5]]
    except ImportError:
        pass
    return bad_vor + bad


_ABK = r"(?:Gesch|Verb|Ford|Aufw|Abschr|Sonst|Betr|Rückst|Umsatzst|Vorst|Verr|Kto|Nr|Abs|Art|Buchst|bzw|ggf|inkl|zzgl|evtl|Tel|Str|Steuerber|Buchf|Verw|Vers|Beitr|Abr|lfd|usw|Dipl|Dr|Prof|St|Kfz|Betriebs|Rechts|Lohn|Geh)"
MERKMALE = [   # вторая ступень контроля, независимая от списка замен: признаки персональных данных в готовом тексте (предложение Салона 09.10.2026)
    ("обращение + слово без метки", r"\b(?:Herrn?|Frau)\s+(?!\[)([A-ZÄÖÜ][a-zäöüß]{2,})"),
    ("буквы вплотную к метке лица", r"\[(?:Mandant|Mandantin|Person|Ehegatte)[^\]]*\][a-zäöüßа-яё]{1,8}\b"),
    ("слово.слово (учётная запись?)", rf"(?<![\w@/.])(?!{_ABK}\.)[A-Za-zÄÖÜäöüß]{{3,}}\.[a-zäöüß]{{5,}}(?![\w.])"),
    ("число от семи цифр без метки", r"(?<![A-Za-z\d.,\[/-])(?<!\(0800\) )(?<!0800 )\d{7,}(?![\d]|[.,]\d)"),      # не считаются: номер внутри имени файла, бесплатная справочная 0800
    ("индекс + город", r"\b\d{5} ?[A-ZÄÖÜ][a-zäöüß]{3,}"),
    ("улица + номер дома", r"[A-ZÄÖÜ][a-zäöüß]+(?:straße|strasse|str\.|weg|platz|allee|gasse|ring|damm) ?\d"),
    ("адрес через запятые после метки", r"\[(?:Ort|Adresse|PLZ)[^\]]*\](?:, ?(?:\[(?!Hausnr)[^\]]{2,30}\]|[A-ZÄÖÜ][a-zäöüß.-]{2,}(?: [A-ZÄÖÜa-zäöüß.-]{2,}){0,2})){1,3}, ?\d{1,4}[a-z]?\b(?![.,]\d)"),      # цепочка с уже поставленной «[Hausnr.]» -- не остаток
    ("фамилия + сокращение должности", r"(?<![\w\[])[A-ZÄÖÜ][a-zäöüß-]{2,}, ?(?:PK|POK|PHK|EPHK|KK|KOK|KHK|EKHK|PM|POM|PHM|PKin|POKin|PHKin|KKin|KOKin|KHKin|PMin|POMin|PHMin|PKA|KKA|ROI|RAR|RR|ORR|StI|StOI|StAR|StAF|VA|RI|ROS)\b"),
    ("название улицы отдельным словом", r"(?<![\w\[])(?!(?:Rechts|Dienst|Um|Klage|Post|Instanzen|Verwaltungs|Zahlungs|Schrift|Aus|Heim|Rück|Hin|Fahr|Arbeits|Stell|Park|Sitz|Markt|Ein|Zu)(?:weg|platz|gasse|ring|damm)\b)[A-ZÄÖÜ][a-zäöüß]{3,}(?:straße|strasse|allee|gasse)\b"),
]


def _merkmal_ocr_wort(name, m_):
    """31.10.2026, итерация 4: «слово.слово» из распознанной буквы «ü» («Buchfi.ihrung», «fi.ir» = «Buchführung», «für»): ложная тревога,
    если после замены «i.i»/«i.» на «ü» получилось немецкое слово. Иначе признак остаётся."""
    if not name.startswith("слово.слово"):
        return False
    w = m_.group(0)
    for a in ("i.i", "i.", ".i"):
        if a in w and _dt_wort(w.replace(a, "ü", 1)):
            return True
    return False


def merkmale(text):
    """-> {признак: число мест}. Значений не возвращает. Обычные слова после «Herr/Frau» (роли, KEEP) не считаются."""
    out = {}
    for name, rx in MERKMALE:
        n = 0
        for m_ in re.finditer(rx, text):
            if name.startswith("обращение") and KEEP.match(m_.group(1)) or _merkmal_ocr_wort(name, m_):
                continue
            n += 1
        if n:
            out[name] = n
    return out


def merkmale_orte(text):
    """Где сработали признаки: [(признак, «Dokument N», страница или None)] -- чтобы проверяющий не искал по всему листу. Значений не возвращает."""
    out = []
    for name, rx in MERKMALE:
        for m_ in re.finditer(rx, text):
            if name.startswith("обращение") and KEEP.match(m_.group(1)) or _merkmal_ocr_wort(name, m_):
                continue
            kopf = re.findall(r"(?m)^## Dokument (\d+)", text[:m_.start()])
            teil = text[text.rfind("## Dokument", 0, m_.start()) if "## Dokument" in text[:m_.start()] else 0: m_.start()]
            seite = re.findall(r"--- Seite (\d+) ---", teil)
            out.append((name, kopf[-1] if kopf else None, seite[-1] if seite else None))
    return out


def fingerprint(text):
    """Короткая контрольная сумма обезличенного текста: одобрение действует только для этого текста."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def review(anon, mapping, level=None):
    """Лист проверки для человека: что уйдёт наружу, что заменено, что насторожило автоматику."""
    level = level or LEVEL
    kinds = {}
    for ph in mapping:
        if ph.startswith("["):
            k = re.sub(r" [A-Z0-9]+\]$", "]", ph)
            kinds[k] = kinds.get(k, 0) + 1
    bad = guard(anon, mapping, level)
    # подсказки глазу: то, что автоматика не считает нарушением, но человек должен посмотреть
    hints = sorted(set(re.findall(r"\b\d[\d ./-]{4,}\d\b", anon)) | set(re.findall(r"\b[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)+\b", anon)))
    try:
        gef = {}
        # 11.10.2026: русские строки читает русская модель (немецкая на русском тексте принимала за имя любую фразу с заглавной буквы:
        # 1049 записей на одном деле); если русской модели нет -- русские строки немецкой модели не показываются вовсе
        zl = anon.split("\n")
        ru_t = "\n".join(l for l in zl if len(_KYR.findall(l)) >= 3)
        de_t = "\n".join(l for l in zl if len(_KYR.findall(l)) < 3)
        for nlp_, txt in ((_nlp(), de_t), (_nlp_x("ru") if ru_t else None, ru_t)):
            if nlp_ is None or not txt:
                continue
            nlp_.max_length = max(nlp_.max_length, len(txt) + 1)
            for e in nlp_(txt).ents:
                if e.label_ in ("PER", "ORG", "LOC") and "[" not in e.text and len(e.text) > 3 and "\n" not in e.text:
                    tx = " ".join(e.text.split())
                    gef[tx] = min(gef.get(tx, 9), {"PER": 0, "LOC": 1, "ORG": 2}[e.label_])
        # 11.10.2026: список шёл по алфавиту и обрезался на 40 -- проверяющий видел только слова на A–E. Теперь сначала лица, затем места,
        # затем организации; внутри -- сначала записи, по виду похожие на имя (слова с заглавной буквы без мусора распознавания)
        sauber = lambda x: not re.fullmatch(r"(?:[A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,}|[A-ZÄÖÜ]{3,})(?:[ -](?:[A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,}|[A-ZÄÖÜ]{3,})){0,2}", x)      # noqa: E731
        ents = sorted(gef, key=lambda x: (gef[x], sauber(x), x))
    except Exception:
        ents = []
    legal = legal_ner_hints(anon)
    # род занятий (решение владельца проекта 11.10.2026: пока только помечать проверяющему; замена -- на отрасль: «сфера услуг», «пищевая промышленность»…):
    # занятие вместе с городом сужает круг лиц (слепой опыт 11.10.2026), метками это не закрывается
    BERUF = re.compile(r"(?i)\b(tätig(?:keit)? als|arbeitet als|beschäftigt als|selbst[äa]ndige?r? \w+|freiberuflich\w* \w+|beruf(?:sbezeichnung)?:|gewerbe:|betreibt (?:ein|eine|einen)|inhaber(?:in)? (?:eines|einer)|"
                       r"\w+(?:trainer|lehrer|berater|meister|händler|friseur|fahrer|pfleger|arzt|ärztin|anwalt|anwältin)(?:in)?\b|работа\w+ (?:как|в качестве)|род занятий|професси\w+|занима\w+ся|"
                       r"\w*(?:тренер|преподавател|парикмахер|водител|мастер|врач|юрист)\w*)")
    beruf = list(dict.fromkeys(" ".join(l.split())[:110] for l in anon.split("\n") if BERUF.search(l)))
    L = [f"# Проверка перед отправкой наружу (уровень строгости {level}, код текста {fingerprint(anon)})", "",
         "## Этот текст уйдёт внешней модели", "", anon, "",
         "## Заменено", "", ", ".join(f"{k} × {n}" for k, n in sorted(kinds.items())) or "ничего", "",
         "## Автоматический контроль", "", ("ОСТАНОВЛЕНО: " + "; ".join(map(str, bad))) if bad else "нарушений не найдено", "",
         "## Посмотрите глазами (автоматика не уверена)", "",
         (f"имена/названия по словарю модели (сначала лица, затем места, затем организации; показано {min(len(ents), 200)} из {len(ents)}): " + ", ".join(ents[:200])) if ents else "имён и названий модель не видит",
         ("числа и составные слова: " + ", ".join(hints[:40])) if hints else "",
         (f"род занятий в открытом виде (вместе с местом сужает круг лиц; при необходимости заменить на отрасль) -- строк {len(beruf)}, первые:\n  - " + "\n  - ".join(beruf[:12])) if beruf else "",
         ("юридическая модель распознавания (лица, фирмы, места; опыт 05.10.2026: ловит 6 из 7 пропусков, ~1 лишняя пометка на письмо): "
          + ", ".join(legal[:40])) if legal else ""]
    return "\n".join(L), bad


_LEGAL_NER = None


def legal_ner_hints(anon, limit=40000):
    """Подсказки проверяющему от немецкой юридической модели (PaDaS-Lab/gbert-legal-ner): только пометки, автоматических замен нет.
    Модель локальная; если её нет на диске или нет torch -- подсказок просто нет."""
    global _LEGAL_NER
    try:
        if _LEGAL_NER is None:
            from transformers import pipeline
            _LEGAL_NER = pipeline("token-classification", model="PaDaS-Lab/gbert-legal-ner", aggregation_strategy="simple", device=-1)
        out, seen = [], set()
        text = anon[:limit]
        for k in range(0, len(text), 1800):                      # окно модели ~512 токенов
            for e in _LEGAL_NER(text[k:k + 1900]):
                w = e["word"].strip()
                if e["entity_group"] in ("PER", "RR", "AN", "UN", "ORG", "INN", "ST", "STR", "LD", "LDS") and len(w) > 3 \
                        and "[" not in w and "]" not in w and "#" not in w and w.lower() not in seen and not KEEP.match(w):
                    seen.add(w.lower())
                    out.append(w)
        return out
    except Exception:
        return []


def confirm(anon, mapping, level=None, approve=None, pending_dir="pipeline_runs"):
    """Подтверждение человеком. Возвращает (разрешено, кто/как одобрил).
    approve: None -- спросить в терминале (без терминала -- сохранить лист проверки и отказать);
             "<код текста>" -- одобрение заранее, действует только если код совпал с текстом;
             "auto" -- без человека (только для испытаний на придуманных случаях; пишется в журнал как auto)."""
    import os
    import sys
    sheet, bad = review(anon, mapping, level)
    fp = fingerprint(anon)
    force = bool(approve) and approve != "auto" and approve.endswith("!")     # «код!» -- человек видел предупреждения контроля и принял их
    if force:
        approve = approve[:-1]
    if bad and not (force and approve == fp):
        return False, "guard: " + "; ".join(map(str, bad)) + f" -- если это ложные срабатывания, одобрите как {fp}! (с восклицательным знаком)"
    if force and approve == fp:
        return True, f"человек, код {fp}, предупреждения контроля приняты: " + "; ".join(sorted(set(map(str, bad))))[:300]
    if approve == "auto":
        return True, "auto (испытание, без человека)"
    if approve:
        return (True, f"человек, код {fp}") if approve == fp else (False, f"код одобрения {approve} не совпал с текстом ({fp}) -- текст изменился")
    if sys.stdin.isatty():
        print(sheet, file=sys.stderr)
        ans = input("\nОтправить этот текст внешней модели? [j/N] ").strip().lower()
        if ans in ("j", "ja", "y", "yes", "д", "да"):
            return True, f"человек в терминале, код {fp}"
        miss = input("Что пропущено? Впишите точно как в тексте, через «;» (пусто -- ничего): ").strip()
        if miss:
            kind = input("Вид данных [Person/Firma/Ort/Kennung] (по умолчанию Person): ").strip() or "Person"
            n = learn(miss.split(";"), kind, anon)
            return False, f"человек отказал; выучено новых: {n} -- запустите ещё раз"
        return False, "человек отказал"
    os.makedirs(pending_dir, exist_ok=True)
    path = os.path.join(pending_dir, f"pending_{fp}.md")
    open(path, "w", encoding="utf-8").write(sheet)
    return False, f"нужно подтверждение: прочитайте {path} и повторите запуск с --approve {fp}"
