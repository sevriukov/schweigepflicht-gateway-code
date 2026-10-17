# Schweigepflicht-Gateway – Programmcode der Anonymisierung

**Stand: 17.10.2026.** Programmcode zum Arbeitsschema [Schweigepflicht-Gateway](https://github.com/sevriukov/schweigepflicht-gateway) (DOI 10.5281/zenodo.23282323): Anonymisierung von Mandantenunterlagen durch Code, bevor ein Text an ein externes Sprachmodell geht, und Kontrolle jedes ausgehenden Textes.

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
| `pruefe_oeffentlich.py` | Prüfung eines Ordners vor Veröffentlichung auf Werte aus Schlüsseln echter Fälle, Zugangsschlüssel, persönliche Pfade. |
| `eval_anonymize*.py` | Messung auf erfundenen Briefen (de, en, ru). |
| `anonymize_test/letters*.json` | Erfundene Briefe mit bekannten Daten. Namen, Anschriften und Nummern sind zufällig aus Listen erzeugt; Übereinstimmungen mit echten Personen sind Zufall. |
| `anonymize_test/REPORT*.md` | Messberichte (russisch, Tabellen selbsterklärend). |
| `de_wortliste*.txt.gz` | `de_wortliste_gesetz.txt.gz`: Wörter aus Gesetzen und BMF-Schreiben (≥ 4 Buchstaben, ≥ 3 Vorkommen). `de_wortliste.txt.gz`: Wörter aus einer Stichprobe der gesamten Rechtsdatenbank (enthält auch Nachnamen aus Urteilen; für Namensregeln wird deshalb die Gesetzesliste benutzt). |

## Messstand 16.10.2026

- Erfundene deutsche Briefe (Sätze v2, wild, wild2, holdout): 0 verbliebene Kennungen (Personen, Firmen, Anschriften, IBAN, Steuernummern, Telefon, E-Mail, Kennzeichen, Geburtsdaten). Beträge und Daten bleiben in Stufe 1 absichtlich stehen.
- Russisch: 0 %; Englisch: 0,3 % verbliebene Kennungen.
- Erprobung an einer echten Akte (Einzelunternehmen, 4 Jahre, Bescheide, Erklärungen, Buchhaltungsexport, Kontoauszüge): 0 Treffer von 1 892 Sollwerten; unabhängige Gegenprüfung durch einen zweiten Agenten: 0 Treffer. Die Akte selbst und ihre Befunde werden nicht veröffentlicht.
- Bekannte Grenzen: Ladennamen, die einen Inhabernamen enthalten; Händler mit ungewöhnlichen Namen werden teils als Person maskiert; Konzernfirmen können dieselbe Maske erhalten (Sinnfehler, kein Datenabfluss).

## Ausführen

```
pip install spacy openpyxl requests && python -m spacy download de_core_news_sm
python3 eval_anonymize.py run --v2          # Messung auf den erfundenen Briefen
python3 anon_paket.py <Aktenordner>         # Austauschblatt + Prüfblatt; Freigabe: --freigabe <CODE aus dem Prüfblatt>
```

Gelernte Ergänzungen schreibt `anonymizer.py` nach `~/.config/leckermath/` – außerhalb des Repositoriums, damit Namen echter Fälle nie in den Code gelangen.

## Nicht enthalten

Rechtsdatenbank, Modelle, Zugangsschlüssel, Daten echter Fälle, Ausgangsprotokoll, interne Arbeitsjournale.
