"""Exemplu de lucru: 2 contracte noi si 5 e-Facturi, in exemplu/ (de mutat manual unde trebuie).

  CURIER RAPID TEST SRL  RO48151628  contract C-300/2026 (servicii, RON)
  CAFEA BIROU TEST SRL   RO13579134  contract C-400/2026 (produse, RON)

Rulare: python scripts/genereaza_exemplu.py
"""
import zipfile
from pathlib import Path

from genereaza_date_test import FIRMA, contract_pdf, ubl

ROOT = Path(__file__).resolve().parent.parent / "exemplu"
CURIER = ("CURIER RAPID TEST SRL", "RO48151628", "J40/4815/2019", "Str. Livezii 7", "SECTOR2", "RO-B")
CAFEA = ("CAFEA BIROU TEST SRL", "RO13579134", "J35/1357/2017", "Str. Aradului 12", "Timisoara", "RO-TM")

FACTURI = [
    ("4400000001.zip", "[OK] conform", ubl("CR-501", "2026-10-19", "2026-11-03", CURIER, [
        ("Livrare colet standard", "C62", 40, "18.00", 21)])),
    ("4400000002.zip", "[X] pret express +4 lei/colet", ubl("CR-502", "2026-10-21", "2026-11-05", CURIER, [
        ("Livrare colet express", "C62", 10, "39.00", 21)])),
    ("4400000003.zip", "[OK] conform", ubl("CB-71", "2026-10-20", "2026-11-19", CAFEA, [
        ("Cafea boabe 1 kg", "KGM", 8, "95.00", 21), ("Lapte UHT 1L", "H87", 24, "7.50", 21)])),
    ("4400000004.zip", "[X] cantitate cafea depasita (8 + 15 > 20 kg)", ubl("CB-72", "2026-10-22", "2026-11-21", CAFEA, [
        ("Cafea boabe 1kg", "KGM", 15, "95.00", 21)])),
    ("4400000005.zip", "[X] articol neidentificat + scadenta 7 zile", ubl("CB-73", "2026-10-23", "2026-10-30", CAFEA, [
        ("Lapte UHT 1L", "H87", 12, "7.50", 21), ("Zahar cubic 500g", "H87", 10, "6.20", 21)])),
]


def contracte() -> None:
    contract_pdf(
        ROOT / "contracte" / "C-300-2026 Curier Rapid.pdf",
        "CONTRACT DE PRESTĂRI SERVICII DE CURIERAT\nNr. C-300/2026 din 05.01.2026",
        [
            f"Între {CURIER[0]}, CUI {CURIER[1]}, Nr. Reg. Com. {CURIER[2]}, cu sediul în București, {CURIER[3]}, "
            f"în calitate de PRESTATOR, și {FIRMA[0]}, CUI {FIRMA[1]}, în calitate de BENEFICIAR.",
            "Art. 1. Prestatorul asigură ridicarea și livrarea coletelor beneficiarului pe teritoriul României.",
            "Art. 2. Contractul este valabil în perioada 05.01.2026 – 31.12.2026.",
            "Art. 3. Tarifele din Anexa 1 sunt exprimate în lei, fără TVA (cota 21%). Valoarea maximă a "
            "contractului este de 2.000,00 lei fără TVA.",
            "Art. 4. Plata se face în termen de 15 zile de la data emiterii facturii.",
        ],
        [("Nr.", "Serviciu", "UM", "Tarif unitar", "Cantitate max."),
         ("1", "Livrare colet standard", "colet", "18,00 lei", "-"),
         ("2", "Livrare colet express", "colet", "35,00 lei", "-")],
    )
    contract_pdf(
        ROOT / "contracte" / "C-400-2026 Cafea Birou.pdf",
        "CONTRACT DE FURNIZARE PRODUSE\nNr. C-400/2026 din 10.01.2026",
        [
            f"Între {CAFEA[0]}, CUI {CAFEA[1]}, Nr. Reg. Com. {CAFEA[2]}, cu sediul în {CAFEA[4]}, {CAFEA[3]}, "
            f"în calitate de FURNIZOR, și {FIRMA[0]}, CUI {FIRMA[1]}, în calitate de CUMPĂRĂTOR.",
            "Art. 1. Furnizorul livrează cafea și produse pentru bucătăria de birou, conform Anexei 1.",
            "Art. 2. Contractul este valabil în perioada 10.01.2026 – 31.12.2026.",
            "Art. 3. Prețurile sunt ferme, în lei, fără TVA (cota 21%). Valoarea maximă a contractului este de "
            "3.000,00 lei fără TVA.",
            "Art. 4. Plata se face în termen de 30 de zile de la data emiterii facturii.",
            "Art. 5. Cantitatea maximă de cafea boabe pe durata contractului este de 20 kg.",
        ],
        [("Nr.", "Produs", "UM", "Preț unitar", "Cantitate max."),
         ("1", "Cafea boabe 1 kg", "kg", "95,00 lei", "20"),
         ("2", "Lapte UHT 1L", "buc", "7,50 lei", "-")],
    )


def facturi() -> None:
    folder = ROOT / "efactura"
    folder.mkdir(parents=True, exist_ok=True)
    for name, _, xml in FACTURI:
        with zipfile.ZipFile(folder / name, "w") as zf:
            zf.writestr(name.replace(".zip", ".xml"), xml)
            zf.writestr(f"semnatura_{name.replace('.zip', '.xml')}", "<Signature>test</Signature>")


if __name__ == "__main__":
    contracte()
    facturi()
    print(f"Exemplu generat în {ROOT}")
    for name, expected, _ in FACTURI:
        print(f"  {name}: {expected}")
