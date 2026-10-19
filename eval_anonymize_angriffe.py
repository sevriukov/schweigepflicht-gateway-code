#!/usr/bin/env python3
"""eval_anonymize_angriffe.py -- атаки на обезличиватель (19.10.2026, замечания DeepSeek/Gemini к досье системы, п. 3 сводки Main).
Придуманные имена и данные (имитации, настоящих людей нет). Каждая атака -- в двух видах:
  «одна»   -- имя встречается только в искажённом виде (должны поймать распознавание имён и правила);
  «якорь»  -- сначала имя в чистом виде, затем искажённый повтор (должна поймать замена повторов).
Утечка считается по НОРМАЛИЗОВАННОМУ результату (NFKC, без невидимых знаков, кириллические двойники -> латиница, перенос
строки внутри слова склеен, разрядка «H a b e r» склеена, без учёта регистра), иначе проверка обманулась бы тем же, чем обезличиватель.
Отдельно -- поймал ли остаток контроль guard() (тогда текст не уйдёт без человека).
    python3 eval_anonymize_angriffe.py   -> anonymize_test/REPORT_angriffe.txt, anonymize_test/angriffe.json
"""
import json
import re
import sys
import unicodedata

from anonymizer import anonymize, guard

HOMO = str.maketrans("АВЕКМНОРСТХаеорсухіјѕԁԛԝ", "ABEKMHOPCTXaeopcyxijsdqw")
UNSICHTBAR = re.compile("[­​-‏⁠-⁤﻿͏᠎]")


def norm(t):
    t = UNSICHTBAR.sub("", unicodedata.normalize("NFKC", t)).translate(HOMO)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)
    t = re.sub(r"\b(\w) (?=\w\b)", r"\1", t)          # «H a b e r m e h l» -> «Habermehl»
    return t.casefold()


# (ключ, описание, искажённое упоминание, что не должно остаться, чистое упоминание для «якоря»)
A = [
    ("homoglyph", "кириллическая «е» внутри фамилии", "Herr Wendelin Habermеhl", "habermehl", "Herr Wendelin Habermehl"),
    ("homoglyph_voll", "кириллические О и е в фамилии", "Frau Grete \u041est\u0435ndorf", "ostendorf", "Frau Grete Ostendorf"),
    ("zwsp", "невидимый пробел (U+200B) внутри фамилии", "Herr Wendelin Haber​mehl", "habermehl", "Herr Wendelin Habermehl"),
    ("shy", "мягкий перенос (U+00AD) внутри фамилии", "Herr Wendelin Haber­mehl", "habermehl", "Herr Wendelin Habermehl"),
    ("zeilenumbruch", "перенос строки с дефисом внутри фамилии", "Herr Wendelin Haber-\nmehl", "habermehl", "Herr Wendelin Habermehl"),
    ("gesperrt", "разрядка буквами", "Herr W e n d e l i n H a b e r m e h l", "habermehl", "Herr Wendelin Habermehl"),
    ("punkte", "буквы через точки", "Herr H.a.b.e.r.m.e.h.l", "h.a.b.e.r.m.e.h.l", "Herr Wendelin Habermehl"),
    ("versal", "фамилия прописными посреди предложения", "der Mandant HABERMEHL", "habermehl", "Herr Wendelin Habermehl"),
    ("klein", "фамилия строчными", "rückfrage bei habermehl wegen der belege", "habermehl", "Herr Wendelin Habermehl"),
    ("genitiv", "родительный падеж без имени", "Habermehls Firmenwagen", "habermehl", "Herr Wendelin Habermehl"),
    ("fullwidth", "полноширинные латинские буквы (NFKC)", "Herr Ｈａｂｅｒｍｅｈｌ", "habermehl", "Herr Wendelin Habermehl"),
    ("gemeinwort_koch", "фамилия = обычное слово (Koch)", "Herr Lorenz Koch hat die Belege gebracht", "lorenz koch", "Herr Lorenz Koch"),
    ("gemeinwort_becker", "фамилия = профессия (Becker/Bäcker)", "Frau Becker kaufte beim Bäcker ein", "frau becker", "Frau Ilse Becker"),
    ("gemeinwort_braun", "фамилия = прилагательное (Braun)", "Mit Herrn Braun ist die Schlussbesprechung vereinbart", "herrn braun", "Herr Detlef Braun"),
    ("geborene", "девичья фамилия без имени", "Die Mandantin, geborene Ostendorf, erbte 2021", "ostendorf", "Frau Grete Ostendorf"),
    ("adel_doppel", "многочастная фамилия с дворянской частицей", "Hans-Peter von der Vogelweide-Schimmelpfennig", "vogelweide-schimmelpfennig", "Hans-Peter von der Vogelweide-Schimmelpfennig"),
    ("url", "фамилия в адресе сайта", "siehe https://kanzlei-habermehl.de/download/rechnung", "habermehl", "Herr Wendelin Habermehl"),
    ("domain_ohne_http", "фамилия в адресе без http", "Rechnung von habermehl-sanitaer.de erhalten", "habermehl", "Herr Wendelin Habermehl"),
    ("mail", "фамилия в адресе почты", "Antwort an w.habermehl@beispiel-mail.de", "habermehl", "Herr Wendelin Habermehl"),
    ("formel", "фамилия в формуле таблицы", "=SUMME(Konto_Habermehl!B2:B40)", "habermehl", "Herr Wendelin Habermehl"),
    ("dateiname", "фамилия в имени файла", "Anlage: Kontoauszug_Habermehl_2023.pdf", "habermehl", "Herr Wendelin Habermehl"),
    ("iban_worte", "IBAN словами", "IBAN DE vier vier fünf null null eins null fünf eins sieben", "de vier vier fünf null", None),
    ("iban_luecken", "IBAN с лишними пробелами", "IBAN: D E 4 4 5 0 0 1 0 5 1 7 5 4 0 7 3 2 4 9 3 1", "de44500105175407324931", None),
    ("iban_kyr", "IBAN с кириллическим кодом страны", "IBAN: \u0414\u0415445001 0517 5407 3249 31", "445001", None),
    ("steuernr_ocr", "налоговый номер с ошибками распознавания (O вместо 0)", "StNr. 3O5/123/4567O", "305/123/45670", None),
    ("az_eigen", "номер собственного дела в суде", "In dem Klageverfahren 3 K 1234/21 des Mandanten", "3 k 1234/21", None),
    ("az_bfh_eigen", "номер собственного дела клиента в BFH", "Revision beim BFH unter dem Az. IX R 7/24 anhängig", "ix r 7/24", None),
    ("az_klammer", "номер дела в скобках с буквой суда", "Ihre Klage (Az. 11 K 2050/19 E) ist anhängig", "2050/19", None),
    ("ort_klein", "маленький город + профессия (роль указывает на человека)", "der einzige Notar in Hallenberg-Liesen", "hallenberg-liesen", None),
]


