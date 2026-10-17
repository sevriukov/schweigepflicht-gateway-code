#!/usr/bin/env python3
"""
anon_ru.py -- дополнительный проход обезличивания для русского текста (11.10.2026). Измерение eval_anonymize_ru.py на выдуманных
фразах показало пропуски: латинское имя в русской строке без «Herr/Frau», название фирмы в кавычках, город в падеже, фамилия в
скобках, слово рядом с меткой лица, фамилия с инициалами, фамилия строчными. Здесь правила на каждый вид.
  nachlese_ru(text, mp) -> (text, mp)   -- вызывать ПОСЛЕ anonymizer.anonymize; mp дополняется.
"""
import re

import anonymizer

KYR = r"А-Яа-яЁё"
NAME = rf"[А-ЯЁ][а-яё]{{2,}}(?:-[А-ЯЁ][а-яё]{{2,}})?"
# слова с заглавной буквы, которые именем не являются (начало фразы, обращения, названия ведомств и месяцев)
KEIN = re.compile(r"(?i)^(это|если|когда|потом|вчера|сегодня|завтра|передайте|спросите|договор|акт|директор|бухгалтер|письмо|счёт|счет|мы|вы|он|она|они|у|в|на|по|за|из|с|к|"
                  r"добрый|уважаем\w+|здравствуйте|спасибо|пожалуйста|налогов\w+|финанс\w+|германи\w+|росси\w+|украин\w+|январ\w+|феврал\w+|март\w*|апрел\w+|ма[йя]|июн\w+|июл\w+|"
                  r"август\w*|сентябр\w+|октябр\w+|ноябр\w+|декабр\w+|работал\w*|господин\w*|госпож\w+)$")
FORM = r"(?:ООО|ОАО|ЗАО|АО|ПАО|ИП|ТОО|фирм[аеуы]|компани[яиюей]|салон[ае]?|магазин[ае]?|кафе|ресторан[ае]?|студи[яиюей])"


LAND = re.compile(r"(?i)^(германи|росси|украин|европ|казахстан|беларус|польш|франци|итали|испани|турци|австри|швейцари|нидерланд|голланди|бельги|чехи|литв|латви|эстони|молдов|"
                  r"грузи|армени|азербайджан|узбекистан|киргизи|кыргызстан|таджикистан|кита|сша|америк|англи|великобритани|израил|болгари|румыни|венгри|греци|серби)\w*$")
_morph = []


def _eigenname(w, art):
    """Слово сущности похоже на имя (или место), а не на обычное слово с заглавной буквы: словарь pymorphy знает его как имя,
    фамилию, отчество или географическое название -- либо не знает совсем. Обычное слово («Документы», «Среду») -- нет."""
    if not _morph:
        try:
            import pymorphy3
            _morph.append(pymorphy3.MorphAnalyzer())
        except Exception:                                # noqa: BLE001
            _morph.append(None)
    if not re.fullmatch(rf"[{KYR}-]+", w):               # латинское слово внутри сущности: имя, если это не обычное немецкое слово
        return len(w) >= 4 and not w.isupper() and re.sub(r"[^a-zäöüß]", "", w.lower()) not in _deutsch()      # сокращение прописными («RAG») -- не имя
    if _morph[0] is None:
        return True
    ps = _morph[0].parse(w)
    marken = ("Geox",) if art == "LOC" else ("Name", "Surn", "Patr")
    return any(m in p.tag for p in ps for m in marken) or not any(_morph[0].word_is_known(x) for x in (w, w.lower()))


_de = []


def _deutsch():
    """Обычные немецкие слова (186 тыс. из базы права, de_wortliste.txt.gz) -- строчными."""
    if not _de:
        import gzip
        from pathlib import Path
        f = Path(__file__).parent / "de_wortliste.txt.gz"
        _de.append({w.strip().lower() for w in gzip.open(f, "rt", encoding="utf-8")} if f.exists() else set())
    return _de[0]


def _person_de(phrase):
    """Немецкая модель, спрошенная о фразе отдельно, видит в ней лицо."""
    try:
        return any(e.label_ == "PER" for e in anonymizer._nlp()(phrase).ents)
    except Exception:                                    # noqa: BLE001
        return True


def _nr(mp):
    return max([800] + [int(x) for ph in mp for x in re.findall(r"^\[\w+ (\d+)\]$", ph)])


