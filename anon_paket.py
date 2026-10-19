#!/usr/bin/env python3
"""
anon_paket.py -- «папка с подлинными материалами -> один обезличенный JSON + ключ + лист проверки», всё локально (08.10.2026).

Зачем: внешняя модель (в том числе сессия Claude Code) не должна видеть подлинные документы.
Кто запускает шаг 1: обработчик в отдельном терминале ЛИБО сессия-агент по его прямому указанию -- на экран выходят только
числа и пути, содержимое документов и вывод шагов идут в журнал в папке дела. Лист проверки читает и код передачи вводит
ТОЛЬКО человек (шаг 2). Сеть не используется: модели берутся из локального кэша (HF_HUB_OFFLINE=1), внешние модели не вызываются.
Что меняется в папке дела: создаётся/обновляется _pipeline/ (права 700) и дописывается _analyse/voice_messages.txt.

  Шаг 1 (сборка):     python3 anon_paket.py <папка дела> [--frage "вопрос по делу"] [--genau] [--neu-lesen]
     (--genau: большая модель речи, медленнее; --neu-lesen: распознать сканы и фото заново)
     голосовые (.ogg .opus .mp3 .m4a .wav)      -> расшифровка локально (faster-whisper)
     тексты (.txt .md .docx .html .eml .rtf)    -> как есть
     PDF, сканы, фото                           -> текст и распознавание (pipeline_case.py ingest)
     переписка WhatsApp (zip с _chat.txt)       -> реестр участников и протокол (figuranten.py, protokoll.py)
     всё вместе                                 -> обезличивание -> <дело>/_pipeline/austausch.json (один JSON),
                                                   ключ <дело>/_pipeline/schluessel.json, лист проверки PRUEFBLATT.md
     В конце печатается КОД текста. Обработчик читает PRUEFBLATT.md и исправляет пропуски.

  Если контроль нашёл остатки (в листе проверки -- раздел «Автоматический контроль»), человек в своём терминале:
     python3 anon_paket.py <папка дела> --merke "слово1;слово2" [--art Person|Firma|Ort|Nummer]   -- запомнить пропущенное
     и повторить шаг 1 (распознавание и расшифровка повторно не делаются). Ложное срабатывание -- см. --trotzdem.

  Шаг 2 (передача):   python3 anon_paket.py <папка дела> --freigabe <КОД> [--trotzdem]
     Только если код совпадает с текущим текстом: копирует austausch.json и dossier_anon.md
     в папку передачи ~/Documents/uebergabe/<КОД>/ (в названии нет имени клиента). Ключ и подлинники не копируются.

Ключ (schluessel.json), реестр участников и лист проверки остаются в папке дела.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import versteckt  # noqa: E402  (19.10.2026: скрытое содержимое файлов)

HERE = Path(__file__).resolve().parent
AUDIO = (".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac")
TEXT = (".txt", ".md", ".html", ".htm", ".eml", ".rtf", ".csv")
SKIP_DIRS = {"_pipeline", "_analyse", "_uebergabe"}
FRAGE = ("Was ist hier geschehen, welche Risiken und Fristen bestehen, und welche Fragen sind zu klären?")


SKIP_FILES = {"CLAUDE.md", "README.md", "LIESMICH.md"}


# xlsx_text / docx_text -- в versteckt.py (19.10.2026: скрытые листы, удалённые правки, скрытый текст)


def files(case, exts):
    """Служебные папки (начинаются с «_» или «.») и служебные файлы в материалы дела не входят."""
    return [f for f in sorted(case.rglob("*")) if f.is_file() and f.suffix.lower() in exts and f.name not in SKIP_FILES
            and not any(p.startswith(("_", ".")) for p in f.relative_to(case).parts[:-1])]


def safe(case, f):
    return re.sub(r"[^\w.-]+", "_", str(f.relative_to(case)))


def step_voice(case, docs):
    au = files(case, AUDIO)
    docs = docs.parent / "roh"
    docs.mkdir(exist_ok=True)
    todo = [f for f in au if not (docs / (safe(case, f) + ".txt")).exists()]
    if not todo:
        return len(au), 0
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from faster_whisper import WhisperModel
    model = None
    # на этих видеокартах (Quadro M4000) распознавание речи не запускается (ошибка CUDA в ctranslate2) -- только процессор
    for name, dev, ct in ((("large-v3", "cpu", "int8"),) if "--genau" in sys.argv else ()) + (("medium", "cpu", "int8"),):
        try:
            model = WhisperModel(name, device=dev, compute_type=ct)
            print(f"  распознавание речи: {name} на {dev}", flush=True)
            break
        except Exception as e:                                  # нет памяти на карте и т. п. -- следующий вариант
            print(f"  [{name}/{dev} недоступно: {str(e)[:60]}]", flush=True)
    an = case / "_analyse"
    an.mkdir(exist_ok=True)
    vm = an / "voice_messages.txt"
    schon = vm.read_text(encoding="utf-8") if vm.exists() else ""
    with open(vm, "a", encoding="utf-8") as vf:
        for k, f in enumerate(todo, 1):
            segs, info = model.transcribe(str(f), vad_filter=True, beam_size=5)
            text = " ".join(s.text.strip() for s in segs).strip()
            (docs / (safe(case, f) + ".txt")).write_text(f"Sprachnachricht ({f.name}), Sprache: {info.language}\n{text}\n", encoding="utf-8")
            if f.name not in schon:                                            # уже расшифрованное ранее не дублировать
                vf.write(f"===== {f.name} [{info.language}]\n{text}\n\n")       # формат, который читает protokoll.py
            print(f"  голосовое {k}/{len(todo)}: {len(text)} знаков", flush=True)
    return len(au), len(todo)


def step_text(case, docs):
    n = 0
    docs = docs.parent / "roh"
    docs.mkdir(exist_ok=True)
    for f in files(case, TEXT + (".docx", ".xlsx", ".xlsm")):
        if f.name == "_chat.txt":                                  # переписка -- через protokoll.py
            continue
        dst = docs / (safe(case, f) + ".txt")
        if dst.exists():
            continue
        try:
            # 19.10.2026 (versteckt.py): DOCX без удалённых правок и скрытого текста, XLSX с пометкой скрытых листов/строк, EML без служебных заголовков
            sfx = f.suffix.lower()
            t = (versteckt.docx_text(f) if sfx == ".docx" else versteckt.xlsx_text(f) if sfx in (".xlsx", ".xlsm") else versteckt.eml_text(f) if sfx == ".eml"
                 else f.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            print(f"  [!] не прочитан текстовый файл № {n + 1}: {str(e)[:60]}")
            continue
        if f.suffix.lower() in (".html", ".htm"):
            t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
            t = re.sub(r"<[^>]+>", "\n", t)
        if len(t.strip()) >= 20:
            dst.write_text(t, encoding="utf-8")
            n += 1
    versteckt.speichern(docs.parent)
    return n


KURZ = 400          # обменный лист отбрасывает документы короче ~300 знаков: короткие заметки и голосовые собираются в один документ
KOPF = ("Sammlung kurzer Notizen und Sprachnachrichten aus den Unterlagen des Falles. Jeder Abschnitt ist eine eigene Notiz oder Nachricht; "
        "es handelt sich um Aussagen der Beteiligten, nicht um belegte Tatsachen. Die Reihenfolge entspricht den Dateinamen.")


def aufraeumen(case, docs):
    """Промежуточный текст документа, подлинник которого убран из папки дела, удаляется (имитация дела Б 16.10.2026: файл, исключённый из дела,
    продолжал попадать в лист из кэша roh/ и docs/). Удаляются только файлы вида «<имя подлинника>.<расширение>.txt»; сборные и служебные остаются."""
    ext = AUDIO + TEXT + (".docx", ".xlsx", ".xlsm", ".pdf", ".jpg", ".jpeg", ".png")
    da = {safe(case, f) + ".txt" for f in files(case, ext)}
    n = 0
    for d in (docs.parent / "roh", docs):
        if not d.exists():
            continue
        for f in list(d.glob("*.txt")):
            if f.name not in da and any(f.name.lower().endswith(e + ".txt") for e in ext):
                f.unlink()
                n += 1
                j = f.with_name(f.name + ".ocr.json")
                if j.exists():
                    j.unlink()
    return n


def step_merge(docs):
    roh = docs.parent / "roh"
    kurz, n_lang, n_leer = [], 0, 0
    for f in sorted(roh.glob("*.txt")):
        t = f.read_text(encoding="utf-8")
        body = t.split("\n", 1)[1] if t.startswith("Sprachnachricht (") and "\n" in t else t
        if len(body.strip()) < 3:
            n_leer += 1
        elif len(t) >= KURZ:
            (docs / f.name).write_text(t, encoding="utf-8")
            n_lang += 1
        else:
            kurz.append(f"--- Notiz {len(kurz) + 1} ---\n{t.strip()}")
    target = docs / "kurze_notizen_und_sprachnachrichten.txt"
    if kurz:
        target.write_text(KOPF + "\n\n" + "\n\n".join(kurz) + "\n", encoding="utf-8")
    else:
        target.unlink(missing_ok=True)
    return n_lang, len(kurz), n_leer


LOG = None       # вывод шагов -- в <дело>/_pipeline/anon_paket.log; на экран только числа: в выводе шагов бывают имена файлов и обрывки текста


def run(*args):
    r = subprocess.run([sys.executable, *args], cwd=HERE, capture_output=True, text=True, env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "LM_DOC_LIMIT": os.environ.get("LM_DOC_LIMIT", "400000"), "LM_PROTO_LIMIT": "6000"})   # документы целиком, не первые 9000 знаков
    if LOG:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== {time.strftime('%F %T')} {' '.join(args[:1])} -> {r.returncode}\n{r.stdout}\n{r.stderr}\n")
    return r.returncode, (r.stdout + r.stderr)


def build(case, frage):
    P = case / "_pipeline"
    docs = P / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    if "--einleitung" in sys.argv:                           # вводная аудитора из любого файла (свой текст, свои заголовки)
        src = Path(sys.argv[sys.argv.index("--einleitung") + 1]).expanduser()
        alt = (P / "EINLEITUNG.txt").read_text(encoding="utf-8") if (P / "EINLEITUNG.txt").exists() else ""
        runden = alt[alt.find("\nRUNDE "):] if "\nRUNDE " in alt else ""
        (P / "EINLEITUNG.txt").write_text(src.read_text(encoding="utf-8").strip() + "\n" + runden, encoding="utf-8")
        os.chmod(P / "EINLEITUNG.txt", 0o600)
        print(f"0. вводная аудитора взята из файла {src.name} (прежние круги ответов сохранены)")
    os.chmod(P, 0o700)
    global LOG
    LOG = P / "anon_paket.log"
    t0 = time.time()
    weg = aufraeumen(case, docs)
    if weg:
        print(f"0. из промежуточных файлов убрано {weg}: их подлинников в папке дела больше нет", flush=True)
    print("1. голосовые сообщения", flush=True)
    na, nn = step_voice(case, docs)
    print(f"   всего {na}, расшифровано сейчас {nn}")
    print("2. текстовые файлы", flush=True)
    print(f"   добавлено {step_text(case, docs)}")
    n_lang, n_kurz, n_leer = step_merge(docs)
    print(f"   отдельными документами {n_lang}; коротких, собранных в один документ, {n_kurz}; пустых (без речи или текста) {n_leer}")
    print("3. PDF, сканы, фото (распознавание может идти долго)", flush=True)
    if "--neu-lesen" in sys.argv:                                 # распознать сканы и фото заново; «--neu-lesen 9,13» -- только тексты с этими номерами
        k = sys.argv.index("--neu-lesen")
        nur = {int(x) for x in sys.argv[k + 1].split(",")} if len(sys.argv) > k + 1 and re.fullmatch(r"[\d,]+", sys.argv[k + 1]) else None
        alle = sorted(x.name for x in docs.glob("*.txt"))
        ziel = [f for f in files(case, (".pdf", ".jpg", ".jpeg", ".png")) if nur is None or (safe(case, f) + ".txt") in alle and alle.index(safe(case, f) + ".txt") + 1 in nur]
        print(f"   распознаётся заново файлов: {len(ziel)}; ориентировочно {max(1, round(len(ziel) * 1.3))} мин")
        for f in ziel:
            (docs / (safe(case, f) + ".txt")).unlink(missing_ok=True)
            (docs / (safe(case, f) + ".txt.ocr.json")).unlink(missing_ok=True)
    vorher = {f.name for f in docs.glob("*.txt")}
    code, out = run("pipeline_case.py", str(case), "ingest")
    quellen = files(case, (".pdf", ".jpg", ".jpeg", ".png"))
    neu = len({f.name for f in docs.glob("*.txt")} - vorher)
    print(f"   файлов PDF и изображений: {len(quellen)}; распознано сейчас {neu}, взято из прежнего распознавания {len(quellen) - neu}"
          + ("" if code == 0 else "; ОШИБКА -- см. _pipeline/anon_paket.log"))
    if list(case.rglob("*.zip")):
        print("4. переписка: участники и протокол", flush=True)
        for prog in ("figuranten.py", "protokoll.py"):
            if prog == "protokoll.py" and "--akteure-modell" in sys.argv:      # локальная модель предлагает организации и написания (всё локально; минуты)
                k_ = sys.argv.index("--akteure-modell")
                modell = sys.argv[k_ + 1] if len(sys.argv) > k_ + 1 and not sys.argv[k_ + 1].startswith("--") else "llama3.1:8b-instruct-q8_0"
                print(f"   локальная модель {modell}: шапки и подписи документов (это минуты)…", flush=True)
                c_, o_ = run("eval_akteure_llm.py", str(case), "--modelle", modell, "--wege", "A")
                print("   " + (o_.strip().split("\n")[-1][:150] if c_ == 0 else "ОШИБКА -- см. _pipeline/anon_paket.log"))
            if prog == "protokoll.py":                   # выбор действующих лиц -- до протокола, чтобы маски в нём были те же
                sys.path.insert(0, str(HERE))
                os.environ.setdefault("LM_DOC_LIMIT", "400000")
                import exchange as _ex0
                _ex0.vorschlag(docs)
                mf = Path(sys.argv[sys.argv.index("--meinung") + 1]).expanduser() if "--meinung" in sys.argv else P / "MEINUNG.txt"
                if mf.exists() and ("--meinung" in sys.argv or not (P / "AKTEURE_VORGABE.txt").exists() or mf.stat().st_mtime > (P / "AKTEURE_VORGABE.txt").stat().st_mtime):
                    import diktat                            # мнение аудитора свободным текстом -> файл состава (кодом; прежний файл -- в копию)
                    diktat.meinung(case, mf, "llama3.1:8b-instruct-q8_0", "--mit-modell" in sys.argv)
                    vg = P / "AKTEURE_VORGABE.txt"
                    if vg.exists():
                        shutil.copy2(vg, P / f"AKTEURE_VORGABE.vor_meinung_{time.strftime('%Y%m%d_%H%M%S')}.txt")
                    shutil.copy2(P / "AKTEURE_VORGABE_ENTWURF.txt", vg)
                    print(f"   состав взят из мнения аудитора ({mf.name}); проверьте {vg} -- вопросы секретаря стоят в его конце")
            code, out = run(prog, str(case))
            print(f"   {prog}: {'готово' if code == 0 else 'ОШИБКА -- см. _pipeline/anon_paket.log'}")
    else:
        print("4. переписки (zip с _chat.txt) нет -- пропущено")
    sys.path.insert(0, str(HERE))
    os.environ.setdefault("LM_DOC_LIMIT", "400000")
    import exchange as _ex
    n_haupt, n_zeilen, n_neu = _ex.vorschlag(docs)             # диалог с обработчиком: найденные лица -> он выбирает основных и проверяет роли
    print(f"   действующие лица: найдено {n_zeilen}, основными отмечено {n_haupt}" + (f", новых с прошлой сборки {n_neu}" if n_neu else "")
          + f"\n   <- ПРОВЕРИТЬ И ПОПРАВИТЬ (только для вас, с подлинными именами): {P / 'AKTEURE_VORGABE.txt'}; после правки повторить сборку")
    if frage or not (P / "frage.txt").exists():
        (P / "frage.txt").write_text(frage or FRAGE, encoding="utf-8")
    print("5. обезличивание и обменный лист", flush=True)
    code, out = run("pipeline_case.py", str(case), "exchange")
    if code != 0:
        raise SystemExit("ОШИБКА на шаге обезличивания -- см. _pipeline/anon_paket.log")
    erste = out.strip().split("\n")[0]
    print("   " + re.sub(r"; код \w+", "", erste.split("; схема:")[0]) + ("; схема: в порядке" if "схема: в порядке" in erste else "; схема: ОШИБКА"))
    if "схема: в порядке" not in erste:
        sch = erste.split("схема:")[-1].split("; код")[0].strip()
        raise SystemExit("ОШИБКА: обменный лист не соответствует схеме -- лист НЕ готов, передавать нельзя.\n  " + sch +
                         "\n  Это ошибка программы, а не материалов: сообщите текст этой ошибки в сессию Gesetz.")
    code, out = run("pipeline_case.py", str(case), "review")
    m = re.search(r"код текста: (\S+)", out)
    stop = "ОСТАНОВЛЕНО" in out
    n_docs = len(list(docs.glob("*.txt")))
    n_json = sum(1 for d in json.load(open(P / "austausch.json", encoding="utf-8"))["documents"] if not d["kind"].startswith("Gesprächsprotokoll"))
    print(f"\nГотово за {round((time.time() - t0) / 60, 1)} мин. Текстов в деле: {n_docs}, вошло в JSON: {n_json}.")
    if n_json < n_docs:
        print(f"  ВНИМАНИЕ: {n_docs - n_json} текст(ов) не вошли в JSON. Причины (без имён файлов; порядок -- по алфавиту имён в _pipeline/docs):")
        sys.path.insert(0, str(HERE))
        os.environ.setdefault("LM_DOC_LIMIT", "400000")
        import exchange
        gesehen = set()
        for nr, f in enumerate(sorted(docs.glob("*.txt")), 1):
            roh_t = f.read_text(encoding="utf-8")
            sauber = exchange.clean(exchange.fix_ocr(roh_t))
            art = (re.search(r"\.(pdf|jpe?g|png|ogg|opus|mp3|m4a|wav|md|docx|txt|html?|eml)\.txt$", f.name.lower()) or [None, "текст"])[1]
            schl = re.sub(r"[^a-zäöüа-яё]+", "", sauber.lower())
            schl = schl[300:420] if len(schl) >= 420 else schl
            if len(sauber) < 300:
                print(f"    текст № {nr} ({art}): распознано {len(roh_t)} знаков, после очистки {len(sauber)} -- слишком мало читаемого текста")
            elif schl in gesehen:
                print(f"    текст № {nr} ({art}): {len(sauber)} знаков -- повтор другого документа (тот же текст)")
            gesehen.add(schl)
    print(f"  обезличенный JSON:  {P / 'austausch.json'}")
    print(f"  ключ (не передавать): {P / 'schluessel.json'}")
    print(f"  лист проверки:      {P / 'PRUEFBLATT.md'}   <- ПРОЧИТАТЬ")
    n_rest = 0
    for line in (P / "PRUEFBLATT.md").read_text(encoding="utf-8").split("\n"):
        if line.startswith("ОСТАНОВЛЕНО:"):
            n_rest = len([x for x in line[len("ОСТАНОВЛЕНО:"):].split(";") if x.strip()])
    print(f"  автоматический контроль: {'НАШЁЛ ОСТАТКИ: ' + str(n_rest) + ' -- список в листе проверки, раздел «Автоматический контроль»' if stop else 'остатков по списку замен не нашёл'}")
    sys.path.insert(0, str(HERE))
    import anonymizer as _an
    mk = _an.merkmale((P / "dossier_anon.md").read_text(encoding="utf-8"))               # вторая ступень: признаки, не зависящие от списка замен
    print("  контроль по признакам: " + ("чисто" if not mk else "; ".join(f"{k}: {v}" for k, v in mk.items()) + " -- посмотреть в листе проверки:"))
    for name_, dok_, seite_ in _an.merkmale_orte((P / "dossier_anon.md").read_text(encoding="utf-8"))[:20]:
        print(f"      {name_}: документ {dok_ or '— (до первого документа: вводная, перечень, переписка)'}" + (f", страница {seite_}" if seite_ else ""))
    kyr = sum(len(re.findall(r"[А-Яа-яЁё]", f.read_text(encoding="utf-8"))) for f in docs.glob("*.txt"))
    if kyr > 200:
        print(f"  ВНИМАНИЕ: в документах есть русский текст ({kyr} букв). Русские имена убираются моделью, правилами (обращения, отчества, падежи), реестром участников и запомненными словами; на настоящих документах это проверено мало -- русские места в листе читайте особенно внимательно.")
    # отчёт сборки без значений: что прочитано, насколько, прошла ли самопроверка таблиц, сколько остатков нашёл контроль
    sheet = json.load(open(P / "austausch.json", encoding="utf-8"))
    L = [f"# Отчёт сборки обезличенного пакета ({time.strftime('%d.%m.%Y %H:%M')})", "",
         f"Текстов в деле: {n_docs}; вошло в лист: {n_json}; время сборки: {round((time.time() - t0) / 60, 1)} мин; остатков по контролю: {n_rest}; "
         f"замен: {len(json.load(open(P / 'mapping_dossier.json', encoding='utf-8')))}.", "",
         "| № | Вид документа | Кто выдал | Страниц | Читаемость | Таблицы: строк / самопроверка | Знаков текста |", "|---:|---|---|---:|---:|---|---:|"]
    for d in sheet["documents"]:
        tb = []
        for t in d.get("tables", []):
            probe = [r[-1] for r in t["rows"] if r and r[-1] in ("ja", "nein")]
            tb.append(f"{t['name']}: {len(t['rows'])}" + (f" / сходится {probe.count('ja')} из {len(probe)}" if probe else (" / контрольная сумма есть" if t.get("control_sum") is not None else "")))
        L.append(f"| {d['nr']} | {d['kind'][:60]} | {d['issuer_role']} | {d['pages']} | {int(100 * d['ocr_quality'])} % | {'; '.join(tb) or '—'} | {len(d['text'])} |")
    # документ вошёл не целиком: меток страниц в тексте листа меньше, чем страниц в документе (имитация дела А 11.10.2026: три документа молча вошли одной страницей)
    kurz = [(d["nr"], d["pages"], d["text"].count("--- Seite"), len(d["text"])) for d in sheet["documents"]
            if d["pages"] > 1 and d["text"].count("--- Seite") < d["pages"] and d["text"] != "(siehe Tabelle)"]
    if kurz:
        L += ["", f"**ВНИМАНИЕ: {len(kurz)} документ(ов) вошли в лист не целиком** (страницы убраны как нечитаемые или пустые, либо текст обрезан):", ""]
        L += [f"- № {nr}: страниц в документе {pg}, в листе {max(1, mk)}; знаков текста {zn}" for nr, pg, mk, zn in kurz]
        print(f"  ВНИМАНИЕ: документов, вошедших в лист не целиком: {len(kurz)} (№ " + ", ".join(str(k[0]) for k in kurz) + ") -- см. отчёт сборки")
    nf = P / "annahme_namensrest.json"
    nrest = json.load(open(nf, encoding="utf-8")) if nf.exists() else {}
    if nrest:
        L += ["", "**Третья ступень контроля: удержаны места с возможным остатком имени** (строка или ячейка заменена пометкой «zurückgehalten – möglicher Namensrest»): "
              + ("ошибка проверки: " + str(nrest["fehler"]) if "fehler" in nrest else "; ".join(f"№ {nr} — {n}" for nr, n in sorted(nrest.items(), key=lambda x: -x[1])))
              + ". Обычное слово, принятое за имя, впишите в KEIN_NAME.txt и повторите сборку."]
        print("  третья ступень: " + ("ОШИБКА проверки " + str(nrest["fehler"]) if "fehler" in nrest else f"удержано мест с возможным остатком имени: {sum(nrest.values())} в {len(nrest)} документах") + " -- см. отчёт сборки")
    infos = []
    for f in sorted(docs.glob("*.ocr.json")):
        for k, i in enumerate(json.load(open(f, encoding="utf-8")), 1):
            infos.append(f"- текст № {sorted(x.name for x in docs.glob('*.txt')).index(f.name[:-9]) + 1}, страница {k}: способ {i.get('verfahren', '—')}, поворот {i.get('drehung', '—')}°, "
                         f"оценка {i.get('wertung', '—')}, дат {i.get('daten', '—')}, сумм {i.get('betraege', '—')}" + (f", ошибка: {i['fehler']}" if i.get("fehler") else ""))
    if infos:
        L += ["", "## Распознавание по страницам (только заново распознанные)", ""] + infos
    L += ["", "Значений документов в отчёте нет. Остатки, найденные человеком после одобрения, записываются отдельно (журнал обкатки)."]
    (P / "BERICHT_SBORKA.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  отчёт сборки (без значений): {P / 'BERICHT_SBORKA.md'}")
    import annahme                                                            # протокол приёмки: что принято, что сверить, что переснять
    LA, z = annahme.protokoll(P)
    (P / "ANNAHMEPROTOKOLL.md").write_text("\n".join(LA) + "\n", encoding="utf-8")
    n_ers, n_prf = annahme.fuer_bearbeiter(case)
    print(f"  заменить документов: {n_ers}, сверить отдельные места: {n_prf} -- список с именами файлов (только для вас, моделям не показывать): {P / 'ANNAHME_FUER_BEARBEITER.md'}")
    print(f"  протокол приёмки:   {P / 'ANNAHMEPROTOKOLL.md'}   <- ПРОЧИТАТЬ ПЕРВЫМ: принято {z['принят']}, с оговоркой {z['принят с оговоркой']}, не принято {z['не принят']}")
    with open(P / "PRUEFBLATT.md", "a", encoding="utf-8") as fh:              # код -- только в листе проверки: его получает тот, кто лист прочитал
        fh.write(f"\n\n---\nКОД ДЛЯ ПЕРЕДАЧИ (после проверки листа): {m.group(1) if m else '?'}\n")
    print("  КОД для передачи стоит в конце листа проверки -- его вводит человек, прочитавший лист.")
    print(f"Передача после проверки:  python3 anon_paket.py \"{case}\" --freigabe <КОД>")


def release(case, code):
    sys.path.insert(0, str(HERE))
    import anonymizer
    P = case / "_pipeline"
    md = (P / "dossier_anon.md").read_text(encoding="utf-8")
    real = anonymizer.fingerprint(md)
    if real != code:
        raise SystemExit(f"Код не совпадает: текст изменился после проверки (сейчас {real}). Передача отменена -- проверьте лист заново.")
    mapping = json.load(open(P / "mapping_dossier.json", encoding="utf-8"))
    from pipeline_case import GUARD_KINDS
    bad = anonymizer.guard(md + json.dumps(json.load(open(P / "austausch.json", encoding="utf-8")), ensure_ascii=False),
                           {k: v for k, v in mapping.items() if k.startswith(GUARD_KINDS) and len(str(v)) > 3}, 1)
    if bad and "--trotzdem" not in sys.argv:
        raise SystemExit(f"Контроль перед передачей нашёл совпадения с подлинными данными ({len(bad)}). Передача отменена.\n"
                         "  Настоящий пропуск: python3 anon_paket.py <папка> --merke \"слово1;слово2\" [--art Person|Firma|Ort|Nummer] и повторить сборку.\n"
                         "  Ложное срабатывание (обычное слово совпало с частью имени): повторить передачу с ключом --trotzdem -- решение человека, пишется в журнал.")
    import sekretaer                                     # третья ступень (решение автора к шагу 8, 09.10.2026): подтверждённые имена дела с допуском на искажение
    rs = sekretaer.reste(case)
    if rs and "--trotzdem" not in sys.argv:
        raise SystemExit(f"Третья ступень контроля нашла остатки имён дела ({len(rs)}): " + "; ".join(f"документ № {n}, стр. {se}: {ar}; {kl} ({fo})" for n, se, ar, kl, fo in rs[:12]) +
                         ".\n  Настоящий остаток: --merke \"слово\" и повторить сборку. Обычное слово, принятое за имя: вписать его в _pipeline/KEIN_NAME.txt и повторить; обход всего листа -- ключ --trotzdem (отметка пойдёт в журнал).")
    mk = anonymizer.merkmale(md)
    if mk and "--trotzdem" not in sys.argv:
        raise SystemExit("Контроль по признакам нашёл места, похожие на персональные данные: " + "; ".join(f"{k}: {v}" for k, v in mk.items()) + ". Передача отменена.\n"
                         "  Настоящий пропуск: --merke \"слово\" и повторить сборку. Если это не персональные данные (общий номер справочной и т.п.): повторить с ключом --trotzdem.")
    dst = Path.home() / "Documents" / "uebergabe" / code
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("austausch.json", "dossier_anon.md"):
        shutil.copy2(P / name, dst / name)
    (dst / "LIESMICH.md").write_text(
        f"Обезличенный пакет дела. Код текста: {code}. Проверен и одобрен человеком {time.strftime('%d.%m.%Y %H:%M')}.\n"
        "austausch.json -- обменный лист (все документы, таблицы, протокол); dossier_anon.md -- он же для чтения со сверкой кодом.\n"
        "Метки вида [Mandantin 1], [Steuerberater 2] заменяют подлинные имена; ключ остаётся у обработчика.\n"
        "Ответ с метками обработчик возвращает к подлинным именам сам.\n", encoding="utf-8")
    with open(HERE / "night_run" / "outbound_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%F %T"), "id": "anon_paket_freigabe", "code": code, "ziel": str(dst), "approved": True, "by": "Bearbeiter",
                            "kontrolle_treffer": len(bad), "merkmale": mk, "trotzdem": "--trotzdem" in sys.argv}, ensure_ascii=False) + "\n")
    import ausgangslog                                   # 19.10.2026: печать журнала исходящих цепочкой хешей
    print(f"журнал исходящих запечатан; голова цепочки {ausgangslog.versiegeln()[1][:16]}")
    print(f"Передано: {dst}\n  austausch.json, dossier_anon.md, LIESMICH.md. Ключ и подлинники остались в папке дела.")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    case = Path(sys.argv[1]).expanduser().resolve()
    if not case.is_dir():
        raise SystemExit(f"нет папки: {case}")
    if "--merke" in sys.argv:
        sys.path.insert(0, str(HERE))
        import anonymizer
        terms = [t for t in sys.argv[sys.argv.index("--merke") + 1].split(";") if t.strip()]
        art = sys.argv[sys.argv.index("--art") + 1] if "--art" in sys.argv else "Person"
        n = anonymizer.learn(terms, art, "")
        # что именно закроет правка (имитация дела А 11.10.2026): номер документа и число мест, без самого слова
        sf = case / "_pipeline" / "austausch.json"
        if sf.exists():
            sheet = json.load(open(sf, encoding="utf-8"))
            for k, t in enumerate(terms, 1):
                rx = re.compile(rf"(?i)(?<![\w\[]){re.escape(t.strip())}(?![\w\]])")
                wo = []
                for d in sheet["documents"]:
                    c = len(rx.findall(d.get("text") or "")) + sum(len(rx.findall(str(z))) for tb in d.get("tables", []) for r in tb["rows"] for z in r)
                    if c:
                        wo.append(f"№ {d['nr']} — {c}")
                print(f"  слово {k} ({len(t.strip())} знаков, вид {art}): в нынешнем листе открыто " + ("; ".join(wo) if wo else "нигде (в листе его нет: проверьте написание)"))
        print(f"Запомнено новых: {n} (вид: {art}). Они будут убираться при каждой сборке. Теперь повторите сборку: python3 anon_paket.py \"{case}\"")
    elif "--maskieren" in sys.argv:                          # обратный ход: текст аудитора с подлинными именами (комментарии к тексту эксперта) -> под маски
        sys.path.insert(0, str(HERE))
        os.environ.setdefault("LM_DOC_LIMIT", "400000")
        import anonymizer
        import exchange
        P = case / "_pipeline"
        src = Path(sys.argv[sys.argv.index("--maskieren") + 1]).expanduser()
        t = src.read_text(encoding="utf-8")
        t = "\n".join(l for l in t.split("\n") if not l.startswith("# Вид с подлинными именами"))
        reg = exchange.load_registry(P / "docs")
        mp = json.load(open(P / "mapping_dossier.json", encoding="utf-8"))
        for r in exchange.load_vorgabe(P / "docs"):          # пары «Имя [Маска]», которые поставил --klartext, -> просто маска (привязка к месту сохраняется: текст тот же)
            for v in r.get("varianten", []):
                t = t.replace(f"{v} {r['label']}", r["label"])
        for ph, v in mp.items():
            t = t.replace(f"{str(v).strip()} {ph}", ph)
        t = exchange.frei_text_anon(t, reg, mp)
        t, mp2 = anonymizer.anonymize(t, 1, ner="per")       # общее обезличивание для того, чего в деле ещё не было
        dst = P / (re.sub(r"_KLARTEXT$", "", src.stem) + "_MASKIERT.md")
        dst.write_text(t, encoding="utf-8")
        from pipeline_case import GUARD_KINDS                # как при передаче: суммы и даты на уровне 1 остаются, остатком не считаются
        bad = anonymizer.guard(t, {k: v for k, v in mp.items() if k.startswith(GUARD_KINDS) and len(str(v)) > 3}, 1)
        mk = anonymizer.merkmale(t)
        print(f"Текст под масками: {dst}\n  новых замен в этом тексте: {len([k for k in mp2 if k.startswith('[')])}; контроль по списку: {'остатков ' + str(len(bad)) if bad else 'чисто'}; "
              f"контроль по признакам: {'; '.join(f'{k}: {v}' for k, v in mk.items()) if mk else 'чисто'}\n  Прочитайте файл перед тем, как отдавать его эксперту.")
    elif "--antworten" in sys.argv:                          # свободные ответы аудитора на вопросы -> новый круг во вводной (прежние круги не стираются)
        P = case / "_pipeline"
        src = Path(sys.argv[sys.argv.index("--antworten") + 1]).expanduser()
        f = P / "EINLEITUNG.txt"
        alt = f.read_text(encoding="utf-8") if f.exists() else ""
        n = len(re.findall(r"(?m)^RUNDE \d+", alt)) + 1
        f.write_text(alt.rstrip() + f"\n\nRUNDE {n} ({time.strftime('%d.%m.%Y')}):\n" + src.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
        print(f"Ответы внесены во вводную как круг {n}: {f}\n  Исправления к отдельным документам (вид, дата, отправитель) -- в {P / 'KORREKTUR.txt'}. Теперь повторите сборку.")
        sys.path.insert(0, str(HERE))
        os.environ.setdefault("LM_DOC_LIMIT", "400000")
        import sekretaer                                 # шаг 9: «вот как я понял ваши ответы» -- сразу после приёма ответов
        L, _ = sekretaer.verstanden(case)
        print("\n".join(L))
    elif "--klartext" in sys.argv:                           # вопросы модели с масками -> вид с подлинными именами, только для экрана обработчика
        sys.path.insert(0, str(HERE))
        os.environ.setdefault("LM_DOC_LIMIT", "400000")
        import exchange
        P = case / "_pipeline"
        src = Path(sys.argv[sys.argv.index("--klartext") + 1]).expanduser()
        t = src.read_text(encoding="utf-8")
        for r in exchange.load_vorgabe(P / "docs"):          # маски состава -> первое написание из файла выбора
            t = t.replace(r["label"], f"{r['name']} {r['label']}" if r.get("varianten") else r["label"])
        for ph, v in sorted(json.load(open(P / "mapping_dossier.json", encoding="utf-8")).items(), key=lambda x: -len(x[0])):
            t = t.replace(ph, f"{str(v).strip()} {ph}")
        dst = P / (src.stem + "_KLARTEXT.md")
        dst.write_text("# Вид с подлинными именами -- только для обработчика, моделям не показывать\n\n" + t, encoding="utf-8")
        os.chmod(dst, 0o600)
        print(f"Вид с подлинными именами (только для вас): {dst}")
    elif "--verstanden" in sys.argv or "--aufgaben" in sys.argv or "--reste" in sys.argv:      # шаги секретаря отдельно (см. sekretaer.py)
        sys.path.insert(0, str(HERE))
        os.environ.setdefault("LM_DOC_LIMIT", "400000")
        import sekretaer
        sys.argv[1] = str(case)
        sekretaer.main()
    elif "--freigabe" in sys.argv:
        release(case, sys.argv[sys.argv.index("--freigabe") + 1])
    else:
        build(case, sys.argv[sys.argv.index("--frage") + 1] if "--frage" in sys.argv else "")


if __name__ == "__main__":
    main()
