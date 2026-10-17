# Проверка обезличивания — 16.10.2026 20:53

Писем: 35 (придуманные, данные известны заранее). Обезличивание: `anonymize_hard` (версия 1), до любого ИИ.

| Вид данных | Всего | Осталось в тексте | Доля утечки |
|---|---:|---:|---:|
| steuer_id | 35 | 35 | 100 % |
| telefon | 35 | 35 | 100 % |
| kennzeichen | 35 | 29 | 83 % |
| email | 35 | 20 | 57 % |
| plz_ort | 35 | 14 | 40 % |
| adresse | 35 | 13 | 37 % |
| person | 70 | 15 | 21 % |
| firma | 35 | 0 | 0 % |
| iban | 35 | 0 | 0 % |
| steuernummer | 35 | 0 | 0 % |
| ust_id | 35 | 0 | 0 % |
| geburtsdatum | 35 | 0 | 0 % |
| betrag | 35 | 0 | 0 % |
| datum | 34 | 0 | 0 % |

**Писем хотя бы с одной утечкой: 35 из 35.** Из них контроль исходящих (`outbound_guard`) остановил бы: 28.

Примеры утечек:
- brief_001 (Telefonnotiz der Kanzleimitarbeiterin): steuer_id: 26 309 375 042; telefon: +49 179 4313700; kennzeichen: HAM-KT 6819
- brief_002 (E-Mail des Mandanten an die Kanzlei): person: Katarzyna Kowalczyk; plz_ort: 44649 Wanne-Eickel; steuer_id: 70 436 931 269; telefon: 0231 989321; email: katarzyna.kowalczyk@t-online.de; kennzeichen: MK-AW 8210
- brief_003 (interner Aktenvermerk des Steuerberaters): person: Nguyen Van Petrenko; adresse: Zum Mühlenteich 177a; steuer_id: 62 357 593 889; telefon: 0231 403586; email: nguyen.petrenko@t-online.de; kennzeichen: EN-EW 5103
- brief_004 (förmlicher Brief des Mandanten): steuer_id: 55 722 270 840; telefon: 02355/51316; kennzeichen: MK-EW 6119
- brief_005 (interner Aktenvermerk des Steuerberaters): steuer_id: 59 016 063 073; telefon: 02356/57904; email: dragan.elmasri@web.de; kennzeichen: MK-FT 1733
- brief_006 (interner Aktenvermerk des Steuerberaters): steuer_id: 59 999 979 606; telefon: 02368/32967; email: annegret.grossekathoefer@web.de; kennzeichen: MK-FR 3358
- brief_007 (interner Aktenvermerk des Steuerberaters): adresse: An der Palmweide 122a; plz_ort: 59065 Hamm; steuer_id: 82 388 718 343; telefon: +49 175 6379949; kennzeichen: MK-MT 1570
- brief_008 (förmlicher Brief des Mandanten): person: Nguyen Van Hoffmann; adresse: Am Kattenbusch 66a; steuer_id: 67 803 225 246; telefon: 02360/95699; email: nguyen.hoffmann@gmx.de
- brief_009 (interner Aktenvermerk des Steuerberaters): person: Swetlana Oberhuber; adresse: Am Kattenbusch 188; plz_ort: 58452 Witten; steuer_id: 83 381 065 434; telefon: +49 177 5520083; email: swetlana.oberhuber@web.de; kennzeichen: HAM-DN 468
- brief_010 (Telefonnotiz der Kanzleimitarbeiterin): steuer_id: 45 091 658 991; telefon: 0231 285204
- brief_011 (förmlicher Brief des Mandanten): plz_ort: 58507 Lüdenscheid; steuer_id: 09 328 893 461; telefon: +49 174 3821981; email: sabine.schulteuebbing@gmx.de; kennzeichen: MK-KV 2794
- brief_012 (Telefonnotiz der Kanzleimitarbeiterin): person: Maximilian Lindqvist; plz_ort: 58239 Schwerte; steuer_id: 38 995 093 051; telefon: 0231 881006; email: maximilian.lindqvist@web.de; kennzeichen: EN-MV 4255

Оговорка: письма написаны моделью по заданным данным; суммы и даты считаются «утечкой», только если остались дословно (округление — допустимо).