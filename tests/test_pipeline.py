import xml.etree.ElementTree as ET
import zipfile
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from saga_check.config import Config
from saga_check.invoices_run import process
from saga_check.matcher import match_line, normalize
from saga_check.models import ContractArticol
from saga_check.rules import Settings, fmt, verifica
from saga_check.saga_xml import SagaSettings, TotalsMismatch, build, file_name, saga_text
from saga_check.ubl import load_file, parse

from conftest import FIXTURES, FakeRepo, contract

S = Settings(simboluri="unicode")
ZERO = lambda _id: Decimal(0)  # noqa: E731


def invoice():
    return load_file(FIXTURES / "factura.xml")


def check(inv, contracts, rates, cv=ZERO, cq=ZERO):
    return verifica(inv, contracts, rates, S, cv, cq)


# --- parsare UBL -------------------------------------------------------------

def test_parse_ubl():
    inv = invoice()
    assert (inv.nr, inv.data, inv.scadenta, inv.moneda) == ("FURN 0042", date(2026, 11, 5), date(2026, 12, 5), "RON")
    assert inv.furnizor_cif == "12345678" and inv.furnizor.nr_reg_com == "J12/345/2010"
    assert inv.furnizor.judet == "CJ" and inv.furnizor.iban.startswith("RO49")
    assert inv.client.cif == "RO87654321"
    assert [l.valoare for l in inv.linii] == [Decimal("250.00"), Decimal("600.00")]
    assert inv.total_tva == Decimal("178.50") and not inv.este_storno


def test_zip_from_spv_ignores_signature(tmp_path):
    z = tmp_path / "4231234567.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(FIXTURES / "factura.xml", "4231234567.xml")
        zf.writestr("semnatura_4231234567.xml", "<Signature/>")
    inv = load_file(z)
    assert inv.nr == "FURN 0042" and inv.index_descarcare_spv == "4231234567"


def test_credit_note_is_negative():
    xml = (FIXTURES / "factura.xml").read_text(encoding="utf-8")
    xml = (xml.replace("xsd:Invoice-2", "xsd:CreditNote-2").replace("<Invoice ", "<CreditNote ")
              .replace("</Invoice>", "</CreditNote>").replace(">380<", ">381<").replace("InvoiceTypeCode", "CreditNoteTypeCode")
              .replace("InvoiceLine", "CreditNoteLine").replace("InvoicedQuantity", "CreditedQuantity"))
    inv = parse(xml.encode())
    assert inv.este_storno and inv.total_fara_tva == Decimal("-850.00")
    assert inv.linii[0].cantitate == Decimal("-10") and inv.linii[0].valoare == Decimal("-250.00")


# --- potrivire -----------------------------------------------------------------

def test_normalize_strips_diacritics():
    assert normalize("Servicii  Mentenanță-IT") == "servicii mentenanta it"


def test_match_prefers_closer_name_on_tie():
    c = contract(articole=[
        ContractArticol(id=1, denumire="Hârtie A4", pret_unitar=Decimal(1)),
        ContractArticol(id=2, denumire="Hârtie A4 premium", pret_unitar=Decimal(2)),
    ])
    line = replace(invoice().linii[0], denumire="Hartie A4 premium 80g")
    assert match_line(line, [c], 85).articol.id == 2


def test_match_by_code_and_threshold():
    line = replace(invoice().linii[0], denumire="Cu totul altceva", cod="HA4")
    assert match_line(line, [contract()], 85).articol.id == 10
    assert match_line(replace(line, cod=""), [contract()], 85) is None


# --- reguli ---------------------------------------------------------------------

def test_conform(rates):
    inv = invoice()
    inv.linii[1] = replace(inv.linii[1], pret=Decimal("500"), valoare=Decimal("500"))
    r = check(inv, [contract()], rates)
    assert r.conform and r.mesaj == "✔ Conform contract C-12"
    assert sum(c.valoare_contract for c in r.consum) == Decimal("750.00")


