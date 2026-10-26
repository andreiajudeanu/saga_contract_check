AIWarriors: Ajudeanu Andrei, Lacatusu Daniel, Bondaret Lucas, Mirauta Bogdan;
# Verificare factură ↔ contract pentru SAGA C

Pentru fiecare e-Factură primită, aplicația verifică dacă respectă contractul furnizorului și pregătește
fișierul de import SAGA. Rezultatul apare în SAGA, în Intrări, în coloana **„Informații suplimentare”**
de pe liniile facturii:

| Linie | Exemplu |
|---|---|
| linia 1 = verdictul întregii facturi | `[OK] Conform contract C-300/2026` |
| | `[X] C-300/2026: Pret linia 1: +4,00 lei/unit.` |
| | `[X] C-400/2026: Articol neidentificat: linia 2; Scadenta 7 zile < 30 din contract` |
| | `[X] Contract neclar C-7 - verificare necesara` / `[X] Fara contract pentru furnizor` |
| celelalte linii | `[OK]`, `[OK] linie conforma`, `[X] Articol neidentificat in contract`, `[X] vezi linia 1` |

Contabilul nu are nimic de făcut în plus: pornește SAGA cu `porneste_saga.bat` și importă din
`Import verificat` cu **Import date** (în loc de „Import e-Facturi primite”). Bifa e deja pe factură.

Procesul complet, pas cu pas, e descris în [PROCES.md](PROCES.md).

## Cum funcționează
```
C:\SAGA C.3.0\Contracte (PDF) ─► citire cu Claude ─► Supabase (Storage privat + tabele)
C:\SAGA C.3.0\e-Factura ───────► verificare ───────► F_<cif>_<nr>_<data>.xml ─► C:\SAGA C.3.0\Import verificat
                                                                                 (SAGA: Import date)
```
- **Contracte**: un PDF nou sau modificat e urcat în bucket-ul privat `contracte` și citit cu Claude.
  Dacă un câmp e nesigur, contractul devine `neclar`, iar facturile lui primesc „Contract neclar”.
- **Facturi**: se iau XML-urile și ZIP-urile din folderul e-Factura al SAGA, cu data ≥ `data_start`.
  Fișierele originale nu se modifică niciodată; aplicația scrie copii noi în `Import verificat`.
- **Verificări**: preț unitar (toleranță 0,01 lei, după conversie la cursul BNR din data facturii),
  valabilitate, plafon valoric și de cantitate cumulat pe toată durata contractului, monedă, scadență,
  cotă TVA. Legătura cu contractul se face după CIF furnizor + denumire articol (potrivire aproximativă).
  Fiecare abatere începe cu numărul contractului.
- **Fără dubluri**: fiecare factură se procesează o singură dată (tabelul `facturi_procesate`), deci
  plafoanele nu se adună de două ori. Facturile deja înregistrate în SAGA nu se ating.

## Instalare
1. Python ≥ 3.12, apoi în acest folder: `python -m pip install -e .[dev]`.
   Dacă mutați folderul proiectului, rulați din nou comanda din noul loc.
2. În Supabase → SQL Editor rulați [sql/schema.sql](sql/schema.sql).
3. Copiați `config.example.toml` în `config.toml` și `.env.example` în `.env`, apoi completați-le.
   În `.env` puneți cheia **service_role** din Supabase (cu cheia anon, scrierea e blocată de RLS).
   `.env` și `config.toml` nu se pun pe git.
4. Creați folderele din `config.toml` (implicit `C:\SAGA C.3.0\Contracte` și `Import verificat`).

## Utilizare
| Fișier | Ce face |
|---|---|
| `porneste_saga.bat` | citește contractele noi, verifică facturile noi, apoi deschide SAGA. Se folosește în locul iconiței SAGA |
| `ruleaza.bat` | același lucru, fără să deschidă SAGA |
| `reproceseaza.bat` | verifică din nou **toate** facturile și rescrie fișierele din `Import verificat` (după ce ați schimbat un contract sau ați șters fișierele) |

Din linia de comandă:
```
python -m saga_check --config config.toml                 # tot fluxul
python -m saga_check --config config.toml --fortat        # recitește toate contractele
python -m saga_check --config config.toml --reproceseaza  # reverifică toate facturile
python -m saga_check.verifica factura.zip --config config.toml   # o factură, fără să salveze nimic
```
Programare automată la 15 minute și la logare: `powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1`.

În SAGA: **Import date** → folderul `Import verificat` → **Import** → **Validare**.

Logurile se scriu în folderul `log` din config. O factură care nu poate fi convertită corect
(de ex. totalurile nu se potrivesc) **nu** se scrie, ca să nu intre greșit în SAGA.

## Date de test
- `python scripts/genereaza_exemplu.py`: 2 contracte PDF (C-300/2026 curierat, C-400/2026 cafea) și
  5 e-Facturi, una conformă și restul cu abateri diferite, în folderul `exemplu/`.
- `python scripts/rulare_locala.py --config config.toml`: rulare fără Supabase și fără Claude.
- `python -m pytest`: testele automate.

## Comportamentul SAGA C (testat)
- SAGA afișează doar ASCII în „Informații suplimentare” (ț/ș și ✔/✘ devin „?”), de aceea textul
  e trimis fără diacritice, cu `[OK]` / `[X]` (`simboluri = "ascii"`).
- Fără cont pe linie, SAGA dă „Cont invalid” și importă doar antetul. Cu `cont = "3028"` liniile intră
  complet și factura se validează; tipul articolului rămâne „Nedefinit”, dar nu blochează validarea.
  Gestiunea nu e necesară. Un articol din contract poate avea cont propriu (`contract_articole.cont`).
- Formatul `dd.mm.yyyy` și numele `F_<CIF firmă>_<nr>_<data>.xml` (`cif_in_nume_fisier = "firma"`)
  sunt acceptate.
- SAGA **copiază** fișierele la prima listare în `C:\SAGA C.3.0\import\<cod firmă>\` și importă de acolo.
  Un fișier regenerat cu **același nume** nu e recitit: SAGA folosește copia veche.
- SAGA **ține minte numerele de factură** văzute în Import date (chiar neimportate) și nu le mai afișează.
  Lista nu se poate goli din afara SAGA. Pentru o demonstrație nouă folosiți facturi cu numere noi
  sau o firmă de test nouă.
- Facturile neconforme se importă oricum; motivul e în „Informații suplimentare”.

## Pentru admin
- O potrivire greșită sau lipsă de articol se corectează în tabelul `mapari_articole`
  (`denumire_factura` normalizată: litere mici, fără diacritice).
- Un contract `neclar`: vedeți motivele în `contracte.detalii_neclare`. Corectați rândul direct
  și setați `status = 'clar'`, sau înlocuiți PDF-ul.
