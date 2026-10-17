#!/usr/bin/env python3
"""
exchange.py -- «обменный лист» дела: единственный формат, в котором документы клиента уходят наружу (02.10.2026).

Хранение и проверка -- JSON по строгой схеме (лишнее поле не пройдёт); человеку и модели -- Markdown, построенный из того же JSON.
Код одобрения считается по JSON. Таблица «метка -> имя» в лист НЕ входит и остаётся локально.

  build(docs_dir, question, level)  -> (sheet: dict, mapping: dict)
  validate(sheet)                   -> список нарушений схемы
  render_md(sheet)                  -> текст для листа проверки и для внешней модели
  code(sheet)                       -> код текста (к нему привязано одобрение)
"""
import hashlib
import json
import re
from pathlib import Path

import anon_ru
import anonymizer

VERSION = "leckermath-exchange/1"
KINDS = {
    "Beitragskonto Krankenkasse (Kontenaufstellung)": (r"KONTENAUFSTELLUNG|Kontenaufstellung\s+f.r\s+Beitr|(?:\n[A-Z][a-zä]{2}\w* ?20\d\d \| \d{2}\.\d{2}\.20\d\d \|[^\n]*){8}", "Krankenkasse"),   # вид документа -> (признаки в тексте, роль выдавшего); порядок важен
    "Steuerbescheid": (r"Bescheid\s+für\s+\d{4}\s+über|Rechtsbehelfsbelehrung.{0,3000}Einspruch|Art der Festsetzung", "Finanzamt"),
    "Betriebsprüfungsbericht": (r"Betriebsprüfungsbericht|Bericht\s+über die (Betriebsprüfung|Außenprüfung|Umsatzsteuer-Sonderprüfung|Lohnsteuer-Außenprüfung)", "Finanzamt"),
    "Bescheid über Nebenleistungen (Zuschläge)": (r"Verspätungszuschl\w* \(§ ?152|Festsetzung von Verspätungszuschl|Säumniszuschl\w* \(§ ?240", "Finanzamt"),
    "Schreiben Krankenkasse": (r"Unterlagen zur Kranken- und Pflegeversicherung|Einkommensprüfung|Bitte Unterlagen direkt zusenden", "Krankenkasse"),
    "Beitragsbescheid Krankenkasse": (r"Beitragsbescheid|wird .{0,80}festgesetzt", "Krankenkasse"),
    "Einkommensteuererklärung (Berechnung)": (r"Berechnung der Einkommensteuer|Hauptvordruck ESt", "Steuerberater"),
    "Gewinnermittlung § 4 Abs. 3 EStG": (r"GEWINNERMITTLUNG|Gewinnermittlung nach", "Steuerberater"),
    "Summen- und Saldenliste": (r"Summen und Salden", "Steuerberater"),
    "Kontoblatt Buchhaltung": (r"Jahreskonto|Buchungsübersicht", "Steuerberater"),
    "Kontoauszug Bank": (r"Kontoauszug\s+\d+|Kontostand in EUR", "Bank"),
    "Lohnunterlagen": (r"Beitragsnachweis|Lohn- und Gehaltszahlungen", "Steuerberater"),
    "Schreiben Behörde": (r"Ausländerbehörde|Niederlassungserlaubnis|DER LANDRAT", "Behörde"),
    "Bestätigung Steuerberater": (r"Bestätigung gewerbliche Tätigkeit|hiermit bestätige ich", "Steuerberater"),
    "Rechnung": (r"Rechnung\s+Nr\.|Rechnungsbetrag|Rechnungsnummer", "Geschäftspartner"),
    "Korrespondenz": (r"Mit freundlichen Grüßen", "unbekannt"),
}
WORD = re.compile(r"[A-Za-zÄÖÜäöüßА-Яа-яЁё]{3,}")     # с кириллицей (08.10.2026): русский текст клиента раньше выбрасывался очисткой
COMMON = re.compile(r"\b(der|die|das|und|für|von|mit|nicht|den|des|ist|zur|zum|auf|bei|wird|sind|eine[rnms]?|Betrag|Datum|Konto|Seite|Steuer|Beitrag|Summe)\b")
COMMON_RU = re.compile(r"(?<![А-Яа-яЁё])(и|в|не|на|что|с|по|это|как|для|или|при|от|за|из|к|но|если|то|же|так|уже|есть|был[аио]?|сумм[аыу]|дат[аыу]|счёт|счет|налог[аиу]?)(?![А-Яа-яЁё])", re.I)   # 11.10.2026: русский текст (диалог, переписка) мерился по немецким словам и получал читаемость 0
AMOUNT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["format", "level", "question", "documents"],
    "properties": {
        "akteure": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["maske", "art", "rolle", "dokumente", "nennungen", "status"],
                    "properties": {"maske": {"type": "string"}, "art": {"enum": ["Person", "Organisation", "Behörde oder Kasse"]}, "rolle": {"type": "string"},
                                   "gruppe": {"type": ["string", "null"]}, "gehoert_zu": {"type": ["string", "null"]}, "gehoert_zu_status": {"enum": ["bestätigt", "vermutet", None]},
                                   "dokumente": {"type": "array", "items": {"type": "integer"}}, "nennungen": {"type": "integer"},
                                   "erstes_datum": {"type": ["string", "null"]}, "letztes_datum": {"type": ["string", "null"]},
                                   "evtl_identisch_mit": {"type": "array", "items": {"type": "string"}}, "name_offen": {"type": "array", "items": {"type": "string"}}, "status": {"enum": ["bestätigt", "aus Unterlagen erschlossen"]}}}},
        "akteure_hinweis": {"type": "string"},
        "einleitung": {"type": "object", "additionalProperties": False, "required": ["status", "text"], "properties": {"status": {"type": "string"}, "text": {"type": "string"}}},
        "verkehr": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["dok", "von", "an"],
                    "properties": {"dok": {"type": "string"}, "von": {"type": ["string", "null"]}, "unterzeichnet": {"type": ["string", "null"]}, "an": {"type": ["string", "null"]},
                                   "betrifft": {"type": "array", "items": {"type": "string"}}, "datum": {"type": ["string", "null"]}, "grundlage": {"type": "string"}}}},
        "beziehungen": {"type": "array", "items": {"type": "string"}},
        "format": {"const": VERSION}, "level": {"enum": [1, 2, 3]}, "question": {"type": "string", "maxLength": 2000},
        "documents": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False, "required": ["nr", "kind", "issuer_role", "pages", "ocr_quality", "text"],
            "properties": {
                "nr": {"type": "integer"}, "kind": {"type": "string"}, "issuer_role": {"enum": ["Finanzamt", "Krankenkasse", "Bank", "Steuerberater", "Behörde", "Geschäftspartner", "unbekannt"]},
                "date": {"type": ["string", "null"], "pattern": r"^\d{2}\.\d{2}\.\d{4}$"}, "years": {"type": "array", "items": {"type": "integer", "minimum": 1990, "maximum": 2100}},
                "pages": {"type": "integer", "minimum": 1}, "ocr_quality": {"type": "number", "minimum": 0, "maximum": 1},
                "text": {"type": "string"},
                "annahme": {"enum": ["angenommen", "mit Vorbehalt", "nicht angenommen"]}, "annahme_grund": {"type": "string"},
                "tables": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["name", "columns", "rows"],
                    "properties": {"name": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}},
                                   "rows": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "null"]}}},
                                   "control_sum": {"type": ["number", "null"]}, "note": {"type": "string"}}}}}}}}}


def quality(text):
    w = WORD.findall(text)
    return round(min(1.0, 12 * (len(COMMON.findall(text)) + len(COMMON_RU.findall(text)) / 3) / max(len(w), 1)), 2) if w else 0.0      # русские служебные слова короче и чаще -- вес 1/3


_TOK = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
ZWEIFEL, ENTSCHEID = {}, {}      # имя текста -> сомнительные страницы; имя текста -> {страница: знак аудитора}
MUELL = {}          # имя текста -> (убрано страниц, убрано строк) за последнюю сборку


def _wort_ok(w, vocab):
    return vocab.has_vector(w) or vocab.has_vector(w.lower()) or vocab.has_vector(w.capitalize()) or bool(anonymizer.KEEP.match(w))


SEITEN_KOPF = ("# Сомнительные страницы: распознаватель оценил их как почти не прочитанные. Знак ставит аудитор, сверив с подлинником.\n"
               "# Строка:  имя текста | страница | знак\n"
               "#   x -- в лист не выводить (так по умолчанию)\n"
               "#   h -- вывести как вспомогательное сведение с пометкой «Hilfsangabe, unsicher gelesen»\n"
               "#   + -- вывести как основной текст (аудитор сверил страницу с подлинником)\n"
               "# Отдельные нечитаемые строки не выводятся при любом знаке. Файл остаётся в папке дела и наружу не уходит.\n")


def seiten_entscheid(docs_dir, neu=None):
    """Три уровня текста (решение автора 09.10.2026): основной / вспомогательный с пометкой / не выводится. Знак по каждой сомнительной
    странице ставит аудитор в <дело>/_pipeline/SEITEN_ENTSCHEID.txt. neu -- {имя текста: [страницы]}: недостающие строки дописываются
    со знаком x. -> {имя текста: {страница: знак}}"""
    f = Path(docs_dir).parent / "SEITEN_ENTSCHEID.txt"
    out = {}
    if f.exists():
        for ln in f.read_text(encoding="utf-8").split("\n"):
            t = [x.strip() for x in ln.split("|")]
            if ln.lstrip().startswith("#") or len(t) < 3 or not t[1].isdigit():
                continue
            out.setdefault(t[0], {})[int(t[1])] = t[2].lower()[:1] if t[2].lower()[:1] in ("x", "h", "+") else "x"
    if neu is not None:
        dazu = [f"{name} | {nr} | x" for name, ss in sorted(neu.items()) for nr in ss if nr not in out.get(name, {})]
        if dazu or not f.exists():
            alt = f.read_text(encoding="utf-8").rstrip("\n") + "\n" if f.exists() else SEITEN_KOPF
            f.write_text(alt + "".join(x + "\n" for x in dazu), encoding="utf-8")
    return out


