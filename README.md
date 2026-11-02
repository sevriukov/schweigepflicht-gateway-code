# Schweigepflicht-Gateway – Programmcode der Anonymisierung

**Stand: 02.11.2026 (v0.3.0).** Programmcode zum Arbeitsschema [Schweigepflicht-Gateway](https://github.com/sevriukov/schweigepflicht-gateway) (DOI 10.5281/zenodo.23282323): Anonymisierung von Mandantenunterlagen durch Code, bevor ein Text an ein externes Sprachmodell geht, und Kontrolle jedes ausgehenden Textes.

Autor: Sergei Sevriukov, LeckerMath, Dortmund · https://leckermath.de

> **Neu veröffentlicht – Ergebnis von über vier Jahren Arbeit.** Dieses Repositorium ist neu angelegt; die Commit-Historie beginnt mit der Veröffentlichung. Der Code ist das Ergebnis meiner Arbeit seit 2022 (die Idee stammt aus der Bankanalyse um 2000): zuerst allein, mit kleinem Budget und vielen Sackgassen, ab August 2026 systematisch neu aufgebaut und gemessen. Weitere Teile folgen schrittweise in weiteren Versionen. Wie es entstanden ist: https://leckermath.de/entstehung.html
>
> *Newly published – the result of more than four years of work (since 2022; the idea goes back to bank analysis around 2000). The commit history starts at publication; further parts will follow in later versions.*
Lizenz: Code AGPL-3.0 (`LICENSE`); Texte, Berichte und erfundene Testbriefe CC BY 4.0.

## Inhalt

| Pfad | Zweck |
|---|---|
| `anonymizer.py` | Regeln (IBAN, Steuernummer, USt-IdNr., Steuer-ID, Telefon, E-Mail, Kennzeichen, Geburtsdatum, Anschrift), Namenserkennung mit spaCy (de; en/ru ergänzend), Übertragung erkannter Namensteile auf den ganzen Text. Stufe 1: nur was auf Person oder Firma hinweist; Beträge und Daten bleiben. |
| `exchange.py` | Austauschblatt: durchgehende Masken (`[Person 3]`, `[Firma 7]`), Schlüssel bleibt lokal, Nachlese-Regeln (Tabellenspalten mit Namen, Vertragsnummern, Koordinaten, Straßen ohne Hausnummer, Nachnamen in allen Formen), Rückübersetzung der Antwort. |
| `anon_ru.py` | Russischsprachige Texte. |
| `anon_paket.py` | Ablauf für eine ganze Akte (PDF, Bilder mit OCR, Tabellen, xlsx): Text → Austauschblatt → Prüfblatt. Freigabe nur durch einen Menschen mit einem Code aus dem Prüfblatt. |
| `anon_echtpruef.py` | Prüfung gegen die Originale einer Akte: Sollwerte aus Tabellenspalten und Mustern, Ausgabe nur als Zahlen. |
| `pruefe_oeffentlich.py` | Prüfung eines Ordners vor Veröffentlichung auf Werte aus Schlüsseln der Fall-Imitationen, Zugangsschlüssel, persönliche Pfade. |
| `eval_anonymize*.py` | Messung auf erfundenen Briefen (de, en, ru). |
| `anonymize_test/letters*.json` | Erfundene Briefe mit bekannten Daten. Namen, Anschriften und Nummern sind zufällig aus Listen erzeugt; Übereinstimmungen mit echten Personen sind Zufall. |
| `anonymize_test/REPORT*.md` | Messberichte (russisch, Tabellen selbsterklärend). |
| `versteckt.py` | Verborgene Inhalte der Akte (v0.2): unsichtbarer Text in PDF (weiß, < 3 pt, außerhalb der Seite) wird nicht übernommen; gelöschte Änderungen und versteckter Text in DOCX ebenso; ausgeblendete Blätter, Zeilen und Spalten in XLSX werden im Text gekennzeichnet; E-Mail ohne technische Kopfzeilen; Metadaten (PDF, DOCX, EXIF) werden gezählt, nicht übernommen. `injektion()`: Anweisungen an ein Sprachmodell im Text der Unterlagen. |
| `ausgangslog.py` | Siegel des Ausgangsprotokolls als Hash-Kette (HMAC-SHA256, Schlüssel lokal): Änderung, Löschung oder Umstellung einer bereits gesiegelten Zeile wird erkannt. |
| `eval_anonymize_angriffe.py` | Angriffe auf die Anonymisierung (v0.2): Homoglyphen, unsichtbare Zeichen, Trennung im Namen, Sperrschrift, Großschreibung, Namen als gewöhnliche Wörter, Namen in URL/Formel/Dateiname, IBAN in Worten, Aktenzeichen. |
| `eval_versteckt.py` | Prüfung von `versteckt.py` an erfundenen Dateien (PDF, DOCX, XLSX, EML, Foto, Anweisungen). |
| `de_wortliste*.txt.gz` | `de_wortliste_gesetz.txt.gz`: Wörter aus Gesetzen und BMF-Schreiben (≥ 4 Buchstaben, ≥ 3 Vorkommen). `de_wortliste.txt.gz`: Wörter aus einer Stichprobe der gesamten Rechtsdatenbank (enthält auch Nachnamen aus Urteilen; für Namensregeln wird deshalb die Gesetzesliste benutzt). |

## Messstand 19.10.2026 (v0.2.0)

Gezählt werden nur Daten, die auf eine Person oder Firma hinweisen (`eval_anonymize.py run --v2 --ident`); Beträge und Daten bleiben in Stufe 1 absichtlich stehen.

| Satz erfundener Briefe | Briefe mit mindestens einem Rest | Reste |
|---|---:|---|
| v2 | 0 von 35 | – |
| holdout | 0 von 41 | – |
| wild | 8 von 40 | 1 von 82 Namen, Firmen- und Ladennamen (5), Finanzamt mit Ortsangabe (2), Bankname (1) |
| wild2 | 1 von 40 | 1 Firmenname |

- **Berichtigung zu v0.1:** Der Messstand 16.10.2026 nannte „0 verbliebene Kennungen“ für alle Sätze. Für die Sätze wild und wild2 galt das nur für einen Teil der Datenarten; nach heutiger Zählung blieben in v0.1 Reste in 14 von 40 (wild) und 4 von 40 (wild2) Briefen, darunter 2 von 82 Namen, Grundbuch- und Flurstücksangaben, Fahrgestell-, Beleg- und Mandantennummern.
- Angriffe (`eval_anonymize_angriffe.py`, 29 Angriffe, 50 Proben): 1 Rest – Genitiv eines Nachnamens ohne Vornamen und ohne frühere Nennung („Habermehls Firmenwagen“); das erkennt nur die Namenserkennung oder der Mensch bei der Freigabe. Öffentliche Fundstellen (BFH, FG, BVerfG mit Aktenzeichen) bleiben vollständig stehen.
- Verborgene Inhalte (`eval_versteckt.py`): 22 von 22 Prüfungen bestanden.
- Russisch: 0 %; Englisch: 1 Rest (O'Connor).

### Bekannte Grenzen

- Genitiv eines allein stehenden Nachnamens; Namen direkt nach einer Funktionsbezeichnung, die die Namenserkennung zuvor als Firma maskiert hat.
- Firmen- und Ladennamen aus gewöhnlichen Wörtern („Goldener Drache“), Finanzamt und Bank mit Ortsangabe.
- Kombination von Fakten (genaue Beträge, Daten, Branche, Ort) kann auch ohne Namen auf eine Person führen; eine Messung dieser Eindeutigkeit vor dem Versand ist noch nicht enthalten.
- Das Siegel des Ausgangsprotokolls schützt nicht gegen den Inhaber des Schlüssels selbst; dafür den Kettenkopf zusätzlich außerhalb des Rechners festhalten.
- Ein Freigabe-Schritt durch eine zweite Person ist nicht vorgesehen.

## Ausführen

```
pip install spacy openpyxl requests && python -m spacy download de_core_news_sm
python3 eval_anonymize.py run --v2          # Messung auf den erfundenen Briefen
python3 eval_anonymize_angriffe.py         # Angriffe auf die Anonymisierung
python3 eval_versteckt.py                  # verborgene Inhalte (PDF, DOCX, XLSX, EML, Foto)
python3 ausgangslog.py pruefen             # Siegel des Ausgangsprotokolls prüfen
python3 anon_paket.py <Aktenordner>         # Austauschblatt + Prüfblatt; Freigabe: --freigabe <CODE aus dem Prüfblatt>
```

Gelernte Ergänzungen schreibt `anonymizer.py` nach `~/.config/leckermath/` – außerhalb des Repositoriums, damit Namen der Fall-Imitationen nie in den Code gelangen.

## Nicht enthalten

Rechtsdatenbank, Modelle, Zugangsschlüssel, Daten der Fall-Imitationen, Ausgangsprotokoll, interne Arbeitsjournale.