def main():
    # публичные ссылки на решения должны остаться целиком (иначе теряется источник) -- проверка лишних замен
    for s_, soll in (("vgl. BFH, Urteil vom 12.03.2020 - VI R 5/18", "VI R 5/18"), ("vgl. FG Köln, Urteil vom 12.03.2020 - 3 K 1234/21", "FG Köln, Urteil vom 12.03.2020 - 3 K 1234/21"),
                     ("BVerfG, Beschluss vom 01.02.2020, 2 BvR 123/19", "2 BvR 123/19")):
        o_ = anonymize(s_, level=1)[0]
        print(("ОК     " if soll in o_ else "ЛИШНЯЯ ЗАМЕНА ") + f"публичная ссылка остаётся: {s_}")
    rows = []
    for key, txt, angriff, rest, anker in A:
        for art in ("одна", "якорь"):
            if art == "якорь" and not anker:
                continue
            text = (f"{anker} hat uns am Montag angerufen. " if art == "якорь" else "") + f"Aktennotiz: {angriff}. Bitte Unterlagen prüfen."
            out, mapping = anonymize(text, level=1)
            leck = rest in norm(out)
            g = guard(out, mapping, level=1) if leck else []
            rows.append({"key": key, "art": art, "text": txt, "leck": leck, "guard_fängt": bool(g), "out": out})
    lecks = [r for r in rows if r["leck"]]
    ungefangen = [r for r in lecks if not r["guard_fängt"]]
    L = [f"Атаки на обезличиватель, уровень 1, {len(rows)} проб ({len(A)} атак, одна/якорь). Имена и данные придуманы (имитации).",
         f"Остаток после обезличивания: {len(lecks)}; из них НЕ пойман контролем guard (ушёл бы без предупреждения): {len(ungefangen)}.", ""]
    for r in rows:
        mark = "ОК    " if not r["leck"] else ("ОСТАТОК, guard ловит" if r["guard_fängt"] else "УТЕЧКА")
        L.append(f"{mark:22} {r['key']:18} {r['art']:6} {r['text']}")
    L += ["", "Вывод для утечек (как ушло бы наружу):"]
    L += [f"  {r['key']} / {r['art']}: {r['out'][:200]!r}" for r in ungefangen]
    open("anonymize_test/REPORT_angriffe.txt", "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump(rows, open("anonymize_test/angriffe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(L[:2]))
    print(f"ANGRIFFE: проб {len(rows)}, остатков {len(lecks)}, утечек мимо guard {len(ungefangen)}")
    return 1 if "--streng" in sys.argv and ungefangen else 0


if __name__ == "__main__":
    sys.exit(main())
