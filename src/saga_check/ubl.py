"""Citire facturi e-Factura (UBL 2.1 / CIUS-RO), din XML sau din ZIP-ul descarcat din SPV."""
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Invoice, InvoiceLine, Party

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
INVOICE_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CREDIT_NS = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"


class NotAnInvoice(ValueError):
    pass


def load_file(path: Path) -> Invoice:
    """Citeste un .xml sau un .zip din SPV (care contine factura + semnatura_*.xml)."""
    index = path.stem if path.stem.isdigit() else ""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist()
                     if n.lower().endswith(".xml") and not Path(n).name.lower().startswith("semnatura")]
            if len(names) != 1:
                raise NotAnInvoice(f"{path.name}: {len(names)} fisiere XML de factura in arhiva")
            data = zf.read(names[0])
            if not index and Path(names[0]).stem.isdigit():
                index = Path(names[0]).stem
    else:
        data = path.read_bytes()
    inv = parse(data)
    inv.sursa = str(path)
    inv.index_descarcare_spv = index
    return inv


def _t(el: ET.Element | None, xpath: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(xpath, NS)
    return found.text.strip() if found is not None and found.text else default


def _d(el, xpath: str) -> Decimal:
    v = _t(el, xpath)
    return Decimal(v) if v else Decimal("0")


def _date(v: str) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _party(p: ET.Element | None) -> Party:
    if p is None:
        return Party()
    tax_id = _t(p, "cac:PartyTaxScheme/cbc:CompanyID")
    legal_id = _t(p, "cac:PartyLegalEntity/cbc:CompanyID")
    addr = p.find("cac:PostalAddress", NS)
    judet = _t(addr, "cbc:CountrySubentity")
    return Party(
        nume=_t(p, "cac:PartyLegalEntity/cbc:RegistrationName") or _t(p, "cac:PartyName/cbc:Name"),
        cif=tax_id or legal_id,
        # In CIUS-RO, PartyLegalEntity/CompanyID e de obicei nr. Reg. Com. cand exista si CUI-ul.
        nr_reg_com=legal_id if tax_id and legal_id != tax_id else "",
        tara=_t(addr, "cac:Country/cbc:IdentificationCode"),
        judet=judet.removeprefix("RO-"),
        localitate=_t(addr, "cbc:CityName"),
        adresa=_t(addr, "cbc:StreetName"),
        telefon=_t(p, "cac:Contact/cbc:Telephone"),
        mail=_t(p, "cac:Contact/cbc:ElectronicMail"),
    )


def parse(data: bytes) -> Invoice:
    root = ET.fromstring(data)
    tag_ns = root.tag.split("}")[0].lstrip("{")
    if tag_ns not in (INVOICE_NS, CREDIT_NS):
        raise NotAnInvoice(f"radacina XML necunoscuta: {root.tag}")
    is_credit = tag_ns == CREDIT_NS
    # Nota de credit UBL are valori pozitive; le inversam ca sa scada din plafoane.
    sign = Decimal(-1) if is_credit else Decimal(1)
    type_code = _t(root, "cbc:CreditNoteTypeCode" if is_credit else "cbc:InvoiceTypeCode")
    moneda = _t(root, "cbc:DocumentCurrencyCode", "RON")

    linii: list[InvoiceLine] = []
    line_tag, qty_tag = ("cac:CreditNoteLine", "cbc:CreditedQuantity") if is_credit \
        else ("cac:InvoiceLine", "cbc:InvoicedQuantity")
    for i, ln in enumerate(root.findall(line_tag, NS), start=1):
        qty_el = ln.find(qty_tag, NS)
        qty = Decimal(qty_el.text.strip()) if qty_el is not None and qty_el.text else Decimal("0")
        base_qty = _d(ln, "cac:Price/cbc:BaseQuantity") or Decimal(1)
        linii.append(InvoiceLine(
            nr_crt=i,
            denumire=_t(ln, "cac:Item/cbc:Name") or _t(ln, "cac:Item/cbc:Description"),
            cod=_t(ln, "cac:Item/cac:SellersItemIdentification/cbc:ID"),
            um=qty_el.get("unitCode", "") if qty_el is not None else "",
            cantitate=qty * sign,
            pret=_d(ln, "cac:Price/cbc:PriceAmount") / base_qty,
            valoare=_d(ln, "cbc:LineExtensionAmount") * sign,
            cota_tva=_d(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent"),
            categorie_tva=_t(ln, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID", "S"),
        ))

    # Reduceri/majorari la nivel de document devin linii separate, ca totalul sa se pastreze.
    for ac in root.findall("cac:AllowanceCharge", NS):
        is_charge = _t(ac, "cbc:ChargeIndicator").lower() == "true"
        amount = _d(ac, "cbc:Amount") * (1 if is_charge else -1) * sign
        linii.append(InvoiceLine(
            nr_crt=len(linii) + 1,
            denumire=_t(ac, "cbc:AllowanceChargeReason") or ("Majorare" if is_charge else "Discount"),
            cod="", um="", cantitate=Decimal(1), pret=amount, valoare=amount,
            cota_tva=_d(ac, "cac:TaxCategory/cbc:Percent"),
            categorie_tva=_t(ac, "cac:TaxCategory/cbc:ID", "S"),
            ajustare=True,
        ))

    total_tva = Decimal("0")
    for tt in root.findall("cac:TaxTotal", NS):
        amt = tt.find("cbc:TaxAmount", NS)
        if amt is not None and amt.get("currencyID", moneda) == moneda:
            total_tva = Decimal(amt.text.strip())
            break

    scadenta = _t(root, "cbc:DueDate") or _t(root, "cac:PaymentMeans/cbc:PaymentDueDate")
    furnizor = _party(root.find("cac:AccountingSupplierParty/cac:Party", NS))
    furnizor.iban = _t(root, "cac:PaymentMeans/cac:PayeeFinancialAccount/cbc:ID")
    total_fara_tva = _d(root, "cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount") * sign

    return Invoice(
        nr=_t(root, "cbc:ID"),
        data=_date(_t(root, "cbc:IssueDate")),
        scadenta=_date(scadenta),
        moneda=moneda,
        furnizor=furnizor,
        client=_party(root.find("cac:AccountingCustomerParty/cac:Party", NS)),
        linii=linii,
        total_fara_tva=total_fara_tva,
        total_tva=total_tva * sign,
        este_storno=is_credit or type_code == "381" or total_fara_tva < 0,
    )
