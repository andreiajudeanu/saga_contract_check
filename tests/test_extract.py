from types import SimpleNamespace

import pytest

from saga_check.contracts_sync import _date_errors
from saga_check.extract import ArticolExtras, CampNesigur, ContractExtras, ExtractionRefused, evalueaza, extrage


def extras(**kw) -> ContractExtras:
    base = dict(
        furnizor_cif="RO12345678", furnizor_nume="FURNIZOR TEST SRL", nr_contract="C-12",
        data_start="2026-01-01", data_end="2026-12-31", moneda="RON", plafon_valoare_fara_tva=10000,
        termen_plata_zile=30, cota_tva=21, campuri_nesigure=[], observatii=["plafon atins repede"],
        incredere_generala=0.95,
        articole=[ArticolExtras(denumire="Hârtie A4", cod=None, um="top", pret_unitar_fara_tva=25,
                                moneda="RON", cantitate_max=None, incredere=0.9)],
    )
    base.update(kw)
    return ContractExtras(**base)


class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_extrage_sends_pdf_and_schema():
    msgs = FakeMessages(SimpleNamespace(stop_reason="end_turn", parsed_output=extras()))
    out = extrage(b"%PDF-1.7", SimpleNamespace(messages=msgs), "claude-sonnet-5-5")
    assert out.nr_contract == "C-12"
    doc = msgs.kwargs["messages"][0]["content"][0]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"
    assert msgs.kwargs["output_format"] is ContractExtras


def test_extrage_refusal():
    msgs = FakeMessages(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(ExtractionRefused):
        extrage(b"%PDF", SimpleNamespace(messages=msgs), "m")


def test_evalueaza():
    assert evalueaza(extras(), 0.8) == []
    motive = evalueaza(extras(furnizor_cif=None, incredere_generala=0.5,
                              campuri_nesigure=[CampNesigur(camp="plafon", motiv="ilizibil")]), 0.8)
    assert motive == ["plafon: ilizibil", "CIF furnizor lipsă", "încredere generală 0.50"]
    assert evalueaza(extras(articole=[]), 0.8) == ["niciun articol cu preț"]


def test_invalid_dates_become_unclear():
    ex = extras(data_end="31.12.2026")
    assert _date_errors(ex) == ["data_end: dată invalidă „31.12.2026”"] and ex.data_end is None


def test_sync_rereads_when_extraction_version_changes(tmp_path):
    import hashlib
    from datetime import date as d
    from saga_check import contracts_sync
    from saga_check.config import Config
    from saga_check.extract import VERSIUNE_EXTRACTIE

    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.7 test")
    plain = hashlib.sha256(pdf.read_bytes()).hexdigest()

    class Repo:
        def __init__(self, sha):
            self.sha, self.saved = sha, []
        def contract_sha(self, path):
            return self.sha
        def upload_pdf(self, path, data):
            pass
        def save_contract(self, path, sha, ex, motive):
            self.saved.append(sha)

    msgs = FakeMessages(SimpleNamespace(stop_reason="end_turn", parsed_output=extras()))
    client = SimpleNamespace(messages=msgs)
    c = Config(firma_cif="RO1", efactura_dir=tmp_path, contracte_dir=tmp_path, import_dir=tmp_path,
               log_dir=tmp_path, data_start=d(2026, 1, 1))

    old = Repo(plain)  # citit cu versiunea veche (amprenta fara sufix)
    contracts_sync.sync(c, old, client)
    assert old.saved == [f"{plain}-v{VERSIUNE_EXTRACTIE}"]

    current = Repo(f"{plain}-v{VERSIUNE_EXTRACTIE}")  # deja citit cu versiunea curenta
    contracts_sync.sync(c, current, client)
    assert current.saved == []


def test_reextraction_keeps_existing_articles():
    from saga_check.db import articole_plan
    existing = [{"id": 1, "denumire": "Hârtie copiator A4"}, {"id": 2, "denumire": "Toner vechi"}]
    art = lambda d, p: ArticolExtras(denumire=d, cod=None, um=None, pret_unitar_fara_tva=p,  # noqa: E731
                                     moneda="RON", cantitate_max=None, incredere=0.9)
    new, update, keep = articole_plan(existing, [art("Hartie copiator A4", 26), art("Dosar plic", 0.8)])
    assert [(i, v["pret_unitar"]) for i, v in update] == [(1, 26)]  # acelasi id -> cont/mapari pastrate
    assert [v["denumire"] for v in new] == ["Dosar plic"]
    assert keep == {1}  # "Toner vechi" (id 2) nu mai e in contract -> se sterge
