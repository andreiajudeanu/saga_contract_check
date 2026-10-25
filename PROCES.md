# Procesul aplicației: contracte → facturi → SAGA C

Aplicația rulează **lângă** SAGA C, pe același calculator. Nu scrie în SAGA: pregătește fișiere pe care
SAGA le importă prin **Import date**. O rulare (`ruleaza.bat`, sau automat din Task Scheduler) face, în
ordine: **A. contractele noi** → **B. facturile noi**. Tot ce citește și scrie e setat în `config.toml`.

## Folderele

| Cheie în `config.toml` | Ce conține | Cine scrie | Cine citește |
|---|---|---|---|
| `contracte_pdf` | PDF-urile contractelor | tu | aplicația |
| `efactura_saga` | e-Facturile primite (ZIP/XML din SPV) | SAGA (descărcare SPV) | aplicația (doar citire) |
| `import_saga` | `F_<cif>_<nr>_<data>.xml` cu rezultatul | aplicația | SAGA → Import date |
| `log` | `saga_check.log`, `erori.log` | aplicația | tu |

Baza de date (Supabase) ține: contractele și articolele lor, PDF-urile (bucket privat `contracte`),
facturile deja procesate și ce au consumat din plafoane, cursurile BNR.

---

## A. Cum ajunge un contract în baza de date

1. **Pui PDF-ul** în folderul `contracte_pdf` (sunt permise și subfoldere). Un contract = un PDF,
   inclusiv anexele cu prețuri. Un act adițional: înlocuiești PDF-ul cu varianta completă.
2. **La următoarea rulare**, pentru fiecare PDF aplicația calculează o amprentă (SHA-256 + versiunea de
   citire). Dacă amprenta e cea salvată, PDF-ul e sărit — nu se plătește nimic.
3. **PDF nou sau modificat:**
   1. se urcă în Supabase Storage (`contracte/<cale relativă>`);
   2. e trimis la Claude, care extrage: CIF și nume furnizor, nr. contract, valabilitate, monedă,
      plafon valoric fără TVA, termen de plată, cotă TVA, articole (denumire, preț unitar fără TVA,
      monedă, UM, cod, cantitate maximă) + câmpurile nesigure și observații;
   3. se evaluează: contractul e **`neclar`** dacă lipsește CIF-ul, nu are niciun articol cu preț,
      o dată e invalidă, un câmp e marcat nesigur sau încrederea e sub `prag_incredere`;
      altfel e **`clar`**;
   4. se salvează în tabelul `contracte` (un rând per PDF) și `contract_articole`. La o recitire,
      articolele cu aceeași denumire se actualizează pe loc, deci **își păstrează** contul setat
      manual, corecțiile din `mapari_articole` și cantitățile deja consumate.
4. **Observațiile** apar doar în log (`... observatie: ...`), nu schimbă statusul.

Ce poți face după (opțional, în Supabase → Table Editor):
- `contract_articole.cont` — contul SAGA pentru articol (ex. 371 marfă, 628 servicii); gol = `cont` din config.
- `contracte` neclar: vezi `detalii_neclare`, corectezi valorile și pui `status = clar`
  (rămâne așa până se schimbă PDF-ul).
- `mapari_articole` — dacă o denumire de pe factură nu e găsită: `furnizor_cif` (doar cifre),
  `denumire_factura` (litere mici, fără diacritice), `contract_articol_id`.

## B. Cum ajunge o factură să fie analizată

1. **SAGA descarcă** e-Factura din SPV în folderul `efactura_saga` (cu codul SPV asociat în SAGA).
   Aplicația nu modifică niciodată fișierele de acolo — sunt originalele legale.
2. **La rulare**, aplicația citește toate `.xml`/`.zip` din folder (ignoră `semnatura_*.xml`) și
   păstrează doar facturile care:
   - au clientul = CIF-ul firmei din config (facturi **primite**);
   - au data ≥ `data_start` (cele vechi, deja în SAGA, nu se ating);
   - **nu** sunt deja în tabelul `facturi_procesate` (fiecare factură se procesează **o singură dată**,
     cheia fiind CIF furnizor + număr + dată).
   Le ia în ordinea datei, ca plafoanele să se consume cronologic.
3. **Găsește contractul**: contractele cu același CIF de furnizor → cele valabile la data facturii →
   pentru fiecare linie, articolul potrivit (mapare manuală → cod articol → denumire asemănătoare,
   scor ≥ `prag_potrivire`).
