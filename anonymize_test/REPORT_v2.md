# Проверка обезличивания — 16.10.2026 22:03

Писем: 35 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| betrag | 35 | 35 | 100 % |
| datum | 34 | 33 | 97 % |
| person | 70 | 0 | 0 % |
| firma | 35 | 0 | 0 % |
| adresse | 35 | 0 | 0 % |
| plz_ort | 35 | 0 | 0 % |
| iban | 35 | 0 | 0 % |
| steuernummer | 35 | 0 | 0 % |
| ust_id | 35 | 0 | 0 % |
| steuer_id | 35 | 0 | 0 % |
| geburtsdatum | 35 | 0 | 0 % |
| telefon | 35 | 0 | 0 % |
| email | 35 | 0 | 0 % |
| kennzeichen | 35 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 35 из 35.** Из них контроль исходящих (`outbound_guard`) остановил бы: 1.

Примеры утечек:
- brief_001 (Telefonnotiz der Kanzleimitarbeiterin): betrag: 232.950,33 €; datum: 21.07.2026
- brief_002 (E-Mail des Mandanten an die Kanzlei): betrag: 59.419,56 €; datum: 13.05.2024
- brief_003 (interner Aktenvermerk des Steuerberaters): betrag: 277.392,11 €; datum: 20.06.2023
- brief_004 (förmlicher Brief des Mandanten): betrag: 364.438,13 €; datum: 26.12.2024
- brief_005 (interner Aktenvermerk des Steuerberaters): betrag: 246.628,17 €; datum: 24.05.2023
- brief_006 (interner Aktenvermerk des Steuerberaters): betrag: 429.899,50 €; datum: 21.03.2023
- brief_007 (interner Aktenvermerk des Steuerberaters): betrag: 335.735,53 €; datum: 28.09.2024
- brief_008 (förmlicher Brief des Mandanten): betrag: 426.416,61 €; datum: 04.12.2024
- brief_009 (interner Aktenvermerk des Steuerberaters): betrag: 67.751,44 €; datum: 12.01.2023
- brief_010 (Telefonnotiz der Kanzleimitarbeiterin): betrag: 426.490,70 €; datum: 01.09.2023
- brief_011 (förmlicher Brief des Mandanten): betrag: 113.978,55 €
- brief_012 (Telefonnotiz der Kanzleimitarbeiterin): betrag: 68.592,94 €; datum: 20.05.2025

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).