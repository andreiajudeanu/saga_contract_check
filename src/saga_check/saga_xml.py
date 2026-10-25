"""Fisier de import SAGA C (Import date -> Facturi), cu rezultatul in FacturaInformatiiSuplimentare.

Structura urmeaza manualul: https://manual.sagasoft.ro/sagac/topic-76-import-date.html
"""
import os
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .models import CheckResult, Invoice

CENT = Decimal("0.01")


@dataclass
class SagaSettings:
    firma_cif: str
    format_data: str = "%d.%m.%Y"
    cif_in_nume_fisier: str = "furnizor"
    gestiune: str = ""
    activitate: str = ""
    cont: str = ""
    tip_deducere: str = ""


# Coduri UN/ECE Rec. 20 folosite in e-Factura -> UM afisata in SAGA. Codurile necunoscute raman ca atare.
UM_SAGA = {
    "H87": "buc", "C62": "buc", "XPP": "buc", "SET": "set", "PR": "per", "KGM": "kg", "GRM": "g",
    "TNE": "t", "LTR": "l", "MTR": "m", "MTK": "mp", "MTQ": "mc", "KMT": "km", "HUR": "ora",
    "DAY": "zi", "MON": "luna", "ANN": "an", "KWH": "kWh", "XBX": "cutie", "XPK": "pachet",
}


class TotalsMismatch(ValueError):
    pass


def _num(v: Decimal, places: str = "0.01") -> str:
    return str(v.quantize(Decimal(places), ROUND_HALF_UP))


_SAGA_CHARS = str.maketrans({
    "✔": "[OK]", "✘": "[X]", "≠": "<>", "„": '"', "”": '"', "“": '"', "–": "-", "—": "-", "…": "...",
})


def saga_text(text: str) -> str:
    """Testat in SAGA C: ţ/ş cu sedila ajung „t/s”, iar ț/ș cu virgula si ✔/✘ ajung „?”.
    Trimitem deci doar ASCII: diacriticele fara semne, simbolurile inlocuite."""
    out = []
    for ch in (text or "").translate(_SAGA_CHARS):
        if not ch.isascii():
            ch = unicodedata.normalize("NFKD", ch)[0]
        out.append(ch if ch.isascii() else "?")
    return "".join(out)


def _sub(parent: ET.Element, tag: str, text: str = "") -> None:
    ET.SubElement(parent, tag).text = saga_text(text)


def _line_vat(valoare: Decimal, cota: Decimal) -> Decimal:
    return (valoare * cota / 100).quantize(CENT, ROUND_HALF_UP)


def file_name(inv: Invoice, s: SagaSettings) -> str:
    cif = inv.furnizor.cif if s.cif_in_nume_fisier == "furnizor" else s.firma_cif
    nr = re.sub(r'[\\/:*?"<>|\s]+', "-", inv.nr)
    return f"F_{re.sub(r'\W', '', cif)}_{nr}_{inv.data.strftime(s.format_data)}.xml"


def texte_linii(inv: Invoice, result: CheckResult) -> dict[int, str]:
    """In SAGA se vede coloana „Informatii suplimentare” de pe linii, nu cea din antet. Linia 1 primeste
    rezultatul intregii facturi; celelalte [OK] sau [X] cu motivul lor."""
    out = {}
    for i, ln in enumerate(inv.linii):
        if i == 0:
            out[ln.nr_crt] = result.mesaj
        elif ln.nr_crt in result.abateri_linii:
            out[ln.nr_crt] = f"[X] {result.abateri_linii[ln.nr_crt]}"
        elif result.conform:
            out[ln.nr_crt] = "[OK]"
        elif ln.nr_crt in result.linii_potrivite:
            out[ln.nr_crt] = "[OK] linie conforma"
        else:
            out[ln.nr_crt] = "[X] vezi linia 1"
    return out


