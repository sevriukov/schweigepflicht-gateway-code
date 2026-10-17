# Проверка обезличивания — 02.10.2026 08:17

Писем: 41 (придуманные, данные известны заранее). Обезличивание: `anonymize_hard` (версия 1), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| steuer_id | 41 | 41 | 100 % |
| telefon | 41 | 41 | 100 % |
| geburtsdatum | 41 | 35 | 85 % |
| kennzeichen | 41 | 32 | 78 % |
| email | 41 | 28 | 68 % |
| betrag | 41 | 19 | 46 % |
| iban | 41 | 18 | 44 % |
| steuernummer | 41 | 17 | 41 % |
| plz_ort | 41 | 16 | 39 % |
| datum | 39 | 15 | 38 % |
| adresse | 41 | 14 | 34 % |
| person | 79 | 12 | 15 % |
| firma | 41 | 0 | 0 % |
| ust_id | 41 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 41 из 41.** Из них контроль исходящих (`outbound_guard`) остановил бы: 21.

Примеры утечек:
- brief_001 (Telefonnotiz der Kanzleimitarbeiterin): plz_ort: 45879 Gelsenkirchen; iban: AT58 7225 1444 6289 7921; steuer_id: 71 872 074 396; telefon: (0231) 07 94 40; email: karl-heinz.elmasri@t-online.de; kennzeichen: DO DZ 304; betrag: 34 T€
- brief_002 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): person: Fatima El-Masri; plz_ort: 59065 Hamm; steuernummer: 9587902203657; steuer_id: 31 690 077 660; geburtsdatum: 06.12.88; telefon: 0049 151 67150885; email: fatima.elmasri@web.de; kennzeichen: B-C 4642E
- brief_003 (interner Aktenvermerk des Steuerberaters): adresse: Kirchgasse 26 c; plz_ort: 44649 Wanne-Eickel; iban: NL54 INGB 6143 7125 66; steuer_id: 63 575 739 139; geburtsdatum: 13. Januar 1986; telefon: +49 (0) 2301 13612; betrag: EUR 311.924,74
- brief_004 (förmlicher Brief des Mandanten): plz_ort: 44575 Castrop-Rauxel; steuer_id: 00 604 273 719; geburtsdatum: 13. Januar 1977; telefon: 0231-360876; email: katarzyna.jovanovi@t-online.de; kennzeichen: B-C 9545E; datum: 12. Januar 2024
- brief_005 (förmlicher Brief des Mandanten): person: Mehmet Tran; plz_ort: 58239 Schwerte; iban: AT33 0951 6630 3343 2208; steuernummer: 2527522975351; steuer_id: 08 665 527 180; geburtsdatum: 03.07.78; telefon: 0231-906348; email: mehmet.tran@t-online.de; kennzeichen: DO DZ 426; betrag: 25 T€
- brief_006 (förmlicher Brief des Mandanten): steuernummer: 7661922207978; steuer_id: 50 826 941 326; geburtsdatum: 7. März 1957; telefon: (0231) 87 34 25; email: dragan.grossekathoefer@t-online.de; betrag: EUR 356.729,05; datum: 23. März 2025
- brief_007 (Telefonnotiz der Kanzleimitarbeiterin): steuer_id: 07 690 683 459; geburtsdatum: 4. März 1988; telefon: 0231-758325; kennzeichen: B-A 6240E; betrag: 81 T€
- brief_008 (E-Mail des Mandanten an die Kanzlei): steuer_id: 70 396 845 759; telefon: 0049 151 95102227; kennzeichen: HSK-L 28; datum: 27. März 2024
- brief_009 (förmlicher Brief des Mandanten): person: Karl-Heinz Petrenko; adresse: Kirchgasse 4 c; steuer_id: 45 833 196 323; geburtsdatum: 10.08.52; telefon: (0231) 52 84 55; email: karl-heinz.petrenko@gmx.de; kennzeichen: HSK-M 16; betrag: EUR 368.749,42
- brief_010 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): adresse: Unter den Linden 29; plz_ort: 59065 Hamm; iban: AT30 9661 7904 4115 8545; steuernummer: 9081577740992; steuer_id: 27 296 308 016; geburtsdatum: 24.03.99; telefon: 0049 151 87578552; kennzeichen: B-C 3228E; betrag: EUR 364.764,48; datum: 3. August 2025
- brief_011 (interner Aktenvermerk des Steuerberaters): person: Katarzyna Petrenko; plz_ort: 58239 Schwerte; iban: AT24 7869 7702 7105 9105; steuer_id: 97 554 818 445; geburtsdatum: 08.07.92; telefon: 0049 151 05780450; email: katarzyna.petrenko@t-online.de; kennzeichen: DO CZ 063; datum: 7. März 2023
- brief_012 (WhatsApp-artige kurze Nachricht, umgangssprachlich mit Tippfehlern): iban: AT66 6805 3008 8488 9577; steuernummer: 7329083717886; steuer_id: 54 005 959 002; telefon: (0231) 01 78 65; email: swetlana.weiss@t-online.de; kennzeichen: B-C 2039E

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).