#!/usr/bin/env python3
"""Сверка обезличенного пакета с подлинниками на имитации дела (16.10.2026). Только локально, без сети.
Эталон берётся из подлинников кодом: структурные поля таблиц (владелец счёта, контрагент, IBAN, клиент, адрес, e-mail)
и образцы по всем текстам (IBAN, Steuernummer, USt-IdNr, VIN, номер машины, e-mail, телефон, координаты, имя налогоплательщика).
Затем ищет каждое значение в austausch.json (без учёта регистра и пробелов).
На экран -- только числа по видам; сами остатки -> <дело>/../<имя>_reste.tsv (папка 700).
    python3 anon_echtpruef.py <папка копии дела> [--name "Имя;Фамилия"]"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

case = Path(sys.argv[1]).expanduser()
extra = sys.argv[sys.argv.index("--name") + 1].split(";") if "--name" in sys.argv else []
aus = (case / "_pipeline" / "austausch.json").read_text(encoding="utf-8")
norm = lambda s: re.sub(r"\s+", "", s).lower()
AUS = norm(aus)

gold = defaultdict(set)
FELD = {"Account Holder Name": "person_firma", "Counterparty Name": "person_firma", "Counterparty Account": "iban_konto",
        "Account Number": "iban_konto", "Client Name": "firma", "VAT Number": "ust_id", "Street Name And Number": "adresse",
        "E-mail": "email", "Supplier Name": "lieferant", "Name/Adresse (ausfüllen)": "adresse", "Koord.": "koordinaten",
        "Von Koord.": "koordinaten", "Nach Koord.": "koordinaten", "Geschäftspartner (ausfüllen)": "person_firma"}
GOLD = Path(sys.argv[sys.argv.index("--gold") + 1]).expanduser() if "--gold" in sys.argv else case
for f in GOLD.glob("*.csv"):
    for row in csv.DictReader(open(f, encoding="utf-8")):
        for k, art in FELD.items():
            v = (row.get(k) or "").strip()
            if len(v) >= 4 and not re.fullmatch(r"[\d.,\- ]+", v) or art in ("iban_konto", "koordinaten") and len(v) >= 6:
                gold[art].add(v)
MUSTER = {"iban_konto": r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b",
          "steuernummer": r"\b\d{3}/\d{4}/\d{4}\b|\b3\d{10}\b|\b\d{2,3}/\d{3}/\d{5}\b",
          "ust_id": r"\bDE ?\d{9}\b", "vin": r"\b[A-HJ-NPR-Z0-9]{17}\b", "kennzeichen": r"\b[A-ZÄÖÜ]{1,3}[- ][A-Z]{1,2} ?\d{1,4}[EH]?\b",
          "email": r"[\w.+-]+@[\w-]+\.[\w.]+", "telefon": r"(?:\+|00)\d{2}[\d /-]{7,}\d",
          "koordinaten": r"\b\d{1,2}\.\d{4,},\s*\d{1,2}\.\d{4,}\b"}
for f in list(case.iterdir()) + list(GOLD.glob("*.csv")):
    if f.suffix.lower() in (".csv", ".md", ".txt"):
        t = f.read_text(encoding="utf-8", errors="ignore")
    elif f.suffix.lower() == ".pdf":
        import subprocess
        t = subprocess.run(["pdftotext", "-layout", str(f), "-"], capture_output=True, text=True).stdout
    else:
        continue
    for art, m in MUSTER.items():
        for x in re.findall(m, t):
            if art == "vin" and not (re.search(r"\d", x) and re.search(r"[A-Z]", x)):
                continue
            gold[art].add(x.strip())
for n in extra:
    gold["name_stpfl"].add(n)

out = open(case.parent / f"{case.name}_reste.tsv", "w", encoding="utf-8")
print(f"{'вид':14} {'эталон':>7} {'осталось':>8}")
tot_g = tot_r = 0
for art in sorted(gold):
    vals = {v for v in gold[art] if len(norm(v)) >= 4}
    rest = sorted(v for v in vals if norm(v) in AUS)
    for v in rest:
        out.write(f"{art}\t{v}\n")
    print(f"{art:14} {len(vals):7} {len(rest):8}")
    tot_g += len(vals)
    tot_r += len(rest)
print(f"{'всего':14} {tot_g:7} {tot_r:8}  -> остатки: {out.name}")
