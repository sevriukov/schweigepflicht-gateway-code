#!/usr/bin/env python3
"""
eval_anonymize.py -- проверка обезличивания (роль Аналитика, шаг 1) на придуманных письмах с ИЗВЕСТНЫМИ данными.

  python3 eval_anonymize.py make [N]   # придуманные данные (кодом) -> Gemini пишет письма, вставляя их дословно
                                       # (данные вымышленные, настоящих людей нет) -> anonymize_test/letters.json
  python3 eval_anonymize.py run        # anonymize_hard + outbound_guard по каждому письму -> что осталось в тексте
                                       # -> anonymize_test/REPORT.md
"""
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

D = Path("anonymize_test")
WILD = "letters_" + (sys.argv[sys.argv.index("--name") + 1] if "--name" in sys.argv else "wild") + ".json"   # независимые партии: --name wild2
VOR = ["Heinrich", "Aylin", "Katarzyna", "Mehmet", "Sabine", "Thorsten", "Oksana", "Giovanni", "Annegret", "Jürgen", "Nguyen Van", "Fatima",
       "Björn", "Swetlana", "Karl-Heinz", "Maximilian", "Zeynep", "Dragan", "Ingeborg", "Luca"]
NACH = ["Brinkmöller", "Yıldırım", "Kowalczyk", "Schulte-Uebbing", "Öztürk", "von Hagenbeck", "Petrenko", "Esposito", "Müller", "Schmidt",
        "Tran", "El-Masri", "Großekathöfer", "Jovanović", "Weiß", "Oberhuber", "Krämer", "Lindqvist", "Wagner", "Hoffmann"]
FIRMA = ["{n} Haustechnik GmbH", "Autohaus {n} e.K.", "{n} & Söhne OHG", "Bäckerei {n}", "{n} Consulting UG (haftungsbeschränkt)", "Praxis Dr. {n}",
         "{n} Logistik GmbH & Co. KG", "Ristorante Da {v}", "{n} Immobilienverwaltung GbR", "Friseursalon {v}", "MediTech {n} AG", "{n} Bau"]
ORT = [("Dortmund", "44137"), ("Castrop-Rauxel", "44575"), ("Unna", "59423"), ("Bad Salzuflen", "32105"), ("Lüdenscheid", "58507"), ("Gelsenkirchen", "45879"),
       ("Hamm", "59065"), ("Witten", "58452"), ("Schwerte", "58239"), ("Iserlohn", "58636"), ("Garmisch-Partenkirchen", "82467"), ("Wanne-Eickel", "44649")]
STR = ["Hohe Straße", "Am Kattenbusch", "Rheinlanddamm", "Zum Mühlenteich", "Kaiserstraße", "An der Palmweide", "Märkische Straße", "Brackeler Hellweg"]
FORM = ["E-Mail des Mandanten an die Kanzlei", "Telefonnotiz der Kanzleimitarbeiterin", "förmlicher Brief des Mandanten", "interner Aktenvermerk des Steuerberaters",
        "WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern", "Schreiben des Finanzamts (Anhörung) an den Mandanten"]
THEMA = ["Entnahme eines Firmenwagens", "Verkauf einer vermieteten Wohnung", "verdeckte Gewinnausschüttung", "innergemeinschaftliche Lieferung", "häusliches Arbeitszimmer",
         "Schenkung eines GmbH-Anteils an die Tochter", "Umsatzsteuer-Sonderprüfung", "Kleinunternehmerregelung", "Lohnsteuer-Außenprüfung", "Erbschaft eines Mietshauses",
         "Bewirtungskosten und Geschenke", "Rückstellung für Prozesskosten", "Investitionsabzugsbetrag", "Betriebsaufgabe wegen Krankheit", "Reverse-Charge bei Bauleistungen"]


