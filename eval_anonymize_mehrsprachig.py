#!/usr/bin/env python3
"""
eval_anonymize_mehrsprachig.py -- замер обезличивания на русских и английских текстах (придуманные письма, заметки, сообщения).
Мера: доля чувствительных строк (имена, фирмы, места, телефоны, адреса, номера), оставшихся в тексте после обезличивания (уровень 1),
и число «лишних» меток на обычных словах. Сравнение: до (LM_ANON_MEHRSPRACHIG=0) и после.
    python3 eval_anonymize_mehrsprachig.py   -> benchmark/leckermath/ANON_MEHRSPRACHIG.md
Тексты придуманы разработчиком тех же правил -- оценка оптимистична; независимой проверки нет.
"""
import os, re, sys, time, random, json
rnd = random.Random(20261008)
RU_V = [("Ольга", "Петрова", "Викторовна"), ("Иван", "Сидоров", "Петрович"), ("Марина", "Кузнецова", "Андреевна"), ("Дмитрий", "Орлов", "Сергеевич"), ("Елена", "Васильева", "Игоревна"),
        ("Алексей", "Громов", "Николаевич"), ("Татьяна", "Белова", "Павловна"), ("Сергей", "Лебедев", "Олегович")]
RU_F = ["ООО «Ромашка»", "ООО «Северный ветер»", "ИП Громов", "АО «Балтстрой»", "ООО «Вектор Плюс»"]
RU_O = ["Дортмунд", "Казань", "Самара", "Бохум", "Тверь"]
EN_V = [("John", "Smith"), ("Emily", "Clarke"), ("Peter", "Brown"), ("Sarah", "Whitfield"), ("David", "Hargreaves"), ("Laura", "Bennett"), ("Michael", "O'Connor"), ("Anna", "Fletcher")]
EN_F = ["Acme Trading Ltd", "Northfield Consulting LLP", "Harbour Logistics Inc", "Greenway Studios Ltd", "Pemberton & Sons Ltd"]
EN_O = ["Manchester", "Leeds", "Bristol", "Dublin", "Glasgow"]

def dat(n, fall):
    return n if fall == "n" else {"Петрова": {"g": "Петровой", "d": "Петровой", "a": "Петрову"}, "Сидоров": {"g": "Сидорова", "d": "Сидорову", "a": "Сидорова"},
        "Кузнецова": {"g": "Кузнецовой", "d": "Кузнецовой", "a": "Кузнецову"}, "Орлов": {"g": "Орлова", "d": "Орлову", "a": "Орлова"},
        "Васильева": {"g": "Васильевой", "d": "Васильевой", "a": "Васильеву"}, "Громов": {"g": "Громова", "d": "Громову", "a": "Громова"},
        "Белова": {"g": "Беловой", "d": "Беловой", "a": "Белову"}, "Лебедев": {"g": "Лебедева", "d": "Лебедеву", "a": "Лебедева"}}[n][fall]

def ru_text(k):
    a, b, c = rnd.sample(RU_V, 3); f = rnd.choice(RU_F); o = rnd.choice(RU_O)
    tel = f"+7 ({rnd.randint(900, 999)}) {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}"
    inn = "".join(str(rnd.randint(0, 9)) for _ in range(12)); adr = f"ул. {rnd.choice(['Садовая', 'Ленина', 'Лесная'])}, д. {rnd.randint(1, 90)}, кв. {rnd.randint(1, 200)}"
    forms = [
        f"Уважаемая {a[0]} {a[2]}!\n\nВаш консультант {b[1]} не подал декларацию за 2023 год. Я звонила {dat(b[1], 'd')} дважды и писала {dat(c[1], 'd')}, но ответа нет. {f} из города {o} выставило счёт на 4 800 евро. Мой телефон {tel}.\n\nС уважением, {c[0]} {c[1]}",
        f"Заметка по разговору. Клиентка {a[1]} {a[0]} {a[2]} рассказала, что документы за 2021 год передавал её муж {b[0]}. У {dat(b[1], 'g')} была доверенность. ИНН {inn}. Адрес: {adr}. Бухгалтерию вела фирма {f}, потом дело перешло к {dat(c[1], 'd')}.",
        f"{a[0]}, добрый день! Письмо из кассы пришло вчера, там доплата 4 666,96 евро. {b[0]} {b[1]} обещал разобраться до пятницы. Если что, звоните {dat(c[1], 'd')} на {tel}. Встреча в {o}е, в офисе {f}.",
        f"Протокол. Присутствовали: {a[1]} {a[0][0]}. {a[2][0]}., {b[1]} {b[0][0]}. {b[2][0]}. Решили: {dat(a[1], 'a')} просят представить выписки, {b[1]} готовит возражение. Паспорт клиентки: серия 45 08 номер 123456. От {dat(c[1], 'g')} ответа ждут до 15.10.2026.",
    ]
    t = forms[k % len(forms)]
    sens = [x for x in (a[1], b[1], c[1], a[0] + " " + a[2] if k % 4 == 0 else None, tel if tel in t else None, inn if inn in t else None, f.split("«")[-1].strip("»") if "«" in f else f.split()[-1], o if k % 4 != 1 else None,
                        "123456" if "123456" in t else None, "Садовая" if "Садовая" in t else None) if x]
    for full in (a, b, c):
        for fall in "gda":
            v = dat(full[1], fall)
            if v in t: sens.append(v)
    return t, sorted(set(sens))