def test_price_difference(rates):
    r = check(invoice(), [contract()], rates)
    assert not r.conform
    assert r.mesaj == "✘ C-12: Preț linia 2: +100,00 lei/unit."
    assert r.abateri_linii == {2: "Preț +100,00 lei/unit. față de contract"}


def test_no_contract_and_expired(rates):
    assert check(invoice(), [], rates).mesaj == "✘ Fără contract pentru furnizor"
    expired = contract(data_end=date(2026, 6, 30))
    assert check(invoice(), [expired], rates).mesaj == "✘ Fără contract activ la 05.11.2026"


def test_unclear_contract_wins(rates):
    r = check(invoice(), [contract(status="neclar")], rates)
    assert r.mesaj == "✘ Contract neclar C-12 – verificare necesară"


def test_unidentified_article(rates):
    inv = invoice()
    inv.linii[0] = replace(inv.linii[0], denumire="Toner imprimantă")
    r = check(inv, [contract()], rates)
    assert "Articol neidentificat: linia 1" in r.mesaj and "Preț linia 2" in r.mesaj


def test_ceiling_value_and_quantity(rates):
    r = check(invoice(), [contract(plafon_valoare=Decimal("1000"))], rates,
              cv=lambda _: Decimal("900"), cq=lambda _: Decimal("12"))
    assert r.mesaj.startswith("✘ C-12: ") and "; Plafon depășit cu 750,00 lei" in r.mesaj
    assert "Cantitate „Servicii mentenanță IT” depășită cu 1" in r.mesaj


def test_payment_term_and_vat(rates):
    inv = replace(invoice(), scadenta=date(2026, 11, 20))
    inv.linii[0] = replace(inv.linii[0], cota_tva=Decimal("19"))
    r = check(inv, [contract()], rates)
    assert "Scadență 15 zile < 30 din contract" in r.mesaj
    assert "TVA linia 1: 19% în loc de 21%" in r.mesaj


def test_foreign_currency_contract_uses_bnr_rate(rates):
    # 05.11.2026 nu are curs in fixture -> se ia cel din 04.11 (5,00). 5 EUR * 5 = 25 lei: conform.
    c = contract(moneda="EUR", plafon_valoare=Decimal("100"), articole=[
        ContractArticol(id=10, denumire="Hârtie copiator A4 80g", pret_unitar=Decimal("5"), moneda="EUR"),
        ContractArticol(id=11, denumire="Servicii mentenanță IT", pret_unitar=Decimal("120"), moneda="EUR"),
    ])
    r = check(invoice(), [c], rates)
    assert "Preț linia 1" not in r.mesaj and "Preț linia 2: +0,00" not in r.mesaj
    # 600 lei vs 120 EUR * 5 = 600 lei -> conform pe pret; plafon 100 EUR depasit de 170 EUR.
    assert r.mesaj == "✘ C-12: Plafon depășit cu 70,00 EUR"


def test_currency_mismatch(rates):
    inv = replace(invoice(), moneda="EUR")
    r = check(inv, [contract()], rates)
    assert "C-12: Monedă EUR în loc de RON" in r.mesaj


def test_ascii_symbols_and_truncation(rates):
    s = Settings(simboluri="ascii", lungime_max_mesaj=20)
    r = verifica(invoice(), [contract()], rates, s, ZERO, ZERO)
    assert r.mesaj.startswith("[X] ") and len(r.mesaj) == 20 and r.mesaj.endswith("…")


def test_fmt():
    assert fmt(Decimal("1250.5")) == "1.250,50 lei"
    assert fmt(Decimal("-3"), "eur", semn=True) == "-3,00 EUR"


# --- XML SAGA ----------------------------------------------------------------------

SS = SagaSettings(firma_cif="RO87654321")