def nachlese_ru(text, mp):
    k = [_nr(mp)]

    def neu(val, art):
        ph = next((p for p, v in mp.items() if v == val and p.startswith(f"[{art} ")), None)
        if not ph:
            k[0] += 1
            ph = f"[{art} {k[0]}]"
            mp[ph] = val
        return ph
    out = []
    for ln in text.split("\n"):
        if len(re.findall(rf"[{KYR}]", ln)) < 3:
            out.append(ln)
            continue
        # 1) фирма: организационная форма + название в кавычках; название в кавычках + GmbH/UG/AG
        ln = re.sub(rf"({FORM}\s+)([«\"„][^»\"“\n]{{2,40}}[»\"“])", lambda m: m.group(1) + neu(m.group(2), "Firma"), ln)
        ln = re.sub(r"([«\"„][^»\"“\n]{2,40}[»\"“])(\s+(?:GmbH|UG|AG|KG|OHG|e\.K\.))", lambda m: neu(m.group(1), "Firma") + m.group(2), ln)
        ln = re.sub(rf"\b(ИП\s+)({NAME})", lambda m: m.group(1) + neu(m.group(2), "Person"), ln)
        # 2) латинское имя в русской строке: два-три слова с заглавной буквы, не из немецкого словаря
        def lat(m):
            w = m.group(0).split()
            if any(anonymizer.KEEP.match(x) for x in w) or re.search(r"\b(GmbH|AG|UG|KG|Finanzamt|Steuer\w*|Krankenkasse)\b", m.group(0)):
                return m.group(0)
            if all(x.lower() in _deutsch() for x in w) or (any(x.lower() in _deutsch() for x in w) and not _person_de(m.group(0))):      # «Selbständige Tätigkeit», «Soll Umsatz» -- термины, а не имя
                return m.group(0)
            return neu(m.group(0), "Person")
        ln = re.sub(r"(?<![\w\[])[A-ZÄÖÜ][a-zäöüß]{2,}(?: [A-ZÄÖÜ][a-zäöüß]{2,}){1,2}(?![\w\]])", lat, ln)
        # 3) слово с заглавной буквы вплотную к метке лица (часть того же имени) и фамилия с инициалами
        for _ in range(2):
            ln = re.sub(rf"(?<![{KYR}\w])({NAME})(\s+\[Person [^\]]+\])", lambda m: m.group(0) if KEIN.match(m.group(1)) or not _eigenname(m.group(1), "PER") else neu(m.group(1), "Person") + m.group(2), ln)
            ln = re.sub(rf"(\[Person [^\]]+\]\s+)({NAME})(?![{KYR}\w])", lambda m: m.group(0) if KEIN.match(m.group(2)) or not _eigenname(m.group(2), "PER") else m.group(1) + neu(m.group(2), "Person"), ln)
        ln = re.sub(rf"(?<![{KYR}\w])({NAME})(\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)", lambda m: m.group(0) if KEIN.match(m.group(1)) else neu(m.group(1) + m.group(2), "Person"), ln)
        # 4) фамилия в скобках
        ln = re.sub(rf"\(({NAME}(?: {NAME})?)\)", lambda m: m.group(0) if KEIN.match(m.group(1).split()[0]) or not all(_eigenname(x, "PER") for x in m.group(1).split()) else "(" + neu(m.group(1), "Person") + ")", ln)
        # 5) место после предлога: слово с заглавной буквы не в начале фразы, которое русская модель считает местом
        out.append(ln)
    text = "\n".join(out)
    nlp = anonymizer._nlp_x("ru")
    if nlp is not None:
        ru = "\n".join(l for l in text.split("\n") if len(re.findall(rf"[{KYR}]", l)) >= 3)
        nlp.max_length = max(nlp.max_length, len(ru) + 1)
        for e in sorted({(e.text, e.label_) for e in nlp(ru).ents if e.label_ in ("LOC", "PER") and not re.search(r"[\[\]()\n]", e.text)}, key=lambda x: -len(x[0])):
            t = e[0].strip()
            if len(t) < 4 or not t[:1].isupper() or all(KEIN.match(w) for w in t.split()) or any(LAND.match(w) for w in t.split()) or not any(_eigenname(w, e[1]) for w in t.split() if len(w) >= 3):
                continue
            text = re.sub(rf"(?<![{KYR}\w\[]){re.escape(t)}(?![{KYR}\w\]])", neu(t, "Ort" if e[1] == "LOC" else "Person"), text)
    # 6) известные значения строчными и в других падежах: основа фамилии или имени (без окончания) + до трёх букв
    for ph, v in list(mp.items()):
        if not ph.startswith("[Person"):
            continue
        for w in str(v).split():
            w = w.strip("«».,()")
            if len(w) >= 5 and re.fullmatch(rf"[{KYR}-]+", w) and not KEIN.match(w):
                stamm = re.sub(r"(ого|ому|ым|ой|ую|ая|ов|ев|а|у|е|ы|и|ю|я|ом|ем)$", "", w) if len(w) >= 7 else w
                text = re.sub(rf"(?i)(?<![{KYR}\w\[]){re.escape(stamm)}[а-яё]{{0,3}}(?![{KYR}\w\]])", ph, text)
    return text, mp
