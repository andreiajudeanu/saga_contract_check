"""Genereaza date de test fictive: 2 contracte PDF si 8 e-Facturi (UBL), in test_run/.

Firme (CIF-uri fictive, cu cifra de control valida):
  FIRMA TEST SRL       RO12345674  - firma noastra (cumparatorul)
  BIROTICA TEST SRL    RO76543210  - contract C-100/2026, RON
  IT SERVICE TEST SRL  RO24681350  - contract C-200/2026, EUR
  FARA CONTRACT SRL    RO35792469  - fara contract

Rulare: python scripts/genereaza_date_test.py
"""
import zipfile
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent / "test_run"
FONT = Path("C:/Windows/Fonts/arial.ttf")
FIRMA = ("FIRMA TEST SRL", "RO12345674", "J40/1234/2020", "Bd. Unirii 10", "SECTOR3", "RO-B")
BIROTICA = ("BIROTICA TEST SRL", "RO76543210", "J12/555/2015", "Str. Fabricii 5", "Cluj-Napoca", "RO-CJ")
ITS = ("IT SERVICE TEST SRL", "RO24681350", "J22/777/2018", "Str. Pacurari 20", "Iasi", "RO-IS")
FARA = ("FARA CONTRACT SRL", "RO35792469", "J05/999/2021", "Str. Republicii 1", "Oradea", "RO-BH")


# --- contracte PDF -------------------------------------------------------------------

