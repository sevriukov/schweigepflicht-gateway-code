#!/usr/bin/env python3
"""versteckt.py -- скрытое содержимое файлов дела и вставленные указания для модели (19.10.2026, замечания DeepSeek/Gemini к досье:
метаданные, скрытые листы и слои, невидимый текст, инъекции в документе).

Что делает при извлечении текста (вызывается из anon_paket.py и pipeline_case.py):
  PDF   -- из текстового слоя выбрасывается текст, который человек на странице не видит: белый, мельче 3 pt, за краем страницы
           (невидимый слой распознанного скана -- режим 3 -- остаётся: это обычный OCR-слой); метаданные (автор, программа) в текст не идут и не шли.
  DOCX  -- удалённые правки (w:del), скрытый текст (w:vanish) в текст не идут; примечания и сведения об авторе не читались и не читаются.
  XLSX  -- скрытые листы, строки и столбцы помечаются в тексте («ausgeblendet»), чтобы человек видел их при одобрении; формулы и примечания не читаются.
  EML   -- служебные заголовки (Received, Message-ID, X-…, DKIM) отбрасываются; остаются Datum, Betreff, Von, An и текст письма.
  Фото  -- EXIF (место съёмки, автор, устройство): в текст не идёт; наличие отмечается в отчёте.
Отчёт (только числа и виды, без содержимого) -- <дело>/_pipeline/versteckt.json; строки в протокол приёмки и лист проверки.
injektion(text) -- указания для модели внутри материалов дела («ignore previous instructions», «du bist jetzt…», «system prompt»):
список найденных мест; anonymizer.guard() считает их нарушением -- лист уходит только после явного одобрения человеком.
"""
import json
import re
import zipfile
from pathlib import Path

BERICHT = {}          # имя файла -> {вид: число}

INJEKTION = [
    r"\b(?:ignore|disregard|forget)\b.{0,30}\b(?:previous|prior|above|all|earlier)\b.{0,30}\b(?:instructions?|rules|prompts?|messages?)",
    r"\b(?:ignorier(?:e|en Sie|t)|vergiss|vergessen Sie|missachte|missachten Sie)\b.{0,40}\b(?:Anweisung\w*|Regeln|Vorgaben|Instruktion\w*|Prompt\w*)",
    r"\b(?:игнорир\w*|забудь\w*)\b.{0,40}\b(?:инструкц\w*|правил\w*|указани\w*)",
    r"\bsystem\s*-?\s*(?:prompt|message|nachricht|anweisung)\b",
    r"\b(?:you are now|from now on you|act as|du bist (?:jetzt|ab sofort|nun)|ab sofort bist du|ты теперь)\b",
    r"\b(?:as an? (?:ai|language model)|als (?:KI|Sprachmodell))\b.{0,40}\b(?:must|musst|sollst|should)\b",
    r"\b(?:output|print|reveal|gib|zeige?|выведи)\b.{0,40}\b(?:system ?prompt|platzhalter|placeholders?|unmasked|klarnamen|настоящ\w* имен\w*)",
    r"(?:\[|<)\s*/?\s*(?:SYSTEM|INST|assistant|im_start|im_end)\s*(?:\]|>)",
    r"\b(?:Anweisung|Hinweis|Nachricht|Note|Instruction)\s+(?:an|für|to|for)\s+(?:die|den|the)?\s*(?:KI|AI|LLM|Modell|model|Assistent\w*|assistant|ChatGPT|Claude|Gemini)\b",
]
_INJ = [re.compile(p, re.I | re.S) for p in INJEKTION]


def injektion(text):
    """места, похожие на указания модели внутри материалов дела: [(начало, образец)]"""
    hits = []
    for rx in _INJ:
        for m in rx.finditer(text):
            hits.append((m.start(), m.group(0)[:80]))
    return sorted(set(hits))


def _zaehle(name, art, n=1):
    if n:
        BERICHT.setdefault(name, {})
        BERICHT[name][art] = BERICHT[name].get(art, 0) + n