def test_saga_xml(rates):
    inv = invoice()
    r = check(inv, [contract()], rates)
    root = ET.fromstring(build(inv, r, SS))
    antet = root.find("Factura/Antet")
    assert antet.findtext("FurnizorCIF") == "RO12345678"
    assert antet.findtext("ClientCIF") == "RO87654321"
    assert antet.findtext("FacturaData") == "05.11.2026"
    # In XML textul e deja ASCII, ca sa nu apara "?" in SAGA.
    assert antet.findtext("FacturaInformatiiSuplimentare") == "[X] C-12: Pret linia 2: +100,00 lei/unit."
    linii = root.findall("Factura/Detalii/Continut/Linie")
    assert [l.findtext("TVA") for l in linii] == ["52.50", "126.00"]
    # Linia 1 poarta rezultatul facturii, linia 2 propria abatere.
    assert linii[0].findtext("InformatiiSuplimentare") == "[X] C-12: Pret linia 2: +100,00 lei/unit."
    assert linii[1].findtext("InformatiiSuplimentare") == "[X] Pret +100,00 lei/unit. fata de contract"
    assert root.findtext("Factura/FacturaID") == "12345678-FURN 0042-20261105"
    assert file_name(inv, SS) == "F_RO12345678_FURN-0042_05.11.2026.xml"


def test_cont_from_article_else_default(rates):
    c = contract()
    c.articole[1].cont = "628"
    inv = invoice()
    root = ET.fromstring(build(inv, check(inv, [c], rates), replace(SS, cont="6028")))
    assert [l.findtext("Cont") for l in root.iter("Linie")] == ["6028", "628"]


def test_line_texts_ok_and_unmatched(rates):
    from saga_check.saga_xml import texte_linii
    inv = invoice()
    inv.linii[1] = replace(inv.linii[1], pret=Decimal("500"), valoare=Decimal("500"))
    ok = check(inv, [contract()], rates)
    assert texte_linii(inv, ok) == {1: "✔ Conform contract C-12", 2: "[OK]"}
    assert saga_text(texte_linii(inv, ok)[1]) == "[OK] Conform contract C-12"
    none = check(inv, [], rates)
    assert texte_linii(inv, none) == {1: "✘ Fără contract pentru furnizor", 2: "[X] vezi linia 1"}
    inv.linii[1] = replace(inv.linii[1], denumire="Toner")
    plafon = check(inv, [contract(plafon_valoare=Decimal("100"))], rates)
    assert texte_linii(inv, plafon)[2] == "[X] Articol neidentificat în contract"


def test_saga_text_is_ascii():
    txt = saga_text("✔ ✘ Țară, ș ț ţ ă î â „x” – ≠ €")
    assert txt == '[OK] [X] Tara, s t t a i a "x" - <> ?'
    assert txt.isascii()


def test_saga_xml_rejects_wrong_totals(rates):
    inv = replace(invoice(), total_fara_tva=Decimal("900"))
    with pytest.raises(TotalsMismatch):
        build(inv, check(inv, [contract()], rates), SS)


# --- orchestrare ---------------------------------------------------------------------

def test_process_end_to_end(tmp_path, rates):
    src = tmp_path / "efactura"
    src.mkdir()
    (src / "factura.xml").write_bytes((FIXTURES / "factura.xml").read_bytes())
    with zipfile.ZipFile(src / "4231234567.zip", "w") as zf:  # aceeasi factura si ca ZIP
        zf.write(FIXTURES / "factura.xml", "4231234567.xml")
    c = Config(firma_cif="RO87654321", efactura_dir=src, contracte_dir=tmp_path, import_dir=tmp_path / "import",
               log_dir=tmp_path / "log", data_start=date(2026, 11, 1))
    repo = FakeRepo([contract()])

    assert process(c, repo, rates) == 1
    out = list((tmp_path / "import").glob("F_*.xml"))
    assert len(out) == 1
    assert ET.parse(out[0]).getroot().findtext("Factura/Antet/FacturaIndexDescarcareSPV") == "4231234567"
    assert process(c, repo, rates) == 0  # a doua rulare nu dubleaza

    # --reproceseaza: aceeasi factura se rescrie, fara sa dubleze consumul din plafon
    out[0].unlink()
    assert process(c, repo, rates, reproceseaza=True) == 1
    assert len(repo.saved) == 1 and out[0].exists()

    later = replace(c, data_start=date(2026, 12, 1))
    assert process(later, FakeRepo([contract()]), rates) == 0  # facturile vechi nu se ating
