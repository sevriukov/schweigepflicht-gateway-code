# Проверка обезличивания — 16.10.2026 22:03

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymizer.py` (версия 2), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| flächenangabe | 1 | 1 | 100 % |
| restaurantname | 1 | 1 | 100 % |
| belegnummer | 2 | 2 | 100 % |
| fahrzeugmodell | 1 | 1 | 100 % |
| kilometerstand | 1 | 1 | 100 % |
| geldbetrag | 10 | 10 | 100 % |
| uhrzeit | 3 | 3 | 100 % |
| mrn / zollnummer | 1 | 1 | 100 % |
| fahrgestellnummer | 1 | 1 | 100 % |
| flurstück | 1 | 1 | 100 % |
| grundbuch | 1 | 1 | 100 % |
| datum | 87 | 83 | 95 % |
| betrag | 59 | 56 | 95 % |
| finanzamt | 4 | 2 | 50 % |
| unternehmensname | 6 | 2 | 33 % |
| grundbuchangabe | 8 | 2 | 25 % |
| mandantennummer | 5 | 1 | 20 % |
| umsatzsteuer-id | 6 | 1 | 17 % |
| bankname | 8 | 1 | 12 % |
| firmenname | 31 | 1 | 3 % |
| name | 82 | 2 | 2 % |
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
| prüfungsnummer | 1 | 0 | 0 % |
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
| kunden nummer | 3 | 0 | 0 % |
| bank | 2 | 0 | 0 % |
| kanzlei | 1 | 0 | 0 % |
| vorgangsnummer | 1 | 0 | 0 % |
| gericht | 1 | 0 | 0 % |
| firma | 6 | 0 | 0 % |
| projektnummer | 1 | 0 | 0 % |
| sozialversicherungsnummer | 1 | 0 | 0 % |
| beraternummer | 1 | 0 | 0 % |
| gemarkung | 1 | 0 | 0 % |
| id | 1 | 0 | 0 % |
| handelsregister | 1 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 40 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 0.

Примеры утечек:
- wild_001 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): flächenangabe: 18,5qm; betrag: 1.245,50 €; betrag: 210,00 €; datum: 14.01.2023
- wild_002 (Schreiben des Finanzamts (Anhörung) an den Mandanten): datum: 03.11.2023; betrag: 50.000,00 EUR; betrag: 350.000,00 EUR; datum: 15.04.2024
- wild_003 (Schreiben des Finanzamts (Anhörung) an den Mandanten): datum: 18.07.2023; datum: 30.09.2022; datum: 10.10.2022; grundbuchangabe: Blatt 9876; betrag: 450.000,00 €; betrag: 125.000,00 €; datum: 28.05.2024
- wild_004 (Schreiben des Finanzamts (Anhörung) an den Mandanten): datum: 2021; restaurantname: Zur Eiche; belegnummer: 8841; datum: 12.04.2021; betrag: 430,50 EUR; datum: 19.11.2021; betrag: 75,00 EUR; betrag: 750,00 EUR; datum: 30.06.2024
- wild_005 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): fahrzeugmodell: Audi Q5; datum: 31.03.2023; betrag: 68.450,00 €; kilometerstand: 45.890 km; datum: 05.04.2023; betrag: 357,00 €
- wild_006 (interner Aktenvermerk des Steuerberaters): datum: 14.03.2024; unternehmensname: TechnoGmbH; geldbetrag: 45.850,00 €; geldbetrag: 62.100,00 EUR; geldbetrag: 40.000 EUR; datum: 19.03.2024
- wild_007 (Telefonnotiz der Kanzleimitarbeiterin): datum: 22.01.2024; uhrzeit: 10:15 Uhr; datum: 15.01.2024; unternehmensname: Goldener Drache; geldbetrag: 342,50 €; geldbetrag: 45,00 EUR
- wild_008 (E-Mail des Mandanten an die Kanzlei): datum: 05.02.2024; geldbetrag: 12.500,00 €; datum: 30.01.2024
- wild_009 (Telefonnotiz der Kanzleimitarbeiterin): datum: 02.04.2024; datum: 18.03.2024; geldbetrag: 310.000,00 EUR; datum: 10.01.2014; geldbetrag: 215.500,00 €
- wild_010 (förmlicher Brief des Mandanten): datum: 10. Mai 2024; geldbetrag: 21.400,00 €; geldbetrag: 24.500,00 €
- wild_011 (Telefonnotiz der Kanzleimitarbeiterin): datum: 14.03.2024; datum: 22.04.2024; datum: 12.11.2023; betrag: 45.678,90 EUR
- wild_012 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): datum: 10.01.2024; betrag: 485.000,00 Euro

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).