def pdf_seite_text(page, name=""):
    """текст страницы PDF без того, что человек не видит (белый текст, кегль < 3 pt, за краем страницы); порядок строк -- как у get_text()"""
    r = page.rect
    zeilen, weg = [], 0
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            teile = []
            for s in ln["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                unsichtbar = (s["color"] & 0xFFFFFF) >= 0xF0F0F0 and s["text"].strip() or (s["size"] < 3 and s["text"].strip()) \
                    or x1 < r.x0 - 1 or x0 > r.x1 + 1 or y1 < r.y0 - 1 or y0 > r.y1 + 1
                if unsichtbar:
                    weg += len(s["text"].strip())
                    continue
                teile.append(s["text"])
            if teile:
                zeilen.append("".join(teile))
        zeilen.append("")
    if weg:
        _zaehle(name, "PDF: невидимый текст убран (знаков)", weg)
    return "\n".join(zeilen)


def pdf_meta(doc, name=""):
    m = {k: v for k, v in (doc.metadata or {}).items() if v and k in ("author", "creator", "producer", "title", "subject", "keywords")}
    if m:
        _zaehle(name, "PDF: метаданные (в текст не идут): " + ", ".join(sorted(m)))
    if any(p.first_annot for p in doc):
        _zaehle(name, "PDF: примечания на страницах (в текст не идут)")
    if doc.embfile_count():
        _zaehle(name, "PDF: вложенные файлы (в текст не идут)", doc.embfile_count())


def docx_text(f):
    """текст DOCX без удалённых правок и скрытого текста"""
    z = zipfile.ZipFile(f)
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    name = Path(f).name
    n_del = len(re.findall(r"<w:del\b", xml))
    xml = re.sub(r"<w:del\b[^>]*>.*?</w:del>", "", xml, flags=re.S)
    xml = re.sub(r"<w:delText[^>]*>.*?</w:delText>", "", xml, flags=re.S)
    n_hid = 0

    def _run(m):
        nonlocal n_hid
        if re.search(r"<w:vanish(?:\s|/|>)", m.group(0)):
            n_hid += 1
            return ""
        return m.group(0)
    xml = re.sub(r"<w:r\b.*?</w:r>", _run, xml, flags=re.S)
    _zaehle(name, "DOCX: удалённые правки убраны", n_del)
    _zaehle(name, "DOCX: скрытый текст убран (фрагментов)", n_hid)
    if "word/comments.xml" in z.namelist():
        _zaehle(name, "DOCX: примечания (в текст не идут)")
    if "docProps/core.xml" in z.namelist() and re.search(r"<dc:creator>[^<]+|<cp:lastModifiedBy>[^<]+", z.read("docProps/core.xml").decode("utf-8", "ignore")):
        _zaehle(name, "DOCX: автор в свойствах файла (в текст не идёт)")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def xlsx_text(f):
    """таблица Excel -> текст, как прежде (каждый лист «## Blatt: …», строки через запятую); скрытые листы, строки и столбцы помечены"""
    import csv
    import io
    import openpyxl
    name = Path(f).name
    out = []
    wb = openpyxl.load_workbook(f, data_only=True)          # не read_only: нужны признаки скрытых строк и столбцов
    for ws in wb.worksheets:
        zust = ws.sheet_state
        hid_r = {i for i, d in ws.row_dimensions.items() if d.hidden}
        hid_c = {k for k, d in ws.column_dimensions.items() if d.hidden}
        buf = io.StringIO()
        w = csv.writer(buf)
        for i, r in enumerate(ws.iter_rows(values_only=True), 1):
            if any(c not in (None, "") for c in r):
                w.writerow((["(ausgeblendete Zeile)"] if i in hid_r else []) + ["" if c is None else c for c in r])
        kopf = f"## Blatt: {ws.title}" + (" (ausgeblendetes Blatt)" if zust != "visible" else "") + (f" (ausgeblendete Spalten: {', '.join(sorted(hid_c))})" if hid_c else "")
        out.append(f"{kopf}\n{buf.getvalue()}")
        _zaehle(name, "XLSX: скрытые листы (помечены в тексте)", zust != "visible")
        _zaehle(name, "XLSX: скрытые строки (помечены)", len(hid_r))
        _zaehle(name, "XLSX: скрытые столбцы (помечены)", len(hid_c))
    if wb.defined_names:
        _zaehle(name, "XLSX: именованные диапазоны (в текст не идут)", len(list(wb.defined_names)))
    return "\n".join(out)


def eml_text(f):
    """письмо .eml -> Datum, Betreff, Von, An, текст; служебные заголовки и вложения в текст не идут"""
    import email
    from email import policy
    msg = email.message_from_bytes(Path(f).read_bytes(), policy=policy.default)
    name = Path(f).name
    kopf = [f"{k}: {msg[k]}" for k in ("Date", "Subject", "From", "To", "Cc") if msg[k]]
    _zaehle(name, "EML: служебные заголовки убраны", len([k for k in msg.keys() if k not in ("Date", "Subject", "From", "To", "Cc")]))
    teile = []
    for p in msg.walk():
        if p.is_multipart():
            continue
        if p.get_content_disposition() == "attachment":
            _zaehle(name, "EML: вложения (в текст не идут; положить в папку дела отдельным файлом)")
            continue
        if p.get_content_type() == "text/plain":
            teile.append(p.get_content())
        elif p.get_content_type() == "text/html" and not teile:
            h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", p.get_content())
            teile.append(re.sub(r"<[^>]+>", "\n", h))
    return "\n".join(kopf) + "\n\n" + "\n".join(teile)


def bild_meta(f):
    """фото: EXIF (место съёмки, автор, устройство) -- только отметка в отчёте; в текст EXIF не идёт (текст -- распознавание изображения)"""
    try:
        from PIL import Image
        ex = Image.open(f).getexif()
    except Exception:                                        # noqa: BLE001
        return
    name = Path(f).name
    if ex.get(34853):
        _zaehle(name, "Фото: координаты места съёмки в EXIF (в текст не идут)")
    if ex.get(315) or ex.get(33432):
        _zaehle(name, "Фото: автор в EXIF (в текст не идёт)")


def speichern(pipeline_dir):
    """отчёт без содержимого (только виды и числа); лежит локально в папке дела, наружу не уходит"""
    p = Path(pipeline_dir) / "versteckt.json"
    alt = json.load(open(p, encoding="utf-8")) if p.exists() else {}
    for name, v in BERICHT.items():
        alt[name] = v
    json.dump(alt, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    BERICHT.clear()
    return alt
