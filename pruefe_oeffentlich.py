#!/usr/bin/env python3
"""
pruefe_oeffentlich.py -- проверка папки перед публикацией: нет ли в ней примет имитаций дел, ключей, личных путей и почты.

Только чтение, только локально. В отчёт значения НЕ пишутся -- только файл, строка и вид находки (сам отчёт можно показывать).
Что ищется:
  1. запрещённое по списку ~/.config/leckermath/repo_blocklist.txt (ключи, имена из имитаций дел) -- тот же список, что в make_repo.sh;
  2. значения из ключей обезличивания имитаций дел (mapping_dossier.json): имена, адреса, номера, которые программа сама заменяла масками;
     короткие и словарные значения пропускаются, чтобы не было ложных срабатываний на обычные слова;
  3. личные пути (/home/<имя>/, C:\\Users\\<имя>\\) и адреса электронной почты (кроме noreply и примеров);
  4. похожее на ключ доступа (длинные строки после слов key, token, secret; заголовки закрытых ключей).

  python3 pruefe_oeffentlich.py <папка> [--fall <папка дела> ...] [--out отчёт.md]
Код возврата 1, если есть находки видов 1, 2 или 4 (они останавливают публикацию); личные пути и почта -- предупреждение.
"""
import json
import re
import sys
from pathlib import Path

TEXT_ENDUNG = {".py", ".md", ".txt", ".sh", ".json", ".jsonl", ".tsv", ".csv", ".html", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".sql", ""}
RX_PFAD = re.compile(r"/home/[a-z][\w.-]+/|[A-Z]:\\Users\\[\w.-]+\\")
RX_MAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
MAIL_OK = re.compile(r"(?i)noreply|example\.|beispiel|muster|test@|@users\.noreply")
RX_KEY = re.compile(r"(?i)(?:api[_-]?key|token|secret|passwor[dt])\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9]{20,}|\bhf_[A-Za-z0-9]{20,}|\bAIza[0-9A-Za-z_\-]{30,}")


def fall_werte(faelle):
    """Значения имитаций дел. Два уровня: твёрдые -- подтверждённые лица и организации (реестр figuranten.json с отметкой «sicher»,
    состав, заданный аудитором) и длинные номера из ключа; мягкие -- прочие значения ключа обезличивания (среди них много обычных слов,
    принятых программой за имена: проверка 09.10.2026 дала 18 таких значений в собственном коде). Значения в отчёт не идут.
    -> (твёрдые шаблоны, мягкие шаблоны)"""
    hart, weich = set(), set()
    for fall in faelle:
        P = Path(fall).expanduser() / "_pipeline"
        rf = P / "figuranten.json"
        if rf.exists():
            for r in json.load(open(rf, encoding="utf-8")):
                if r.get("sicher"):
                    hart |= {str(v).strip() for v in [r.get("name")] + list(r.get("varianten", [])) if v}
        vf = P / "AKTEURE_VORGABE.txt"
        if vf.exists():                                  # строки состава: маска | роль | написания через «;»
            for ln in vf.read_text(encoding="utf-8").split("\n"):
                # 19.10.2026: комментарий после «#» -- текст шаблона программы, не написания (давал ложные находки в exchange.py);
                # «---» и метки масок («Person 5», «Kanzlei 2») -- тоже не значения дела
                ln = ln.split("#", 1)[0]
                t = [x.strip() for x in ln.split("|")]
                if len(t) >= 3:
                    hart |= {v.strip() for v in re.split(r"[;,]", t[-1]) if v.strip() and v.strip() != "---"
                             and not re.fullmatch(r"\[?[A-Za-zÄÖÜäöüß-]+ \d+\]?", v.strip())}
        for f in P.glob("mapping*.json"):
            try:
                d = json.load(open(f, encoding="utf-8"))
            except Exception:                            # noqa: BLE001
                continue
            for v in (d.values() if isinstance(d, dict) else []):
                v = str(v or "").strip()
                if len(re.sub(r"\D", "", v)) >= 7 and not re.fullmatch(r"[\d.,\s€%-]+", v) or re.fullmatch(r"[A-Z]{2}\d{2}[\dA-Z ]{10,}|\d{9,}", v):
                    hart.add(v)                          # номера: IBAN, налоговые и страховые номера, телефоны
                elif len(v) >= 8:
                    weich.add(v)
    hart = {v for v in hart if len(v) >= 5 and not v.lower().startswith("gesprächspartner")}
    # 19.10.2026: одно обычное слово, вписанное в состав участников («Steuer», «Hinweis», «человек»), -- предупреждение, а не стоп:
    # слово есть в словаре текстов законов (de) либо пишется только строчными кириллицей; имя автора открытой копии -- не находка
    import gzip
    wl = Path(__file__).resolve().parent / "de_wortliste_gesetz.txt.gz"
    gesetz = {w.lower() for w in gzip.open(wl, "rt", encoding="utf-8").read().split("\n")} if wl.exists() else set()
    gemein = {v for v in hart if " " not in v and (v.lower() in gesetz or v.lower() in {"якорь", "человек", "выгрузка"})}
    hart = hart - gemein - {"Sergei Sevriukov"}
    weich |= gemein
    weich -= hart
    rx = lambda vs: [re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)", re.I) for v in sorted(vs, key=len, reverse=True)]     # noqa: E731
    return rx(hart), rx(weich)


