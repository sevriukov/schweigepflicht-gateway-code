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

Уровень строгости (решение автора 02.10.2026: в работе -- необходимый минимум, строгий -- по настройке):
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
    # учётная запись сотрудника в подвале распечатки («Währung: EUR vorname.nachname Seite 1») и после слов «Benutzer», «Bearbeiter» -- имитация дела А 08.10.2026
    (r"(?<=Währung: EUR )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}", "Kennung"),
    (r"(?<![\w@/.])[A-Za-zÄÖÜäöüß]{2,}\.[a-zäöüß]{3,}(?= Seite \d)", "Kennung"),
    (r"(?<=Benutzer: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Benutzer )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Bearbeiter: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}|(?<=Kennung: )[A-Za-zÄÖÜäöüß]{2,}\.[A-Za-zÄÖÜäöüß]{3,}", "Kennung"),
    (r"[\w.+-]+ ?@ ?[\w-]+(?: ?\. ?[\w-]+)+", "E-Mail"),                                 # с пробелами распознавания вокруг «@» и точек
    (r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b", "IBAN"),
    (r"\b(?:AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK)[ ]?[A-Z0-9]{8,12}\b(?<=\d)", "USt-IdNr"),
    (r"(?<=BIC[: ])\s*[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b|(?<=BIC: )\s*[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", "BIC"),
    (r"\b\d{2,3}/\d{3,4}/\d{4,5}\b|\b\d{13}\b", "Steuernummer"),
    (r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b", "Steuer-ID"),
    (r"(?<![\w/+])(?:\+49[ ]?(?:\(0\))?[ ]?|0049[ ]?|\(0\d{2,5}\)[ ]?|0)\d{2,5}(?:[ /-]{0,2}\d{2,9}){1,4}(?![\w/])", "Telefon"),
    (r"\b[A-ZÄÖÜ]{1,3}-[A-Z]{1,2}[ ]?\d{1,4}[EH]?\b|\b(?![IVX]+ )[A-ZÄÖÜ]{1,3} (?!R |B |S |ZR |AR )[A-Z]{1,2} \d{1,4}[EH]?\b(?![/.]\d)", "Kennzeichen"),
    (r"(?<![\w/-])\b(?!\d[\d.]*-[A-ZÄÖÜ][A-Za-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)*\b)(?!\d{2,4}/\d+/(?:EG|EU|EWG|EGV|Euratom)\b)(?![CT]-\d+/\d{2}\b)(?=[\w/.-]*\d)(?=[\w/.-]*[A-ZÄÖÜ])\w+(?:[-/]\w+)+\b", "Kennung"),
    (r"\b[A-Z][ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b|\b[A-Z]\d{5}[ ]\d{4}\b", "Versichertennr"),
    (r"\bPostfach\s+\d[\d ]{2,10}\d\b", "Adresse"),
    (r"(?:[A-ZÄÖÜ][\wäöüß.-]+ ){1,3}\d{1,4} ?[a-z]?(?=,?\s+(?:in\s+)?\d{5}\b)", "Adresse"),
    (rf"\b(?:{PREP}[ \t]+)?(?:[A-ZÄÖÜ][\wäöüß.-]*[ \t]+){{0,2}}[A-ZÄÖÜ]?[\wäöüß.-]*{STREET_END}[ \t]*\d{{1,4}}[ \t]?[a-zA-Z]?\b", "Adresse"),   # в пределах одной строки
    (rf"\b{PREP}\s+(?!{MONTH}\b|Jahr\b|Jahre\b|Monat\b|Zeitraum\b|Höhe\b|Umfang\b)[A-ZÄÖÜ][\wäöüß-]+\s+(?!(?:19|20)\d{{2}}\b)\d{{1,4}}\s?[a-zA-Z]?\b", "Adresse"),
]
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
# Автор: «работать буду однозначно с русскими, английскими и немецкими источниками». Немецкая модель имён русских и английских имён
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
        if not kern or not re.fullmatch(r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?|[А-ЯЁ]\.|[А-ЯЁ]{2,6}", kern) or RU_KEEP.match(kern):
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
    видела ячейки по отдельности: иначе «Q3 2024,,Yes,,Yes» и «Datum,Datum,Generalkonsulat Der» становятся «лицами» (имитация дела Б 16.10.2026).
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
                        if len(t) <= 2 or "[" in t or "]" in t or "\n" in t or _KYR.search(t) or EN_KEEP.match(t.split()[0]) or KEEP.match(t.split()[0]):
                            continue
                        kind = {"PERSON": "Person", "ORG": "Firma", "GPE": "Ort", "LOC": "Ort", "FAC": "Ort"}.get(ent.label_)
                        if kind and re.search(r"(?i)\b(?:name|number|date|amount|item|account|holder|client|supplier|total|vat|code|type|status|price|quantity|description)\b", t):
                            continue                # заголовок столбца таблицы («Item Name» -> «лицо», затем слово «Name» закрывалось во всех заголовках; имитация дела Б 16.10.2026)
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


def anonymize(text, level=None, ner="all"):
    """ner: "all" -- лица, фирмы, места (связный текст); "per" -- только лица (распознанные сканы и бланки:
    на шуме распознавания модель принимает обычные слова за фирмы и места)."""
    level = level or LEVEL
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
    # суммы защищаются до правил о номерах (08.10.2026: на имитации дела целые части сумм становились «налоговым номером» и «телефоном»,
    # а прибыль и база взноса -- «[Zahl]»): «1.234,56», «615,02», «32.000» остаются как есть на уровне 1
    schutz = []

    def _halt(m):
        schutz.append(m.group(0))
        return f"\x01{len(schutz) - 1}\x02"
    if level == 1:
        out = re.sub(r"(?<![\w.,/-])\d{1,3}(?:\.\d{3})+(?:,\d{2})?(?![\w/]|[.,]\d)|(?<![\w.,/-])\d{1,6},\d{2}(?![\w/]|[.,]\d)", _halt, out)
    out = re.sub(r"((?:\bat |_at_)\d{1,2})\.(\d{2})\.(\d{2})(?=\.\w{2,4}\b|\b)", r"\1:\2:\3", out)       # «… at 11.54.49.ogg» -- время, не дата
    # (1) жёсткие форматы
    out = re.sub(rf"((?i:\bgeb\.|\bgeboren\w*|\bGeburts\w*|\bJahrgang)[^\n\d]{{0,60}}?|(?<!\*)\*(?!\*)\s?)(\d{{1,2}}\.\s?(?:\d{{1,2}}\.|{MONTH})\s?\d{{2,4}})\b",
                 lambda m: m.group(0) if m.group(1).startswith("*") and re.search(r"(?:20[1-9]\d)$", m.group(2))      # «**09.07.2024» -- жирный шрифт, не «*» рождения
                 else m.group(1) + tag("Geburtsdatum", m.group(2)), out)
    # полная дата с годом до 2010 (или двузначным годом 30–99) без пояснения -- скорее всего дата рождения: оставить только год
    out = re.sub(rf"\b\d{{1,2}}\.\s?(?:\d{{1,2}}\.|{MONTH})\s?(19\d{{2}}|200\d)\b", r"im Jahr \1", out)
    out = re.sub(r"\b\d{1,2}\.\d{1,2}\.([3-9]\d)\b", r"im Jahr 19\1", out)
    for rx, kind in HARD:
        out = re.sub(rx, lambda m, kind=kind: tag(kind, m.group(0)), out)
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
    tok = r"(?!(?:GmbH|gGmbH|AG|KG|OHG|UG|GbR|Co|SE|eG|Aktiengesellschaft)\b)(?:[A-ZÄÖÜ]\.|[A-ZÄÖÜ][\wäöüßÄÖÜ\-]*)"      # «W. Muster GmbH»: инициал с точкой (имитация дела Б 16.10.2026)
    for m in list(re.finditer(rf"({tok}(?:\s+(?:{tok}|&|und|\+|mehr)){{0,4}})\s+{form}(?![\w])", out)):
        name_part = re.sub(r"^(?:(?:Die|Der|Das|Den|Dem|Firma|Fa|Bei|Von|Mit|Für|An|Eine|Einer)\s+)+", "", m.group(1))
        if name_part and name_part not in ("Die", "Der", "Das", "Eine", "Firma") and not KEEP.match(name_part.split()[0]) and "[" not in name_part:
            out = out.replace(name_part + " " + m.group(2), tag("Firma", name_part) + " " + m.group(2))
    # название в кавычках перед правовой формой («ACT-IMPORT» LLC, „Muster“ GmbH) -- имитация дела Б 16.10.2026: правило выше требует заглавную букву в начале
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
        if "\n" in _maske[ent.start_char:ent.end_char].strip() or (ent.label_ == "ORG" and " " not in t and _de_wort(t)):     # через ячейки таблицы; одно обычное слово («Leasing», «Name») -- не имя (имитация дела Б 16.10.2026)
            continue
        if ent.label_ not in label or len(t) <= 2 or KEEP.match(t) or "[" in t or "]" in t:
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
               rf"\]\s+und\s+({NAME}\s+{NAME})", rf"\[Person [A-Z]\]\s+({NAME})\b"):
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
                    and not (ph.startswith(("[Firma", "[Ort")) and _de_wort(part)):     # обычное слово из названия фирмы («Leasing» из «VW Leasing») -- не по всему тексту (имитация дела Б 16.10.2026); у лиц фамилия-слово закрывается по-прежнему
                out = re.sub(rf"(?<!\[)\b{re.escape(part)}(?:s|'s|’s)?\b(?! [A-Z0-9]+\])", ph, out)
    out = re.sub(r"(\[Person [A-Z0-9]+\])(?:\s+\1)+", r"\1", out)
    if level == 1:                               # минимум: суммы и даты остаются, длинные номера без пояснения -- нет
        for m in reversed(list(re.finditer(r"(?<![\w\[.,])(?<!\d[.,] )\d(?:\d|[ /-]{1,3}(?=\d))*\d(?![\w]|,\d|\.\d)", out))):
            t = m.group(0)
            # год и час в строке письма («2. Dezember 2024 10:41», «Gesendet: … 2024 10:41»): дата, а не длинный номер (имитация дела А 12.10.2026: год терялся в 28 письмах)
            if re.fullmatch(r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])", t):      # месяц «2022-10» -- период, не номер (имитация дела Б 16.10.2026)
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
    """Часть ложного «имени» («B. Lohn», «Schreiben Mustermann») -- обычное слово, а не остаток имени (имитация дела А 12.10.2026: 15 остановок контроля
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


def guard(text, mapping, level=None):
    """Контроль исходящего текста: ничего из таблицы соответствия и никаких данных жёсткого формата. Возвращает нарушения."""
    low = text.lower()
    mapping = {k: (v.strip() if isinstance(v, str) else v) for k, v in mapping.items()}      # значение с пробелом по краям не совпадало с текстом (BIC в начале строки, 08.10.2026)
    bad = [v for k, v in mapping.items() if not k.startswith("rund") and len(v) > 3 and not (" " not in v.strip() and KEEP.match(v.strip())) and
           (re.search(rf"(?<![\wäöüÄÖÜß\[]){re.escape(v.strip())}(?![\wäöüÄÖÜß\]])", text, 0 if any(len(w) < 3 for w in v.split()) else re.I) if " " in v.strip()     # 17.10, имитация дела А: «A Ba» не в «da balance» и (короткие части -- с учётом регистра) не в «nach a ba»
            else re.search(rf"(?<![\wäöüÄÖÜß\[]){re.escape(v.strip())}(?![\wäöüÄÖÜß\]])", text))]
    # номера (шесть цифр и больше) ищутся и вплотную к буквам: распознавание склеивает «KVNR» с номером (имитация дела А 08.10.2026)
    bad += [v for k, v in mapping.items() if not k.startswith(("rund", "[Zahl", "[Betrag", "[Datum")) and " " not in v.strip() and len(v.strip()) >= 7
            and sum(c.isdigit() for c in v) >= 6 and v not in bad and v.strip().lower() in low]
    for k, v in mapping.items():                       # отдельные части имён
        if k.startswith("[Person"):
            bad += [p for p in v.split() if len(p) > 3 and not KEEP.match(p) and re.search(rf"\b{re.escape(p)}" + ("" if p[:1].isupper() else r"(?![a-zäöüß])"), text) and not _gemeinwort_im_text(p, text)]   # обычное слово в ложном «имени» -- не остаток; строчная часть («anna») -- только отдельным словом, не в «annahme» (17.10)
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
    return bad


_ABK = r"(?:Gesch|Verb|Ford|Aufw|Abschr|Sonst|Betr|Rückst|Umsatzst|Vorst|Verr|Kto|Nr|Abs|Art|Buchst|bzw|ggf|inkl|zzgl|evtl|Tel|Str|Steuerber|Buchf|Verw|Vers|Beitr|Abr|lfd|usw|Dipl|Dr|Prof|St|Kfz|Betriebs|Rechts|Lohn|Geh)"
MERKMALE = [   # вторая ступень контроля, независимая от списка замен: признаки персональных данных в готовом тексте (имитация дела А 09.10.2026)
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


def merkmale(text):
    """-> {признак: число мест}. Значений не возвращает. Обычные слова после «Herr/Frau» (роли, KEEP) не считаются."""
    out = {}
    for name, rx in MERKMALE:
        n = 0
        for m_ in re.finditer(rx, text):
            if name.startswith("обращение") and KEEP.match(m_.group(1)):
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
            if name.startswith("обращение") and KEEP.match(m_.group(1)):
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
    # род занятий (решение автора 11.10.2026: пока только помечать проверяющему; замена -- на отрасль: «сфера услуг», «пищевая промышленность»…):
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
