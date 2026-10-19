#!/usr/bin/env python3
"""ausgangslog.py -- печать журнала исходящих night_run/outbound_log.jsonl цепочкой хешей (19.10.2026, замечания DeepSeek/Gemini:
«журнал Freigabe можно подделать»). Запись в журнал не меняется (её ведут разные программы); рядом ведётся файл печати
night_run/outbound_log.kette: на каждую строку журнала -- HMAC-SHA256(ключ, хеш предыдущей печати + SHA256(строки)).
Ключ -- ~/.config/leckermath/ausgang_key (создаётся при первом запуске, права 600, не печатается).
Изменение, удаление или перестановка уже запечатанной строки обнаруживаются проверкой; новые строки печатаются при следующем вызове
versiegeln() (вызывается при одобрении и отправке листа в pipeline_case.py и anon_paket.py).
Ограничение: тот, у кого есть ключ, может пересчитать всю цепочку. Против этого -- отметка вне машины: голова цепочки (последний хеш)
печатается при каждом одобрении и сохраняется в approval.json дела; если её хранить и вне машины (письмо себе, бумага), сверка
с ней показывает переписывание задним числом. Двух людей на одобрение у одного обработчика нет -- это программа не заменяет.
    python3 ausgangslog.py pruefen     # проверить цепочку; код выхода 1 при нарушении
    python3 ausgangslog.py versiegeln  # запечатать новые строки
"""
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

LOG = Path(__file__).resolve().parent / "night_run" / "outbound_log.jsonl"
KETTE = LOG.with_suffix(".kette")
KEY = Path(os.path.expanduser("~/.config/leckermath/ausgang_key"))


def _key():
    if not KEY.exists():
        KEY.parent.mkdir(parents=True, exist_ok=True)
        KEY.write_bytes(os.urandom(32))
        KEY.chmod(0o600)
    return KEY.read_bytes()


def _zeilen():
    return LOG.read_bytes().split(b"\n")[:-1] if LOG.exists() else []


def _siegel():
    return [json.loads(z) for z in open(KETTE, encoding="utf-8")] if KETTE.exists() else []


def _h(key, prev, zeile):
    return hmac.new(key, prev.encode() + hashlib.sha256(zeile).hexdigest().encode(), hashlib.sha256).hexdigest()


def pruefen():
    """[(номер строки, что не так)] -- пусто, если журнал совпадает с печатью"""
    key, zs, ss = _key(), _zeilen(), _siegel()
    fehler, prev = [], "0" * 64
    if len(zs) < len(ss):
        fehler.append((len(zs) + 1, f"в журнале {len(zs)} строк, запечатано {len(ss)}: строки удалены"))
    for i, s in enumerate(ss):
        if s["n"] != i + 1:
            fehler.append((i + 1, "нарушен порядок печати"))
            break
        if i < len(zs) and not hmac.compare_digest(_h(key, prev, zs[i]), s["h"]):
            fehler.append((i + 1, "строка изменена или переставлена"))
            break
        prev = s["h"]
    return fehler


def versiegeln():
    """запечатать строки журнала, ещё не имеющие печати; вернуть (новых, голова цепочки). При нарушении -- ничего не печатает."""
    f = pruefen()
    if f:
        raise SystemExit(f"Журнал исходящих не совпадает с печатью: {f[:3]} -- новые строки не запечатаны, разберитесь вручную.")
    key, zs, ss = _key(), _zeilen(), _siegel()
    prev = ss[-1]["h"] if ss else "0" * 64
    neu = 0
    with open(KETTE, "a", encoding="utf-8") as out:
        for i in range(len(ss), len(zs)):
            prev = _h(key, prev, zs[i])
            out.write(json.dumps({"n": i + 1, "h": prev}) + "\n")
            neu += 1
    return neu, prev


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pruefen"
    if cmd == "versiegeln":
        n, kopf = versiegeln()
        print(f"запечатано новых строк: {n}; голова цепочки {kopf[:16]}")
    else:
        f = pruefen()
        print("журнал исходящих совпадает с печатью" if not f else f"НАРУШЕНИЕ: {f}")
        sys.exit(1 if f else 0)
