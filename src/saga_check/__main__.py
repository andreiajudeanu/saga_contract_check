"""Tot fluxul intr-o singura comanda: contracte noi -> verificare facturi -> XML-uri pentru SAGA.

Rulare: python -m saga_check --config config.toml
"""
import argparse
import logging
import os
from pathlib import Path

import anthropic

from . import config as cfg
from .bnr import BnrRates
from .contracts_sync import sync
from .db import SupabaseRepo
from .invoices_run import find_invoices, process
from .logs import setup_logging

log = logging.getLogger("saga_check")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("config.toml"))
    ap.add_argument("--fortat", action="store_true", help="reciteste toate contractele")
    ap.add_argument("--reproceseaza", action="store_true",
                    help="verifica din nou toate facturile din folderul e-Factura si rescrie fisierele")
    args = ap.parse_args()
    c = cfg.load(args.config)
    setup_logging(c.log_dir, "saga_check.log")
    repo = SupabaseRepo()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        sync(c, repo, anthropic.Anthropic(api_key=api_key), fortat=args.fortat)
    else:
        log.warning("Lipseste ANTHROPIC_API_KEY: contractele noi nu sunt citite, folosesc ce e deja in baza")

    n = process(c, repo, BnrRates(store=repo), reproceseaza=args.reproceseaza)
    log.info("Gata: %d facturi noi in %s. In SAGA: Import date din acest folder.", n, c.import_dir.resolve())
    if n == 0 and not args.reproceseaza and find_invoices(c) and not any(c.import_dir.glob("*.xml")):
        log.warning("Folderul de import e gol, dar facturile din e-Factura sunt deja procesate. "
                    "Daca ai sters fisierele si vrei sa le regenerezi, ruleaza reproceseaza.bat.")


if __name__ == "__main__":
    main()