def invent(rnd):
    v, n = rnd.choice(VOR), rnd.choice(NACH)
    v2, n2 = rnd.choice(VOR), rnd.choice(NACH)
    ort, plz = rnd.choice(ORT)
    iban = "DE" + "".join(rnd.choice("0123456789") for _ in range(20))
    iban = rnd.choice([iban, " ".join(iban[i:i + 4] for i in range(0, 22, 4))])
    mail = f"{v.split()[0].lower()}.{re.sub('[^a-z]', '', n.lower().replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss'))}@{rnd.choice(['gmx.de', 't-online.de', 'web.de'])}"
    return {
        "person": f"{v} {n}", "person2": f"{v2} {n2}", "firma": rnd.choice(FIRMA).format(n=n2, v=v2.split()[0]),
        "adresse": f"{rnd.choice(STR)} {rnd.randint(1, 240)}{rnd.choice(['', '', 'a', 'b'])}", "plz_ort": f"{plz} {ort}",
        "iban": iban, "steuernummer": f"{rnd.randint(300, 399)}/{rnd.randint(5000, 5999)}/{rnd.randint(1000, 9999)}",
        "ust_id": "DE" + "".join(rnd.choice("0123456789") for _ in range(9)),
        "steuer_id": " ".join(["".join(rnd.choice("0123456789") for _ in range(k)) for k in (2, 3, 3, 3)]),
        "geburtsdatum": f"{rnd.randint(1, 28):02d}.{rnd.randint(1, 12):02d}.{rnd.randint(1948, 1999)}",
        "telefon": rnd.choice([f"0231 {rnd.randint(100000, 999999)}", f"+49 17{rnd.randint(0, 9)} {rnd.randint(1000000, 9999999)}", f"0{rnd.randint(2301, 2389)}/{rnd.randint(10000, 99999)}"]),
        "email": mail, "kennzeichen": f"{rnd.choice(['DO', 'UN', 'HAM', 'EN', 'MK'])}-{rnd.choice('ABCDEFGHKLM')}{rnd.choice('NPRSTUVW')} {rnd.randint(100, 9999)}",
        "betrag": f"{rnd.randint(3, 480)}.{rnd.randint(100, 999)},{rnd.randint(10, 99)} €",
        "datum": f"{rnd.randint(1, 28):02d}.{rnd.randint(1, 12):02d}.{rnd.randint(2023, 2026)}",
    }


def invent2(rnd):
    """Отложенная проверка: ДРУГИЕ форматы записи, которых не было при настройке правил."""
    d = invent(rnd)
    digits = lambda k: "".join(rnd.choice("0123456789") for _ in range(k))  # noqa: E731
    d["telefon"] = rnd.choice([f"(0231) {digits(2)} {digits(2)} {digits(2)}", f"0231-{digits(6)}", f"0049 151 {digits(8)}", f"+49 (0) 2301 {digits(5)}"])
    d["iban"] = rnd.choice([f"NL{digits(2)} INGB {digits(4)} {digits(4)} {digits(2)}", f"AT{digits(2)} {digits(4)} {digits(4)} {digits(4)} {digits(4)}",
                            "DE" + digits(2) + " " + " ".join(digits(4) for _ in range(4)) + " " + digits(2)])
    d["steuernummer"] = rnd.choice([digits(13), f"{digits(3)}/{digits(4)}/{digits(4)}", f"{digits(2)}/{digits(3)}/{digits(5)}"])
    d["kennzeichen"] = rnd.choice([f"DO {rnd.choice('ABCD')}{rnd.choice('XYZ')} {digits(3)}", f"B-{rnd.choice('ABC')} {digits(4)}E", f"HSK-{rnd.choice('KLM')} {digits(2)}"])
    d["adresse"] = rnd.choice([f"Hauptstr. {rnd.randint(1, 99)}", f"Unter den Linden {rnd.randint(1, 80)}", f"Schillerplatz {rnd.randint(1, 30)}", f"Kirchgasse {rnd.randint(1, 60)} c",
                               f"Postfach {digits(2)} {digits(2)} {digits(2)}", f"Gewerbepark Nord {rnd.randint(1, 20)}"])
    mon = rnd.choice(["Januar", "März", "Mai", "August", "Oktober", "Dezember"])
    d["geburtsdatum"] = rnd.choice([f"{rnd.randint(1, 28)}. {mon} {rnd.randint(1950, 1999)}", f"{rnd.randint(1, 28):02d}.{rnd.randint(1, 12):02d}.{rnd.randint(50, 99)}"])
    d["datum"] = rnd.choice([f"{rnd.randint(1, 28)}. {mon} {rnd.randint(2023, 2026)}", f"{rnd.randint(1, 28)}.{rnd.randint(1, 12)}.{rnd.randint(2023, 2026)}"])
    d["person"] = rnd.choice(["Dr. ", "Dipl.-Kfm. ", "", ""]) + d["person"]
    d["betrag"] = rnd.choice([f"{rnd.randint(3, 480)}.{digits(3)} Euro", f"EUR {rnd.randint(3, 480)}.{digits(3)},{digits(2)}", f"{rnd.randint(12, 99)} T€", f"{rnd.randint(3000, 99999)} €"])
    return d