def entmuellen(text, seiten=None, schwach=300, anteil=0.4, entscheid=None):
    """Нечитаемое в лист не выводится (решение автора 09.10.2026): в мусоре распознавания прячутся обрывки имён и адресов,
    которых не ловят ни список замен, ни признаки. Страница, которую распознаватель оценил как почти не прочитанную, заменяется
    строкой «nicht gelesen»; строка, где словарных слов меньше доли `anteil`, -- тоже. Строки с числами и короткие строки остаются.
    -> (текст, число убранных страниц, число убранных строк)"""
    vocab = anonymizer._nlp().vocab
    seiten = seiten or []
    teile = re.split(r"(--- Seite \d+ ---)", text)
    genau = all("seite" in i for i in seiten)
    n_seiten = len(re.findall(r"--- Seite \d+ ---", text)) or 1
    weak = set()
    if genau or len(seiten) == n_seiten:
        weak = {i.get("seite", k) for k, i in enumerate(seiten, 1) if i.get("fehler") or (i.get("wertung") or 0) < schwach}
    out, nr, n_s, n_z = [], 1, 0, 0
    entscheid = entscheid or {}
    entmuellen.zweifel = []                              # страницы, по которым нужен знак аудитора
    for t in teile:
        m = re.fullmatch(r"--- Seite (\d+) ---", t)
        if m:
            nr = int(m.group(1))
            out.append(t)
            continue
        if nr in weak and t.strip() and len(re.findall(r"\d,\d{2}(?!\d)", t)) < 6:      # короткая страница-таблица с суммами -- не мусор (прогон 09.10.2026: приложение с расчётом)
            entmuellen.zweifel.append(nr)
            z = entscheid.get(nr, "x")
            if z == "x":
                out.append(f"\n[Seite {nr}: nicht gelesen – Texterkennung unzuverlässig]\n")
                n_s += 1
                continue
            if z == "h":
                out.append(f"\n[Seite {nr}: Hilfsangabe, unsicher gelesen – nicht als Beleg verwenden]")
        zeilen, letzte = [], False
        for ln in t.split("\n"):
            tok = _TOK.findall(re.sub(r"\[[^\]]{1,40}\]", " ", ln))
            if len(tok) >= 3 and not re.search(r"[А-Яа-яЁё]{3,}", ln) and not re.search(r"\d,\d{2}(?!\d)", ln) and sum(_wort_ok(w, vocab) for w in tok) / len(tok) < anteil:
                n_z += 1
                if not letzte:
                    zeilen.append("[Zeile nicht gelesen]")
                letzte = True
                continue
            letzte = False
            zeilen.append(ln)
        out.append("\n".join(zeilen))
    erg = "".join(out)
    # шапка, повторяющаяся на страницах (ведомости, распечатки): если на большинстве страниц первые строки совпадают, а на какой-то
    # странице первые строки с этой шапкой не совпали, они не выводятся вовсе -- без разбора, что в них (стенд 09.10.2026: на трёх
    # страницах ведомостей шапка распознана мусором, строки перемешаны, в них обрывки улицы, фамилии и номер дома)
    seiten_t = re.split(r"(--- Seite \d+ ---)", erg)
    if len(seiten_t) >= 9:                               # от четырёх страниц
        from rapidfuzz import fuzz
        kopf_n = 2
        koepfe = {}
        for k in range(2, len(seiten_t), 2):
            zl = seiten_t[k].split("\n")
            koepfe[k] = [i for i, l in enumerate(zl) if l.strip() and not l.startswith("[Seite")][:kopf_n]
        # первые строки страницы сравниваются БЛОКОМ с блоком чистой шапки: вопрос не «похожа ли строка на шапку», а «стоит ли на месте
        # шапки шапка» (стенд 09.10.2026: перемешанные строки и искажённое слово, совпавшее с настоящим названием, построчно проходили)
        norm = lambda t: re.sub(r"\d", "0", re.sub(r"\s+", " ", t)).strip()          # noqa: E731
        block = {k: norm(" ".join(seiten_t[k].split("\n")[i] for i in idx)) for k, idx in koepfe.items() if idx}
        sauber = {k for k, b in block.items() if len(b) >= 30
                  and sum(1 for kk, bb in block.items() if kk != k and fuzz.ratio(b, bb) >= 80) >= max(2, (len(block) - 1) // 2)}
        if len(sauber) >= max(3, len(block) // 2):
            # сколько строк занимает шапка на чистых страницах: начальные строки, повторяющиеся на большинстве чистых страниц
            voll_k = {k: [l for l in seiten_t[k].split("\n") if l.strip() and not l.startswith("[Seite")][:8] for k in sauber}
            kopf_len = kopf_n
            while kopf_len < 5 and sum(1 for k in sauber if len(voll_k[k]) > kopf_len and sum(
                    1 for kk in sauber if kk != k and len(voll_k[kk]) > kopf_len
                    and fuzz.ratio(norm(voll_k[k][kopf_len]), norm(voll_k[kk][kopf_len])) >= 80) >= (len(sauber) - 1) / 2) > len(sauber) / 2:
                kopf_len += 1
            kopf_z = {norm(l) for k in sauber for l in voll_k[k][:kopf_len]}                      # строки чистой шапки
            anker = {norm(l) for k in sauber for l in voll_k[k][kopf_len:kopf_len + 2] if len(l.strip()) >= 15}   # строки под шапкой
            for k, idx in koepfe.items():
                if k in sauber or not idx or max(fuzz.ratio(block[k], block[kk]) for kk in sauber) >= 80:
                    continue
                # зона шапки на испорченной странице: от начала до строки, которая на чистых страницах идёт под шапкой (заголовок формы).
                # Если такой строки нет -- до последней из первых восьми строк, в которой ещё узнаётся кусок шапки, но не меньше длины
                # шапки (стенд 09.10.2026: перед шапкой три строки мусора, сама шапка разбита на четыре строки)
                zl = seiten_t[k].split("\n")
                voll = [i for i, l in enumerate(zl) if l.strip() and not l.startswith("[Seite")][:8]
                ende = next((n for n, i in enumerate(voll) if n >= 1 and any(fuzz.ratio(norm(zl[i]), a) >= 80 for a in anker)), None)
                if ende is None:
                    rest = [n for n, i in enumerate(voll) if any(fuzz.partial_ratio(norm(zl[i]), a) >= 70 or fuzz.partial_ratio(a, norm(zl[i])) >= 70
                                                               for a in kopf_z if len(a) >= 8)]
                    ende = max(kopf_len, (rest[-1] + 1) if rest else 0)
                gesetzt = False
                for i in voll[:ende]:
                    if any(fuzz.ratio(norm(zl[i]), a) >= 85 for a in kopf_z):
                        continue                          # строка шапки прочитана чисто (испорчена соседняя) -- остаётся
                    # нормально прочитанный верх страницы не страдает (решение автора 09.10.2026): строка уходит, только если в ней узнаётся
                    # испорченный кусок шапки либо она не читается по словарю; обычный текст в начале страницы остаётся
                    nl = norm(zl[i])
                    stueck = any(fuzz.partial_ratio(nl, a) >= 70 or fuzz.partial_ratio(a, nl) >= 70 for a in kopf_z if len(a) >= 8) if len(nl) >= 8 else False
                    tk = _TOK.findall(zl[i])
                    unlesbar = (len(tk) >= 2 and sum(_wort_ok(w, vocab) for w in tk) / len(tk) < 0.5) \
                        or (len(tk) >= 3 and sum(len(w) <= 3 for w in tk) / len(tk) >= 0.6)        # россыпь коротких «слов» -- тоже мусор
                    if not stueck and (not unlesbar or re.search(r"\d,\d{2}(?!\d)", zl[i])):
                        continue
                    if "nicht gelesen" not in zl[i]:
                        n_z += 1
                    zl[i] = "" if gesetzt else "[Kopfzeile nicht gelesen]"
                    gesetzt = True
                seiten_t[k] = "\n".join(zl)
            erg = "".join(seiten_t)
    return erg, n_s, n_z


def classify(text):
    # пачка писем электронной почты (имитация дела А 12.10.2026: 86 страниц переписки определялись как «Rechnung», потому что в темах писем стояло
    # «Rechnung Nr. …»): много строк-заголовков почты -> переписка; кто выдал -- по тексту не установить, ставит обработчик в KORREKTUR.txt
    if len(re.findall(r"(?mi)^\s*(?:Von|From|Gesendet|Betreff|Subject|An|To|От|Кому|Тема)\s*:", text)) >= 12:
        return "Korrespondenz", "unbekannt"
    for kind, (rx, role) in KINDS.items():
        if re.search(rx, text, re.S):
            return kind, role
    return "Sonstiges", "unbekannt"


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def table_bank(text):
    """Выписка: «DD.MM Вид операции Wert: DD.MM.YYYY 615,02-» + строки назначения до следующей операции."""
    rows, cur = [], None
    for line in text.split("\n"):
        m = re.search(rf"(\d{{2}}\.\d{{2}})\s+(.+?)\s+Wert:\s*(\d{{2}}\.\d{{2}}\.\d{{4}})\s+({AMOUNT[2:]})\s?([-+])", line)
        if m:
            cur = [m.group(3), m.group(2).strip(), "", (-1 if m.group(5) == "-" else 1) * num(m.group(4))]
            rows.append(cur)
        elif cur is not None and line.strip() and not re.search(r"Kontoauszug|Konto-Nr|Datum Erl|DATUM \d|^---|SWIFT|IBAN", line):
            cur[2] = (cur[2] + " " + re.sub(r"^[^A-Za-zÄÖÜ\[]{0,4}", "", line.strip())).strip()[:160]
        if re.search(r"Konto-Nr|^--- Seite", line):
            cur = None
    return {"name": "Kontobewegungen", "columns": ["Wertstellung", "Art", "Verwendungszweck", "Betrag EUR"], "rows": rows,
            "control_sum": round(sum(r[3] for r in rows), 2), "note": "Auszug enthält nur die vorgelegten Blätter, nicht alle Buchungen"} if rows else None


def _zahl(s):
    """«1.234,56», «1.234.56», «887.68», «- 909,98» -> число; последний разделитель перед двумя цифрами -- десятичный."""
    s = re.sub(r"[€\s]", "", s or "").replace("–", "-")
    m = re.fullmatch(r"(-?)(\d[\d.,]*)[.,](\d{2})", s)
    return (-1 if m.group(1) else 1) * float(re.sub(r"[.,]", "", m.group(2)) + "." + m.group(3)) if m else None


def table_beitragskonto(text):
    """Выписка кассы по взносам (строки «Монат | Fälligkeit | Bemessungsgrundlage | Status | Beitrag | Säumniszuschlag | Gebühr | Datum | Zahlung [Erstattung] | Saldo»,
    как их расставляет ocr.py по столбцам). Самопроверка: остаток строки = остаток предыдущей + взнос + пени + сбор − платёж + возврат."""
    MONAT = r"(Jan|Feb|Mrz|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\w*\.? ?(20\d\d)"
    rows = []
    for line in text.split("\n"):
        c = [x.strip() for x in line.split("|")]
        m = re.match(MONAT, c[0]) if c else None
        if not m or len(c) < 8:
            continue
        zahl = [(_zahl(x) if x else None) for x in c]
        z2 = re.findall(r"-?\s?\d[\d.,]*[.,]\d{2}", c[-2]) if len(c) >= 2 else []
        zahlung = _zahl(z2[0]) if z2 else None
        erst = abs(_zahl(z2[1])) if len(z2) > 1 else None
        k = len(c)
        rows.append([f"{m.group(1)} {m.group(2)}", c[1] if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", c[1]) else "", zahl[2], re.sub(r"Endg.ltig", "Endgültig", c[3]), zahl[4],
                     zahl[5] if k >= 10 else None, zahl[6] if k >= 10 else None, c[-3] if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", c[-3]) else "", zahlung, erst, zahl[-1]])
    if len(rows) < 6:
        return None
    ok, prev = 0, 0.0
    for r in rows:
        soll = prev + (r[4] or 0) + (r[5] or 0) + (r[6] or 0) - (r[8] or 0) + (r[9] or 0)
        gut = r[10] is not None and abs(soll - r[10]) < 0.015
        ok += gut
        r.append("ja" if gut else "nein")
        prev = r[10] if r[10] is not None else soll
    S = lambda i: round(sum(r[i] or 0 for r in rows), 2)        # noqa: E731
    jahre = {}
    for r in rows:
        j = jahre.setdefault(r[0][-4:], [0, 0, 0, 0])
        for n, i in enumerate((4, 5, 6, 8)):
            j[n] = round(j[n] + (r[i] or 0), 2)
    note = (f"per Code aus der Texterkennung gelesen; Saldo-Probe (Vorsaldo + Beitrag + Säumniszuschlag + Gebühr − Zahlung + Erstattung = Saldo) stimmt in {ok} von {len(rows)} Zeilen. "
            f"Summen: Beiträge {S(4):.2f}; Säumniszuschläge {S(5):.2f}; Gebühren {S(6):.2f}; Zahlungen {S(8):.2f}; Erstattungen {S(9):.2f}. "
            "Je Jahr (Beiträge / Säumniszuschläge / Gebühren / Zahlungen): " + "; ".join(f"{y}: {v[0]:.2f} / {v[1]:.2f} / {v[2]:.2f} / {v[3]:.2f}" for y, v in sorted(jahre.items()))
            + (". ACHTUNG: Zeilen mit «nein» sind Lesefehler oder fehlende Zellen – gegen das Original prüfen" if ok < len(rows) else ""))
    return {"name": "Beitragskonto", "columns": ["Beitragsmonat", "Fälligkeit", "Bemessungsgrundlage", "Status", "Beitrag KV/PV", "Säumniszuschlag", "Gebühr", "Zahlungsdatum",
                                                  "Zahlung", "Erstattung", "Saldo (Forderung)", "Saldo-Probe"],
            "rows": rows, "control_sum": rows[-1][10], "note": note}


def table_ledger(text):
    """Листы счетов DATEV: «DD.MM.YYYY … текст … сумма» и выборки проводок «сумма S/H … DD.MM.YYYY … текст»."""
    rows = []
    for line in text.split("\n"):
        m = re.match(rf"\s*(\d{{2}}\.\d{{2}}\.\d{{4}})\s+(?:\d{{3,5}}\s+)?(.+?)\s+({AMOUNT})\s*$", line)
        m2 = re.match(rf"\s*({AMOUNT})\s+[SH]\s+.*?(\d{{2}}\.\d{{2}}\.\d{{4}})\s+\d{{3,5}}\s+(.+)$", line)
        if m:
            rows.append([m.group(1), re.sub(r"\s+\S*\d{4,}\S*$", "", m.group(2)).strip()[:80], num(m.group(3))])
        elif m2:
            rows.append([m2.group(2), m2.group(3).strip()[:80], num(m2.group(1))])
    return {"name": "Buchungen", "columns": ["Datum", "Buchungstext", "Betrag EUR"], "rows": rows, "control_sum": round(sum(r[2] for r in rows), 2)} if len(rows) >= 3 else None


def table_accounts(text):
    """EÜR / Kontennachweis: «NNNN Название счёта 1.234,56»."""
    rows = [[m.group(1), m.group(2).strip()[:70], num(m.group(3))] for m in re.finditer(rf"(?m)^\s*(\d{{3,4}})\s+([A-ZÄÖÜ][^\n]{{3,70}}?)\s+({AMOUNT})-?(?:\s+{AMOUNT})?\s*$", text)]
    return {"name": "Konten", "columns": ["Konto", "Bezeichnung", "Betrag EUR"], "rows": rows, "control_sum": None} if len(rows) >= 5 else None


KEYWORDS = re.compile(r"(Einkünfte|Einkommen|Summe|Gesamtbetrag|Gesamtbeitrag|festzusetzende|Festgesetzt|tarifliche|Beiträge zur|Krankenversicherungsbeiträge|"
                      r"Pflegeversicherungsbeiträge|Sonderausgaben|Kirchensteuer|Solidaritätszuschlag|Zusatzbeitrag|Arbeitseinkommen|Nachzahlung|Erstattung|"
                      r"Steuerermäßigung|Bemessungsgrundlage|Gewinn|Erlöse|Hinzuschätzung|Umsatzsteuer)", re.I)


def table_keyfigures(text):
    """Решения и расчёты (Finanzamt, страховая): строки «показатель … число» и предложения с суммой и ключевым словом."""
    rows, seen = [], set()
    for line in text.split("\n"):
        l = " ".join(line.split())
        m = re.match(rf"^(?P<label>[A-Za-zÄÖÜäöüß§][^\d]{{7,90}}?)[ .:]{{1,60}}(?P<val>-?\d{{1,3}}(?:\.\d{{3}})*(?:,\d{{2}})?)(?:\s?(?:€|EUR))?(?:\s+[.\d ,€%-]*)?$", l)
        if m and KEYWORDS.search(m.group("label")) and (m.group("label").strip(" .:"), m.group("val")) not in seen:
            seen.add((m.group("label").strip(" .:"), m.group("val")))
            rows.append([m.group("label").strip(" .:")[:80], m.group("val")])
    for m in re.finditer(rf"[^.\n]{{0,140}}?({AMOUNT[2:]}) ?€[^.\n]{{0,120}}", text):      # «…wird auf 565,33 € monatlich festgesetzt», «Nachzahlung von 4.666,96 €»
        sent = " ".join(m.group(0).split())
        if re.search(r"festgesetzt|Nachzahlung|fällig|monatlich|Beitrag|Bemessungs", sent) and (sent[:60], m.group(1)) not in seen:
            seen.add((sent[:60], m.group(1)))
            rows.append([sent[:150], m.group(1)])
    for m in re.finditer(rf"({AMOUNT[2:]}) ?€\s*\|?\s*(\d{{1,2}},\d{{1,2}}) ?%\s*\|?\s*({AMOUNT[2:]}) ?€", text):   # расчёт взноса: база, ставка, взнос
        rows.append([f"Beitragsberechnung: Bemessung {m.group(1)} € × {m.group(2)} %", m.group(3)])
    return {"name": "Kernangaben (per Code ausgelesen)", "columns": ["Angabe", "Wert"], "rows": rows[:40], "control_sum": None} if rows else None


def fix_ocr(t):
    """Типичные ошибки распознавания в правовых текстах: «$ 13b» -> «§ 13b», «It.» -> «lt.»."""
    t = re.sub(r"\$\s?(\d)", r"§ \1", t)
    return re.sub(r"\bIt\.(?= )", "lt.", t)


def clean(t, limit=None):
    """limit -- сколько знаков документа идёт в обменный лист. По умолчанию 9000 (лист для внешней модели с ограничением объёма);
    полный текст -- переменная окружения LM_DOC_LIMIT (её ставит anon_paket.py: работа с обезличенным листом вместо подлинников)."""
    limit = limit or int(__import__("os").environ.get("LM_DOC_LIMIT", "9000"))
    # строка-дата («Musterstadt, 17.02.2025») и строка-заголовок из одного словарного слова («Beitragseinstufung 2021») остаются (имитация дела А 12.10.2026:
    # дата и заголовок ключевого письма выпадали, потому что в строке меньше двух слов)
    W = wortliste()
    L = [l.strip() for l in t.split("\n") if len(WORD.findall(l)) >= 2 or re.search(r"\d+[.,]\d{2}", l) or l.startswith("---")
         or re.search(r"(?<![\d.])\d{1,2}\.\d{1,2}\.(?:19|20)?\d{2}(?!\d)", l)
         or (len(l.strip()) <= 60 and any(len(w) >= 6 and w.lower() in W for w in WORD.findall(l)))]
    return "\n".join(L)[:limit]


_BETRAG_Z = re.compile(r"\s*-?[\d.]+,\d{2} ?[HS+-]?\s*")
_KEIN_PARTNER = re.compile(r"(?i)gutschr|lastschr|entgelt|abschlu|zins|dauerauftrag|überweisung|ueberweisung|saldo|kontostand|übertrag|uebertrag|auszug|buchung|wert|betrag|summe|seite|blatt|kartenzahlung|bargeld|auszahlung|einzahlung|storno|steuer|miete|gehalt|lohn")


def kennungen_rest(anon, mp):
    """Номера, оставшиеся без метки (прогон 11.10.2026: ссылки платежей EREF/MREF/CRED, обрезанный IBAN, номер счёта в имени файла):
    значение после признака ссылки и любое слово с семью и более цифрами подряд вне метки -> [Kennung N]. Суммы (с запятой и
    двумя знаками) не трогаются. -> (текст, замены)"""
    k = [max([950] + [int(x) for ph_ in mp for x in re.findall(r"^\[Kennung (\d+)\]$", ph_)])]      # проход идёт и по готовому листу: номер выше занятых

    def neu(val):
        ph = next((p for p, v in mp.items() if v == val and p.startswith("[Kennung ")), None)
        if not ph:
            k[0] += 1
            ph = f"[Kennung {k[0]}]"
            mp[ph] = val
        return ph
    anon = re.sub(r"\b((?:EREF|MREF|KREF|CRED)[:+]\s*)([A-Z0-9][A-Z0-9.\-]{5,})", lambda m: m.group(1) + neu(m.group(2)), anon)
    # буквы любого алфавита: распознавание ставит в номер счёта кириллическую букву вместо латинской (имитация дела А 12.10.2026)
    anon = re.sub(r"(?<![\w\[.,])[\w.\-/]*\d{7,}[\w.\-/]*(?![\w\]])(?!,\d{2}(?!\d))", lambda m: neu(m.group(0)), anon)
    return anon, mp


_WORTLISTE = None
ZURUECK = "[Zeile zurückgehalten – unsicher gelesen]"


def wortliste():
    """Немецкие слова от четырёх букв, встреченные в базе права три раза и больше (выборка 12 % чанков, 11.10.2026): de_wortliste.txt.gz."""
    global _WORTLISTE
    if _WORTLISTE is None:
        import gzip
        f = Path(__file__).parent / "de_wortliste.txt.gz"
        _WORTLISTE = set(gzip.open(f, "rt", encoding="utf-8").read().split("\n")) if f.exists() else set()
    return _WORTLISTE


def isolieren(text):
    """решение автора 11.10.2026: «с нераспознанными или сомнительными остатками поступать просто -- изолировать от выпуска наружу».
    Строка распознанного скана, в которой есть два и более слова из латинских букв, но ни одного слова от четырёх букв, известного
    словарю базы права, -- обрывок распознавания: в нём прячутся части имён и адресов. Такая строка в лист не выводится.
    Строки с суммами, с кириллицей, из одних меток и строки-разделители страниц остаются. -> (текст, число изолированных строк)"""
    W = wortliste()
    if not W:
        return text, 0
    out, n, letzte = [], 0, False
    for ln in text.split("\n"):
        roh = re.sub(r"\[[^\]]{1,60}\]", " ", ln)
        tok = re.findall(r"[A-Za-zÄÖÜäöüß]{2,}", roh)
        if (len(tok) >= 2 and not ln.startswith("---") and not re.search(r"[А-Яа-яЁё]{3,}", ln) and not re.search(r"\d,\d{2}(?!\d)", ln)
                and len(re.findall(r"\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}", ln)) < 2        # строка счёта с периодом «с … по …» -- строка таблицы, не обрывок
                and not any(len(w) >= 4 and (w.lower() in W or w.lower().rstrip("s") in W) for w in tok)):
            n += 1
            daten = re.findall(r"(?<![\d.])\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}(?!\d)", ln)       # дата в удержанной строке (шапка письма) для хронологии остаётся
            if daten:
                out.append(ZURUECK[:-1] + "; Datum: " + ", ".join(dict.fromkeys(daten)) + "]")
                letzte = False
            elif not letzte:
                out.append(ZURUECK)
                letzte = True
            continue
        letzte = False
        out.append(ln)
    return "\n".join(out), n


NACHLESE_WERTE = set()
ISOLIERT = {}         # имя текста -> число строк, изолированных от выпуска за последнюю сборку


def nachlese(anon, mp):
    """Остатки, найденные слепым опытом 11.10.2026 (читатель без ключа пытался назвать клиента по одному листу):
    1) известное место, фирма или лицо, напечатанное вразрядку или с пробелами распознавания («M u s t e r s t a d t»);
    2) слово, сцепленное дефисом или косой чертой с меткой места или лица (часть составного названия, вторая фамилия);
    3) слово после «Finanzamt», «Amtsgericht», «Haltestelle» и т.п. -- место;
    4) адрес сайта (в том числе искажённый распознаванием);
    5) в выписке: строка после суммы, где метка закрыла лишь часть имени, и следующая за ней строка из 2–3 слов с заглавной буквы.
    -> (текст, замены)"""
    k = [max([970] + [int(x) for ph_ in mp for x in re.findall(r"^\[\w[\w-]* (\d+)\]$", ph_)])]      # номер выше всех уже занятых: проход идёт и по готовому листу

    def neu(val, art):
        k[0] += 1
        ph = f"[{art} {k[0]}]"
        mp[ph] = val
        NACHLESE_WERTE.add(val.strip().lower())           # найдено по месту в тексте: шаг «обычное слово -- вернуть» это не отменяет
        return ph
    for ph, v in list(mp.items()):                       # 0: заголовок столбца, принятый за лицо («Name», «Item Name»; имитация дела Б 16.10.2026) -- вернуть
        if ph.startswith("[Person") and re.fullmatch(r"(?i)(?:\w+ )?(?:name|number|date|amount|account|holder|client|supplier|total|type|status|code)", str(v).strip()):
            anon = anon.replace(ph, str(v))
            del mp[ph]
    for ph, v in list(mp.items()):                       # 1
        kern = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", str(v))
        if ph.startswith(("[Ort", "[Firma", "[Person")) and 6 <= len(kern) <= 40:
            rx = r"(?i)(?<![A-Za-zÄÖÜäöüß\[])" + r"\s{0,2}".join(re.escape(ch) for ch in kern) + r"(?:\s?[a-zäöüß]){0,3}(?![\w\]])"
            anon = re.sub(rx, lambda m: ph if " " in m.group(0).strip() else m.group(0), anon)
    # 2: обычное слово словаря («[Person 5]/Daten», «[Ort 3]-Gesetz») именем не считается (имитация дела А 12.10.2026: 23 таких замены дали остановки контроля)
    anon = re.sub(r"(\[(?:Ort|Person) [^\]]+\])([-/])([A-ZÄÖÜ][a-zäöüß]{2,})", lambda m: m.group(0) if _gemeinwort(m.group(3)) else
                  m.group(1) + m.group(2) + neu(m.group(3), "Ort" if m.group(1).startswith("[Ort") else "Person"), anon)
    anon = re.sub(r"([A-ZÄÖÜ][a-zäöüß]{3,})-(\[Ort [^\]]+\])", lambda m: m.group(0) if _gemeinwort(m.group(1)) else neu(m.group(1), "Ort") + "-" + m.group(2), anon)
    anon = re.sub(r"\b(Finanzamt|Amtsgericht|Landgericht|Arbeitsgericht|Sozialgericht|Hauptzollamt|Jobcenter|Haltestelle|Stadt|Gemeinde|Kreis)\s+([A-ZÄÖÜ][a-zäöüß]{3,})\b",
                  lambda m: m.group(0) if _gewoehnlich(m.group(2)) or (m.group(1) in ("Stadt", "Gemeinde", "Kreis") and _gemeinwort(m.group(2)))
                  or _nomen(m.group(2), anon)             # «dem Finanzamt Daten übermittelt»: нарицательное по модели, не место
                  else m.group(1) + " " + neu(m.group(2), "Ort"), anon)      # 3
    anon = re.sub(r"(?i)(?<![\w\[@])(?:www[. ]\s?[\w-]+(?:\.[\w-]+)*|[\w-]{2,}(?:\.[\w-]{2,})+\.(?:de|com|org|net|eu|info))(?![\w\]])", lambda m: neu(m.group(0), "Web"), anon)      # 4
    # 7: строка «место, дата» в шапке письма («Musterstadt, 17.02.2025», «Musterstadt, den 17.02.2025») -- такие строки с 12.10.2026 остаются в листе, место закрывается
    anon = re.sub(r"(?m)^([A-ZÄÖÜ][a-zäöüß]{2,}(?:[ -][A-ZÄÖÜ][a-zäöüß]{2,})?)(, (?:den |am )?\d{1,2}\.\d{1,2}\.(?:19|20)?\d{2})[ \t]*$",      # только с запятой: без неё это строка выписки («Gutschrift 01.02.2024»)
                  lambda m: m.group(0) if _gewoehnlich(m.group(1)) or _nomen(m.group(1), anon) else neu(m.group(1), "Ort") + m.group(2), anon)
    # 8 (имитация дела Б 16.10.2026): латинская фамилия в другом роде или форме -- «Ivanov» закрыта, «IVANOVA» в выписке (43 раза) и «ivanov_elster.pfx»
    # открыты. Основа фамилии (без -ova/-ov/-skaya/-a …, не короче 5 букв, не обычное слово) -- в любом регистре и с любым из этих окончаний
    # под ту же метку; основа от 6 букв внутри учётной записи или имени файла (части через «_ . -» или цифры) -- вся запись новой меткой.
    ENDE = r"(?:skaya|skaja|skiy|skij|sky|ski|ska|ova|eva|ina|aya|aja|ov|ev|in|iy|ij|yj|a)"
    for ph, v in list(mp.items()):
        if not ph.startswith(("[Person", "[Mandant", "[Ehegatt")):
            continue
        for w in re.findall(r"[A-Za-z]{5,}", str(v)):
            stem = re.sub(rf"(?i){ENDE}$", "", w)
            if len(stem) < 5 or _gesetzwort(w) or _gesetzwort(stem):
                continue
            anon = re.sub(rf"(?i)(?<![\w\[]){re.escape(stem)}{ENDE}?s?(?![\w\]])", ph, anon)
            anon = re.sub(rf"({re.escape(ph)})(?:[ \t]+{re.escape(ph)})+", r"\1", anon)
            if len(stem) >= 6:
                anon = re.sub(r"(?<![\w\[@])\w[\w.-]*[_.]\w[\w.-]*(?![\w\]])",
                              lambda m, st=stem.lower(): neu(m.group(0), "Kennung") if st in m.group(0).lower() else m.group(0), anon)
    # 9 (имитация дела Б 16.10.2026): координаты «51.5136, 7.4653» (журнал поездок, Timeline) указывают дом и места человека -- 1 356 открытых.
    # Одна пара -- одна метка; точность не сохраняется (на уровне 1 место -- такой же признак лица, как адрес).
    koord = {}
    anon = re.sub(r"(?<![\d.])-?(?:[0-8]?\d)\.\d{4,},\s*-?(?:1[0-7]\d|\d{1,2})\.\d{4,}(?![\d.])",      # широта до 89, долгота до 179, от 4 знаков: «92.859,92.859» -- суммы
                  lambda m: koord[re.sub(r"\s", "", m.group(0))] if re.sub(r"\s", "", m.group(0)) in koord
                  else koord.setdefault(re.sub(r"\s", "", m.group(0)), neu(m.group(0), "Koordinaten")), anon)
    # 10 (имитация дела Б 16.10.2026): выгрузка банка или бухгалтерии таблицей -- в столбце контрагента или владельца счёта частные лица
    # («Vorname Nachname», в том числе врачебная практика) оставались открытыми: модель не видит имён в строках CSV. Значение столбца из 2–4 слов
    # только из букв, без правовой формы, без цифр и «*», ни одно слово не обычное (словарь) и не платёжная формула -- лицо.
    # Цена: магазин с необычным названием («Toma Toma») тоже закрывается -- теряется только название продавца.
    import csv as _csv
    SPALTE = re.compile(r"(?i)^(counterparty|account holder|empfänger|empfaenger|auftraggeber|zahlungsempfänger|begünstigter|kontoinhaber|name|client|geschäftspartner)(?:\s.*)?$")
    FORM = re.compile(r"(?i)\b(gmbh|ag|kg|ohg|ug|gbr|e\.?k|e\.?v|se|ltd|limited|inc|llc|s\.?r\.?l|s\.?r\.?o|sas|bv|b\.v|plc|co|oy|ab)\b\.?")
    import io as _io
    werte = []
    for blk in re.split(r"\n\s*\n|\n(?=## Blatt)", anon):                 # таблица целиком: в ячейках бывают переводы строк («-\n-»)
        spalten = None
        try:
            rows = list(_csv.reader(_io.StringIO(blk)))
        except Exception:
            continue
        for zellen in rows:
            idx = [j for j, c in enumerate(zellen) if SPALTE.match(c.strip())]
            if idx and len(zellen) >= 3:
                spalten = idx
                continue
            for j in spalten or []:
                if j >= len(zellen):
                    continue
                v = re.sub(r"(?i)^(?:(?:praxis|zahnarztpraxis|arztpraxis|dr|dr\.|med\.|prof\.?|herr|frau|hr\.|fr\.)\s+)+", "", zellen[j].strip())     # «PRAXIS DR …» -- имя врача
                ws = v.split()
                if (2 <= len(ws) <= 4 and "[" not in v and not re.search(r"[\d*@/]", v) and not FORM.search(v)
                        and all(re.fullmatch(r"[A-Za-zÄÖÜäöüßÀ-ÿ'-]{2,}", w) for w in ws)
                        and not any(_gewoehnlich(w) or _KEIN_PARTNER.search(w) or _HANDEL.fullmatch(w) for w in ws)
                        and not _gesetzwort(ws[-1].capitalize()) and not _gesetzwort(ws[-1].lower())):      # фамилия редкая; «Deutsche Post», «Lidl Dienstleistung» -- нет
                    werte.append(v)
    for v in sorted(set(werte), key=len, reverse=True):
        anon = re.sub(rf"(?<![\w\[]){re.escape(v)}(?![\w\]])", neu(v, "Person"), anon)
    # 12 (имитация дела Б, находки агента дела 16.10.2026): номер договора или документа «M202146», «VW-Vertrag M202146» -- буквы и от пяти цифр
    anon = re.sub(r"(?<![\w\[/.-])(?!DE\d{9}\b)[A-Z]{1,3}-?\d{5,}(?![\w\]])", lambda m: neu(m.group(0), "Kennung"), anon)
    # 13: отличительное слово уже закрытой фирмы стоит отдельно («Rechnung Muster 14.03.2022» при «W. Muster GmbH») -- той же меткой
    for ph, v in list(mp.items()):
        if ph.startswith("[Firma"):
            for w in re.findall(r"[A-ZÄÖÜ][a-zäöüß]{4,}", str(v)):
                if not _gesetzwort(w) and not anonymizer.KEEP.match(w):
                    anon = re.sub(rf"(?<![\w\[]){re.escape(w)}(?![\w\]])", ph, anon)
    fw, fs = {}, {}
    # 15 (находка агента дела 16.10.2026): латинское имя продавца в русском тексте («Rechnung Muster 14.03.2022», «письмо Muster от …»):
    # немецкая модель строки с кириллицей не размечает, русская латиницу не видит. Слово с заглавной буквы после слова-указателя, не из словаря -- фирма.
    anon = re.sub(r"(?<![\w\[])((?:Rechnung|Schreiben|Brief|Angebot|Vertrag|Autohaus|Firma|письмо|письме|счёт|счет|счета|договор|продавец|продавца|у|от)\s+)([A-ZÄÖÜ][a-zäöüß]{3,})(?![\w\]])",
                  lambda m: m.group(0) if _gesetzwort(m.group(2)) or anonymizer.KEEP.match(m.group(2)) or re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß]*(?:G|StG|AO|V|O)", m.group(2))
                  else m.group(1) + (fw.get(m.group(2)) or fw.setdefault(m.group(2), neu(m.group(2), "Firma"))), anon)
    for w, ph in fw.items():                             # то же имя без слова-указателя
        anon = re.sub(rf"(?<![\w\[]){re.escape(w)}(?![\w\]])", ph, anon)
    # 14: столбцы индекса и города в таблице клиентов или поставщиков («72004, Bishkek»): улица закрывалась, индекс и город -- нет
    ORTSPALTE = re.compile(r"(?i)^(post ?code|postcode|zip(?: code)?|plz|postleitzahl|city|ort|stadt|wohnort)$")
    orte = []
    for blk in re.split(r"\n\s*\n|\n(?=## Blatt)", anon):
        try:
            rows = list(_csv.reader(_io.StringIO(blk)))
        except Exception:
            continue
        sp = None
        for zellen in rows:
            idx = [j for j, c in enumerate(zellen) if ORTSPALTE.match(c.strip())]
            if idx and len(zellen) >= 3:
                sp = idx
                continue
            for j in sp or []:
                if j < len(zellen) and len(zellen[j].strip()) >= 3 and "[" not in zellen[j]:
                    orte.append(zellen[j].strip())
    for v in sorted(set(orte), key=len, reverse=True):
        anon = re.sub(rf"(?<![\w\[]){re.escape(v)}(?![\w\]])", neu(v, "Ort"), anon)
    # 16 (находка агента дела 16.10.2026): улица сокращением без номера дома («Musterstr.», «Musterstraße» рядом с индексом) -- 260 открытых мест
    anon = re.sub(r"(?<![\w\[])[A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)*(?:str\.|straße|strasse|weg|allee|platz|gasse|ring)(?![\w\]])",
                  lambda m: m.group(0) if _gesetzwort(m.group(0).rstrip(".")) else (fs.get(m.group(0)) or fs.setdefault(m.group(0), neu(m.group(0), "Adresse"))), anon)
    # 11: улица в английской записи («Toktogula st, 12», «Baker Street 5») -- иностранный клиент в листе Clients
    anon = re.sub(r"(?<![\w\[])([A-Z][a-z]{3,}(?: [A-Z][a-z]+)?) (?:st|str|street|ave|avenue|rd|road|blvd|lane)\b\.?",
                  lambda m: m.group(0) if _gesetzwort(m.group(1).split()[0]) else neu(m.group(0), "Adresse"), anon)
    # 6: остаток адреса почты вплотную к метке («[E-Mail 3][Mandantin 1]-studio.de»: имя в адресе заменил реестр, шаблон адреса сработал на часть) -- под ту же метку
    anon = re.sub(r"(\[E-Mail [^\]]+\])(?:\[[^\]\n]{1,40}\]|[\w.@-])+", r"\1", anon)
    anon = re.sub(r"(?:\[[^\]\n]{1,40}\]|[\w.-])*\[[^\]\n]{1,40}\](?:\[[^\]\n]{1,40}\]|[\w.-])*@(?:\[[^\]\n]{1,40}\]|[\w.-])+", lambda m: neu(m.group(0), "E-Mail"), anon)
    L = anon.split("\n")                                 # 5
    if sum(1 for l in L if _BETRAG_Z.fullmatch(l)) >= 10:
        for i, l in enumerate(L[:-2]):
            if not _BETRAG_Z.fullmatch(l):
                continue
            n = L[i + 1]
            if re.search(r"\[(?:Person|Firma) ", n):
                teil = True
                L[i + 1] = re.sub(r"(?<![\w\[])[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]{2,}(?![\w\]])", lambda m: m.group(0) if _gemeinwort(m.group(0)) or _KEIN_PARTNER.search(m.group(0)) else neu(m.group(0), "Person"), n)
                z = L[i + 2].strip()
                if re.fullmatch(r"[A-ZÄÖÜ][a-zäöüß-]{2,}(?: [A-ZÄÖÜ][a-zäöüß-]{2,}){1,2}", z) and not any(_gewoehnlich(w) or _KEIN_PARTNER.search(w) for w in z.split()):
                    L[i + 2] = neu(z, "Person")
        anon = "\n".join(L)
    return anon, mp


def _gewoehnlich(w):
    """Служебное или обиходное слово (не часть имени): стоп-слово словаря или слово из короткого списка платёжных формул."""
    return anonymizer._nlp().vocab[w.lower()].is_stop or bool(re.fullmatch(r"(?i)sagt|danke|dank|bitte|für|fuer|von|und|oder|monat|rate|beitrag|spende|rechnung|training|kurs|unterricht|gebühr|gebuehr", w))


# улица, названная тем же словом, что и организация из состава («[Finanzamt 10]. 2», «[Krankenkasse 3]str. 14»): это адрес, а не организация
_ORG_STR = re.compile(r"\[(?:Finanzamt|Krankenkasse|Bank|Behörde|Firma|Steuerberater|Kanzlei)[^\]\n]{0,30}\](?:-?[Ss]tra(?:ß|ss)e|-?[Ss]tr\.|weg|platz|allee|gasse|\.)\s?(?!(?:19|20)\d\d\b)\d{1,4}(?: ?[a-z]\b)?(?![\w]|[.,]\d)", re.M)
_NOMEN = {}


def _nomen(w, text):
    """Слово словаря, которое немецкая модель в этом тексте видит нарицательным, а не именем собственным (см. anonymizer._gemeinwort_im_text)."""
    if w not in _NOMEN:
        _NOMEN[w] = anonymizer._gemeinwort_im_text(w, text)
    return _NOMEN[w]


def _gemeinwort(w):
    """Обычное немецкое слово: служебное либо из словаря базы права (de_wortliste.txt.gz). Оговорка: название района, совпадающее с обычным
    словом («Mitte», «Neustadt»), после метки города так не закрывается."""
    return _gewoehnlich(w) or w.lower() in wortliste()


_GESETZWORT = []
# слова из названий торговцев и сервисов (не имена): «CHATGPT SUBSCRIPTION», «Google Workspace» -- находка агента дела 16.10.2026
_HANDEL = re.compile(r"(?i)subscription|workspace|cloud|services?|store|shop|market|online|digital|pay|apps?|tickets?|parking|parken|leasing|bank|insurance|travel|hotel|airlines?|air|rail|bahn|google|amazon|apple|microsoft|chatgpt|openai|netflix|spotify|plus|premium|pro|outlet|express|mobile|telecom|energy|club|academy|campus")


def _gesetzwort(w):
    """Строгая проверка «обычного слова» для правил об именах (16.10.2026): словарь только из законов и писем BMF (de_wortliste_gesetz.txt.gz,
    146 тыс. слов). В общем словаре базы (de_wortliste.txt.gz) есть фамилии из решений и литературы -- фамилия продавца считалась обычным словом."""
    if not _GESETZWORT:
        import gzip
        f = Path(__file__).parent / "de_wortliste_gesetz.txt.gz"
        _GESETZWORT.append(set(gzip.open(f, "rt", encoding="utf-8").read().split("\n")) if f.exists() else wortliste())
    return _gewoehnlich(w) or w.lower() in _GESETZWORT[0]


def gegenpartei_zeilen(anon, mp):
    """Выписка, не распознанная как банковская (прогон 11.10.2026: выписка прошла как «Rechnung», имена плательщиков заглавными буквами
    остались в листе): строка сразу после строки-суммы в выписке -- контрагент. Если это 2–5 слов из букв без метки и без банковского
    слова, строка заменяется меткой во всём тексте. Лишняя замена здесь дешевле пропуска. -> (текст, замены)"""
    L = anon.split("\n")
    if sum(1 for l in L if _BETRAG_Z.fullmatch(l)) < 10:
        return anon, mp
    namen = []
    for i, l in enumerate(L[:-1]):
        n = L[i + 1].strip()
        if _BETRAG_Z.fullmatch(l) and "[" not in n and re.fullmatch(r"[A-Za-zÄÖÜäöüß.&'-]{2,}(?: [A-Za-zÄÖÜäöüß.&'-]{2,}){1,4}", n) and n[:1].isupper() and not _KEIN_PARTNER.search(n) and n not in namen:
            if any(_gewoehnlich(w) for w in n.split()):
                continue                                 # строка из обычных слов -- назначение платежа, не контрагент
            namen.append(n)
    k = 900
    for n in sorted(namen, key=len, reverse=True):
        k += 1
        art = "Firma" if re.search(r"(?i)\b(gmbh|ug|ag|kg|ohg|e\.? ?v\.?|verein|gbr|mbh|se|stiftung|versicherung|kasse|stadt|amt)\b", n) else "Person"
        ph = f"[{art} {k}]"
        anon = re.sub(rf"(?<![\w\[]){re.escape(n)}(?![\w\]])", ph, anon)
        mp[ph] = n
        for w in n.split():                              # часть имени, стоящая в тексте отдельно (фамилия в назначении платежа), -- той же меткой
            if len(w) >= 4 and not _gewoehnlich(w) and not anonymizer.KEEP.match(w.capitalize()):
                anon = re.sub(rf"(?i)(?<![\w\[]){re.escape(w)}(?![\w\]])", ph, anon)
    return anon, mp


def same_label(mapping, ph, val):
    """Глобальная метка для значения: точное совпадение или то же слово в другой записи/форме
    (кириллица <-> латиница, падежное окончание, ошибка распознавания) того же вида данных."""
    g = next((k for k, v in mapping.items() if v == val), None)
    if g or len(val) < 5:
        return g
    from figuranten import norm
    from rapidfuzz import fuzz
    kind = ph[1:-1].rsplit(" ", 1)[0]
    nv = norm(val)
    for k, v in mapping.items():
        if k[1:-1].rsplit(" ", 1)[0] == kind and len(v) >= 5 and fuzz.ratio(nv, norm(v)) >= 88:
            return k
    return None


VORGABE_KOPF = """# ДЕЙСТВУЮЩИЕ ЛИЦА ДЕЛА -- выбирает и проверяет обработчик (аудитор).
# Файл содержит подлинные имена: остаётся в папке дела, моделям не показывать.
#
# Программа нашла в материалах лиц и организации (ниже). Что сделать:
#   1. У ОСНОВНЫХ действующих лиц оставьте в начале строки «+», у остальных поставьте «-».
#   2. Проверьте маску (под ней лицо пойдёт в лист) и роль; поправьте, если неверно.
#   3. Одно лицо в нескольких строках -- перенесите написания в одну строку через «;», лишние строки удалите.
#   4. Сотрудника организации назовите «Организация: кто» (например «Kanzlei 1: Berater») -- связь попадёт в лист.
#   5. Можно добавить свою строку.
# Строка:   +|-  маска | роль | написания через «;»      (после «  #» -- справка программы, её можно не трогать)
# Всё, что помечено «-» или не названо, обезличивается как обычно, но в перечень действующих лиц не входит.
# После правки повторите сборку:  python3 anon_paket.py <папка>
"""


EINLEITUNG_KOPF = """# ВВОДНАЯ ОБРАБОТЧИКА (аудитора) к делу. Свободный текст, можно с подлинными именами: файл остаётся в папке дела,
# в лист идёт обезличенным, отдельным блоком перед документами, с пометкой «со слов обработчика, документами не подтверждено».
# Строки, начинающиеся с «#», в лист не идут. Заполните то, что знаете; пустые разделы можно удалить.

SITUATION (кто клиент, что за дело, кто участвует и в какие периоды):

PROBLEM (что случилось, что требуют, какие суммы):

ZIEL (чего нужно добиться):

AUFGABEN (что нужно проверить или посчитать):

BEKANNT ÜBER DIE UNTERLAGEN HINAUS (то, чего в документах нет: кто кого сменил и когда, личные обстоятельства, устные договорённости):

# Заголовки выше не обязательны: можно вставить сюда свой текст целиком, под своими заголовками.
# КРУГИ ВОПРОСОВ: ответы на вопросы модели дописывайте ниже, не стирая прежних, каждый круг под своей строкой, например:
# RUNDE 1 (09.10.2026):
# Перед ответом можно поставить статус:  НЕ ЗНАЮ: (сведения нужно добыть)   ПРЕДПОЛОЖЕНИЕ: (как я понимаю, не проверено)
# Когда вопросов достаточно, напишите отдельной строкой:  GENUG   (или ДОСТАТОЧНО)
"""


def korrekturen(docs_dir):
    """Исправления обработчика к полям документов: <дело>/_pipeline/KORREKTUR.txt, строки «номер | поле=значение; поле=значение».
    Поля: art, datum (ДД.ММ.ГГГГ), von, an (маски состава в квадратных скобках). -> {номер или «14b»: {поле: значение}}"""
    f = Path(docs_dir).parent / "KORREKTUR.txt"
    if not f.exists():
        f.write_text("# Исправления обработчика к документам листа. Строка:  номер | art=...; datum=ДД.ММ.ГГГГ; von=[Maske]; an=[Maske]\n"
                     "# Номер -- как в листе («16») или письмо сборного файла («14b»). Пример:\n# 16 | art=Einkommensteuerbescheid; datum=12.11.2025; von=[Finanzamt]; an=[Mandantin]\n", encoding="utf-8")
        return {}
    out = {}
    for ln in f.read_text(encoding="utf-8").split("\n"):
        if ln.lstrip().startswith("#") or "|" not in ln:
            continue
        nr, rest = ln.split("|", 1)
        out[nr.strip()] = {k.strip().lower(): v.strip() for k, v in (x.split("=", 1) for x in rest.split(";") if "=" in x)}
    return out


def einleitung_namen(text):
    """Имена, места и названия во вводной, которых общее обезличивание не видит (прогон 09.10.2026: в одобренный лист прошли русское
    название города и название фирмы в кавычках). -> [(написание, вид)]; вид -- Ort, Person или Firma."""
    out = []
    for m in re.finditer(r"[«„\"]([A-ZÄÖÜА-ЯЁ][^»“\"\n]{2,40})[»“\"]", text):
        out.append((m.group(1).strip(), "Firma"))
    try:
        import pymorphy3
        morph = pymorphy3.MorphAnalyzer()
        for w in dict.fromkeys(re.findall(r"(?<![\w\[])[А-ЯЁ][а-яё]{3,}(?![\w\]])", text)):
            tags = {str(g) for p_ in morph.parse(w)[:3] for g in p_.tag.grammemes if p_.score >= 0.2}
            if tags & {"Geox"}:
                out.append((w, "Ort"))
            elif tags & {"Surn", "Patr"} or (tags & {"Name"} and not morph.parse(w.lower())[0].tag.POS in ("PREP", "CONJ")):
                out.append((w, "Person"))
    except Exception:                                    # noqa: BLE001
        pass
    if len(re.findall(r"[А-Яа-яЁё]", text)) > len(text) * 0.3:      # немецкие имена и места внутри русского текста: проверка немецкой моделью на несущей фразе
        nlp = anonymizer._nlp()
        for span in dict.fromkeys(re.findall(r"(?<![\w\[])[A-ZÄÖÜ][a-zäöüß]{3,}(?:[ -][A-ZÄÖÜ][a-zäöüß]{2,}){0,2}(?![\w\]])", text)):
            if anonymizer.KEEP.match(span.split()[0]) and " " not in span:
                continue
            ents = [e.label_ for e in nlp(f"Das Schreiben kam aus {span}.").ents if span.split()[0] in e.text]
            if ents:
                out.append((span, "Ort" if ents[0] == "LOC" else "Firma" if ents[0] == "ORG" else "Person"))
    return list(dict.fromkeys(out))


def einleitung_roh(docs_dir):
    """Текст вводной обработчика без строк-комментариев; пусто, если не заполнена (остались одни заголовки шаблона)."""
    f = Path(docs_dir).parent / "EINLEITUNG.txt"
    if not f.exists():
        f.write_text(EINLEITUNG_KOPF, encoding="utf-8")
        __import__("os").chmod(f, 0o600)
        return ""
    t = "\n".join(l for l in f.read_text(encoding="utf-8").split("\n") if not l.lstrip().startswith("#")).strip()
    inhalt = re.sub(r"(?m)^(SITUATION|PROBLEM|ZIEL|AUFGABEN|BEKANNT ÜBER DIE UNTERLAGEN HINAUS)[^\n:]*:\s*", "", t).strip()
    return t if len(inhalt) >= 20 else ""


def _vorgabe_zeilen(docs_dir):
    f = Path(docs_dir).parent / "AKTEURE_VORGABE.txt"
    out = []
    if not f.exists():
        return out
    for ln in f.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"\s*([+\-?xXхХ])\s+(.+)", ln)
        if not m or ln.lstrip().startswith("#") or m.group(2).count("|") < 2:
            continue
        maske, rolle, schreib = (x.strip() for x in m.group(2).split("  #")[0].split("|", 2))
        vs = [v.strip() for v in schreib.split(";") if len(v.strip()) >= 3 and not v.strip().startswith("---")]      # «=Название» -- название общеизвестно, не скрывать
        if maske and (vs or m.group(1) == "+"):           # основная организация может быть без написаний: строка нужна, чтобы к ней относились сотрудники
            out.append((m.group(1), re.sub(r"[\[\]]", "", maske), rolle, vs))
    return out


_TITEL = [(r"Steuerfachangestellte[rn]?", "Steuerfachangestellte(r) einer Kanzlei"), (r"Assistent(?:in)? der Geschäftsleitung", "Assistenz der Geschäftsleitung einer Kanzlei"),
          (r"Bilanzbuchhalter(?:in)?", "Bilanzbuchhalter(in) einer Kanzlei"), (r"Lohnbuchhalter(?:in)?|Lohnsachbearbeiter(?:in)?", "Lohnbuchhaltung einer Kanzlei"),
          (r"Betriebsprüfer(?:in)?|Prüfende Person|Prüfer(?:in)?", "Betriebsprüfer(in) des Finanzamts"), (r"Sachbearbeiter(?:in)?", "Sachbearbeiter(in)"),
          (r"Steuerberater(?:in)?|StB\b", "Steuerberater(in)"), (r"Rechtsanw[aä]lt(?:in)?", "Rechtsanwalt/Rechtsanwältin")]
_NAMENSTEIL = re.compile(r"[A-ZÄÖÜА-ЯЁ][a-zäöüßа-яё]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]{2,})?")


def _namensartig(v):
    """Похоже ли написание на имя лица или название: не длиннее четырёх слов, без цифр, есть слово с заглавной буквы от четырёх букв."""
    t = v.split()
    return 1 <= len(t) <= 4 and len(v) <= 45 and not re.search(r"\d", v) and any(_NAMENSTEIL.fullmatch(x.strip(".,")) and len(x) >= 4 for x in t)


def vorschlag(docs_dir):
    """Шаг диалога (решение автора 09.10.2026: «анонимайзер после обработки первички спрашивает: обнаружены вот такие действующие
    лица… выберите основных и проверьте их роли»). Пишет предложение программы в AKTEURE_VORSCHLAG.txt (каждый раз заново) и,
    если файла выбора ещё нет, создаёт из него AKTEURE_VORGABE.txt; при повторных сборках дописывает в файл выбора только новых.
    Учтены замечания обкатки 09.10: мусорные написания и строки не предлагаются; одиночная часть двойной фамилии -- другому супругу;
    строки с общим именем склеиваются; должность из подписи идёт в роль; организации предлагаются наравне с людьми; у каждого лица
    указано, в каких документах и рядом с кем оно встречается.  -> (основных отмечено, всего строк, новых дописано)"""
    from rapidfuzz import fuzz
    P = Path(docs_dir).parent
    f, rf = P / "AKTEURE_VORGABE.txt", P / "figuranten.json"
    auto = [dict(r) for r in json.load(open(rf, encoding="utf-8")) if r.get("sicher")] if rf.exists() else []
    texte = {x.name: x.read_text(encoding="utf-8") for x in sorted(Path(docs_dir).glob("*.txt"))}
    # сведения прошлой сборки: номер документа листа, вид, дата
    info = {}
    try:
        q = json.load(open(P / "annahme_quellen.json", encoding="utf-8"))
        sh = {str(d["nr"]): d for d in json.load(open(P / "austausch.json", encoding="utf-8"))["documents"]}
        info = {name: f"№ {nr} {sh[nr]['kind'][:28]} {sh[nr].get('date') or ''}".strip() for nr, name in q.items() if nr in sh}
    except Exception:                                    # noqa: BLE001  (первой сборки ещё не было)
        pass
    kand = []
    for r in sorted(auto, key=lambda r: -r.get("erwaehnungen", 0)):
        if r["rolle"].startswith("Bearbeiter"):
            continue
        vs = [v for v in r.get("varianten", []) if not v.startswith("Gesprächspartner") and _namensartig(v)
              and not (" " not in v and (anonymizer.KEEP.match(v) or re.search(r"(ung|keit|heit|schaft|tion|nis|ungen|steuer|betrag)$", v)))]      # обычное слово -- не имя
        if vs:
            kand.append({"maske": re.sub(r"[\[\]]", "", r["label"]), "rolle": r["rolle"], "vs": vs, "n": r.get("erwaehnungen", 0)})
    if not auto:                                         # дело без переписки: реестра участников нет -- кандидаты из уже поставленных масок лиц
        try:                                             # (прогон 11.10.2026: в шести делах без переписки предложение состава было пустым)
            mp_p = json.load(open(P / "mapping_dossier.json", encoding="utf-8"))
            blob_p = (P / "dossier_anon.md").read_text(encoding="utf-8")
            for ph, v in sorted(mp_p.items(), key=lambda x: -blob_p.count(x[0])):
                v = " ".join(str(v).split())
                if ph.startswith("[Person") and blob_p.count(ph) >= 2 and (_namensartig(v) or re.fullmatch(r"[А-ЯЁ][а-яё]{2,}(?:[ -][А-ЯЁ][а-яё.]+){0,2}", v)) and len(kand) < 40:
                    kand.append({"maske": re.sub(r"[\[\]]", "", ph), "rolle": "unbekannt (aus den Unterlagen, Rolle vom Bearbeiter zu setzen)", "vs": [v], "n": blob_p.count(ph)})
        except Exception:                                # noqa: BLE001  (первой сборки ещё не было)
            pass
    mand = next((k for k in kand if k["rolle"].startswith("Mandant")), None)
    gatte = next((k for k in kand if k["rolle"].startswith("Ehegatte")), None)
    if mand and gatte:                                   # одиночная часть двойной фамилии клиентки -- это другой супруг
        teile = {t.lower() for v in mand["vs"] for t in re.split(r"[\s-]+", v) if "-" in v}
        gn = {t.lower() for v in gatte["vs"] for t in v.split()}
        einzeln = [v for v in mand["vs"] if " " not in v and "-" not in v and v.lower() in teile and v.lower() in gn]
        mand["vs"] = [v for v in mand["vs"] if v not in einzeln]
        gatte["vs"] = list(dict.fromkeys(gatte["vs"] + einzeln))
    # написание с чужим именем -- убрать (склейка распознавания: «Фамилия клиентки Herr Фамилия консультанта»)
    for k in kand:
        fremd = {t.lower() for o in kand if o is not k for v in o["vs"] for t in v.split() if len(t) >= 5} - {t.lower() for t in k["vs"][0].split()}
        k["vs"] = [v for v in k["vs"] if v == k["vs"][0] or not any(t.lower() in fremd for t in v.split())]
    haupt_k = [k for k in kand if not k["rolle"].startswith("unbekannt")]
    for k in [k for k in kand if k["rolle"].startswith("unbekannt")]:      # «unbekannt» с тем же первым именем, что у названного лица, -- к нему
        ziel = next((o for o in haupt_k if any(k["vs"][0].split()[0].lower() == v.split()[0].lower() for v in o["vs"] if len(v.split()[0]) >= 3 and " " in v)), None)
        if ziel:
            ziel["vs"] = list(dict.fromkeys(ziel["vs"] + k["vs"]))
            kand.remove(k)
    zeilen = []
    ein = einleitung_roh(docs_dir)
    ein_namen = []                                       # имена, организации и места, названные во вводной, но не найденные в документах: в состав как кандидаты
    if ein:
        try:
            _, mp_e = anonymizer.anonymize(ein, 1, ner="per")
            roh_e = [str(v).strip() for ph, v in mp_e.items() if ph.startswith(("[Person", "[Firma", "[Ort"))]
            roh_e += [n_ for n_, _ in einleitung_namen(ein)]            # названия в кавычках, русские имена и места, немецкие имена в русском тексте
            bek = [v.lower() for k in kand for v in k["vs"]]
            for n in dict.fromkeys(roh_e):
                if len(n) >= 4 and not anonymizer.KEEP.match(n) and max((fuzz.token_sort_ratio(n.lower(), b) for b in bek), default=0) < 80:
                    in_docs = sum(1 for t in texte.values() if re.search(re.escape(n), t, flags=re.I))
                    ein_namen.append(f"? {n} | названо во вводной | {n}  # в документах встречается в {in_docs} текстах" + ("" if in_docs else " -- В ДОКУМЕНТАХ НЕТ: опечатка или лицо вне документов? проверьте") + "; замените «?» на «+» (основное), «-» (прочее) или «x» (не имя)")
        except Exception:                                # noqa: BLE001
            pass
    for k in kand:
        orte, titel, nachbarn = [], None, set()
        for name, t in texte.items():
            for v in k["vs"]:
                for m in re.finditer(re.escape(v), t):
                    if name not in orte:
                        orte.append(name)
                    nah = t[m.end(): m.end() + 70]
                    titel = titel or next((lab for rx, lab in _TITEL if re.search(rx, nah)), None)
                    fen = t[max(0, m.start() - 300): m.end() + 300]
                    nachbarn |= {o["maske"] for o in kand if o is not k and any(x in fen for x in o["vs"])}
        if k["rolle"].startswith(("Steuerberater", "Mitarbeiter", "unbekannt", "Finanzamt", "Krankenkasse")) and titel:
            k["rolle"] = titel
        haupt = k["rolle"].startswith(("Mandant", "Ehegatte")) and k["n"] >= 3 or (not k["rolle"].startswith(("unbekannt", "Vermieter", "Mitarbeiter")) and k["n"] >= 3)
        in_ein = any(re.search(rf"(?<!\w){re.escape(v)}", ein, flags=re.I) for v in k["vs"] if len(v) >= 4)
        rolle_ein = next((w for rx_r, rx_e, w in (
            (r"(?i)steuerberat|kanzlei|steuerfach|assisten|bilanzbuch|lohnbuch", r"(?i)консультант|бератор|берат|канцеляр|steuerberat|berater|kanzlei", "консультанты"),
            (r"(?i)krankenkasse", r"(?i)касс|krankenkasse|kasse\b", "касса"),
            (r"(?i)finanzamt|prüfer", r"(?i)налогов|финанцамт|проверк|finanzamt|betriebsprüfung|prüfung", "налоговая")) if re.search(rx_r, k["rolle"]) and re.search(rx_e, ein)), None)
        haupt = haupt or in_ein or bool(rolle_ein)
        wo = "; ".join(info.get(o, re.sub(r"^.*\.(pdf|jpe?g|png)\.txt$", r"скан/фото", o) if not info else "текст вне листа") for o in orte[:4])
        zeilen.append((k, f"{'+' if haupt else '-'} {k['maske']} | {k['rolle']} | {'; '.join(k['vs'])}  # {'НАЗВАН ВО ВВОДНОЙ; ' if in_ein else f'РОЛЬ ИЗ ВВОДНОЙ ({rolle_ein}); ' if rolle_ein else ''}упоминаний {k['n']}; документы: {wo or '—'}"
                       + (f"; рядом: {', '.join(sorted(nachbarn)[:5])}" if nachbarn else "")))
    org = ["+ Krankenkasse | Krankenkasse (handelt durch ihre Mitarbeiter) | ---  # организация: написания можно не вписывать; сотрудников запишите «Krankenkasse: …»",
           "+ Finanzamt | Finanzamt (handelt durch Mitarbeiter und Prüfer) | ---  # организация; сотрудников запишите «Finanzamt: …»",
           "+ Kanzlei 1 | Steuerkanzlei | ---  # впишите название; сотрудников запишите «Kanzlei 1: …»; при нескольких канцеляриях добавьте строки «Kanzlei 2», «Kanzlei 3»"]
    try:                                                 # фирмы, найденные прошлой сборкой, -- как кандидаты в организации
        mp = json.load(open(P / "mapping_dossier.json", encoding="utf-8"))
        blob = (P / "dossier_anon.md").read_text(encoding="utf-8")
        for ph, v in mp.items():
            if ph.startswith("[Firma") and len(v.strip()) >= 5 and blob.count(ph) >= 2 and not re.search(r"(?i)bank|sparkasse", v):
                org.append(f"- {re.sub(r'[\[\]]', '', ph)} | Firma (Kanzlei? Betrieb der Mandantin? sonstige) | {v.strip()}  # упоминаний в листе {blob.count(ph)}")
    except Exception:                                    # noqa: BLE001
        pass
    # кандидаты локальной модели (если её прогон есть): организации и новые написания; связи и роли от модели не берутся (стенд 09.10.2026:
    # организации 5 из 5 против 0 у правил, но связей 0–1 из 8, а 40–45 % записей -- мусор; поэтому фильтр перед показом)
    llm_org, llm_neu = [], []
    try:
        llm = json.load(open(P / "akteure_llm.json", encoding="utf-8"))
        FELD = re.compile(r"(?i)^(name|vorname|nachname|ehegatt\w*|ehemann|ehefrau|person [ab]|steuerpflichtige\w*|steuernummer|anschrift|unterschrift|datum|seite|anlage\w*|"
                          r"finanzamt|krankenkasse|bank|steuerberater\w*|mandant\w*|inhalt\w*|bericht|bescheid|deutschland)$")
        ADR = re.compile(r"(?i)stra(ß|ss)e|str\.|\bweg\b|platz|allee|postfach|\b\d{5}\b")
        bekannt_k = [v.lower() for k in kand for v in k["vs"]]
        alt_z = _vorgabe_zeilen(docs_dir)
        bekannt_alt = [v.lower() for _, _, _, vs_ in alt_z for v in vs_]
        gesehen = set()
        for modell, g in llm.items():
            for v in g.values():
                n = " ".join(str(v.get("name", "")).split())
                n = n.rstrip(" .,;:")
                if n.lower() in gesehen or not _namensartig(n) or FELD.match(n) or ADR.search(n) or not any(w[:1].isupper() and len(w) >= 4 for w in n.split()):
                    continue
                if any(w in (".", "-", "/") for w in n.split()) or all(re.search(r"(?i)(ung|versicherung|verzeichnis|verbindung|dienst|beteiligte[rn]?|seite|konto|nummer)$", w) or len(w) < 4 for w in n.split()):
                    continue                             # служебные слова бланков и общие существительные без имени собственного
                gesehen.add(n.lower())
                ist_org = any(str(a).lower().startswith(("org", "beh")) for a in v.get("art", []))
                aehn_k = max((fuzz.token_sort_ratio(n.lower(), b) for b in bekannt_k), default=0)          # против найденного программой
                aehn = max([aehn_k] + [fuzz.token_sort_ratio(n.lower(), b) for b in bekannt_alt])                  # и против файла выбора аудитора
                wo = "; ".join(info.get(o, "скан/фото") for o in v.get("docs", [])[:3])
                kern = re.sub(r"(?i)^(herrn?|frau|firma|dr\.?|prof\.?|stb\.?|dipl\.-\w+\.?)\s+", "", n)
                if kern != n and (kern.lower() in bekannt_k or kern.lower() in bekannt_alt):
                    continue                             # обращение или звание + известное написание -- не новое написание
                if 80 <= aehn < 100:
                    ziel = next((k["maske"] for k in kand if any(fuzz.token_sort_ratio(n.lower(), x.lower()) == aehn for x in k["vs"])), "?")
                    ziel = next((m_ for _, m_, _, vs_ in alt_z if max((fuzz.token_sort_ratio(n.lower(), x.lower()) for x in vs_), default=0) >= 80), ziel)      # маска из файла выбора аудитора, если лицо там уже есть
                    llm_neu.append(f"? {ziel} | возможно, ещё одно написание | {n}  # нашла модель {modell.split(':')[0]}; документы: {wo}; если то же лицо -- перенесите написание в его строку")
                elif ist_org and aehn_k < 80 and len(v.get("docs", [])) >= 1 and len(n) >= 6:
                    llm_org.append((len(v.get("docs", [])), f"- {n} | Organisation (Vorschlag des lokalen Modells) | {n}  # нашла модель {modell.split(':')[0]}; документы: {wo}"))
        llm_org = [z for _, z in sorted(llm_org, key=lambda x: -x[0])][:25]
    except Exception:                                    # noqa: BLE001  (прогона модели нет)
        pass
    if llm_org:
        org += ["# -- организации, предложенные локальной моделью (проверьте: среди них бывают названия программ, бланков и мест) --"] + llm_org
    kopf = VORGABE_KOPF + "#   x  в начале строки -- это не лицо и не организация (обычное слово, ошибка распознавания): из замен убрать совсем.\n"
    text_neu = kopf + "\n# ОРГАНИЗАЦИИ\n" + "\n".join(org) + "\n\n# ЛИЦА\n" + "\n".join(z for _, z in zeilen) + "\n" + \
        ("\n# ВОЗМОЖНЫЕ НОВЫЕ НАПИСАНИЯ (локальная модель)\n" + "\n".join(llm_neu) + "\n" if llm_neu else "") + \
        ("\n# НАЗВАНО ВО ВВОДНОЙ, В СОСТАВЕ ЕЩЁ НЕТ (пока стоит «?», в листе это обезличивается как обычное имя)\n" + "\n".join(ein_namen) + "\n" if ein_namen else "")
    (P / "AKTEURE_VORSCHLAG.txt").write_text("# Предложение программы от " + __import__("time").strftime("%d.%m.%Y %H:%M") + " (для справки; правьте AKTEURE_VORGABE.txt)\n" + text_neu, encoding="utf-8")
    __import__("os").chmod(P / "AKTEURE_VORSCHLAG.txt", 0o600)
    alt = _vorgabe_zeilen(docs_dir)
    n_neu = 0
    if not f.exists():
        f.write_text(text_neu, encoding="utf-8")
        __import__("os").chmod(f, 0o600)
    else:
        bekannt = [v.lower() for _, _, _, vs in alt for v in vs]
        neue = [z for k, z in zeilen if not bekannt or max((fuzz.token_sort_ratio(a.lower(), b) for a in k["vs"] for b in bekannt), default=0) < 86]
        n_neu = len(neue)
        neue += [z for z in ein_namen if not any(z.split(" | ")[2].split("  #")[0].strip().lower() == b for b in bekannt)
                 and z.split(" | ")[0][2:].lower() not in f.read_text(encoding="utf-8").lower()]
        n_neu = len(neue)
        if neue:                                         # 11.10.2026: при пустом списке написаний (в файле только три заготовки организаций) новые лица не дописывались
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(f"\n# НОВЫЕ лица, найденные при сборке {__import__('time').strftime('%d.%m.%Y %H:%M')} -- проверьте:\n" + "\n".join(neue) + "\n")
    z = _vorgabe_zeilen(docs_dir)
    return sum(1 for x in z if x[0] == "+"), sum(1 for x in z if x[0] in "+-"), n_neu


def load_vorgabe(docs_dir):
    """Основные действующие лица, отмеченные обработчиком знаком «+» в AKTEURE_VORGABE.txt. -> записи реестра."""
    out = []
    for zeichen, maske, rolle, vs in _vorgabe_zeilen(docs_dir):
        if zeichen != "+":
            continue
        offen = [v[1:].strip() for v in vs if v.startswith("=")]
        vs = [v for v in vs if not v.startswith("=")]
        out.append({"label": f"[{maske}]", "rolle": rolle or "ohne Angabe", "name": vs[0] if vs else maske, "varianten": vs, "offen": offen, "sicher": True, "bestaetigt": True, "_vorgabe": True,
                    "gehoert_zu": f"[{maske.split(':')[0].strip()}]" if ":" in maske else None})
    return out


def load_registry(docs_dir):
    """Реестр: сначала лица, заданные обработчиком, затем найденные программой. Найденное программой лицо, совпадающее с заданным
    (по имени, с допуском на искажения), отдаёт заданному свои варианты написания и из реестра уходит."""
    from rapidfuzz import fuzz
    f = Path(docs_dir).parent / "figuranten.json"
    auto = [r for r in json.load(open(f, encoding="utf-8")) if r.get("sicher")] if f.exists() else []
    # мусорные написания найденных программой лиц (имитация дела А 12.10.2026: в реестре стояли куски предложений до 22 слов и одиночные обычные слова,
    # одна такая запись получила роль клиента и дала ложные метки): написание длиннее шести слов и написание из одного слова словаря базы права
    # в замену не идут; запись без годных написаний из реестра уходит. Заданного обработчиком это не касается.
    W_ = wortliste()
    for r in auto:
        r["varianten"] = [v for v in r.get("varianten", []) if len(v.split()) <= 6 and not (len(v.split()) == 1 and v.strip().lower() in W_)]
    auto = [r for r in auto if r["varianten"]]
    vor = load_vorgabe(docs_dir)
    weg = [v.lower() for z, _, _, vs in _vorgabe_zeilen(docs_dir) if z in "xXхХ" for v in vs]           # «x» -- не лицо: из реестра убрать совсем
    if weg:
        auto = [r for r in auto if max((fuzz.token_sort_ratio(a.lower(), b) for a in r.get("varianten", []) + [r.get("name", "")] for b in weg), default=0) < 90]
    if not vor:
        return auto
    rest = []
    for r in auto:
        best, score = None, 0
        for v in vor:
            sc = max((fuzz.token_sort_ratio(a.lower(), b.lower()) for a in r.get("varianten", []) + [r.get("name", "")] for b in v["varianten"] if len(a) >= 4), default=0)
            if sc > score:
                best, score = v, sc
        if best is not None and score >= 86:
            best["varianten"] = list(dict.fromkeys(best["varianten"] + [x for x in r.get("varianten", []) if len(x) >= 4]))      # и «Gesprächspartner…»: по нему протокол узнаёт говорящего
        else:
            rest.append(r)
    return vor + rest


def apply_registry(text, registry):
    """Все варианты написания каждого уверенного лица -> его метка («[Mandantin 1]»). Порядок: длинные варианты первыми.
    Варианты длиннее 7 букв -- с допуском на две ошибки распознавания; короче -- с подстановкой похожих знаков («O/ga», «0lga», «Stol1»);
    русские варианты -- с падежными окончаниями; «Herr + фамилия клиентки» -> супруг, если он есть в реестре (08.10.2026)."""
    import regex
    OCR = {"l": "[lI1/|!]", "I": "[lI1/|!]", "i": "[il1!|]", "o": "[o0]", "O": "[O0Q]", "s": "[s5$]", "S": "[S5$]", "B": "[B8]", "g": "[g9q]", "a": "[aä@]", "e": "[eéc]", "t": "[tf]", "m": "(?:m|rn)"}
    gatte = next((r["label"] for r in registry if re.search(r"Ehegatt|Ehemann|Ehefrau|Ehepartner", str(r.get("rolle", "")) + r["label"])), None)
    mand = next((r for r in registry if r["label"].startswith("[Mandant")), None)
    if gatte and mand:
        for v in sorted((v for v in mand["varianten"] if " " not in v and len(v) >= 4), key=len, reverse=True):
            text = re.sub(rf"\b(Herrn?|Hr\.)\s+{re.escape(v)}(?![\w\]])", lambda m: m.group(1) + " " + gatte, text)
    pairs = sorted(((v, r["label"], bool(r.get("_vorgabe"))) for r in registry for v in r["varianten"] if len(v) >= 4 and not v.startswith("Gesprächspartner")), key=lambda x: -len(x[0]))
    for v, lab, vorg in pairs:
        core = re.escape(v)
        text = re.sub(rf"(?<![\w\[]){core}(?![\w\]])", lab, text, flags=re.I if vorg and len(v) >= 5 else 0)
        if vorg and re.search(r"[А-Яа-яЁё]", v) and " " in v:                 # русское название из нескольких слов -- в любом падеже
            stems = [re.escape(re.sub(anonymizer.RU_ENDE, "", w)) + r"[а-яё]{0,4}" if re.fullmatch(r"[А-Яа-яЁё]{4,}", w) else re.escape(w) for w in v.split()]
            text = re.sub(r"(?<![\w\[])" + r"\s+".join(stems) + r"(?![\w\]])", lab, text, flags=re.I)
        if len(re.sub(r"\W", "", v)) >= 8:               # нечёткое совпадение начинается и кончается буквой (иначе съедает пробел перед словом);
            if re.search(r"[А-Яа-яЁё]", v):              # русское слово -- только с заглавной буквы и с одной ошибкой («примерно» -- не «Примеров»)
                text = regex.sub(rf"(?<![\w\[])(?=[А-ЯЁ])(?:{regex.escape(v)}){{e<=1}}(?<=\w)(?![\w\]])", lab, text)
            else:
                text = regex.sub(rf"(?<![\w\[])(?=\w)(?:{regex.escape(v)}){{e<=2}}(?<=\w)(?![\w\]])", lab, text, flags=regex.I)
        elif re.fullmatch(r"[A-Za-zÄÖÜäöüß-]{4,7}", v):
            text = re.sub(rf"(?<![\w\[])" + "".join(OCR.get(c, re.escape(c)) for c in v) + r"(?![\w\]])", lab, text)
            if len(v) >= 6 and v[:1].isupper() and v.lower() not in wortliste():      # одна подменённая буква, не первая («Mustermann» -> «Mustermenn», имитация дела А
                # 12.10.2026: фамилия из 6 букв с другой гласной осталась открытой); слово с заглавной буквы и не из словаря базы права
                text = regex.sub(rf"(?<![\w\[]){regex.escape(v[0])}(?:{regex.escape(v[1:])}){{s<=1}}(?![\w\]])",
                                 lambda m, lab=lab: m.group(0) if m.group(0).lower() in wortliste() else lab, text)
        if re.fullmatch(r"[А-ЯЁ][а-яё]{3,}", v) or vorg and re.fullmatch(r"[А-Яа-яЁё]{4,}", v):
            stem = re.sub(anonymizer.RU_ENDE, "", v)
            if len(stem) >= 4:
                text = re.sub(rf"(?<![\w\[]){re.escape(stem)}[а-яё]{{0,4}}(?![\w\]])", lab, text)
            if len(stem) >= 6:                           # опечатка в переписке («Мустерманным»): одна ошибка в основе, с заглавной буквы
                text = regex.sub(rf"(?<![\w\[])(?=[А-ЯЁ])(?:{regex.escape(stem)}){{e<=1}}(?<=\w)[а-яё]{{1,4}}(?![\w\]])", lab, text)
    # обрывок имени сразу после метки того же лица («[Mandantin 1] Oberschach-», «[Mandantin 1] S/oll»): начало варианта или вариант с двумя ошибками
    for r in registry:
        vs = [v for v in r["varianten"] if " " not in v and len(v) >= 5]
        if not vs:
            continue
        def _rest(m, vs=vs, lab=r["label"]):
            w = m.group(2)
            kern = re.sub(r"[^A-Za-zÄÖÜäöüßА-Яа-яЁё]", "", w)
            if len(kern) >= 3 and any(v.lower().startswith(kern.lower()) or regex.fullmatch(rf"(?:{regex.escape(v)}){{e<=2}}", w, flags=regex.I) for v in vs):
                return m.group(1)
            return m.group(0)
        text = re.sub(rf"({re.escape(r['label'])})[ \t-]+([A-Za-zÄÖÜäöüßА-Яа-яЁё/|!0-9-]{{3,}})(?![\w\]])", _rest, text)
    if gatte and mand:                                   # двойная фамилия клиентки, первая часть которой -- фамилия супруга: «[Ehegatte]-[Mandantin]» -> клиентка (стенд 09.10.2026)
        ml = re.escape(mand["label"])
        text = re.sub(rf"{re.escape(gatte)}-(?:{ml}|[A-Za-zÄÖÜäöüß/|!0-9]{{2,}})", mand["label"], text)
        text = re.sub(rf"({ml})(?:[ \t]+{ml})+", r"\1", text)
    if gatte and mand:                                   # метка клиентки уже поставлена раньше (протокол): «Herr [Mandantin 1]» -- это супруг
        text = re.sub(rf"\b(Herrn?|Hr\.)\s+{re.escape(mand['label'])}", lambda m: m.group(1) + " " + gatte, text)
    return text


def build(docs_dir, question, level=1):
    registry = load_registry(docs_dir)
    docs, mapping, seen = [], {}, set()
    MUELL.clear()
    ZWEIFEL.clear()
    ENTSCHEID.clear()
    ENTSCHEID.update(seiten_entscheid(docs_dir))
    quellen = {}                                         # номер документа листа -> имя текста в docs (локально, для протокола приёмки)
    pf = Path(docs_dir).parent / "protokoll.json"
    proto = [e for e in json.load(open(pf, encoding="utf-8")) if e["art"] not in ("nicht fallbezogen", "Organisatorisches", "Dokument übergeben")] if pf.exists() else []
    # высказывания самого обработчика, кроме вопросов, в лист не идут: это его оценки и рассказы о себе, а не материал дела (08.10.2026)
    proto = [e for e in proto if not (str(e.get("sprecher", "")).startswith("[Bearbeiter") and e["art"] != "Frage")]
    PL = int(__import__("os").environ.get("LM_PROTO_LIMIT", "600"))
    sources = [(f, None) for f in sorted(Path(docs_dir).glob("*.txt"))]
    if proto:
        sources.append((None, "\n".join(f"{e['nr']}\t{e['datum']}\t{e['quelle']}\t{e['sprecher']}\t{e['art']}\t{' '.join(e.get('text_reg', e['text_anon']).split())[:PL]}" for e in proto)))
    ein_roh = einleitung_roh(docs_dir)
    ein_anon = None
    if ein_roh:
        MON_ = ("январь февраль март апрель май июнь июль август сентябрь октябрь ноябрь декабрь" if len(re.findall(r"[А-Яа-яЁё]", ein_roh)) > len(ein_roh) * 0.3
                else "Januar Februar März April Mai Juni Juli August September Oktober November Dezember").split()
        ein_roh = re.sub(r"(?<![\d.])(0?[1-9]|1[0-2])[/.](20\d{2})(?!\d)(?!\.\d)", lambda m: f"{MON_[int(m.group(1)) - 1]} {m.group(2)}", ein_roh)      # «01/2024» -- период, не номер
        ein_reg = apply_registry(ein_roh, registry)
        for k_, (n_, art_) in enumerate(sorted(einleitung_namen(ein_reg), key=lambda x: -len(x[0])), 1):      # то, что общее обезличивание пропускает во вводной
            if n_ in ein_reg:
                lab_ = f"[{art_} {len(mapping) + 1}]"
                mapping[lab_] = n_
                ein_reg = re.sub(rf"(?<![\w\[]){re.escape(n_)}(?![\w\]])", "\x00" + lab_[1:], ein_reg)
        ein_anon, mp = anonymizer.anonymize(ein_reg, level, ner="per")
        ein_anon, mp = anon_ru.nachlese_ru(ein_anon, mp)             # русский текст: падежи, латинское имя в русской строке, фирма в кавычках (11.10.2026)
        for ph, val in mp.items():
            if ph.startswith("["):
                g = same_label(mapping, ph, val)
                if g is None:
                    g = f"{ph[:-1].rsplit(' ', 1)[0]} {len(mapping) + 1}]"
                    mapping[g] = val
                ein_anon = ein_anon.replace(ph, "\x00" + g[1:])
        ein_anon = ein_anon.replace("\x00", "[")
    for f, proto_text in sources:
        if proto_text is not None:                      # протокол беседы -- через тот же цикл, чтобы метки совпадали с документами
            anon, mp = anonymizer.anonymize(apply_registry(proto_text, registry), level, ner="per")
            anon, mp = anon_ru.nachlese_ru(anon, mp)             # русский текст: падежи, латинское имя в русской строке, фирма в кавычках (11.10.2026)
            for ph, val in mp.items():
                if ph.startswith("["):
                    g = same_label(mapping, ph, val)
                    if g is None:
                        g = f"{ph[:-1].rsplit(' ', 1)[0]} {len(mapping) + 1}]"
                        mapping[g] = val
                    elif mapping[g] != val:
                        mapping[f"{g[:-1]}·{len(mapping) + 1}]"] = val          # вторая запись того же значения -- для возврата по ключу
                    anon = anon.replace(ph, "\x00" + g[1:])
            rows = [ln.replace("\x00", "[").split("\t") for ln in anon.split("\n") if ln.count("\t") >= 5]
            docs.append({"nr": len(docs) + 1, "kind": "Gesprächsprotokoll (Chat und Sprachnachrichten; Aussagen, keine belegten Tatsachen)", "issuer_role": "unbekannt",
                         "date": None, "years": [], "pages": 1, "ocr_quality": 1.0, "text": "(siehe Tabelle)",
                         "tables": [{"name": "Aussagen", "columns": ["Nr", "Datum", "Quelle", "Sprecher", "Art", "Aussage"], "rows": [r[:5] + ["\t".join(r[5:])] for r in rows],
                                     "control_sum": None, "note": "aus dem Russischen nicht übersetzt; Behauptungen sind gegen die Unterlagen zu prüfen"}]})
            continue
        raw_full = fix_ocr(f.read_text(encoding="utf-8"))
        raw_lesbar = raw_full
        if re.search(r"\.(pdf|jpe?g|png)\.txt$", f.name.lower()):          # только распознанные сканы и фото; чат, заметки и расшифровки речи не трогаем
            import annahme as _an
            raw_lesbar, n_s, n_z = entmuellen(raw_full, _an.seiten_info(docs_dir, f.name), entscheid=ENTSCHEID.get(f.name))
            MUELL[f.name] = (n_s, n_z)
            if entmuellen.zweifel:
                ZWEIFEL[f.name] = list(entmuellen.zweifel)
        raw = clean(raw_lesbar)
        if len(raw) < 300:
            continue
        # бланк декларации: значения только на странице расчёта -- в короткий лист (без LM_DOC_LIMIT) идёт первая страница. Ошибка 11.10.2026: слово
        # «Zeile» считалось и в пометках «[Zeile nicht gelesen]», которые ставит entmuellen, -- большие пачки писем (145 и 86 страниц) обрезались до
        # первой страницы без предупреждения. Теперь считаются только строки бланка («Zeile 12»), а при полном тексте правило не применяется вовсе.
        if not __import__("os").environ.get("LM_DOC_LIMIT") and (len(re.findall(r"\bZeilen? \d{1,3}\b", raw)) > 30 or "Hauptvordruck" in raw):
            raw = raw.split("--- Seite 2 ---")[0]
        key = re.sub(r"[^a-zäöüа-яё]+", "", raw.lower())
        key = key[300:420] if len(key) >= 420 else key           # у короткого текста ключ -- весь текст (иначе пустой ключ «склеивал» разные короткие документы)
        if key in seen:
            continue
        seen.add(key)
        kind, role = classify(raw)
        MON = {m: i + 1 for i, m in enumerate("Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split())}
        cand = [(m.start(), m.group(1)) for m in re.finditer(r"\b(\d{2}\.\d{2}\.20\d{2})\b", raw[:1800])]
        cand += [(m.start(), f"{int(m.group(1)):02d}.{MON[m.group(2)]:02d}.{m.group(3)}") for m in re.finditer(r"\b(\d{1,2})\. (" + "|".join(MON) + r") (20\d{2})\b", raw[:1800])]
        dates = [d for _, d in sorted(cand)]
        raw = raw.replace("[", "(").replace("]", ")")          # скобки из мусора распознавания не должны выглядеть как метки
        raw = apply_registry(raw, registry)                   # сначала реестр фигурантов: все варианты лица -> одна метка с ролью
        anon, mp = anonymizer.anonymize(raw, level, ner="per")
        anon, mp = anon_ru.nachlese_ru(anon, mp)             # русский текст: падежи, латинское имя в русской строке, фирма в кавычках (11.10.2026)
        anon, mp = gegenpartei_zeilen(anon, mp)
        anon, mp = kennungen_rest(anon, mp)
        anon, mp = nachlese(anon, mp)
        tables = [t for t in ((table_bank(anon) if role == "Bank" else None), (table_ledger(anon) if kind == "Kontoblatt Buchhaltung" else None),
                              (table_accounts(anon) if kind in ("Gewinnermittlung § 4 Abs. 3 EStG", "Summen- und Saldenliste") else None),
                              (table_keyfigures(anon) if kind in ("Beitragsbescheid Krankenkasse", "Einkommensteuerbescheid", "Steuerbescheid", "Bescheid über Nebenleistungen (Zuschläge)", "Rechnung", "Einkommensteuererklärung (Berechnung)",
                                                                  "Betriebsprüfungsbericht", "Schreiben Krankenkasse") else None)) if t]
        if kind.startswith("Beitragskonto"):
            tb = table_beitragskonto(raw_full)
            if tb:
                tables = [tb]
                anon = "\n".join(l for l in anon.split("\n") if l.count("|") < 5)
                beitragskonto_q = round(sum(r[-1] == "ja" for r in tb["rows"]) / len(tb["rows"]), 2)
        for ph, val in mp.items():                                     # метки сквозные по делу
            if ph.startswith("["):
                g = same_label(mapping, ph, val)
                if g is None:
                    g = f"{ph[:-1].rsplit(' ', 1)[0]} {len(mapping) + 1}]"
                    mapping[g] = val
                elif mapping[g] != val:
                    mapping[f"{g[:-1]}·{len(mapping) + 1}]"] = val
                anon = anon.replace(ph, "\x00" + g[1:])
                for t in tables:
                    t["rows"] = [[c.replace(ph, "\x00" + g[1:]) if isinstance(c, str) else c for c in r] for r in t["rows"]]
        fix = lambda s: s.replace("\x00", "[") if isinstance(s, str) else s      # noqa: E731
        for t in tables:
            t["rows"] = [[fix(c) for c in r] for r in t["rows"]]
        q = quality(raw)
        if kind.startswith("Beitragskonto") and tables and tables[0]["name"] == "Beitragskonto":
            q = beitragskonto_q                               # читаемость таблицы = доля строк, прошедших проверку остатка
        d = {"nr": len(docs) + 1, "kind": kind, "issuer_role": role, "date": dates[0] if dates and role != "Bank" else None,
             "years": sorted({int(y) for y in re.findall(r"\b(20[12]\d)\b", raw)})[:8], "pages": max(1, raw_full.count("--- Seite")),
             "ocr_quality": q, "text": fix(anon) if q >= 0.15 else "[unleserlich – Texterkennung unzuverlässig]"}
        if tables:
            d["tables"] = tables
            if role == "Bank":                      # выписка: текст заменяется таблицей (в тексте шум и повтор тех же данных)
                d["text"] = "(siehe Tabelle)"
        docs.append(d)
        quellen[str(d["nr"])] = f.name
    for d in docs:                                       # повторный проход: часть меток ставится после прохода по отдельному документу
        if d["text"] not in ("(siehe Tabelle)",):
            d["text"], mapping = nachlese(d["text"], mapping)
    sheet = {"format": VERSION, "level": level, "question": question, "documents": docs}
    if ein_anon:
        genug = bool(re.search(r"(?im)^\s*(GENUG|ДОСТАТОЧНО)\b", ein_roh)) or bool(STOPP_FREI.search(ein_roh[ein_roh.rfind("\nRUNDE "):] if "\nRUNDE " in ein_roh else ""))      # обработчик закрыл круги вопросов
        schluss = bool(re.search(r"(?im)^\s*(SCHLUSS|ХВАТИТ|ФОРМУЛИРУЙ ЗАКЛЮЧЕНИЕ|ZUSAMMENFASSEN)\b", ein_roh))      # второй «стоп»: конец правок, пора формулировать заключение
        sheet["einleitung"] = {"status": "Angaben des Bearbeiters, durch die Unterlagen nicht belegt" + ("; Rückfragen sind beendet: mit dem vorhandenen Stand arbeiten, keine weiteren Fragen stellen" if genug else "")
                               + ("; Überarbeitung ist beendet: jetzt die Schlussfassung mit allen Varianten und den offenen Fragen formulieren" if schluss else ""),
                               "text": ein_anon}
    # ложные «имена» (обычные слова) -- вернуть; части настоящих имён -- сквозной заменой
    blob = json.dumps(sheet, ensure_ascii=False)
    noun = re.compile(r"(zuschlag|aufwendungen|ungen|ung|steuer|betrag|beitrag|gruppe|kosten|konto|nummer|stelle|urkunde|schrift)$")
    junk = {ph: v for ph, v in mapping.items() if ph.startswith(("[Person", "[Firma", "[Ort")) and (
        (" " not in v.strip() and "-" not in v and (len(v.strip()) < 4 or re.search(rf"\b{re.escape(v.strip())}[a-zäöüß]{{2,}}", blob)))
        or (ph.startswith("[Person") and v.split() and noun.search(v.split()[-1])))}
    learned = {x["text"].lower() for x in anonymizer.load_learned()} | NACHLESE_WERTE       # отмеченное человеком и найденное по месту в тексте назад не возвращается
    junk = {ph: v for ph, v in junk.items() if v.strip().lower() not in learned}
    # обычное слово по самому делу (имитация дела А 12.10.2026: «Schreiben», «Einkünfte», «Daten» закрыты как лицо или место; «A. Sozialhilfe», «B. Lohn» -- пункты
    # перечня, принятые за инициал с фамилией): слово есть в словаре базы права И в тексте дела стоит сразу после артикля или притяжательного слова.
    # Фамилия так почти не стоит. Отмеченное человеком (--merke) этим не отменяется.
    _art = r"(?:der|die|das|dem|den|des|eine?|eine[mnrs]|Ihr(?:e[mnrs]?)?|unser(?:e[mnrs]?)?|mein(?:e[mnrs]?)?|kein(?:e[mnrs]?)?|diese[mnrs]?|jede[mnrs]?|Der|Die|Das|Ihr(?:e[mnrs]?)?|Unser(?:e[mnrs]?)?)"
    _gf = {}

    def gemein_im_fall(w):
        w = w.strip(".,;:()")
        if w not in _gf:
            _gf[w] = len(w) >= 4 and w.lower() in wortliste() and bool(re.search(rf"\b{_art}\s+{re.escape(w)}\b", blob))
        return _gf[w]
    human = {x["text"].lower() for x in anonymizer.load_learned()}
    for ph, v in mapping.items():
        if ph.startswith(("[Person", "[Ort")) and ph not in junk and v.strip().lower() not in human:
            ws = [w for w in v.split() if not re.fullmatch(r"[A-Za-zÄÖÜ]\.?", w)]             # инициал («A.») не считается
            if ws and len(ws) <= 2 and all(gemein_im_fall(w) for w in ws):
                junk[ph] = v
    for ph, v in mapping.items():                                        # целое значение -- обычное слово или роль: не имя
        if ph.startswith(("[Person", "[Firma", "[Ort")) and ph not in junk and v.strip().lower() not in learned and " " not in v.strip() and (anonymizer.KEEP.match(v.strip()) or _ANREDEWORT.match(v.strip())):
            junk[ph] = v
    for ph, v in junk.items():
        blob = blob.replace(json.dumps(ph, ensure_ascii=False)[1:-1], json.dumps(v, ensure_ascii=False)[1:-1])
        del mapping[ph]
    for ph, v in list(mapping.items()):
        if "\n" in v:
            mapping[ph] = v = v.split("\n")[0].strip()
        if ph.startswith("[Person") and "." not in v and 2 <= len(v.split()) <= 3 and not any(_gewoehnlich(w) for w in v.split()):     # «Lidl sagt Danke» -- не имя, «Lidl» не закрывать
            for part in v.split():
                part = part.strip(".,;:")
                if len(part) > 3 and part[0].isupper() and part not in mapping.values() and not anonymizer.KEEP.match(part) and not _ANREDEWORT.match(part) and not re.search(rf"\b{re.escape(part)}[a-zäöüß]{{2,}}", blob) \
                        and not gemein_im_fall(part):      # «Schreiben Mustermann» -> слово «Schreiben» по всему делу не закрывается
                    mapping[f"[Person {len(mapping) + 1}]"] = part
    for ph, v in sorted(mapping.items(), key=lambda x: -len(x[1])):
        if len(v) > 3:
            # в JSON начало строки текста выглядит как «\n» + значение: буква n перед значением -- не часть слова (имитация дела А 08.10.2026: BIC в начале строки)
            blob = re.sub(rf"(?:(?<![\w\[])|(?<=\\n)|(?<=\\t)){re.escape(json.dumps(v.strip(), ensure_ascii=False)[1:-1])}(?![\w\]])", lambda m, ph=ph: ph, blob)
    for ph, v in sorted(mapping.items(), key=lambda x: -len(x[1])):      # номера -- и вплотную к буквам или цифрам («KVNR» + номер без пробела)
        w = v.strip()
        if not ph.startswith(("[Zahl", "[Betrag", "[Datum")) and " " not in w and len(w) >= 7 and sum(c.isdigit() for c in w) >= 6:
            blob = blob.replace(json.dumps(w, ensure_ascii=False)[1:-1], ph)
    neu = json.loads(blob)
    for d_alt, d_neu in zip(sheet["documents"], neu["documents"]):       # служебные поля листа заменам не подлежат (08.10.2026: слово-роль
        for feld in ("nr", "kind", "issuer_role", "date", "years", "pages", "ocr_quality"):     # «Steuerberater» стало меткой лица и сломало схему)
            if feld in d_alt:
                d_neu[feld] = d_alt[feld]
    neu["question"] = sheet["question"]
    for d_neu in neu["documents"]:                       # проход по готовому тексту: метки сквозной замены стоят только теперь (11.10.2026)
        if d_neu.get("text") and d_neu["text"] != "(siehe Tabelle)":
            d_neu["text"], mapping = kennungen_rest(d_neu["text"], mapping)       # число от семи цифр, открытое сквозной заменой или возвратом «обычного слова»
            d_neu["text"], mapping = nachlese(d_neu["text"], mapping)
            if re.search(r"\.(pdf|jpe?g|png)\.txt$", quellen.get(str(d_neu.get("nr")), "").lower()):      # только распознанные сканы и фото
                d_neu["text"], n_iso = isolieren(d_neu["text"])
                ISOLIERT[quellen.get(str(d_neu.get("nr")), "")] = n_iso
    # обрывок имени рядом с меткой лица (распознавание потеряло первую букву, остаток слова не вошёл в замену): имитация дела А 08.10.2026
    P_M = r"\[(?:Mandant|Mandantin|Person|Ehegatte|Steuerberater|Gesprächspartner)[^\]]*\]"

    def _rest(s):
        if not isinstance(s, str):
            return s
        s = re.sub(rf"({P_M})[a-zäöüßа-яё]{{1,8}}\b", r"\1", s)                                   # «[Mandantin 1]lga»
        # улица, названная тем же словом, что и организация из состава («[Finanzamt 10]. 2», «[Krankenkasse 3]str. 14»): это адрес, а не организация
        s = _ORG_STR.sub("[Adresse], [Hausnr.]", s)
        # адрес бланка через запятые: «[Ort], район, улица, 14» -- район и улица не всегда узнаются как места (улица названа по району,
        # слово «Straße» отдельно): всё между меткой места и номером дома уходит под одну маску адреса (стенд 09.10.2026, справка полиции)
        s = re.sub(r"(\[(?:Ort|Adresse|PLZ)[^\]]*\])(?:, ?(?:\[[^\]]{2,30}\]|[A-ZÄÖÜ][A-Za-zÄÖÜäöüß. -]{2,40})){1,3}, ?(?:\[Hausnr\.\]|\d{1,4} ?[a-z]?(?=[ \t]*(?:,|\n|$)))", r"\1, [Adresse], [Hausnr.]", s, flags=re.M)
        return re.sub(rf"((?:Name, ?Vorname|Vorname, ?Name|Vorname|Nachname|Versicherter?|Mitglied|Kontoinhaber(?:in)?): ?{P_M})(?: [A-Za-zÄÖÜäöüß-]{{1,14}}){{1,3}}(?= [A-ZÄÖÜ][\w.-]*:| *$| *\n)",
                      r"\1", s, flags=re.M)                                                    # «Name,Vorname: [Mandantin 1] lga KVNR:»
    for d in neu["documents"]:
        d["text"] = _rest(d["text"])
        for t in d.get("tables", []):
            t["rows"] = [[_rest(c) for c in r] for r in t["rows"]]
    ef = Path(docs_dir).parent / "figuranten_entscheidungen.json"
    akt, hin, fragen = build_akteure(neu, registry, json.load(open(ef, encoding="utf-8")) if ef.exists() else {}, mapping)
    if akt:
        # решение автора к шагу 6 (09.10.2026): в листе прямо сказано, что маска читается как имя -- для разбора всё равно, кто за ней
        neu["akteure"], neu["akteure_hinweis"] = akt, ("Jede Maske steht durchgehend für denselben Beteiligten und ist wie ein Name zu lesen; "
                                                        "für die rechtliche Prüfung ist der wirkliche Name ohne Bedeutung. " + hin)
    (Path(docs_dir).parent / "AKTEURE_FRAGEN.md").write_text(          # с подлинными именами: только для обработчика, в передачу не входит
        "# Вопросы по перечню действующих лиц (только для обработчика; содержит подлинные имена)\n\n"
        "Ответы -- в figuranten_entscheidungen.json: «zusammen» (одно лицо), «gehoert_zu» (лицо -> организация), «rolle», «weg» (не лицо).\n\n"
        + ("\n".join(fragen) or "вопросов нет") + "\n", encoding="utf-8")
    kor = korrekturen(docs_dir)
    ROLLE_VON = (("finanzamt", "Finanzamt"), ("kasse", "Krankenkasse"), ("kanzlei", "Steuerberater"), ("bank", "Bank"), ("behörde", "Behörde"))
    for d in neu["documents"]:                           # исправления обработчика к виду, дате и отправителю документа -- до таблицы «кто кому пишет»
        k = kor.get(str(d["nr"]), {})
        if k.get("art"):
            d["kind"] = k["art"]
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", k.get("datum", "")):
            d["date"] = k["datum"]
        elif k.get("datum", "").strip() in ("–", "-", "—", "nein", "нет"):
            d["date"] = None
        if k.get("von"):
            d["issuer_role"] = next((r for w, r in ROLLE_VON if w in k["von"].lower()), d["issuer_role"])
    if neu.get("akteure"):
        vk, _ = verkehr(neu)
        for v in vk:
            k = kor.get(v["dok"], {})
            if k:
                v["von"], v["an"] = k.get("von", v["von"]), k.get("an", v["an"])       # «an=[A], [B]» -- два адресата
                if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", k.get("datum", "")):
                    v["datum"] = k["datum"]
                elif k.get("datum", "").strip() in ("–", "-", "—", "nein", "нет"):
                    v["datum"] = None
                if v["an"]:
                    v["betrifft"] = [m for m in v.get("betrifft", []) if m not in v["an"]]
                v["grundlage"] = "Angabe des Bearbeiters"
        gh, gf = gegenprobe(neu, getattr(build_akteure, "kandidaten", []), vk)
        if gh:
            neu["akteure_hinweis"] += gh
            with open(Path(docs_dir).parent / "AKTEURE_FRAGEN.md", "a", encoding="utf-8") as fh:
                fh.write("\n".join(gf) + "\n")
        if vk:
            neu["verkehr"] = vk
            bz = beziehungen(neu, vk)                    # связи -- уже по исправленной таблице
            if bz:
                neu["beziehungen"] = bz
    # третья ступень контроля прямо в сборке (решение автора 11.10.2026: сомнительные остатки наружу не выпускать): строка или ячейка, где
    # стоит подтверждённое имя дела дословно или с искажением, удерживается. Число мест по документам -- в annahme_namensrest.json (без значений).
    try:
        import sekretaer
        nrest = sekretaer.reste_isolieren(neu, Path(docs_dir).parent)
    except Exception as e:                               # noqa: BLE001
        nrest = {"fehler": type(e).__name__}
    json.dump(nrest, open(Path(docs_dir).parent / "annahme_namensrest.json", "w", encoding="utf-8"))
    import annahme                                       # приёмка (решение автора 08.10.2026): непринятый документ остаётся в листе, но с пометкой
    DE = {"принят": "angenommen", "принят с оговоркой": "mit Vorbehalt", "не принят": "nicht angenommen"}
    for d in neu["documents"]:
        u, _, _ = annahme.urteil(d, annahme.seiten_info(docs_dir, quellen.get(str(d["nr"]))))
        d["annahme"] = DE[u]
        if u == "не принят":
            d["annahme_grund"] = "Texterkennung unzuverlässig: Zahlen, Daten und Namen aus diesem Dokument nicht ohne Abgleich mit dem Original verwenden; Ersatz (neuer Scan) ist angefordert"
        elif u == "принят с оговоркой":
            d["annahme_grund"] = "einzelne Stellen sind vom Bearbeiter mit dem Original abzugleichen (z. B. Tabellenzeilen mit Saldo-Probe »nein«, fehlendes Datum oder unbekannter Aussteller)"
    json.dump(quellen, open(Path(docs_dir).parent / "annahme_quellen.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({nr: MUELL.get(name, (0, 0)) for nr, name in quellen.items()}, open(Path(docs_dir).parent / "annahme_muell.json", "w", encoding="utf-8"))
    for d in neu["documents"]:                           # метки организаций получают роль в названии только к концу сборки -- правило улицы ещё раз
        if isinstance(d.get("text"), str):
            d["text"] = _ORG_STR.sub("[Adresse], [Hausnr.]", d["text"])
    seiten_entscheid(docs_dir, ZWEIFEL)                  # недостающие строки для знака аудитора
    json.dump({nr: {str(s): ENTSCHEID.get(name, {}).get(s, "x") for s in ZWEIFEL[name]} for nr, name in quellen.items() if name in ZWEIFEL},
              open(Path(docs_dir).parent / "annahme_seiten.json", "w", encoding="utf-8"))
    return neu, mapping


from collections import Counter as collections_Counter

_ORG = re.compile(r"(?i)\b(gmbh|ug\b|ag\b|kg\b|ohg|gbr|e\.?k\.?|mbb|partg|partnerschaft|kanzlei|steuerberatung|steuerberatungsgesellschaft|sozietät|& ?co|& ?partner|"
                  r"partner\b|gesellschaft|verwaltung|consulting|treuhand|datev|hausverwaltung|praxis|salon|studio|verein|e\.?v\.?)")
_AMT = re.compile(r"(?i)\b(finanzamt|krankenkasse|ikk|aok|barmer|dak|tk\b|techniker|knappschaft|bkk|rentenversicherung|agentur für arbeit|jobcenter|amt\b|behörde|"
                  r"gericht|stadt\b|gemeinde|kreis\b|ministerium|zoll|bundesamt|landesamt|kammer|berufsgenossenschaft|sparkasse|bank\b|volksbank)")


_KANZLEI = re.compile(r"(?i)steuerberat|kanzlei|treuhand|wirtschaftsprüf|buchführ|buchhaltung|lohnsteuerhilfe|\bstb\b|rechtsanw")


def frei_text_anon(text, registry, mapping):
    """Свободный текст обработчика (роль в файле состава, пояснение) -> обезличенный теми же правилами, что вводная: состав и реестр,
    уже известные значения дела без учёта регистра, имена и места по словарю форм. Замечание стенда 09.10.2026: в дословной роли стояло имя клиентки."""
    t = apply_registry(text, registry)
    for ph, v in sorted((mapping or {}).items(), key=lambda x: -len(str(x[1]))):
        w = str(v).strip()
        if len(w) >= 4 and not ph.startswith(("[Zahl", "[Betrag", "[Datum", "rund")):
            t = re.sub(rf"(?<![\w\[]){re.escape(w)}(?![\w\]])", ph, t, flags=re.I)
    for r in registry:                                   # написания состава -- и с иным регистром букв («Мустер»)
        for v in r.get("varianten", []):
            if len(v) >= 4 and not v.startswith("Gesprächspartner"):
                t = re.sub(rf"(?<![\w\[]){re.escape(v)}(?![\w\]])", r["label"], t, flags=re.I)
            if re.fullmatch(r"[А-Яа-яЁё]{5,}", v):       # русское имя в падеже и с любым регистром букв («ЭРики»)
                st = v[:-1] if v[-1].lower() in "аяыиеуюйь" else v
                t = re.sub(rf"(?<![\w\[]){re.escape(st)}[а-яё]{{0,3}}(?![\w\]])", r["label"], t, flags=re.I)
    for n_, art_ in sorted(einleitung_namen(t), key=lambda x: -len(x[0])):
        t = re.sub(rf"(?<![\w\[]){re.escape(n_)}(?![\w\]])", f"[{art_}]", t)
    return t


def build_akteure(sheet, registry, entscheidungen=None, mapping=None):
    """Перечень действующих лиц дела как часть листа (решение автора 09.10.2026): маска, вид (лицо / организация / ведомство),
    роль, к какой организации относится, в каких документах и когда встречается. Имён в перечне нет -- только маски листа.
    Связь «лицо -- организация» выводится из близости масок в тексте и помечается «vermutet», пока обработчик не подтвердит
    (figuranten_entscheidungen.json: {"gehoert_zu": {"<имя лица>": "<имя организации>"}}).
    -> (список для листа, пояснение, [вопросы обработчику с подлинными именами -- только локально])"""
    from rapidfuzz import fuzz
    ent = entscheidungen or {}
    texte = {}
    for d in sheet["documents"]:
        t = d["text"] + "\n" + "\n".join(" | ".join(str(c) for c in r) for tb in d.get("tables", []) for r in tb["rows"])
        texte[d["nr"]] = (t, d.get("date"))
    dat = lambda x: tuple(reversed(x.split("."))) if x else ("",)                     # noqa: E731
    roh = []
    firmen = []                                          # фирмы, найденные в документах без роли: в перечень идут как организации
    for ph, v in (mapping or {}).items():
        if ph.startswith("[Firma") and not any(ph == r["label"] for r in registry):
            rolle = "Steuerberater/Kanzlei" if _KANZLEI.search(v) else "Krankenkasse" if re.search(r"(?i)krankenkasse|\bikk\b|\baok\b|\bbkk\b|barmer|\bdak\b", v) else \
                "Bank" if re.search(r"(?i)sparkasse|\bbank\b|volksbank", v) else "Finanzamt" if re.search(r"(?i)finanzamt", v) else "Firma ohne erkannte Rolle"
            firmen.append({"label": ph, "rolle": rolle, "name": v, "varianten": [v], "sicher": False, "bestaetigt": False, "_firma": True})
    vorgabe = any(r.get("_vorgabe") for r in registry)
    for r in ([x for x in registry if x.get("_vorgabe")] if vorgabe else list(registry) + firmen):
        lab = r["label"]
        doks = {nr: t.count(lab) + sum(len(re.findall(rf"(?<!\w){re.escape(o)}(?!\w)", t, flags=re.I)) for o in r.get("offen", []))
                for nr, (t, _) in texte.items() if lab in t or any(re.search(rf"(?<!\w){re.escape(o)}(?!\w)", t, flags=re.I) for o in r.get("offen", []))}
        if not doks and not r.get("_vorgabe"):
            continue                                     # отмеченное аудитором лицо или организация остаётся в перечне и без упоминаний (прогон 09.10.2026)
        name = r.get("name", "")
        if r.get("_vorgabe"):                           # вид заданного лица -- по маске, которую написал обработчик
            m_ = r["label"]
            art_v = "Person" if ":" in m_ else "Behörde oder Kasse" if re.search(r"(?i)finanzamt|kasse|behörde|\bamt\b|bank|gericht|ikk|aok", m_) else \
                "Organisation" if re.search(r"(?i)kanzlei|firma|gmbh|gesellschaft|büro|buero|betrieb|salon|verein", m_) else "Person"
        art = art_v if r.get("_vorgabe") else "Behörde oder Kasse" if (_AMT.search(name) or r["rolle"] in ("Finanzamt", "Krankenkasse", "Behörde", "Bank")) else \
            "Organisation" if (r.get("_firma") or _ORG.search(name) or _KANZLEI.search(name) and len(name.split()) >= 3) else "Person"
        daten = []                                       # даты документов пока определяются ненадёжно (8 верных из 19 на имитации дела): в перечень не выводятся
        roh.append({"r": r, "maske": lab, "art": art, "rolle": r["rolle"], "dokumente": sorted(doks), "nennungen": sum(doks.values()),
                    "erstes_datum": daten[0] if daten else None, "letztes_datum": daten[-1] if daten else None})
    # связь лицо -- организация: сколько раз маски стоят рядом (в пределах 300 знаков) в одном документе
    orgs = [a for a in roh if a["art"] == "Organisation"]          # консультант или сотрудник относится к организации, не к ведомству
    fragen = []
    for a in roh:
        a["gehoert_zu"], a["gehoert_zu_status"] = None, None
        if a["r"].get("_vorgabe"):
            if a["r"].get("gehoert_zu"):
                a["gehoert_zu"], a["gehoert_zu_status"] = a["r"]["gehoert_zu"], "bestätigt"
            continue
        if a["art"] != "Person" or a["rolle"].startswith(("Mandant", "Ehegatte", "Bearbeiter")):
            continue
        fest = next((o for n, on in ent.get("gehoert_zu", {}).items() if n in a["r"].get("varianten", []) + [a["r"].get("name")]
                     for o in orgs if on in o["r"].get("varianten", []) + [o["r"].get("name")]), None)
        if fest:
            a["gehoert_zu"], a["gehoert_zu_status"] = fest["maske"], "bestätigt"
            continue
        nah = collections_Counter()
        for nr in a["dokumente"]:
            t = texte[nr][0]
            for m in re.finditer(re.escape(a["maske"]), t):
                fenster = t[max(0, m.start() - 300): m.end() + 300]
                for o in orgs:
                    if o["maske"] in fenster and (o["rolle"] == a["rolle"] or a["rolle"] == "Mitarbeiter" or o["rolle"] == "Firma ohne erkannte Rolle"):
                        nah[o["maske"]] += 1 + (o["rolle"] == a["rolle"])
        if nah and nah.most_common(1)[0][1] >= 2:
            a["gehoert_zu"], a["gehoert_zu_status"] = nah.most_common(1)[0][0], "vermutet"
            o = next(x for x in orgs if x["maske"] == a["gehoert_zu"])
            fragen.append(f"- {a['maske']} = «{a['r'].get('name')}» относится к {o['maske']} = «{o['r'].get('name')}»? (стоят рядом {nah.most_common(1)[0][1]} раз)")
    # группы: консультанты и сотрудники, названные рядом (шапка письма, подпись) -- вероятно, одна канцелярия
    ber = [a for a in roh if a["art"] == "Person" and a["rolle"] in ("Steuerberater/Kanzlei", "Mitarbeiter") and not a["r"].get("_vorgabe")]
    eltern = {a["maske"]: a["maske"] for a in ber}

    def wurzel(x):
        while eltern[x] != x:
            x = eltern[x]
        return x
    for i, a in enumerate(ber):
        for b in ber[i + 1:]:
            nahe = 0
            for nr in set(a["dokumente"]) & set(b["dokumente"]):
                t = texte[nr][0]
                pos_b = [m.start() for m in re.finditer(re.escape(b["maske"]), t)]
                nahe += sum(1 for m in re.finditer(re.escape(a["maske"]), t) if any(abs(m.start() - pb) <= 400 for pb in pos_b))
            if nahe >= 1:
                eltern[wurzel(a["maske"])] = wurzel(b["maske"])
    gruppen = {}
    for a in ber:
        gruppen.setdefault(wurzel(a["maske"]), []).append(a)
    k = 0
    for g in sorted(gruppen.values(), key=lambda g: -len(g)):
        if len(g) >= 2:
            k += 1
            for a in g:
                a["gruppe"] = f"Kanzlei-Gruppe {chr(64 + k)} (vermutet: gemeinsam genannt)"
            fragen.append(f"- Kanzlei-Gruppe {chr(64 + k)}: " + "; ".join(f"{a['maske']} = «{a['r'].get('name')}»" for a in g) + " -- одна канцелярия? как она называется и с какого по какой месяц вела дело?")
    # возможные двойники: та же роль и похожее имя
    for a in roh:
        a["evtl_identisch_mit"] = []
    for i, a in enumerate(roh):
        for b in roh[i + 1:]:
            if not vorgabe and a["rolle"] == b["rolle"] and a["art"] == b["art"] and fuzz.token_set_ratio(a["r"].get("name", ""), b["r"].get("name", "")) >= 75:
                a["evtl_identisch_mit"].append(b["maske"])
                b["evtl_identisch_mit"].append(a["maske"])
                fragen.append(f"- {a['maske']} = «{a['r'].get('name')}» и {b['maske']} = «{b['r'].get('name')}» -- одно и то же? (роль {a['rolle']})")
    for a in roh:                                        # роль у заданного состава -- свободный текст обработчика: в лист только обезличенной
        if a["r"].get("_vorgabe"):
            a["rolle"] = frei_text_anon(a["rolle"], [x for x in registry if x is not a["r"]] + [a["r"]], mapping)
            vs_ = [v for v in a["r"].get("varianten", []) if not v.startswith("Gesprächspartner")]
            if a["art"] != "Person" and vs_ and all(re.fullmatch(r"[A-ZÄÖÜА-ЯЁ][\w.-]+ [A-ZÄÖÜА-ЯЁ][\w-]+", v) for v in vs_[:2]):
                fragen.append(f"- {a['maske']}: маска организации, а написание похоже на имя человека («{vs_[0]}») -- это сам консультант или организация, где он работает? "
                              "Если человек, запишите его «" + a["maske"].strip("[]") + ": …», а организацию -- отдельной строкой.")
    out = [{"maske": a["maske"], "art": a["art"], "rolle": a["rolle"], "gruppe": a.get("gruppe"), "gehoert_zu": a["gehoert_zu"], "gehoert_zu_status": a["gehoert_zu_status"], "dokumente": a["dokumente"],
            "nennungen": a["nennungen"], "erstes_datum": a["erstes_datum"], "letztes_datum": a["letztes_datum"], "evtl_identisch_mit": sorted(set(a["evtl_identisch_mit"])),
            "name_offen": a["r"].get("offen", []),
            "status": "bestätigt" if a["r"].get("bestaetigt") and a["r"].get("sicher") else "aus Unterlagen erschlossen"} for a in roh]
    out = [a for a in out if not (a["rolle"] == "Firma ohne erkannte Rolle" and a["nennungen"] < 2)]       # разовые «фирмы» без роли -- чаще ошибка распознавания
    ordn = {"Mandantin/Mandant": 0, "Ehegatte": 1, "Steuerberater/Kanzlei": 2, "Mitarbeiter": 3, "Finanzamt": 4, "Krankenkasse": 5, "Behörde": 6, "Bank": 7}
    if not vorgabe:
        out.sort(key=lambda a: (ordn.get(a["rolle"], 9), a["art"] == "Person", -a["nennungen"]))
    blob = json.dumps(sheet["documents"], ensure_ascii=False)
    rest = {k: len(set(re.findall(rf"\[{k} \d+\]", blob)) - {a["maske"] for a in out}) for k in ("Person", "Firma")}
    if vorgabe:
        sonst = len({m for m in re.findall(r"\[[A-ZÄÖÜa-zäöü][^\]\n]{1,30} \d+\]", blob) if re.match(r"\[(Mandant|Steuerberater|Mitarbeiter|Ehegatte|Vermieter|unbekannt|Finanzamt|Krankenkasse|Behörde|Person|Firma)", m)} - {a["maske"] for a in out})
        hinweis = (f"Das Verzeichnis ist vom Bearbeiter vorgegeben. Übrige Masken im Text (sonstige Personen, Firmen und Stellen ohne Rolle für die Sache): {sonst}. "
                   "Zeiträume werden nicht angegeben: die Dokumentdaten sind noch nicht zuverlässig bestimmt.")
        build_akteure.kandidaten = [r for r in [x for x in registry if not x.get("_vorgabe")] + firmen
                                    if r["label"] not in {a["maske"] for a in out} and not r.get("rolle", "").startswith("Bearbeiter")]
        return out, hinweis, fragen
    hinweis = (f"Masken ohne Rolle im Text (nicht im Verzeichnis): {rest['Person']} Personen, {rest['Firma']} Firmen. "
               "Zuordnung »gehört zu« mit Status »vermutet« ist aus der Nähe der Masken im Text erschlossen und vom Bearbeiter nicht bestätigt. "
               "Die Daten sind Daten der Dokumente, in denen die Maske vorkommt, nicht Daten von Handlungen.")
    return out, hinweis, fragen


_SIGN = re.compile(r"(?i)mit freundlichen gr[uü](?:ß|ss)en|freundliche gr[uü](?:ß|ss)e|im auftrag|hochachtungsvoll|\bgez\.")
_ANREDE = re.compile(r"(?i)sehr geehrte[r]?\s+(?:frau|herr|damen und herren|\[)|guten (?:tag|morgen|abend)[ ,]|hallo (?:frau|herr)")
_MASKE = re.compile(r"\[[^\]\n]{2,40}\]")
# слово обращения или титул (имитация дела А 12.10.2026: «Frau» из значения «Frau + фамилия» разошлось по делу как часть имени и закрылось меткой лица;
# из-за этого письма сборного файла не делились по обращению и дата письма в таблицу переписки не попадала)
_ANREDEWORT = re.compile(r"(?i)^(?:herrn?|frau|familie|eheleute|damen|herren|geehrte[rn]?|liebe[rn]?|firma|dr|prof|hr|fr)\.?$")
_DAT = re.compile(r"(?<!\d)(\d{2}\.\d{2}\.20\d{2})(?!\d)")


_MONAT = {m: i + 1 for i, m in enumerate("januar februar märz april mai juni juli august september oktober november dezember".split())}


def _dat_norm(t):
    """«24. September 2026» -> «24.09.2026», чтобы словесные даты (удостоверения, подписи) находились теми же правилами."""
    return re.sub(r"(?<!\d)(\d{1,2})\.\s*(" + "|".join(_MONAT) + r")\s+(20\d{2})", lambda m: f"{int(m.group(1)):02d}.{_MONAT[m.group(2).lower()]:02d}.{m.group(3)}", t, flags=re.I)


def datum_schreiben(t):
    """Дата письма, а не срока или периода: дата в начале письма, стоящая после «Datum», «, den», названия места или отдельно в строке;
    даты после «ab / vom / bis / seit / zum / Frist / Zeitraum» не берутся. Если уверенного кандидата нет -- None (лучше ничего, чем неверно)."""
    kopf = t[:1600]
    # дата с названием месяца («17. Februar 2025») читается так же, как цифровая (имитация дела А 12.10.2026: ключевое письмо не попало в таблицу переписки)
    _MON = {m: i + 1 for i, m in enumerate("Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split())}
    kopf = re.sub(r"\b(\d{1,2})\.\s?(" + "|".join(_MON) + r")\s+((?:19|20)\d{2})\b", lambda m: f"{int(m.group(1)):02d}.{_MON[m.group(2)]:02d}.{m.group(3)}", kopf)
    best, sc_best = None, 0
    for m in _DAT.finditer(kopf):
        davor = kopf[max(0, m.start() - 30): m.start()]
        zeile = kopf[kopf.rfind("\n", 0, m.start()) + 1: (kopf.find("\n", m.end()) if kopf.find("\n", m.end()) > 0 else len(kopf))]
        sc = 0
        if re.search(r"(?i)(datum|, den|vom)\s*:?\s*$", davor) and not re.search(r"(?i)(bescheid|schreiben|antrag|bericht)\s+vom\s*$", davor):
            sc += 3
        if re.search(r"[A-ZÄÖÜ][a-zäöüß.-]+,\s*(den\s*)?$", davor):
            sc += 3
        if len(zeile.strip()) <= 28:
            sc += 2
        if re.search(r"(?i)\b(ab|bis|seit|zum|bis zum|spätestens|frist|zeitraum|für die zeit|beginn|ende|geb\.|geboren|gültig|fällig)\s*(dem|den|am)?\s*:?\s*$", davor):
            sc -= 4
        if re.search(r"(?i)(bescheid|schreiben|antrag|bericht|rechnung)\s+vom\s*$", davor):
            sc -= 2
        if sc > sc_best:
            best, sc_best = m.group(1), sc
    return (best, sc_best) if sc_best >= 2 else (None, 0)


# «стоп» свободными словами в последнем круге ответов (решение автора к шагу 11 схемы, 09.10.2026): аудитор не обязан помнить слово GENUG
STOPP_FREI = re.compile(r"(?i)(больше|более)\s+(у меня\s+)?(нет|нету)\s+(никакой\s+)?информации|больше\s+(мне\s+)?нечего\s+(добавить|сказать|сообщить)|"
                        r"не знаю,?\s+что\s+(тебе\s+|вам\s+)?ещ[её]\s+(сказать|добавить)|это\s+вс[её],?\s+что\s+(я\s+)?(знаю|есть)|вопросов\s+достаточно|"
                        r"keine\s+weiteren\s+(angaben|informationen|unterlagen)|mehr\s+(weiß|weiss)\s+ich\s+nicht|mehr\s+habe\s+ich\s+nicht")


def gegenprobe(sheet, kandidaten, vk):
    """Встречная проверка выбора аудитора (решение автора к шагу 5 схемы, 09.10.2026): названные «главные» -- пожелание, а не фильтр;
    люди ошибаются и смотрят на второстепенное, программа сама смотрит суть. Суть -- не частота, а роль в переписке (имитация дела А на
    деле): в проверку идёт каждая не названная маска, которая подписала документ или стоит в его шапке, и частые маски; маски вида
    «unbekannt» не идут (обычное слово, принятое за имя). Названная организация считается найденной и по отправителю или адресату
    документа, и по своим сотрудникам. -> (пояснение для листа -- только маски, [вопросы аудитору с подлинными именами])"""
    akt = {a["maske"]: a for a in sheet.get("akteure", [])}
    mand = next((m for m, a in akt.items() if re.search(r"(?i)mandant|inhaber|klient", m + " " + a["rolle"]) and a["art"] == "Person"), None)
    texte = {d["nr"]: d["text"] for d in sheet["documents"] if not d["kind"].startswith("Gesprächsprotokoll")}
    _REKV = re.compile(r"(?i)\bIBAN\b|\bBIC\b|\bBLZ\b|bankverbindung|sparkasse|volksbank|\bkonto\b|\bust-?id|steuer-?nr|handelsregister|\bHRB\b|amtsgericht")
    _POST = re.compile(r"(?i)\b\d{5}\b|\[(Adresse|Ort|Hausnr|PLZ)[^\]]*\]|postfach|\btel(efon)?\b|\bfax\b|stra(ß|ss)e\b|str\.")
    _ORTDAT = re.compile(r"(?i),\s*(den\s+)?(\d{1,2}\.\s*(\d{1,2}\.|januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s*\d{2,4}|\[Datum[^\]]*\])\s*$")

    def unterzeichner(t):
        """Маски, стоящие подписью: в четырёх строках после формулы подписи (до следующего обращения -- границы письма; строки
        реквизитов бланка не считаются) либо отдельной строкой сразу после строки «место, den дата»."""
        out = set()
        zl = t.split("\n")
        for k, ln in enumerate(zl):
            nach_formel = bool(_SIGN.search(ln))
            if nach_formel or _ORTDAT.search(ln.strip()):
                n = 0
                for ln2 in zl[k + 1:]:
                    if not ln2.strip():
                        continue
                    n += 1
                    if n > (4 if nach_formel else 1) or _ANREDE.search(ln2):
                        break
                    if _REKV.search(ln2):
                        continue
                    if nach_formel or re.fullmatch(r"\s*\[[^\]\n]{2,40}\]\s*", ln2):      # после «место, дата» -- только маска одной строкой
                        out |= set(_MASKE.findall(ln2))
        return out

    def im_kopf(t, lab):                                 # фирма в шапке: не в почтовой строке и не в строке реквизитов
        return any(lab in ln and not _POST.search(ln.replace(lab, "")) and not _REKV.search(ln) for ln in t[:500].split("\n"))
    sign = {nr: unterzeichner(t) for nr, t in texte.items()}
    from rapidfuzz import fuzz as _fz
    tm = getattr(verkehr, "teil_masken", {})
    teil_von = {}                                        # документ -> [(маски части, отправитель части)] по таблице «кто кому пишет»
    for v in vk:
        nr_ = re.match(r"\d+", str(v.get("dok", "")))
        if nr_:
            teil_von.setdefault(int(nr_.group(0)), []).append((tm.get(str(v["dok"])), v.get("von") if v.get("von") in akt else None))

    def absender_von(nr, lab):
        """Отправитель той части документа, где стоит маска (имитация дела А: в сборном документе письма разных канцелярий). Если маска
        стоит в части без определённого отправителя или в частях с разными отправителями -- привязки нет: лучше «не определено»."""
        teile_ = teil_von.get(nr, [])
        mit = [von for masken, von in teile_ if masken is None or lab in masken]
        return mit[0] if mit and all(v == mit[0] for v in mit) and mit[0] else None

    _FORM = {"gmbh", "mbh", "ug", "kg", "ohg", "gbr", "co", "inh", "inhaber", "und", "der", "die", "das", "für", "von"}

    def gleiche_firma(a, b):                             # значимые слова короткого названия все есть в длинном (порядок и лишнее слово не важны)
        wa, wb = ([w for w in re.findall(r"[a-zäöüß]{3,}", str(x).lower()) if w not in _FORM] for x in (a, b))
        kurz, lang = sorted((wa, wb), key=len)
        return len(kurz) >= 2 and all(any(_fz.ratio(w, v) >= 85 or (min(len(w), len(v)) >= 5 and (w.startswith(v) or v.startswith(w))) for v in lang) for w in kurz)
    funde, gleich = [], {}
    for r in kandidaten:
        lab = r["label"]
        if re.match(r"(?i)\[unbekannt", lab):
            continue
        dk = [nr for nr, t in texte.items() if lab in t]
        if not dk:
            continue
        nn = sum(texte[nr].count(lab) for nr in dk)
        unterz = [nr for nr in dk if lab in sign[nr]]
        kopf = [nr for nr in dk if r.get("_firma") and im_kopf(texte[nr], lab)]
        if not (unterz or len(dk) >= 3 or nn >= 10 or kopf):
            continue
        # одна и та же фирма под двумя масками (полное и краткое название) -- одна строка
        doppelt = next((f for f in funde if r.get("_firma") and f[9] and r.get("name") and f[4]
                        and gleiche_firma(r["name"], f[4])), None)
        if doppelt:
            gleich.setdefault(doppelt[3], []).append(lab)
            continue
        wie = "unterzeichnet " + ", ".join(f"Nr. {n}" for n in unterz[:4]) if unterz else f"im Kopf von Nr. {kopf[0]}" if kopf else "häufig"
        rolle = r.get("rolle", "?")
        vorschlag_de = vorschlag_ru = ""
        org = next((o for o in (absender_von(nr, lab) for nr in unterz) if o and akt[o]["art"] != "Person"), None)     # подписал документ названной организации
        org = org or next((m for m, a in akt.items() if a["art"] != "Person" and not unterz and rolle not in ("Mitarbeiter", "Firma ohne erkannte Rolle", "?")
                           and re.search(re.escape(rolle.split("/")[0][:6]), m, flags=re.I)), None)
        if org:
            vorschlag_de, vorschlag_ru = f"; gehört vermutlich zu {org}", f" -- относится к {org}?"
        elif r.get("_firma") and not unterz and rolle == "Firma ohne erkannte Rolle" and mand and (len(dk) >= 3 or any(abs(m.start() - k.start()) <= 600 for nr in dk for m in re.finditer(re.escape(lab), texte[nr])
                                                                 for k in re.finditer(re.escape(mand), texte[nr]))):
            vorschlag_de, vorschlag_ru = "; möglicherweise Betrieb der Mandantschaft (vom Bearbeiter zu bestätigen)", " -- это предприятие клиента?"
        funde.append((bool(unterz), len(dk), nn, lab, r.get("name"), rolle, wie, vorschlag_de, vorschlag_ru, bool(r.get("_firma"))))
    # слабое совпадение названий (одно общее значимое слово от пяти букв, остальное искажено распознаванием): не склеивать, а спросить
    evtl = {}
    for x, y in ((x, y) for n_, x in enumerate(funde) for y in funde[n_ + 1:] if x[9] and y[9] and x[4] and y[4]):
        wx, wy = ({w for w in re.findall(r"[a-zäöüß]{5,}", str(z[4]).lower()) if w not in _FORM} for z in (x, y))
        if wx & wy:
            evtl.setdefault(x[3], []).append(y[3])
            evtl.setdefault(y[3], []).append(x[3])
    funde = [f[:7] + (f[7] + (f"; möglicherweise dieselbe Firma wie {', '.join(evtl[f[3]])} (vom Bearbeiter zu bestätigen)" if f[3] in evtl else ""),
                      f[8] + (f" (возможно, то же предприятие, что {', '.join(evtl[f[3]])}?)" if f[3] in evtl else "")) + f[9:] for f in funde]
    funde = [f[:7] + (f[7] + (f"; dieselbe Firma auch als {', '.join(gleich[f[3]])}" if f[3] in gleich else ""),
                      f[8] + (f" (она же {', '.join(gleich[f[3]])})" if f[3] in gleich else "")) for f in funde]
    funde.sort(key=lambda x: (-x[0], -x[1], -x[2]))
    belegt = {m for v in vk for m in [v.get("von"), v.get("unterzeichnet")] + list(v.get("betrifft") or []) if m}
    for v in vk:
        belegt |= set(_MASKE.findall(str(v.get("an") or "")))
    belegt |= {a.get("gehoert_zu") for a in akt.values() if a.get("gehoert_zu") and (a["dokumente"] or a["maske"] in belegt)}
    leer = [m for m, a in akt.items() if not a["dokumente"] and m not in belegt]
    hin, fragen = "", []
    if funde:
        hin += (" Gegenprobe des Programms (die Auswahl des Bearbeiters ist ein Hinweis, kein Filter): vom Bearbeiter nicht benannt, aber am Schriftverkehr "
                "beteiligt oder häufig genannt: " + "; ".join(f"{lab} ({rolle}; {wie}; {d} Dokumente{vd})" for _, d, n, lab, _, rolle, wie, vd, _ in funde[:12])
                + ". Diese Masken sind bei der Prüfung mitzulesen.")
        fragen.append("- Встречная проверка: вы их не назвали, но они подписывали документы, стоят в шапке или встречаются часто -- "
                      + "; ".join(f"{lab} = «{name}» ({d} док., {wie.replace('unterzeichnet', 'подпись:').replace('häufig', 'часто').replace('im Kopf von', 'в шапке')}){vr}"
                                  for _, d, n, lab, name, rolle, wie, _, vr in funde[:12])
                      + ". Кто из них важен для дела -- допишите строкой в состав; остальных можно не трогать.")
    if leer:
        hin += " Vom Bearbeiter benannt, in den gelesenen Unterlagen aber weder genannt noch als Absender oder Empfänger gefunden: " + ", ".join(leer) + "."
        fragen.append("- Встречная проверка: названы вами, но в прочитанных документах не найдены ни в тексте, ни как отправитель или адресат -- "
                      + ", ".join(leer) + ". Проверьте написание имени либо недостающие документы.")
    return hin, fragen


def teil_buchst(i):
    """Буква части сборного файла без потолка: a..z, aa, ab, ... (в скане на сотню страниц писем больше 26)."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(97 + r) + s
    return s


def verkehr(sheet):
    """Кто кому пишет (способы «от вида документа» и «граф переписки», предложены при обкатке 09.10.2026): по каждому документу и по
    каждому письму сборного файла -- отправитель, подписавший, адресат, о ком, дата письма. Только правила, без модели; работает по маскам
    заданного состава. Из этого кодом выводятся связи: кто кого представлял, кому писали напрямую. -> (записи, связи)"""
    akt = {a["maske"]: a for a in sheet.get("akteure", [])}
    verkehr.teil_masken = {}
    if not akt:
        return [], []
    org_von = lambda m: akt[m].get("gehoert_zu") or m if m in akt else m          # noqa: E731
    mand = next((m for m, a in akt.items() if re.search(r"(?i)mandant|inhaber|klient", m + " " + a["rolle"]) and a["art"] == "Person"), None)
    gatte = next((m for m, a in akt.items() if re.search(r"(?i)ehe(mann|frau|gatt|partner)", m + " " + a["rolle"])), None)
    nach_rolle = {"Krankenkasse": next((m for m in akt if re.search(r"(?i)kasse", m) and ":" not in m), None),
                  "Finanzamt": next((m for m in akt if re.search(r"(?i)finanzamt", m) and ":" not in m), None)}
    kanzleien = [m for m, a in akt.items() if a["art"] == "Organisation" or re.search(r"(?i)kanzlei", m) and ":" not in m]
    out = []
    for d in sheet["documents"]:
        if d["kind"].startswith("Gesprächsprotokoll"):
            continue
        t = d["text"] + "\n" + "\n".join(" | ".join(str(c) for c in r) for tb in d.get("tables", []) for r in tb["rows"][:3])
        anr = list(_ANREDE.finditer(t))
        if len(anr) >= 2:                                # сборный файл: письмо кончается после подписи (и двух строк под ней), следующее начинается там же
            grenzen = [0]
            for a in anr[1:]:
                sg = [m for m in _SIGN.finditer(t, grenzen[-1], a.start())]
                if sg:
                    p_ = sg[-1].end()
                    for _ in range(3):                   # подпись, имя, должность
                        q_ = t.find("\n", p_ + 1, a.start())
                        if q_ < 0:
                            break
                        p_ = q_
                    grenzen.append(min(p_, a.start()))
                else:
                    grenzen.append(max(grenzen[-1], a.start() - 200))
            grenzen.append(len(t))
            teile = [(f"{d['nr']}{teil_buchst(i)}", t[grenzen[i]: grenzen[i + 1]]) for i in range(len(anr))]
        else:
            teile = [(str(d["nr"]), t)]
        for dok, x in teile:
            verkehr.teil_masken[dok] = set(_MASKE.findall(x))        # для встречной проверки: в какой части сборного документа стоит маска
            unterz = None
            for sg in _SIGN.finditer(x):
                m = next((mm for mm in _MASKE.finditer(x[sg.end(): sg.end() + 260]) if mm.group(0) in akt), None)
                if m:
                    unterz = m.group(0)
                    break
            grund = []
            von = org_von(unterz) if unterz else None
            if von:
                grund.append("Unterschrift")
            if von is None and d["issuer_role"] in nach_rolle and nach_rolle[d["issuer_role"]]:
                von = nach_rolle[d["issuer_role"]]
                grund.append("Art des Dokuments")
            if von is None:                              # шапка: организация (или её сотрудник), чаще всего названная в начале и в конце письма
                kopf = x[:500] + " " + x[-400:]
                c = collections_Counter(org_von(m) for m in _MASKE.findall(kopf) if m in akt and org_von(m) in kanzleien + [v for v in nach_rolle.values() if v])
                if c:
                    von = c.most_common(1)[0][0]
                    grund.append("Kopf oder Fuß")
            if von is None and d["issuer_role"] == "Bank":
                von = "Bank (nicht im Verzeichnis)"
                grund.append("Art des Dokuments")
            eigen = re.search(r"(?i)gewinnermittlung|kontoblatt|summen- und saldenliste|lohnunterlagen|einkommensteuererklärung|bestätigung steuerberater|jahresabschluss|buchhaltung", d["kind"])
            if von is None and (eigen or d["issuer_role"] == "Steuerberater"):      # документ, который составляет канцелярия: её маска (или её сотрудника) где угодно в документе
                c = collections_Counter(org_von(m) for m in _MASKE.findall(x) if m in akt and org_von(m) in kanzleien)
                if c:
                    von = c.most_common(1)[0][0]
                    grund.append("Art des Dokuments: von der Kanzlei erstellt")
            if von is None and re.search(r"(?i)steuerbescheid|einkommensteuerbescheid|betriebsprüfungsbericht|bescheid über", d["kind"]) and nach_rolle["Finanzamt"]:
                von = nach_rolle["Finanzamt"]
                grund.append("Art des Dokuments")
            fremd = lambda m: m in akt and org_von(m) != von and m != von          # noqa: E731  (не сам отправитель и не его сотрудник)
            a = _ANREDE.search(x)
            an = None
            if a:
                m = _MASKE.search(x[a.end(): a.end() + 60])
                an = m.group(0) if m and fremd(m.group(0)) else None
            if an is None:
                m = next((mm for mm in re.finditer(r"(?:Herrn?|Frau|Firma|An)\s+(" + _MASKE.pattern + ")", x[:900]) if fremd(mm.group(1))), None)
                an = m.group(1) if m else None
            if an is None:                               # адресный блок: маска одна в строке в начале письма
                m = next((mm for mm in re.finditer(r"(?m)^\s*(" + _MASKE.pattern + r")\s*$", x[:900]) if fremd(mm.group(1))), None)
                if m:
                    an = m.group(1)
                    grund.append("Empfänger aus dem Anschriftsfeld")
            if an is None and von and (von in nach_rolle.values() or von.startswith("Bank")) and mand and mand in x[:1200]:
                an = mand
                grund.append("Empfänger vermutet: Mandantin im Anschriftsfeld")
            if an is None and von and mand:              # адресат по виду документа
                if re.search(r"(?i)einkommensteuererklärung", d["kind"]) and nach_rolle["Finanzamt"]:
                    an = nach_rolle["Finanzamt"]
                    grund.append("Empfänger nach Art des Dokuments")
                elif (eigen or re.search(r"(?i)bescheid", d["kind"])) and mand in x:
                    an = mand
                    grund.append("Empfänger nach Art des Dokuments")
            if an == von:
                an = None
            betr = [m for m in (mand, gatte) if m and m in (x[:-120] if len(teile) > 1 and len(x) > 400 else x) and m != an]
            x_d = _dat_norm(x)
            m = re.search(r"(?i)\b(?:Datum|Druckdatum|gedruckt am|erstellt am|Erstelldatum)\s*:?\s*(\d{2}\.\d{2}\.20\d{2})", x_d[:2500]) or \
                re.search(r"(?im)^\s*(?:Datum|Druckdatum)\s*:\s*(\d{2}\.\d{2}\.20\d{2})", x_d)                       # «Datum: …» отдельной строкой где угодно (приложение к решению)
            if not m and re.search(r"(?i)gewinnermittlung|kontoblatt|summen- und saldenliste|buchhaltung", d["kind"]):   # распечатки учёта: удостоверение «…, den 24. September 2026» или дата в первой строке
                m = re.search(r"(?i),\s*den\s+(\d{2}\.\d{2}\.20\d{2})", x_d) or re.search(r"(\d{2}\.\d{2}\.20\d{2})", "\n".join(x_d.split("\n")[:3]))
            alt = d.get("date") if len(teile) == 1 else None      # письмо внутри сборного файла дату файла не наследует
            neu_d, neu_sc = datum_schreiben(x_d)
            if m:                                        # 1) дата рядом со словом «Datum» в шапке письма или распечатки
                dat_ = m.group(1)
            elif neu_d and neu_sc >= 3:                  # 2) дата письма с явным признаком (место, «den», отдельная строка в шапке)
                dat_ = neu_d
            elif alt and not alt.startswith("01.") and (neu_d is None or neu_d == alt):      # 3) прежнее поле, если оно не начало периода и не спорит с правилом
                dat_ = alt
            else:                                        # сомнение -- прочерк: лучше спросить обработчика, чем показать срок или начало периода
                dat_ = None
            out.append({"dok": dok, "von": von, "unterzeichnet": unterz if unterz and unterz != von else None, "an": an, "betrifft": betr,
                        "datum": dat_, "grundlage": "; ".join(grund) or "nicht bestimmt"})
    # распечатки учёта без отправителя: тот же день печати, что у документа с известной канцелярией, -- та же канцелярия
    for v in out:
        d = next((x for x in sheet["documents"] if str(x["nr"]) == re.sub(r"[a-z]+$", "", v["dok"])), None)
        if d is None:                                    # часть без документа в листе -- строку не трогаем, сборку не роняем
            continue
        buch = lambda nr: re.search(r"(?i)gewinnermittlung|kontoblatt|summen- und saldenliste|buchhaltung|lohnunterlagen",      # noqa: E731
                                    next((x for x in sheet["documents"] if str(x["nr"]) == re.sub(r"[a-z]+$", "", nr)), {}).get("kind") or "")
        if v["von"] is None and v["datum"] and d["issuer_role"] in ("unbekannt", "Steuerberater"):
            gleiche = {o["von"] for o in out if o is not v and o["von"] in kanzleien and o["datum"] == v["datum"] and (buch(o["dok"]) or buch(v["dok"]))}
            if len(gleiche) == 1:
                v["von"] = gleiche.pop()
                v["grundlage"] = "gleiches Druckdatum wie ein Dokument dieser Kanzlei"
                if v["an"] is None and mand:
                    v["an"] = mand
    return out, beziehungen(sheet, out)


def beziehungen(sheet, out):
    """Связи из таблицы «кто кому пишет»: кто кого представлял, кому писали напрямую. Вызывается заново после исправлений обработчика."""
    akt = {a["maske"]: a for a in sheet.get("akteure", [])}
    mand = next((m for m, a in akt.items() if re.search(r"(?i)mandant|inhaber|klient", m + " " + a["rolle"]) and a["art"] == "Person"), None)
    gatte = next((m for m, a in akt.items() if re.search(r"(?i)ehe(mann|frau|gatt|partner)", m + " " + a["rolle"])), None)
    aemter = [m for m in akt if re.search(r"(?i)kasse|finanzamt", m) and ":" not in m]
    kanzleien = [m for m, a in akt.items() if a["art"] == "Organisation" or re.search(r"(?i)kanzlei", m) and ":" not in m]
    bez = {}
    for v in out:
        von, an = v["von"], v["an"] or ""
        if not von or not an or not mand:
            continue
        an_k = next((k for k in kanzleien if k in an), None)
        if von in aemter and an_k and (mand in v.get("betrifft", []) or mand in an):
            k = f"{an_k} vertritt {mand} gegenüber {von}"
        elif von in kanzleien and gatte and gatte in an and mand not in an:
            k = f"Ansprechpartner von {von} ist {gatte}, nicht {mand}"
        elif von in aemter and mand in an:
            k = f"{von} schreibt unmittelbar an {mand} (kein Vertreter im Anschriftsfeld)"
        elif von in kanzleien and mand in an:
            k = f"{von} schreibt an {mand}"
        elif von in kanzleien and any(x in an for x in aemter):
            k = f"{von} tritt gegenüber {next(x for x in aemter if x in an)} auf"
        else:
            continue
        bez.setdefault(k, []).append((v["dok"], v["datum"]))
    return [f"{k} – Dok. {', '.join(d for d, _ in vs)}" + (f" ({'; '.join(sorted({x for _, x in vs if x}, key=lambda z: z[6:] + z[3:5] + z[:2]))})" if any(x for _, x in vs) else "") for k, vs in bez.items()]


def validate(sheet):
    import jsonschema
    return [f"{'/'.join(map(str, e.path))}: {e.message[:120]}" for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(sheet)]


def code(sheet):
    return hashlib.sha256(json.dumps(sheet, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def render_md(sheet):
    L = [f"FRAGE DES BEARBEITERS: {sheet['question']}", ""]
    if sheet.get("einleitung"):
        L += [f"## Einleitung des Bearbeiters ({sheet['einleitung']['status']})", "", sheet["einleitung"]["text"], ""]
    if sheet.get("akteure"):
        L += ["## Verzeichnis der Beteiligten (Masken; Namen kennt nur der Bearbeiter)", "",
              "| Maske | Art | Rolle | Gruppe | gehört zu | in Dokumenten | Nennungen | offener Name (nicht verborgen) | evtl. identisch mit | Status |", "|---|---|---|---|---|---|---:|---|---|---|"]
        for a in sheet["akteure"]:
            gz = f"{a['gehoert_zu']} ({a['gehoert_zu_status']})" if a.get("gehoert_zu") else "–"
            L.append(f"| {a['maske']} | {a['art']} | {a['rolle']} | {a.get('gruppe') or '–'} | {gz} | {', '.join(map(str, a['dokumente']))} | {a['nennungen']} | "
                     f"{', '.join(a.get('name_offen', [])) or '–'} | {', '.join(a.get('evtl_identisch_mit', [])) or '–'} | {a['status']} |")
        L += ["", sheet.get("akteure_hinweis", ""), ""]
    if sheet.get("verkehr"):
        L += ["## Schriftverkehr: wer schreibt wem (per Code aus Kopf, Anrede und Unterschrift; »–« = nicht bestimmt)", "",
              "| Dok. | von | unterzeichnet | an | betrifft | Datum des Schreibens | Grundlage |", "|---|---|---|---|---|---|---|"]
        L += [f"| {v['dok']} | {v['von'] or '–'} | {v.get('unterzeichnet') or '–'} | {v['an'] or '–'} | {', '.join(v.get('betrifft', [])) or '–'} | {v.get('datum') or '–'} | {v.get('grundlage', '')} |"
              for v in sheet["verkehr"]]
        L.append("")
    if sheet.get("beziehungen"):
        L += ["## Beziehungen, die sich aus dem Schriftverkehr ergeben (per Code)", ""] + [f"- {b}" for b in sheet["beziehungen"]] + [""]
    for d in sheet["documents"]:
        L += [f"## Dokument {d['nr']}: {d['kind']}",
              f"Aussteller: {d['issuer_role']} · Datum: {d.get('date') or 'nicht erkannt'} · betroffene Jahre: {', '.join(map(str, d.get('years', []))) or '–'} · "
              f"Seiten: {d['pages']} · Lesbarkeit der Texterkennung: {int(100 * d['ocr_quality'])} %", ""]
        if d.get("annahme") and d["annahme"] != "angenommen":
            L += [f"**ANNAHME: {d['annahme'].upper()}** – {d.get('annahme_grund', '')}", ""]
        for t in d.get("tables", []):
            L += [f"**Tabelle: {t['name']}**" + (f" ({t['note']})" if t.get("note") else ""), "", "| " + " | ".join(t["columns"]) + " |", "|" + "---|" * len(t["columns"])]
            L += ["| " + " | ".join(f"{c:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if isinstance(c, float) else str(c) for c in r) + " |" for r in t["rows"]]
            if t.get("control_sum") is not None:
                L.append(f"\nKontrollsumme der Tabelle: {t['control_sum']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            L.append("")
        L += [d["text"], ""]
    return "\n".join(L)


# --- ключ Секретаря: журнал замен, по которому всё возвращается на место ---------------------------------------------
VORNAMEN = "Anna Bernd Clara Dieter Eva Frank Greta Hans Ines Jens Karin Lars Maria Nils Olaf Petra Ralf Silke Tom Ute".split()


def _owner(val, persons):
    """Часть имени (фамилия или имя отдельно) -> полное имя, в которое она входит; иначе None."""
    v = val.strip()
    for full in persons:
        if full != v and v and re.search(rf"(?<![\w]){re.escape(v)}(?![\w])", full):
            return full
    return None


def make_key(mapping):
    """Ключ дела: по записи на каждую замену -- номер, вид, метка, вымышленное имя (для лиц и фирм), подлинное значение.
    Хранится только локально, у Секретаря; наружу не уходит."""
    key = []
    for i, (ph, val) in enumerate(mapping.items(), 1):
        if not ph.startswith("["):
            continue
        kind = ph[1:-1].rsplit(" ", 1)[0]
        pseudo = (f"{VORNAMEN[len([k for k in key if k['kind'] == 'Person']) % len(VORNAMEN)]} Muster-{i}" if kind == "Person"
                  else f"Musterfirma-{i}" if kind == "Firma" else None)
        key.append({"index": i, "kind": kind, "placeholder": ph, "pseudonym": pseudo, "original": val})
    # одно лицо -- одно вымышленное имя: фамилия или имя, стоящие отдельно, получают ту же фамилию «Muster-N», что и полное имя
    persons = sorted({k["original"].strip() for k in key if k["kind"] == "Person" and len(k["original"].split()) >= 2}, key=len, reverse=True)
    full = {k["original"].strip(): k for k in key if k["kind"] == "Person"}
    for k in key:
        if k["kind"] == "Person" and len(k["original"].split()) == 1:
            o = _owner(k["original"], persons)
            if o and o in full:
                base = full[o]["pseudonym"]                          # «Anna Muster-7»
                first, last = base.split(" ", 1)
                k["pseudonym"] = (first if full[o]["original"].split()[0] == k["original"].strip() else last) + f"\u200b{k['index']}"
                k["same_person_as"] = full[o]["index"]
    return key


def pseudonymize(text, key):
    """Вместо меток -- вымышленные имена (лица, фирмы): текст читается естественнее. Номер в имени делает замену однозначной и обратимой.
    Номера, адреса, счета остаются метками: вымышленный номер могут принять за настоящий."""
    for k in sorted(key, key=lambda k: -len(k["placeholder"])):
        if k["pseudonym"]:
            text = text.replace(k["placeholder"], k["pseudonym"])
    return text


def restore(text, key):
    """Возврат подлинных значений по ключу -- и из меток, и из вымышленных имён."""
    for k in sorted(key, key=lambda k: -len(k["pseudonym"] or "")):
        if k["pseudonym"]:
            text = text.replace(k["pseudonym"], k["original"])
            if "\u200b" in k["pseudonym"]:                          # модель могла выбросить невидимый разделитель с номером
                text = re.sub(rf"(?<![\w-]){re.escape(k['pseudonym'].split(chr(0x200b))[0])}(?![\w-])", k["original"], text)
    for k in sorted(key, key=lambda k: -len(k["placeholder"])):
        text = text.replace(k["placeholder"], k["original"])
    return text