def pruefe(ordner, faelle=()):
    ordner = Path(ordner).expanduser()
    bl = Path("~/.config/leckermath/repo_blocklist.txt").expanduser()
    block = [re.compile(z.strip()) for z in bl.read_text(encoding="utf-8").split("\n") if z.strip() and not z.startswith("#")] if bl.exists() else []
    werte, weich = fall_werte(faelle)
    funde = []                                           # (вид, файл, строка)
    n_dat = 0
    for f in sorted(ordner.rglob("*")):
        if not f.is_file() or ".git" in f.parts or "__pycache__" in f.parts or f.suffix.lower() not in TEXT_ENDUNG or f.stat().st_size > 5_000_000:
            continue
        try:
            zeilen = f.read_text(encoding="utf-8").split("\n")
        except Exception:                                # noqa: BLE001  (двоичный файл)
            continue
        n_dat += 1
        rel = str(f.relative_to(ordner))
        for k, z in enumerate(zeilen, 1):
            if len(z) > 4000:
                z = z[:4000]
            if any(b.search(z) for b in block):
                funde.append(("запрещённое по списку", rel, k))
            if werte and any(w.search(z) for w in werte):
                funde.append(("значение из ключа имитации дела", rel, k))
            elif weich and any(w.search(z) for w in weich):
                funde.append(("возможно: слово из ключа дела (чаще обычное слово, просмотреть)", rel, k))
            if RX_KEY.search(z):
                funde.append(("похоже на ключ доступа", rel, k))
            if RX_PFAD.search(z):
                funde.append(("личный путь", rel, k))
            if any(not MAIL_OK.search(m) for m in RX_MAIL.findall(z)):
                funde.append(("адрес почты", rel, k))
    return funde, n_dat, len(block), len(werte) + len(weich)


def main():
    arg = sys.argv[1:]
    faelle = [arg[k + 1] for k, a in enumerate(arg) if a == "--fall"]
    out = Path(arg[arg.index("--out") + 1]).expanduser() if "--out" in arg else None
    funde, n_dat, n_bl, n_w = pruefe(arg[0], faelle)
    hart = [f for f in funde if f[0] in ("запрещённое по списку", "значение из ключа имитации дела", "похоже на ключ доступа")]
    L = [f"# Проверка папки перед публикацией: {Path(arg[0]).name}", "",
         f"Файлов прочитано: {n_dat}. Шаблонов запрещённого: {n_bl}. Значений из ключей имитаций дел: {n_w} (дел: {len(faelle)}).",
         f"Находок, останавливающих публикацию: {len(hart)}. Предупреждений (возможные слова из ключа, личные пути, почта): {len(funde) - len(hart)}.",
         "Значения в отчёт не пишутся -- только место.", ""]
    for art in ("запрещённое по списку", "значение из ключа имитации дела", "похоже на ключ доступа", "возможно: слово из ключа дела (чаще обычное слово, просмотреть)", "личный путь", "адрес почты"):
        orte = [(d, k) for a, d, k in funde if a == art]
        if orte:
            dateien = {}
            for d, k in orte:
                dateien.setdefault(d, []).append(k)
            L += [f"## {art}: {len(orte)} строк в {len(dateien)} файлах", ""]
            L += [f"- {d}: строки {', '.join(map(str, ks[:12]))}{' …' if len(ks) > 12 else ''}" for d, ks in sorted(dateien.items(), key=lambda x: -len(x[1]))[:60]]
            L.append("")
    text = "\n".join(L) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
        print("\n".join(L[:5]) + f"\nотчёт: {out}")
    else:
        print(text)
    sys.exit(1 if hart else 0)


if __name__ == "__main__":
    main()
