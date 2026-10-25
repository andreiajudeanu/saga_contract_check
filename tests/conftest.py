from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from saga_check.bnr import BnrRates
from saga_check.models import CheckResult, Contract, ContractArticol, Invoice

FIXTURES = Path(__file__).parent / "fixtures"

BNR_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<DataSet xmlns="http://www.bnr.ro/xsd"><Body>
  <Cube date="2026-11-04"><Rate currency="EUR">5.0000</Rate><Rate currency="HUF" multiplier="100">1.3000</Rate></Cube>
  <Cube date="2026-11-06"><Rate currency="EUR">5.1000</Rate></Cube>
</Body></DataSet>"""


@pytest.fixture
def rates():
    return BnrRates(fetch=lambda url: BNR_XML)


def contract(**kw) -> Contract:
    base = dict(
        id=1, furnizor_cif="12345678", nr_contract="C-12", data_start=date(2026, 1, 1),
        data_end=date(2026, 12, 31), moneda="RON", plafon_valoare=Decimal("10000"),
        termen_plata_zile=30, cota_tva=Decimal("21"),
        articole=[
            ContractArticol(id=10, denumire="Hârtie copiator A4 80g", pret_unitar=Decimal("25.00"), cod="HA4"),
            ContractArticol(id=11, denumire="Servicii mentenanță IT", pret_unitar=Decimal("500.00"),
                            cantitate_max=Decimal("12")),
        ],
    )
    base.update(kw)
    return Contract(**base)


class FakeRepo:
    def __init__(self, contracts: list[Contract]):
        self.contracts = contracts
        self.saved: list[tuple[Invoice, CheckResult, str]] = []

    def contracts_for_cif(self, cif):
        return [c for c in self.contracts if c.furnizor_cif == cif]

    def mapari(self, cif):
        return {}

    def is_processed(self, inv):
        return any((i.furnizor_cif, i.nr, i.data) == (inv.furnizor_cif, inv.nr, inv.data) for i, _, _ in self.saved)

    def consum_valoare(self, contract_id):
        return sum((c.valoare_contract for _, r, _ in self.saved for c in r.consum if c.contract_id == contract_id),
                   Decimal(0))

    def consum_cantitate(self, articol_id):
        return sum((c.cantitate for _, r, _ in self.saved for c in r.consum if c.contract_articol_id == articol_id),
                   Decimal(0))

    def forget_processed(self, inv):
        key = (inv.furnizor_cif, inv.nr, inv.data)
        self.saved = [s for s in self.saved if (s[0].furnizor_cif, s[0].nr, s[0].data) != key]

    def save_processed(self, inv, result, path):
        self.saved.append((inv, result, path))
