# Проверка обезличивания — 19.10.2026 06:05

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| restaurantname | 1 | 1 | 100 % |
| finanzamt | 4 | 2 | 50 % |
| unternehmensname | 6 | 2 | 33 % |
| bankname | 8 | 1 | 12 % |
| firmenname | 31 | 1 | 3 % |
| name | 82 | 1 | 1 % |
| adresse | 11 | 0 | 0 % |
| steuernummer | 31 | 0 | 0 % |
| iban | 18 | 0 | 0 % |
| rechnungsnummer | 17 | 0 | 0 % |
| telefonnummer | 36 | 0 | 0 % |
| e-mail | 7 | 0 | 0 % |
| aktenzeichen | 25 | 0 | 0 % |
| geburtsdatum | 25 | 0 | 0 % |
| urkundenrolle | 1 | 0 | 0 % |
| identifikationsnummer | 1 | 0 | 0 % |
| umsatzsteuer-id | 6 | 0 | 0 % |
| grundbuchangabe | 8 | 0 | 0 % |
| prüfungsnummer | 1 | 0 | 0 % |
| belegnummer | 2 | 0 | 0 % |
| kennzeichen | 2 | 0 | 0 % |
| kanzleiname | 1 | 0 | 0 % |
| anschrift | 33 | 0 | 0 % |
| steuer-id | 10 | 0 | 0 % |
| ust-idnr. | 5 | 0 | 0 % |
| kundennummer | 5 | 0 | 0 % |
| e-mail-adresse | 7 | 0 | 0 % |
| faxnummer | 2 | 0 | 0 % |
| flurstücksangabe | 1 | 0 | 0 % |
| benutzername | 1 | 0 | 0 % |
| vertragsnummer | 4 | 0 | 0 % |
| behördenname | 6 | 0 | 0 % |
| kunden- oder mandantennummer | 1 | 0 | 0 % |
| personenname | 22 | 0 | 0 % |
| bankverbindung | 5 | 0 | 0 % |
| kfz-kennzeichen | 7 | 0 | 0 % |
| ust-idnr | 4 | 0 | 0 % |
| mandatsnummer | 2 | 0 | 0 % |
| blz | 1 | 0 | 0 % |
| erbschaftssteuer-id | 1 | 0 | 0 % |
| bic | 2 | 0 | 0 % |
| mrn / zollnummer | 1 | 0 | 0 % |
| kunden nummer | 3 | 0 | 0 % |
| mandantennummer | 5 | 0 | 0 % |
| bank | 2 | 0 | 0 % |
| kanzlei | 1 | 0 | 0 % |
| vorgangsnummer | 1 | 0 | 0 % |
| gericht | 1 | 0 | 0 % |
| firma | 6 | 0 | 0 % |
| fahrgestellnummer | 1 | 0 | 0 % |
| projektnummer | 1 | 0 | 0 % |
| sozialversicherungsnummer | 1 | 0 | 0 % |
| beraternummer | 1 | 0 | 0 % |
| flurstück | 1 | 0 | 0 % |
| gemarkung | 1 | 0 | 0 % |
| grundbuch | 1 | 0 | 0 % |
| id | 1 | 0 | 0 % |
| handelsregister | 1 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 8 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 0.

Примеры утечек:
- wild_004 (Schreiben des Finanzamts (Anhörung) an den Mandanten): restaurantname: Zur Eiche
- wild_006 (interner Aktenvermerk des Steuerberaters): unternehmensname: TechnoGmbH
- wild_007 (Telefonnotiz der Kanzleimitarbeiterin): unternehmensname: Goldener Drache
- wild_017 (interner Aktenvermerk des Steuerberaters): bankname: HypoVereinsbank
- wild_023 (Telefonnotiz der Kanzleimitarbeiterin): firmenname: Kanzlei Berg & Partner
- wild_029 (Schreiben des Finanzamts (Anhörung) an den Mandanten): finanzamt: FINANZAMT BERLIN-CHARLOTTENBURG
- wild_033 (Telefonnotiz der Kanzleimitarbeiterin): name: Stefanie Müller
- wild_040 (Schreiben des Finanzamts (Anhörung) an den Mandanten): finanzamt: FINANZAMT MÜNCHEN ABTEILUNG III

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).