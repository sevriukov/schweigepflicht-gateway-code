# Проверка обезличивания — 17.10.2026 16:09

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| geldbetrag | 18 | 18 | 100 % |
| datum | 73 | 72 | 99 % |
| betrag | 40 | 38 | 95 % |
| grundbuchangabe | 8 | 2 | 25 % |
| aktenzeichen | 28 | 1 | 4 % |
| firmenname | 29 | 1 | 3 % |
| rechnungsnummer | 15 | 0 | 0 % |
| unternehmensname | 6 | 0 | 0 % |
| anschrift | 56 | 0 | 0 % |
| steuernummer | 30 | 0 | 0 % |
| umsatzsteuer-identifikations | 2 | 0 | 0 % |
| name | 72 | 0 | 0 % |
| telefonnummer | 35 | 0 | 0 % |
| iban | 24 | 0 | 0 % |
| geburtsdatum | 31 | 0 | 0 % |
| kfz-kennzeichen | 4 | 0 | 0 % |
| kunden-/vertragsnummer | 2 | 0 | 0 % |
| e-mail-adresse | 4 | 0 | 0 % |
| handelsregisternummer | 1 | 0 | 0 % |
| firma | 4 | 0 | 0 % |
| steuer-id | 10 | 0 | 0 % |
| personenname | 14 | 0 | 0 % |
| bic | 2 | 0 | 0 % |
| kunden-nr. | 3 | 0 | 0 % |
| ust-idnr. | 4 | 0 | 0 % |
| e-mail | 15 | 0 | 0 % |
| vorgangsnummer | 1 | 0 | 0 % |
| betriebsnummer | 1 | 0 | 0 % |
| sozialversicherungsnummer | 1 | 0 | 0 % |
| mandantenkürzel | 1 | 0 | 0 % |
| steuer-idnr. | 1 | 0 | 0 % |
| ust-idnr | 3 | 0 | 0 % |
| kunden-/mandantennummer | 1 | 0 | 0 % |
| bankverbindung | 2 | 0 | 0 % |
| umsatzsteuer-id | 1 | 0 | 0 % |
| mandatsnummer | 2 | 0 | 0 % |
| handelsregister | 2 | 0 | 0 % |
| bank | 2 | 0 | 0 % |
| prüfungs-id | 1 | 0 | 0 % |
| mandanten-id | 1 | 0 | 0 % |
| belegnummer | 1 | 0 | 0 % |
| vertragsnummer | 1 | 0 | 0 % |
| kennzeichen | 1 | 0 | 0 % |
| kundennummer | 2 | 0 | 0 % |
| objekt-id | 1 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 40 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 0.

Примеры утечек:
- wild_001 (förmlicher Brief des Mandanten): datum: 14. November 2024; geldbetrag: 45.678,90 EUR; datum: 30.11.2024
- wild_002 (E-Mail des Mandanten an die Kanzlei): datum: 31.10.2024; datum: 15.10.2024; geldbetrag: 32.450,00 Euro
- wild_003 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): geldbetrag: 4.321,50 €; datum: 10.01.2023
- wild_004 (interner Aktenvermerk des Steuerberaters): datum: 25.11.2024; datum: 04.11.2024; geldbetrag: 12.890,45 EUR; datum: 19.08.2024; datum: 15.12.2024
- wild_005 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): datum: 18.10.2024; geldbetrag: 150.000,00 €
- wild_006 (Telefonnotiz der Kanzleimitarbeiterin): datum: 14.04.2024; betrag: 18.750,50 EUR; datum: 18.04.2024
- wild_007 (Telefonnotiz der Kanzleimitarbeiterin): datum: 02.11.2023; betrag: 1.450,00 EUR; betrag: 210,00 EUR; datum: 05.11.2023
- wild_008 (interner Aktenvermerk des Steuerberaters): datum: 22.09.2023; datum: 31.08.2023; betrag: 34.250,00 EUR; datum: 10.05.2020; betrag: 68.400,00 EUR
- wild_009 (Telefonnotiz der Kanzleimitarbeiterin): datum: 19.01.2024; datum: 05.11.2023; betrag: 450.000,00 EUR; betrag: 1.850.000,00 EUR
- wild_010 (interner Aktenvermerk des Steuerberaters): datum: 12.12.2023; betrag: 45.890,00 PLN; betrag: 10.650,20 EUR; datum: 28.12.2023
- wild_011 (E-Mail des Mandanten an die Kanzlei): datum: 14.04.2023; datum: 02.05.2023; betrag: 345.890,50 EUR; datum: 15.05.2023
- wild_012 (E-Mail des Mandanten an die Kanzlei): datum: 19. November 2022; betrag: 45.320,00 €; datum: 28.11.2022; betrag: 5.000,00 EUR

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).