def build(inv: Invoice, result: CheckResult, s: SagaSettings) -> bytes:
    """Construieste XML-ul si verifica faptul ca totalurile coincid cu factura originala."""
    root = ET.Element("Facturi")
    fac = ET.SubElement(root, "Factura")
    antet = ET.SubElement(fac, "Antet")
    f, c = inv.furnizor, inv.client
    for tag, val in [
        ("FurnizorNume", f.nume), ("FurnizorCIF", f.cif), ("FurnizorNrRegCom", f.nr_reg_com),
        ("FurnizorCapital", ""), ("FurnizorTara", f.tara), ("FurnizorLocalitate", f.localitate),
        ("FurnizorJudet", f.judet), ("FurnizorAdresa", f.adresa), ("FurnizorTelefon", f.telefon),
        ("FurnizorMail", f.mail), ("FurnizorBanca", ""), ("FurnizorIBAN", f.iban),
        ("FurnizorInformatiiSuplimentare", ""),
        ("ClientNume", c.nume), ("ClientInformatiiSuplimentare", ""), ("ClientCIF", c.cif or s.firma_cif),
        ("ClientNrRegCom", c.nr_reg_com), ("ClientJudet", c.judet), ("ClientTara", c.tara),
        ("ClientLocalitate", c.localitate), ("ClientAdresa", c.adresa), ("ClientBanca", ""),
        ("ClientIBAN", ""), ("ClientTelefon", c.telefon), ("ClientMail", c.mail),
        ("FacturaNumar", inv.nr),
        ("FacturaData", inv.data.strftime(s.format_data)),
        ("FacturaScadenta", inv.scadenta.strftime(s.format_data) if inv.scadenta else ""),
        ("FacturaTaxareInversa", "Da" if inv.taxare_inversa else "Nu"),
        ("FacturaTVAIncasare", "Nu"),
        ("FacturaTip", ""),
        ("FacturaInformatiiSuplimentare", result.mesaj),
        ("FacturaMoneda", "" if inv.moneda == "RON" else inv.moneda),
        ("FacturaGreutate", ""),
        ("FacturaIndexSPV", ""),
        ("FacturaIndexDescarcareSPV", inv.index_descarcare_spv),
    ]:
        _sub(antet, tag, val)

    continut = ET.SubElement(ET.SubElement(fac, "Detalii"), "Continut")
    texte = texte_linii(inv, result)
    sum_val = sum_tva = Decimal(0)
    for ln in inv.linii:
        val = ln.valoare.quantize(CENT, ROUND_HALF_UP)
        tva = _line_vat(val, ln.cota_tva) if ln.categorie_tva == "S" else Decimal(0)
        sum_val += val
        sum_tva += tva
        linie = ET.SubElement(continut, "Linie")
        for tag, v in [
            ("LinieNrCrt", str(ln.nr_crt)), ("Gestiune", s.gestiune), ("Activitate", s.activitate),
            ("Descriere", ln.denumire), ("CodArticolFurnizor", ln.cod),
            ("InformatiiSuplimentare", texte[ln.nr_crt]),
            ("UM", UM_SAGA.get(ln.um, ln.um)), ("Cantitate", _num(ln.cantitate, "0.001")), ("Pret", _num(ln.pret, "0.0001")),
            ("Valoare", _num(val)), ("ProcTVA", _num(ln.cota_tva)), ("TVA", _num(tva)),
            ("Cont", result.conturi_linii.get(ln.nr_crt) or s.cont), ("TipDeducere", s.tip_deducere),
        ]:
            _sub(linie, tag, v)
    _sub(fac, "FacturaID", f"{inv.furnizor_cif}-{inv.nr}-{inv.data:%Y%m%d}")

    # Diferentele de rotunjire TVA pe linie vs. total pot fi de cativa bani; peste asta e o eroare de citire.
    toleranta_tva = CENT * max(len(inv.linii), 1)
    if abs(sum_val - inv.total_fara_tva) > CENT or abs(sum_tva - inv.total_tva) > toleranta_tva:
        raise TotalsMismatch(
            f"{inv.nr}: linii {sum_val}/{sum_tva} vs. factura {inv.total_fara_tva}/{inv.total_tva}")

    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_atomic(folder: Path, name: str, data: bytes) -> Path:
    """Scriere prin fisier temporar + rename, ca SAGA sa nu vada niciodata un XML pe jumatate."""
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    target = folder / name
    os.replace(tmp, target)
    return target