def gemini(prompt):
    key = open(os.path.expanduser("~/.config/leckermath/gemini_key")).read().strip()
    for model in ("gemini-flash-latest", "gemini-flash-lite-latest"):
        for _ in range(3):
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key},
                                  timeout=240, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9}})
                if r.status_code == 200:
                    return "".join(x.get("text", "") for x in r.json()["candidates"][0]["content"]["parts"])
                if r.status_code in (429, 404):
                    break
            except Exception:
                pass
            time.sleep(30)
    return ""


def cmd_make(n=60, holdout=False):
    rnd = random.Random(777 if holdout else 20261002)
    p = D / ("letters_holdout.json" if holdout else "letters.json")
    inv = invent2 if holdout else invent
    letters = json.load(open(p)) if p.exists() else []
    while len(letters) < n:
        batch = [{"id": f"brief_{len(letters) + i + 1:03d}", "form": rnd.choice(FORM), "thema": rnd.choice(THEMA), "pii": inv(rnd)} for i in range(5)]
        prompt = ("Schreibe 5 realistische, FIKTIVE Texte aus dem Alltag einer deutschen Steuerkanzlei (alle Personen und Daten sind erfunden; "
                  "sie dienen als Testmaterial für einen Anonymisierungsfilter). Jeder Text 120–220 Wörter, in der angegebenen Form und zum Thema. "
                  "Baue ALLE angegebenen Daten WÖRTLICH und unverändert ein (gleiche Schreibweise, gleiche Leerzeichen), natürlich im Text verteilt; "
                  "Namen dürfen zusätzlich in gebeugter oder verkürzter Form vorkommen (z. B. »Herr Müller«, »Müllers Wagen«). "
                  "Antwort NUR als JSON-Liste von 5 Objekten {\"id\": ..., \"text\": ...}.\n\n"
                  + json.dumps(batch, ensure_ascii=False, indent=1))
        out = gemini(prompt)
        m = re.search(r"\[.*\]", out, re.S)
        try:
            texts = {x["id"]: x["text"] for x in json.loads(m.group(0))}
        except Exception:
            print("ответ не разобран / квота -- останавливаюсь", flush=True)
            break
        for b in batch:
            t = texts.get(b["id"], "")
            b["pii"] = {k: v for k, v in b["pii"].items() if v in t}    # в проверку -- только то, что реально попало в текст дословно
            if t and len(b["pii"]) >= 6:
                letters.append({**b, "text": t})
        json.dump(letters, open(p, "w"), ensure_ascii=False, indent=1)
        print(f"писем: {len(letters)}", flush=True)
        time.sleep(15)


def cmd_wild(n=40):
    """Независимый набор: данные и их запись придумывает сама модель (форматы мне заранее неизвестны)."""
    p = D / WILD
    letters = json.load(open(p)) if p.exists() else []
    rnd = random.Random(len(letters) + 5 + len(WILD))
    while len(letters) < n:
        forms = [(rnd.choice(FORM), rnd.choice(THEMA)) for _ in range(5)]
        prompt = ("Schreibe 5 realistische, FIKTIVE Texte aus dem Alltag einer deutschen Steuerkanzlei (Testmaterial für einen Anonymisierungsfilter; "
                  "alle Personen und Daten frei erfunden). Je 120–220 Wörter. Jeder Text enthält 10–14 personenbezogene oder identifizierende Angaben "
                  "unterschiedlicher Art (Namen auch ausländischer Herkunft, Firmen, Anschriften, Bank- und Steuerdaten, Kontaktdaten, Geburtsdaten, "
                  "Kennzeichen, Aktenzeichen, Vertrags-/Kunden-/Rechnungsnummern, Grundbuch-/Flurstücksangaben, genaue Beträge und Daten usw.) "
                  "in möglichst VERSCHIEDENEN, auch ungewöhnlichen Schreibweisen, wie sie in echten Schreiben vorkommen. "
                  "Antwort NUR als JSON-Liste von 5 Objekten {\"text\": ..., \"pii\": [{\"art\": ..., \"wert\": <genau so wie im Text>}]}.\n\nFormen und Themen:\n"
                  + "\n".join(f"{i + 1}. {f} — {t}" for i, (f, t) in enumerate(forms)))
        out = gemini(prompt)
        m = re.search(r"\[.*\]", out, re.S)
        try:
            items = json.loads(m.group(0))
        except Exception:
            print("ответ не разобран / квота -- останавливаюсь", flush=True)
            break
        for (f, t), it in zip(forms, items):
            pii = {f"{x['art']}#{i}": x["wert"] for i, x in enumerate(it.get("pii", [])) if isinstance(x.get("wert"), str) and x["wert"] in it["text"]}
            if len(pii) >= 6:
                letters.append({"id": f"wild_{len(letters) + 1:03d}", "form": f, "thema": t, "pii": pii, "text": it["text"]})
        json.dump(letters, open(p, "w"), ensure_ascii=False, indent=1)
        print(f"писем: {len(letters)}", flush=True)
        time.sleep(15)


