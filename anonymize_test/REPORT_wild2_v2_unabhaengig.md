# Проверка обезличивания — 02.10.2026 13:05

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| unternehmensname | 6 | 2 | 33 % |
| grundbuchangabe | 8 | 2 | 25 % |
| firma | 4 | 1 | 25 % |
| firmenname | 29 | 2 | 7 % |
| aktenzeichen | 28 | 1 | 4 % |
| name | 72 | 1 | 1 % |
| rechnungsnummer | 15 | 0 | 0 % |
| anschrift | 56 | 0 | 0 % |
| steuernummer | 30 | 0 | 0 % |
| umsatzsteuer-identifikations | 2 | 0 | 0 % |
| telefonnummer | 35 | 0 | 0 % |
| iban | 24 | 0 | 0 % |
| geburtsdatum | 31 | 0 | 0 % |
| kfz-kennzeichen | 4 | 0 | 0 % |
| kunden-/vertragsnummer | 2 | 0 | 0 % |
| e-mail-adresse | 4 | 0 | 0 % |
| handelsregisternummer | 1 | 0 | 0 % |
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

**Писем хотя бы с одной утечкой: 9 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 1.

Примеры утечек:
- wild_001 (förmlicher Brief des Mandanten): unternehmensname: BAU-PROFI GmbH & Co. KG
- wild_003 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): unternehmensname: Handwerksbetrieb Müller & Söhne OHG
- wild_010 (interner Aktenvermerk des Steuerberaters): firma: Warszawa Budownictwo Sp. z o.o.
- wild_019 (förmlicher Brief des Mandanten): firmenname: TechnoImport GmbH
- wild_020 (Telefonnotiz der Kanzleimitarbeiterin): grundbuchangabe: Blatt 9988, Flurstück 12/4
- wild_025 (förmlicher Brief des Mandanten): aktenzeichen: 18 IV 90/24
- wild_033 (Telefonnotiz der Kanzleimitarbeiterin): grundbuchangabe: Blatt 4410
- wild_038 (interner Aktenvermerk des Steuerberaters): name: StB Klein
- wild_040 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): firmenname: Schreinerei Holz & mehr

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).