def contract_pdf(path: Path, titlu: str, paragrafe: list[str], tabel: list[tuple[str, ...]]) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("Arial", "", str(FONT))
    pdf.add_font("Arial", "B", str(FONT.with_name("arialbd.ttf")))
    pdf.set_font("Arial", "B", 14)
    pdf.multi_cell(0, 8, titlu, align="C")
    pdf.ln(4)
    pdf.set_font("Arial", "", 10)
    for p in paragrafe:
        pdf.multi_cell(0, 5.5, p)
        pdf.ln(2)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 7, "Anexa 1 – Lista de prețuri (fără TVA)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Arial", "", 9)
    with pdf.table(col_widths=(10, 55, 15, 20, 25)) as t:
        for row in tabel:
            r = t.row()
            for cell in row:
                r.cell(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def contracte() -> None:
    contract_pdf(
        ROOT / "contracte" / "C-100-2026 Birotica.pdf",
        "CONTRACT DE FURNIZARE PRODUSE\nNr. C-100/2026 din 15.12.2025",
        [
            f"Între {BIROTICA[0]}, CUI {BIROTICA[1]}, Nr. Reg. Com. {BIROTICA[2]}, cu sediul în {BIROTICA[4]}, "
            f"{BIROTICA[3]}, în calitate de FURNIZOR, și {FIRMA[0]}, CUI {FIRMA[1]}, cu sediul în București, "
            f"{FIRMA[3]}, în calitate de CUMPĂRĂTOR, s-a încheiat prezentul contract.",
            "Art. 1. Obiectul contractului îl constituie furnizarea de consumabile de birou, conform Anexei 1.",
            "Art. 2. Contractul este valabil în perioada 01.01.2026 – 31.12.2026.",
            "Art. 3. Valoarea totală maximă a contractului este de 5.000,00 lei, fără TVA. "
            "Prețurile din Anexa 1 sunt ferme pe toată durata contractului și nu includ TVA (cota 21%).",
            "Art. 4. Plata se face prin ordin de plată, în termen de 30 de zile de la data emiterii facturii.",
            "Art. 5. Cantitatea maximă de tonere HP 85A care poate fi livrată pe durata contractului este de 10 bucăți.",
        ],
        [("Nr.", "Produs", "UM", "Preț unitar", "Cantitate max."),
         ("1", "Hârtie copiator A4 80g/mp", "top", "25,00 lei", "-"),
         ("2", "Toner HP 85A", "buc", "320,00 lei", "10"),
         ("3", "Dosar plic transparent", "buc", "0,80 lei", "-")],
    )
    contract_pdf(
        ROOT / "contracte" / "C-200-2026 IT Service.pdf",
        "CONTRACT DE PRESTĂRI SERVICII IT\nNr. C-200/2026 din 20.02.2026",
        [
            f"Între {ITS[0]}, CUI {ITS[1]}, Nr. Reg. Com. {ITS[2]}, cu sediul în {ITS[4]}, {ITS[3]}, "
            f"în calitate de PRESTATOR, și {FIRMA[0]}, CUI {FIRMA[1]}, în calitate de BENEFICIAR.",
            "Art. 1. Prestatorul asigură mentenanța sistemelor informatice ale beneficiarului și intervenții la sediu.",
            "Art. 2. Durata contractului: 01.03.2026 – 28.02.2027.",
            "Art. 3. Prețurile sunt exprimate în EUR, fără TVA (cota 21%). Facturarea se poate face în lei, la "
            "cursul BNR din data facturii. Valoarea maximă a contractului este de 3.000 EUR fără TVA.",
            "Art. 4. Termenul de plată este de 15 zile de la emiterea facturii.",
        ],
        [("Nr.", "Serviciu", "UM", "Preț unitar", "Cantitate max."),
         ("1", "Mentenanță IT lunară", "lună", "250,00 EUR", "12"),
         ("2", "Intervenție la sediu", "oră", "40,00 EUR", "-")],
    )


# --- facturi UBL ----------------------------------------------------------------------

def _party(p) -> str:
    nume, cif, regcom, strada, oras, judet = p
    return f"""<cac:Party>
      <cac:PostalAddress><cbc:StreetName>{strada}</cbc:StreetName><cbc:CityName>{oras}</cbc:CityName>
        <cbc:CountrySubentity>{judet}</cbc:CountrySubentity><cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
      <cac:PartyTaxScheme><cbc:CompanyID>{cif}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>
      <cac:PartyLegalEntity><cbc:RegistrationName>{nume}</cbc:RegistrationName><cbc:CompanyID>{regcom}</cbc:CompanyID></cac:PartyLegalEntity>
    </cac:Party>"""


def ubl(nr, data, scadenta, furnizor, linii, moneda="RON", credit=False) -> bytes:
    """linii: (denumire, um, cantitate, pret, cota)."""
    root, line, qty, code = ("CreditNote", "CreditNoteLine", "CreditedQuantity", "CreditNoteTypeCode") if credit \
        else ("Invoice", "InvoiceLine", "InvoicedQuantity", "InvoiceTypeCode")
    q = Decimal("0.01")
    rows, total, tva = [], Decimal(0), Decimal(0)
    for i, (den, um, cant, pret, cota) in enumerate(linii, 1):
        val = (Decimal(cant) * Decimal(pret)).quantize(q)
        total += val
        tva += (val * Decimal(cota) / 100).quantize(q)
        rows.append(f"""  <cac:{line}><cbc:ID>{i}</cbc:ID>
    <cbc:{qty} unitCode="{um}">{cant}</cbc:{qty}>
    <cbc:LineExtensionAmount currencyID="{moneda}">{val}</cbc:LineExtensionAmount>
    <cac:Item><cbc:Name>{den}</cbc:Name>
      <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>{cota}</cbc:Percent><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="{moneda}">{pret}</cbc:PriceAmount></cac:Price>
  </cac:{line}>""")
    due = f"<cbc:DueDate>{scadenta}</cbc:DueDate>" if scadenta and not credit else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<{root} xmlns="urn:oasis:names:specification:ubl:schema:xsd:{root}-2"
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1</cbc:CustomizationID>
  <cbc:ID>{nr}</cbc:ID>
  <cbc:IssueDate>{data}</cbc:IssueDate>
  {due}
  <cbc:{code}>{"381" if credit else "380"}</cbc:{code}>
  <cbc:DocumentCurrencyCode>{moneda}</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>{_party(furnizor)}</cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>{_party(FIRMA)}</cac:AccountingCustomerParty>
  <cac:TaxTotal><cbc:TaxAmount currencyID="{moneda}">{tva}</cbc:TaxAmount></cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{moneda}">{total}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{moneda}">{total}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{moneda}">{total + tva}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{moneda}">{total + tva}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{chr(10).join(rows)}
</{root}>
""".encode()


FACTURI = [
    # (fisier, ce ar trebui sa iasa, xml)
    ("4300000001.zip", "✔ conform", ubl("BT-1001", "2026-10-05", "2026-11-04", BIROTICA, [
        ("Hartie copiator A4 80 g/mp", "H87", 20, "25.00", 21), ("Toner HP 85A original", "H87", 2, "320.00", 21)])),
    ("4300000002.zip", "✘ preț toner +30 lei", ubl("BT-1002", "2026-10-08", "2026-11-07", BIROTICA, [
        ("Toner HP 85A", "H87", 3, "350.00", 21), ("Dosar plic transparent", "H87", 50, "0.80", 21)])),
    ("4300000003.zip", "✘ scadență 10 zile + articol neidentificat", ubl("BT-1003", "2026-10-12", "2026-10-22", BIROTICA, [
        ("Hartie A4 80g", "H87", 10, "25.00", 21), ("Pix gel albastru", "H87", 20, "3.50", 21)])),
    ("4300000004.zip", "✘ cantitate toner depășită (2+3+6 > 10)", ubl("BT-1004", "2026-10-14", "2026-11-13", BIROTICA, [
        ("Toner HP 85A", "H87", 6, "320.00", 21)])),
    ("4300000005.zip", "✔ conform (lei, curs BNR 15.10 = 5,3370)", ubl("ITS-55", "2026-10-15", "2026-10-30", ITS, [
        ("Mentenanta IT lunara - octombrie", "MON", 1, "1334.25", 21)])),
    ("4300000006.zip", "✘ plafon C-200 depășit (250 + 3250 > 3000 EUR)", ubl("ITS-56", "2026-10-20", "2026-11-04", ITS, [
        ("Mentenanta IT lunara", "MON", 1, "250.00", 21), ("Interventie la sediu", "HUR", 75, "40.00", 21)],
        moneda="EUR")),
    ("4300000007.zip", "✔ storno conform", ubl("BT-1005", "2026-10-21", None, BIROTICA, [
        ("Hartie copiator A4 80g/mp", "H87", 5, "25.00", 21)], credit=True)),
    ("4300000008.xml", "✘ fără contract", ubl("FC-9", "2026-10-22", "2026-11-21", FARA, [
        ("Servicii curatenie", "C62", 1, "800.00", 21)])),
    ("4300000009.zip", "ignorată: înainte de data_start", ubl("BT-0990", "2026-09-15", "2026-10-15", BIROTICA, [
        ("Hartie copiator A4 80g/mp", "H87", 10, "25.00", 21)])),
]


def facturi() -> None:
    folder = ROOT / "efactura"
    folder.mkdir(parents=True, exist_ok=True)
    for name, _, xml in FACTURI:
        path = folder / name
        if path.suffix == ".zip":
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr(f"{path.stem}.xml", xml)
                zf.writestr(f"semnatura_{path.stem}.xml", "<Signature>test</Signature>")
        else:
            path.write_bytes(xml)


if __name__ == "__main__":
    contracte()
    facturi()
    print(f"Date de test generate în {ROOT}")
    for name, expected, _ in FACTURI:
        print(f"  {name}: {expected}")