def cmd_run():
    ns = {}
    if "--v2" not in sys.argv:                       # версия 1 обезличивания живёт в night_run.py; для --v2 он не нужен
        exec(open("night_run.py").read().split('if __name__ == "__main__":')[0], ns)
    wild = "--wild" in sys.argv
    letters = json.load(open(D / (WILD if wild else "letters_holdout.json" if "--holdout" in sys.argv else "letters.json")))
    v2 = "--v2" in sys.argv
    if v2:
        import anonymizer
        lvl = int(sys.argv[sys.argv.index("--level") + 1]) if "--level" in sys.argv else 1
        ns["anonymize_hard"] = lambda t: anonymizer.anonymize(t, lvl)
        ns["outbound_guard"] = lambda t, m: anonymizer.guard(t, m, lvl)
    tot, leak, guard_hit, examples = defaultdict(int), defaultdict(int), 0, []
    leaked_letters = 0
    for b in letters:
        anon, mapping = ns["anonymize_hard"](b["text"])[:2]
        low = anon.lower()
        bad_here = []
        for k, v in b["pii"].items():
            kind = "person" if k.startswith("person") else k.split("#")[0].strip().lower()[:28]
            ident = not re.search(r"betrag|summe|datum|uhrzeit|fläche|kilometer|modell|zeitraum|jahr", kind) or "geburt" in kind
            if "--ident" in sys.argv and not ident:      # считать только данные, указывающие на человека или фирму
                continue
            tot[kind] += 1
            parts = [v] if kind not in ("person",) or wild else [v, v.split()[-1]]          # для лица -- и фамилия отдельно
            if any(x.lower() in low for x in parts) or (kind in ("iban", "steuer_id", "telefon") and re.sub(r"\D", "", v) in re.sub(r"[ /-]", "", anon)):
                leak[kind] += 1
                bad_here.append(f"{kind}: {v}")
        if bad_here:
            leaked_letters += 1
            guard_hit += bool(ns["outbound_guard"](anon, mapping))
            if len(examples) < 12:
                examples.append(f"- {b['id']} ({b['form']}): " + "; ".join(bad_here))
        b["anon"] = anon
    json.dump(letters, open(D / ("letters_anon_v2.json" if v2 else "letters_anon.json"), "w"), ensure_ascii=False, indent=1)
    L = [f"# Проверка обезличивания — {time.strftime('%d.%m.%Y %H:%M')}", "",
         f"Писем: {len(letters)} (придуманные, данные известны заранее). Обезличивание: {'`anonymizer.py` (версия 2)' if v2 else '`anonymize_hard` (версия 1)'}, до любого ИИ.", "",
         "| Вид данных | Всего | Осталось в тексте | Доля утечки |", "|---|---:|---:|---:|"]
    for k in sorted(tot, key=lambda k: -leak[k] / tot[k]):
        L.append(f"| {k} | {tot[k]} | {leak[k]} | {100 * leak[k] / tot[k]:.0f} % |")
    L += ["", f"**Писем хотя бы с одной утечкой: {leaked_letters} из {len(letters)}.** Из них контроль исходящих (`outbound_guard`) остановил бы: {guard_hit}.",
          "", "Примеры утечек:", *examples, "",
          "Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо)."]
    (D / (("REPORT_" + WILD[8:-5] if wild else "REPORT_holdout" if "--holdout" in sys.argv else "REPORT") + ("_v2.md" if v2 else ".md"))).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if sys.argv[1] == "wild":
        cmd_wild(int(sys.argv[2]) if len(sys.argv) > 2 else 40)
    elif sys.argv[1] == "make":
        cmd_make(int(sys.argv[2]) if len(sys.argv) > 2 else 60, holdout="--holdout" in sys.argv)
    else:
        cmd_run()
