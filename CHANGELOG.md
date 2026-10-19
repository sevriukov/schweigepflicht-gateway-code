# Änderungen

## v0.2.0 – 19.10.2026

Anlass: kritische Durchsicht des Systems durch zwei externe Sprachmodelle (DeepSeek, Gemini) am 18.10.2026.

- **Vorbereitung jedes Textes** (`anonymizer.vorbereiten`): Unicode-NFKC (außer Hochzahlen und Brüchen), unsichtbare Zeichen entfernt, Wörter aus gemischtem lateinischem und kyrillischem Alphabet vereinheitlicht, Zeilentrennung im Wort zusammengefügt, Sperrschrift zusammengezogen.
- **Neue Regeln:** Internetadressen ohne http (Behördenadressen bleiben), IBAN mit kyrillischem Ländercode, Nummern in Worten, Grundbuch-Blatt und Flurstück, Fahrgestellnummer, MRN (Zoll), USt-IdNr. außerhalb der EU, Nummern mit Bezeichnung (Beleg-, Mandanten-, Berater-Nr. …), Namen nach Funktionsbezeichnung („Sachbearbeiterin: …“), „hr./fr.“ mit kleingeschriebenem Namen.
- **Aktenzeichen:** eigenes Verfahren („Az.“, „Klageverfahren“, „anhängig“) wird vollständig maskiert; Fundstellen veröffentlichter Entscheidungen („vgl. BFH, Urteil vom … – VI R 5/18“) bleiben samt Gericht stehen.
- **Eine Maske je Person:** in Großbuchstaben geschriebener Nachname und von der Namenserkennung als Ort oder Firma maskierte Namensteile erhalten die Maske der Person.
- **Kontrolle `guard()`:** unsichtbare Zeichen im Wort, gemischte Alphabete und Anweisungen an ein Sprachmodell in den Unterlagen gelten als Befund; Freigabe dann nur ausdrücklich.
- **`versteckt.py`** (neu): verborgene Inhalte von PDF, DOCX, XLSX, EML und Fotos; Bericht ohne Inhalte.
- **`ausgangslog.py`** (neu): Hash-Kette über das Ausgangsprotokoll; `anon_paket.py` siegelt bei jeder Freigabe.
- **Austauschblatt:** ein Dokument, das nach Entfernen unlesbarer Stellen zu kurz ist, erscheint als „nicht ausgewertet“ statt stillschweigend zu fehlen.
- **`pruefe_oeffentlich.py`:** Schreibweisen aus der Beteiligtenliste werden ohne Kommentarteil gelesen (vorher wurde hinter dem letzten „|“ teils der Kommentar statt der Schreibweisen geprüft); einzelne gewöhnliche Wörter sind Warnung statt Stopp.
- **Messberichte** neu erzeugt; Berichtigung des Messstands von v0.1 im README.

## v0.1.1 – 17.10.2026

- `guard()`: mehrteilige Werte nur als ganze Wörter; kleingeschriebene Namensteile nur als eigenes Wort.
- Kommentare ohne Bezug auf echte Akten.

## v0.1.0 – 17.10.2026

- Erstveröffentlichung.
