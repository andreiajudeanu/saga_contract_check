"""Rulare de proba FARA Supabase si FARA Claude: contractele de test sunt definite mai jos, asa cum
le-ar extrage Claude din PDF-urile generate de genereaza_date_test.py. Produce XML-urile pentru SAGA
in folderul import_saga din config, ca sa poata fi testat importul in SAGA C.

Rulare: python scripts/rulare_locala.py --config config.toml
"""
import argparse
import shutil
import sys
from datetime import date
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from saga_check import config as cfg  # noqa: E402
from saga_check.bnr import BnrRates  # noqa: E402
from saga_check.invoices_run import process  # noqa: E402
from saga_check.models import Contract, ContractArticol  # noqa: E402

CONTRACTE = [
    Contract(id=1, furnizor_cif="76543210", nr_contract="C-100/2026", data_start=date(2026, 1, 1),
             data_end=date(2026, 12, 31), moneda="RON", plafon_valoare=D("5000"), termen_plata_zile=30,
             cota_tva=D("21"), articole=[
                 ContractArticol(id=11, denumire="Hârtie copiator A4 80g/mp", um="top", pret_unitar=D("25"), cont="3028"),
                 ContractArticol(id=12, denumire="Toner HP 85A", um="buc", pret_unitar=D("320"), cantitate_max=D("10"),
                                 cont="3028"),
                 ContractArticol(id=13, denumire="Dosar plic transparent", um="buc", pret_unitar=D("0.80"), cont="3028"),
             ]),
    Contract(id=2, furnizor_cif="24681350", nr_contract="C-200/2026", data_start=date(2026, 3, 1),
             data_end=date(2027, 2, 28), moneda="EUR", plafon_valoare=D("3000"), termen_plata_zile=15,
             cota_tva=D("21"), articole=[
                 ContractArticol(id=21, denumire="Mentenanță IT lunară", um="lună", pret_unitar=D("250"),
                                 moneda="EUR", cantitate_max=D("12"), cont="628"),
                 ContractArticol(id=22, denumire="Intervenție la sediu", um="oră", pret_unitar=D("40"), moneda="EUR", cont="628"),
             ]),
]


class MemoryRepo:
    def __init__(self):
        self.saved = []

    def contracts_for_cif(self, cif):
        return [c for c in CONTRACTE if c.furnizor_cif == cif]

    def mapari(self, cif):
        return {}

    def is_processed(self, inv):
        return False

    def consum_valoare(self, contract_id):
        return sum((x.valoare_contract for r in self.saved for x in r.consum if x.contract_id == contract_id), D(0))

    def consum_cantitate(self, articol_id):
        return sum((x.cantitate for r in self.saved for x in r.consum if x.contract_articol_id == articol_id), D(0))

    def save_processed(self, inv, result, path):
        self.saved.append(result)
        print(f"  {inv.nr:8} {inv.furnizor.nume:22} -> {result.mesaj}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("config.toml"))
    c = cfg.load(ap.parse_args().config)
    shutil.rmtree(c.import_dir, ignore_errors=True)  # rulare curata de fiecare data
    n = process(c, MemoryRepo(), BnrRates())
    print(f"\n{n} fișiere generate în {c.import_dir}")