def en_text(k):
    a, b, c = rnd.sample(EN_V, 3); f = rnd.choice(EN_F); o = rnd.choice(EN_O)
    tel = f"+44 {rnd.randint(20, 79)} {rnd.randint(1000, 9999)} {rnd.randint(1000, 9999)}"; adr = f"{rnd.randint(2, 180)} {rnd.choice(['Baker', 'Church', 'Station', 'Mill'])} {rnd.choice(['Street', 'Road', 'Lane'])}"
    forms = [
        f"Dear Mr. {a[0]} {a[1]},\n\nplease find attached the invoice from {f}, {adr}, {o}. We have not received your payment of EUR 4,800. Mrs {b[0]} {b[1]} will call you on {tel}. {a[0]}, please reply by Friday.\n\nKind regards,\n{c[0]} {c[1]}",
        f"Meeting note. The client {a[0]} {a[1]} said that her husband handled all the paperwork with the adviser {b[0]} {b[1]}. {b[1]} did not file the return for 2021. The company {f} in {o} has been informed. Contact: {tel}.",
        f"Hi {a[0]},\n\nthe letter from the insurer arrived yesterday and it asks for an additional payment of EUR 4,666.96. {b[0]} {b[1]} promised to sort it out by Friday. If needed, please call {c[0]} {c[1]} on {tel}. We meet in {o} at the office of {f}.\n\nBest regards,\n{c[0]}",
        f"Minutes. Present: {a[0]} {a[1]}, {b[0]} {b[1]} and Dr {c[1]}. It was agreed that {a[1]} will provide the bank statements and that {b[1]}'s office prepares the objection. The registered address is {adr}, {o}. The reply from {f} is expected by 15 October 2026.",
    ]
    t = forms[k % len(forms)]
    sens = [x for x in (a[1], b[1], c[1] if c[1] in t else None, a[0] if a[0] in t else None, b[0] if b[0] in t else None, tel if tel in t else None, adr.split()[1] if adr in t else None, o, f.rsplit(" ", 1)[0]) if x]
    return t, sorted(set(sens))

def run(mode):
    os.environ["LM_ANON_MEHRSPRACHIG"] = mode
    import importlib, anonymizer
    importlib.reload(anonymizer)
    global rnd
    rnd = random.Random(20261008)
    res = {}
    for lang, gen in (("русский", ru_text), ("английский", en_text)):
        tot = left = extra = 0; bsp = []
        for k in range(40):
            t, sens = gen(k)
            o, m = anonymizer.anonymize(t, 1)
            rest = [s for s in sens if s in o]
            tot += len(sens); left += len(rest)
            falsch = [v for ph, v in m.items() if ph.startswith(("[Person", "[Firma", "[Ort")) and not any(s in v or v in s for s in sens) and not any(v in " ".join(x) for x in RU_V + EN_V)
                      and v not in RU_O + EN_O and not any(v in x for x in RU_F + EN_F)]
            extra += len(falsch)
            if rest and len(bsp) < 4: bsp.append("осталось: " + ", ".join(rest))
            if falsch and len(bsp) < 6: bsp.append("лишняя метка: " + ", ".join(falsch[:3]))
        res[lang] = (tot, left, extra, bsp)
    return res

a, b = run("0"), run("1")
L = [f"# Обезличивание русских и английских текстов ({time.strftime('%d.%m.%Y %H:%M')})", "", "40 придуманных текстов на язык (письма, заметки, сообщения, протоколы); уровень 1.", "",
     "| Язык | Чувствительных строк | Осталось до | Осталось после | Лишних меток до | Лишних меток после |", "|---|---:|---:|---:|---:|---:|"]
for lang in a:
    L.append(f"| {lang} | {a[lang][0]} | {a[lang][1]} ({100 * a[lang][1] / a[lang][0]:.0f} %) | {b[lang][1]} ({100 * b[lang][1] / b[lang][0]:.1f} %) | {a[lang][2]} | {b[lang][2]} |")
L += ["", "Примеры после:"] + [f"- {lang}: {x}" for lang in b for x in b[lang][3]]
open(("benchmark/leckermath/" if os.path.isdir("benchmark/leckermath") else "anonymize_test/") + "ANON_MEHRSPRACHIG.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L))