4. **Verifică**, în ordinea priorității:

   | Situație | Mesaj |
   |---|---|
   | furnizorul nu are niciun contract | `[X] Fara contract pentru furnizor` |
   | are contracte, dar niciunul valabil la data facturii | `[X] Fara contract activ la ZZ.LL.AAAA` |
   | contractul folosit e `neclar` | `[X] Contract neclar ... - verificare necesara` |
   | o linie nu se regăsește în contract | `[X] Articol neidentificat: linia N` |
   | preț unitar diferit (> 0,01 lei, după conversia BNR din data facturii) | `[X] Pret linia N: +X lei/unit.` |
   | cotă TVA diferită | `[X] TVA linia N: 19% in loc de 21%` |
   | monedă nepermisă (alta decât RON sau moneda contractului) | `[X] Moneda ...` |
   | plafon valoric depășit (cumulat cu facturile anterioare) | `[X] Plafon ... depasit cu ...` |
   | cantitate maximă depășită pe articol | `[X] Cantitate "..." depasita cu N` |
   | scadență mai scurtă decât termenul de plată | `[X] Scadenta N zile < M din contract` |
   | totul în regulă | `[OK] Conform contract C-...` |

   Abaterile se adună într-un singur mesaj, separate prin `;`. Notele de credit (storno) scad din plafon.
5. **Scrie fișierul SAGA** `F_<cif>_<nr>_<data>.xml` în `import_saga`, cu toate datele facturii,
   contul pe fiecare linie, rezultatul în `FacturaInformatiiSuplimentare` și mesajul fiecărei linii în
   `InformatiiSuplimentare` (fără diacritice — SAGA nu le afișează). Dacă totalurile nu se potrivesc cu
   factura originală, fișierul **nu** se scrie, iar eroarea apare în `erori.log`.
6. **Înregistrează** factura în `facturi_procesate` (plus consumul din plafoane).
7. **În SAGA**: Import date → cale = `import_saga` → Import → Validare. Rezultatul apare în
   „Informații suplimentare”.

---

## Când se rulează

| Situație | Ce faci |
|---|---|
| Lucru zilnic | Nimic: Task Scheduler rulează aplicația la 15 minute și la logare (`scripts\install_tasks.ps1`). |
| Deschizi SAGA | Pornești SAGA prin `porneste_saga.bat` (verifică întâi facturile, apoi deschide SAGA). |
| Vrei rezultatul imediat (ex. înainte de import) | Dublu-click pe `ruleaza.bat`. |
| Ai adăugat/modificat un contract | Îl pui în folder **înainte** să sosească facturile furnizorului; se citește la următoarea rulare. |
| Vrei să recitești toate contractele | `python -m saga_check --config config.toml --fortat` |
| Vrei să regenerezi facturile (ex. după ce ai corectat un contract) | Dublu-click pe `reproceseaza.bat` — verifică din nou toate facturile din folderul e-Factura, recalculează plafoanele și rescrie fișierele. |
| O singură factură, fără să salvezi nimic | `python -m saga_check.verifica fisier.zip --config config.toml` |

**Rutina recomandată:** SAGA descarcă e-Facturile → aplicația rulează (automat sau `ruleaza.bat`) →
contabilul face Import date din `import_saga`. Facturile nu se mai preiau din „Import e-Facturi primite”
(se marchează *Anulat* acolo), altfel ar intra de două ori.

## Limite de știut

- **Contract adăugat prea târziu:** o factură procesată înainte să existe contractul primește
  `[X] Fara contract` și nu se reverifică automat. Remediu: ștergi rândul ei din `facturi_procesate`
  (Supabase) și fișierul din `import_saga`; dacă era deja importată în SAGA, o ștergi și din Intrări;
  apoi rulezi din nou.
- **SAGA ține copii:** la prima listare, SAGA copiază fișierele în `C:\SAGA C.3.0\import\<cod firmă>\`
  și importă de acolo. Un fișier regenerat cu același nume nu e recitit — ștergi copia veche din acel folder.
  Dar nu ștergi copia unei facturi care încă apare în lista din Import date: SAGA ține lista separat și,
  fără copie, raportează „fișierul XML nu e valid”. Pentru rânduri vechi folosești **Anulare** în SAGA.
- **Facturile deja înregistrate în SAGA** nu primesc retroactiv textul (SAGA C nu are API). Pentru ele:
  `verifica` + copiere manuală, sau ștergere și reimport din `import_saga`.
- **Tip articol „Nedefinit”** în SAGA nu blochează validarea; contul (`cont`, implicit 3028) contează.
