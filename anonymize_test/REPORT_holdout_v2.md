# Проверка обезличивания — 16.10.2026 22:03

Писем: 41 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| betrag | 41 | 41 | 100 % |
| datum | 39 | 36 | 92 % |
| person | 79 | 0 | 0 % |
| firma | 41 | 0 | 0 % |
| adresse | 41 | 0 | 0 % |
| plz_ort | 41 | 0 | 0 % |
| iban | 41 | 0 | 0 % |
| steuernummer | 41 | 0 | 0 % |
| ust_id | 41 | 0 | 0 % |
| steuer_id | 41 | 0 | 0 % |
| geburtsdatum | 41 | 0 | 0 % |
| telefon | 41 | 0 | 0 % |
| email | 41 | 0 | 0 % |
| kennzeichen | 41 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 41 из 41.** Из них контроль исходящих (`outbound_guard`) остановил бы: 0.

Примеры утечек:
- brief_001 (Telefonnotiz der Kanzleimitarbeiterin): betrag: 34 T€; datum: 25.9.2026
- brief_002 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): betrag: 40071 €
- brief_003 (interner Aktenvermerk des Steuerberaters): betrag: EUR 311.924,74; datum: 8.11.2023
- brief_004 (förmlicher Brief des Mandanten): betrag: 27025 €; datum: 12. Januar 2024
- brief_005 (förmlicher Brief des Mandanten): betrag: 25 T€; datum: 23.11.2025
- brief_006 (förmlicher Brief des Mandanten): betrag: EUR 356.729,05; datum: 23. März 2025
- brief_007 (Telefonnotiz der Kanzleimitarbeiterin): betrag: 81 T€; datum: 25.5.2023
- brief_008 (E-Mail des Mandanten an die Kanzlei): betrag: 28180 €; datum: 27. März 2024
- brief_009 (förmlicher Brief des Mandanten): betrag: EUR 368.749,42; datum: 13.2.2026
- brief_010 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): betrag: EUR 364.764,48; datum: 3. August 2025
- brief_011 (interner Aktenvermerk des Steuerberaters): betrag: 34333 €; datum: 7. März 2023
- brief_012 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): betrag: 222.997 Euro; datum: 12.1.2025

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).