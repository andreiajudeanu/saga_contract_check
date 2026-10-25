"""Verifica una sau mai multe e-Facturi (XML/ZIP) si afiseaza rezultatul, fara sa scrie nimic.

Util pentru o factura deja inregistrata in SAGA: textul afisat se poate copia manual in
"Informatii suplimentare". Nu se salveaza in baza de date, deci nu consuma din plafoane.
Pentru o factura deja procesata se afiseaza rezultatul salvat atunci.

Rulare: python -m saga_check.verifica factura.xml [alta.zip ...] --config config.toml
"""
import argparse
import sys
from pathlib import Path

from . import config as cfg
from .bnr import BnrRates
from .db import SupabaseRepo
from .rules import Settings, verifica
from .saga_xml import saga_text
from .ubl import load_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fisiere", type=Path, nargs="+")
    ap.add_argument("--config", type=Path, default=Path("config.toml"))
    args = ap.parse_args()
    c = cfg.load(args.config)
    repo = SupabaseRepo()
    rates = BnrRates(store=repo)
    s = Settings(c.toleranta_pret, c.prag_potrivire, c.simboluri, c.lungime_max_mesaj)
    for path in args.fisiere:
        try:
            inv = load_file(path)
            # O factura deja procesata e deja in plafoane; recalculata, s-ar aduna a doua oara.
            if (salvat := repo.processed_message(inv)) is not None:
                print(f"{inv.furnizor.nume} {inv.nr} din {inv.data:%d.%m.%Y} (deja procesata):")
                print(f"  {saga_text(salvat)}")
                continue
            r = verifica(inv, repo.contracts_for_cif(inv.furnizor_cif), rates, s,
                         repo.consum_valoare, repo.consum_cantitate, repo.mapari(inv.furnizor_cif))
        except Exception as e:  # un fisier gresit nu opreste restul
            print(f"{path.name}: EROARE {e}", file=sys.stderr)
            continue
        print(f"{inv.furnizor.nume} {inv.nr} din {inv.data:%d.%m.%Y}:")
        print(f"  {saga_text(r.mesaj)}")
        for nr, msg in sorted(r.abateri_linii.items()):
            print(f"  linia {nr}: {saga_text(msg)}")


if __name__ == "__main__":
    main()
