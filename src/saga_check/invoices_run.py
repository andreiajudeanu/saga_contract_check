"""Facturi noi din folderul e-Factura al SAGA -> verificare -> XML de import cu rezultatul.

Rulare: python -m saga_check.invoices_run --config config.toml
"""
import argparse
import logging
from pathlib import Path
from typing import Protocol

from . import config as cfg
from .bnr import BnrRates
from .models import CheckResult, Contract, Invoice, normalize_cif
from .rules import Settings, verifica
from .saga_xml import SagaSettings, build, file_name, write_atomic
from .ubl import NotAnInvoice, load_file
from .logs import setup_logging

log = logging.getLogger("facturi")


class Repo(Protocol):
    def contracts_for_cif(self, cif: str) -> list[Contract]: ...
    def mapari(self, cif: str) -> dict[str, int]: ...
    def is_processed(self, inv: Invoice) -> bool: ...
    def consum_valoare(self, contract_id: int): ...
    def consum_cantitate(self, articol_id: int): ...
    def save_processed(self, inv: Invoice, result: CheckResult, saga_path: str) -> None: ...
    def forget_processed(self, inv: Invoice) -> None: ...


def find_invoices(c: cfg.Config) -> list[Invoice]:
    """Facturi primite de firma, de la data_start incolo, o singura data fiecare (XML si ZIP pot coexista)."""
    firma = normalize_cif(c.firma_cif)
    seen: dict[tuple, Invoice] = {}
    for path in sorted(c.efactura_dir.rglob("*")):
        if path.suffix.lower() not in (".xml", ".zip") or path.name.lower().startswith("semnatura"):
            continue
        try:
            inv = load_file(path)
        except NotAnInvoice:
            continue
        except Exception:
            log.exception("nu pot citi %s", path)
            continue
        if normalize_cif(inv.client.cif) != firma or inv.furnizor_cif == firma or inv.data < c.data_start:
            continue
        key = (inv.furnizor_cif, inv.nr, inv.data)
        # Preferam varianta cu index SPV (ZIP-ul original) cand avem ambele.
        if key not in seen or (inv.index_descarcare_spv and not seen[key].index_descarcare_spv):
            seen[key] = inv
    # Ordine cronologica, ca plafoanele cumulate sa se consume in ordinea reala.
    return sorted(seen.values(), key=lambda i: (i.data, i.furnizor_cif, i.nr))


def process(c: cfg.Config, repo: Repo, rates: BnrRates, reproceseaza: bool = False) -> int:
    """reproceseaza=True: uita intai toate facturile din folder, apoi le verifica din nou in ordinea datei,
    ca plafoanele sa se recalculeze fara dublare. Fisierele din import_saga se rescriu."""
    s = Settings(c.toleranta_pret, c.prag_potrivire, c.simboluri, c.lungime_max_mesaj)
    ss = SagaSettings(c.firma_cif, c.format_data, c.cif_in_nume_fisier,
                      c.gestiune, c.activitate, c.cont, c.tip_deducere)
    written = 0
    invoices = find_invoices(c)
    if reproceseaza:
        for inv in invoices:
            repo.forget_processed(inv)
    for inv in invoices:
        try:
            if repo.is_processed(inv):
                continue
            result = verifica(inv, repo.contracts_for_cif(inv.furnizor_cif), rates, s,
                              repo.consum_valoare, repo.consum_cantitate, repo.mapari(inv.furnizor_cif))
            data = build(inv, result, ss)
            # Intai fisierul, apoi baza de date: daca salvarea cade, rularea urmatoare rescrie acelasi fisier.
            target = write_atomic(c.import_dir, file_name(inv, ss), data)
            repo.save_processed(inv, result, str(target))
            written += 1
            log.info("%s %s -> %s", inv.furnizor.nume, inv.nr, result.mesaj)
        except Exception:
            log.exception("factura %s / %s (%s) nu a fost generata", inv.furnizor.nume, inv.nr, inv.sursa)
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("config.toml"))
    c = cfg.load(ap.parse_args().config)
    setup_logging(c.log_dir, "facturi.log")
    from .db import SupabaseRepo
    repo = SupabaseRepo()
    n = process(c, repo, BnrRates(store=repo))
    log.info("%d facturi noi pregătite pentru import", n)


if __name__ == "__main__":
    main()
