# Проверка обезличивания — 02.10.2026 08:26

Писем: 40 (придуманные, данные известны заранее). Обезличивание: `anonymize_hard` (версия 1), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| flächenangabe | 1 | 1 | 100 % |
| rechnungsnummer | 17 | 17 | 100 % |
| telefonnummer | 36 | 36 | 100 % |
| identifikationsnummer | 1 | 1 | 100 % |
| prüfungsnummer | 1 | 1 | 100 % |
| restaurantname | 1 | 1 | 100 % |
| belegnummer | 2 | 2 | 100 % |
| kennzeichen | 2 | 2 | 100 % |
| kilometerstand | 1 | 1 | 100 % |
| uhrzeit | 3 | 3 | 100 % |
| faxnummer | 2 | 2 | 100 % |
| kunden- oder mandantennummer | 1 | 1 | 100 % |
| mandatsnummer | 2 | 2 | 100 % |
| blz | 1 | 1 | 100 % |
| erbschaftssteuer-id | 1 | 1 | 100 % |
| mrn / zollnummer | 1 | 1 | 100 % |
| mandantennummer | 5 | 5 | 100 % |
| vorgangsnummer | 1 | 1 | 100 % |
| fahrgestellnummer | 1 | 1 | 100 % |
| beraternummer | 1 | 1 | 100 % |
| flurstück | 1 | 1 | 100 % |
| grundbuch | 1 | 1 | 100 % |
| id | 1 | 1 | 100 % |
| e-mail | 7 | 6 | 86 % |
| kfz-kennzeichen | 7 | 6 | 86 % |
| aktenzeichen | 25 | 19 | 76 % |
| vertragsnummer | 4 | 3 | 75 % |
| kunden nummer | 3 | 2 | 67 % |
| steuer-id | 10 | 6 | 60 % |
| kundennummer | 5 | 3 | 60 % |
| bank | 2 | 1 | 50 % |
| finanzamt | 4 | 2 | 50 % |
| e-mail-adresse | 7 | 3 | 43 % |
| ust-idnr. | 5 | 2 | 40 % |
| firma | 6 | 2 | 33 % |
| betrag | 59 | 18 | 31 % |
| geldbetrag | 10 | 3 | 30 % |
| adresse | 11 | 3 | 27 % |
| ust-idnr | 4 | 1 | 25 % |
| umsatzsteuer-id | 6 | 1 | 17 % |
| firmenname | 31 | 5 | 16 % |
| grundbuchangabe | 8 | 1 | 12 % |
| datum | 87 | 5 | 6 % |
| iban | 18 | 1 | 6 % |
| name | 82 | 4 | 5 % |
| personenname | 22 | 1 | 5 % |
| steuernummer | 31 | 0 | 0 % |
| geburtsdatum | 25 | 0 | 0 % |
| urkundenrolle | 1 | 0 | 0 % |
| fahrzeugmodell | 1 | 0 | 0 % |
| kanzleiname | 1 | 0 | 0 % |
| anschrift | 33 | 0 | 0 % |
| unternehmensname | 6 | 0 | 0 % |
| bankname | 8 | 0 | 0 % |
| flurstücksangabe | 1 | 0 | 0 % |
| benutzername | 1 | 0 | 0 % |
| behördenname | 6 | 0 | 0 % |
| bankverbindung | 5 | 0 | 0 % |
| bic | 2 | 0 | 0 % |
| kanzlei | 1 | 0 | 0 % |
| gericht | 1 | 0 | 0 % |
| projektnummer | 1 | 0 | 0 % |
| sozialversicherungsnummer | 1 | 0 | 0 % |
| gemarkung | 1 | 0 | 0 % |
| handelsregister | 1 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 39 из 40.** Из них контроль исходящих (`outbound_guard`) остановил бы: 19.

Примеры утечек:
- wild_001 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): adresse: Mozartstr. 14, 80336 MUC; flächenangabe: 18,5qm; betrag: 210,00 €; rechnungsnummer: R-2023-9981; telefonnummer: +49 172 5554321; e-mail: y.kacar@gmx-net.de
- wild_003 (Schreiben des Finanzamts (Anhörung) an den Mandanten): identifikationsnummer: 34 567 890 123; grundbuchangabe: Blatt 9876
- wild_004 (Schreiben des Finanzamts (Anhörung) an den Mandanten): firmenname: Alpha & Omega Consulting GmbH; prüfungsnummer: AP-2023-Hamburg; datum: 2021; restaurantname: Zur Eiche; belegnummer: 8841; betrag: 430,50 EUR; rechnungsnummer: G-2021-049; betrag: 75,00 EUR; betrag: 750,00 EUR
- wild_005 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): kennzeichen: HH-BL-7788; kilometerstand: 45.890 km; telefonnummer: 040-9876543; e-mail: petersen@steuer-hamburg.de; adresse: Hauptstr. 55, 22765 HH; rechnungsnummer: Gutachten-2023-089; betrag: 357,00 €
- wild_006 (interner Aktenvermerk des Steuerberaters): steuer-id: 45 678 901 234; rechnungsnummer: RG-2024-889; geldbetrag: 40.000 EUR; telefonnummer: 089/555-12348; telefonnummer: +49 171 9876543; aktenzeichen: W/2024-042
- wild_007 (Telefonnotiz der Kanzleimitarbeiterin): uhrzeit: 10:15 Uhr; geldbetrag: 342,50 €; kundennummer: K-99823; geldbetrag: 45,00 EUR; faxnummer: 030-9988776; aktenzeichen: H-2024/01
- wild_008 (E-Mail des Mandanten an die Kanzlei): rechnungsnummer: 2024-301; ust-idnr.: PL987654321; e-mail-adresse: t.schmidt@elektro-schmidt-kiel.de; telefonnummer: 0431 / 98765-43
- wild_009 (Telefonnotiz der Kanzleimitarbeiterin): telefonnummer: 0176-44332211; name: Dr. jur. A. Braun; aktenzeichen: P-554; e-mail-adresse: g.papadopoulos@gmx.net
- wild_010 (förmlicher Brief des Mandanten): datum: 10. Mai 2024; kunden- oder mandantennummer: KD-7712; steuer-id: 33 445 566 778; telefonnummer: +49(0)221-8877665; e-mail-adresse: mail@fatma-demir-design.de
- wild_011 (Telefonnotiz der Kanzleimitarbeiterin): rechnungsnummer: R-2023-889; telefonnummer: 030-98765432
- wild_012 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): aktenzeichen: W-2024/44a; personenname: Nguyen Van Hau; telefonnummer: 0151-99887766
- wild_013 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): ust-idnr: PL9876543210; rechnungsnummer: RE-2024-0091; kfz-kennzeichen: PO-998X; mandatsnummer: 4711/B; telefonnummer: 0173/4445566

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).