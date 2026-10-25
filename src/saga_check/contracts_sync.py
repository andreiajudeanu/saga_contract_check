"""Sincronizare contracte: PDF nou/modificat -> Storage -> extractie Claude -> tabele.

Rulare: python -m saga_check.contracts_sync --config config.toml
"""
import argparse
import os
import hashlib
import logging
from datetime import date
from pathlib import Path

import anthropic

from . import config as cfg
from .db import SupabaseRepo
from .extract import VERSIUNE_EXTRACTIE, ContractExtras, ExtractionRefused, evalueaza, extrage
from .logs import setup_logging

log = logging.getLogger("contracte")


def _date_errors(ex: ContractExtras) -> list[str]:
    errors = []
    for camp in ("data_start", "data_end"):
        v = getattr(ex, camp)
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                errors.append(f"{camp}: dată invalidă „{v}”")
                setattr(ex, camp, None)
    return errors


def sync(c: cfg.Config, repo: SupabaseRepo, client: anthropic.Anthropic, fortat: bool = False) -> None:
    for pdf in sorted(c.contracte_dir.rglob("*.pdf")):
        rel = pdf.relative_to(c.contracte_dir).as_posix()
        data = pdf.read_bytes()
        sha = f"{hashlib.sha256(data).hexdigest()}-v{VERSIUNE_EXTRACTIE}"
        if not fortat and repo.contract_sha(rel) == sha:
            continue
        log.info("contract nou/modificat (sau citire actualizata): %s", rel)
        try:
            repo.upload_pdf(rel, data)
            try:
                ex = extrage(data, client, c.claude_model)
                motive = _date_errors(ex) + evalueaza(ex, c.prag_incredere)
            except ExtractionRefused as e:
                ex, motive = None, [str(e)]
            # Un contract fara CIF nu poate fi legat de facturi; il salvam totusi ca "neclar" ca sa nu-l
            # re-extragem la fiecare rulare.
            repo.save_contract(rel, sha, ex, motive)
            log.info("%s -> %s %s", rel, "neclar" if motive else "clar", "; ".join(motive))
            for o in (ex.observatii if ex else []):
                log.info("%s observatie: %s", rel, o)
        except Exception:
            log.exception("eroare la contractul %s", rel)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=Path("config.toml"))
    ap.add_argument("--fortat", action="store_true",
                    help="reciteste toate contractele, chiar daca PDF-ul nu s-a schimbat")
    args = ap.parse_args()
    c = cfg.load(args.config)
    setup_logging(c.log_dir, "contracte.log")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Lipseste ANTHROPIC_API_KEY in .env")
    sync(c, SupabaseRepo(), anthropic.Anthropic(api_key=api_key), fortat=args.fortat)


if __name__ == "__main__":
    main()
