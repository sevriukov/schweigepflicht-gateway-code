# Проверка обезличивания — 02.10.2026 13:04

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymize_hard` (версия 1), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| rechnungsnummer | 15 | 15 | 100 % |
| kunden-/vertragsnummer | 2 | 2 | 100 % |
| kunden-nr. | 3 | 3 | 100 % |
| vorgangsnummer | 1 | 1 | 100 % |
| betriebsnummer | 1 | 1 | 100 % |
| sozialversicherungsnummer | 1 | 1 | 100 % |
| steuer-idnr. | 1 | 1 | 100 % |
| kunden-/mandantennummer | 1 | 1 | 100 % |
| umsatzsteuer-id | 1 | 1 | 100 % |
| mandatsnummer | 2 | 2 | 100 % |
| prüfungs-id | 1 | 1 | 100 % |
| mandanten-id | 1 | 1 | 100 % |
| belegnummer | 1 | 1 | 100 % |
| kennzeichen | 1 | 1 | 100 % |
| objekt-id | 1 | 1 | 100 % |
| telefonnummer | 35 | 34 | 97 % |
| steuer-id | 10 | 9 | 90 % |
| e-mail | 15 | 11 | 73 % |
| aktenzeichen | 28 | 18 | 64 % |
| kfz-kennzeichen | 4 | 2 | 50 % |
| bic | 2 | 1 | 50 % |
| bankverbindung | 2 | 1 | 50 % |
| handelsregister | 2 | 1 | 50 % |
| kundennummer | 2 | 1 | 50 % |
| ust-idnr | 3 | 1 | 33 % |
| e-mail-adresse | 4 | 1 | 25 % |
| firma | 4 | 1 | 25 % |
| firmenname | 29 | 5 | 17 % |
| unternehmensname | 6 | 1 | 17 % |
| grundbuchangabe | 8 | 1 | 12 % |
| name | 72 | 4 | 6 % |
| anschrift | 56 | 0 | 0 % |
| steuernummer | 30 | 0 | 0 % |
| umsatzsteuer-identifikations | 2 | 0 | 0 % |
| iban | 24 | 0 | 0 % |
| geburtsdatum | 31 | 0 | 0 % |
| handelsregisternummer | 1 | 0 | 0 % |
| personenname | 14 | 0 | 0 % |
| ust-idnr. | 4 | 0 | 0 % |
| mandantenkürzel | 1 | 0 | 0 % |
| bank | 2 | 0 | 0 % |
| vertragsnummer | 1 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 40 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 16.

Примеры утечек:
- wild_001 (förmlicher Brief des Mandanten): rechnungsnummer: RE-2024/8893; telefonnummer: 089-5551234
- wild_002 (E-Mail des Mandanten an die Kanzlei): kfz-kennzeichen: HH-AB 1234; unternehmensname: Digital Solutions e.K.; aktenzeichen: TÜV-8899/24; telefonnummer: 040-9876543; telefonnummer: +49 171 2345678; kunden-/vertragsnummer: KD-998877
- wild_003 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): rechnungsnummer: R-2023-112; telefonnummer: 0178-9876543; name: Nguyen Van Hau
- wild_004 (interner Aktenvermerk des Steuerberaters): rechnungsnummer: INV-9988776; telefonnummer: 069-1234567; aktenzeichen: 045 250 88991; kunden-/vertragsnummer: M-44321
- wild_005 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): name: herr wagner; aktenzeichen: U 456/2024; telefonnummer: 0151-11223344
- wild_006 (Telefonnotiz der Kanzleimitarbeiterin): telefonnummer: 089/555-1234; aktenzeichen: 3 Ca 4567/23
- wild_007 (Telefonnotiz der Kanzleimitarbeiterin): steuer-id: 45 678 901 234; telefonnummer: 030-9988776
- wild_008 (interner Aktenvermerk des Steuerberaters): firma: TechLogistics e.K.; e-mail-adresse: kanzlei@steuerberatung-klein.de
- wild_009 (Telefonnotiz der Kanzleimitarbeiterin): telefonnummer: 069 / 44 33 22 11; steuer-id: 12 345 678 901
- wild_010 (interner Aktenvermerk des Steuerberaters): rechnungsnummer: WB-2023-889
- wild_011 (E-Mail des Mandanten an die Kanzlei): bic: GENODEF1M01; kunden-nr.: K-998877; aktenzeichen: 2023/V-45
- wild_012 (E-Mail des Mandanten an die Kanzlei): aktenzeichen: Az. 3 O 123/22; rechnungsnummer: RE-2022-9981

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).