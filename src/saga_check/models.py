import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


def normalize_cif(cif: str | None) -> str:
    """'RO 12345678' -> '12345678'. Compararea CIF-urilor se face doar pe cifre."""
    return re.sub(r"\D", "", cif or "")


@dataclass
class Party:
    nume: str = ""
    cif: str = ""          # asa cum apare pe factura (poate contine "RO")
    nr_reg_com: str = ""
    tara: str = ""
    judet: str = ""
    localitate: str = ""
    adresa: str = ""
    iban: str = ""
    telefon: str = ""
    mail: str = ""


@dataclass
class InvoiceLine:
    nr_crt: int
    denumire: str
    cod: str
    um: str
    cantitate: Decimal
    pret: Decimal          # pret unitar fara TVA, in moneda facturii
    valoare: Decimal       # fara TVA, in moneda facturii (negativ pentru storno)
    cota_tva: Decimal
    categorie_tva: str = "S"
    ajustare: bool = False  # reducere/majorare la nivel de document, nu un articol


@dataclass
class Invoice:
    nr: str
    data: date
    scadenta: date | None
    moneda: str
    furnizor: Party
    client: Party
    linii: list[InvoiceLine]
    total_fara_tva: Decimal
    total_tva: Decimal
    este_storno: bool = False
    index_descarcare_spv: str = ""
    sursa: str = ""        # calea fisierului original

    @property
    def furnizor_cif(self) -> str:
        return normalize_cif(self.furnizor.cif)

    @property
    def taxare_inversa(self) -> bool:
        return any(l.categorie_tva == "AE" for l in self.linii)


@dataclass
class ContractArticol:
    id: int
    denumire: str
    pret_unitar: Decimal
    moneda: str = "RON"
    cod: str = ""
    um: str = ""
    cantitate_max: Decimal | None = None
    cont: str = ""  # cont SAGA pentru linie (ex. 6028, 628); gol = contul implicit din config


@dataclass
class Contract:
    id: int
    furnizor_cif: str
    nr_contract: str
    data_start: date | None
    data_end: date | None
    moneda: str = "RON"
    plafon_valoare: Decimal | None = None
    termen_plata_zile: int | None = None
    cota_tva: Decimal | None = None
    status: str = "clar"
    articole: list[ContractArticol] = field(default_factory=list)

    def activ_la(self, zi: date) -> bool:
        return (self.data_start is None or self.data_start <= zi) and (
            self.data_end is None or zi <= self.data_end
        )


@dataclass
class ConsumLinie:
    """Ce consuma o linie de factura dintr-un contract; se salveaza dupa procesare."""
    contract_id: int
    contract_articol_id: int | None
    cantitate: Decimal
    valoare_contract: Decimal


@dataclass
class CheckResult:
    conform: bool
    mesaj: str
    abateri_linii: dict[int, str] = field(default_factory=dict)  # nr_crt -> text scurt
    conturi_linii: dict[int, str] = field(default_factory=dict)  # nr_crt -> cont din articolul de contract
    linii_potrivite: set[int] = field(default_factory=set)  # nr_crt gasite in contract
    consum: list[ConsumLinie] = field(default_factory=list)
    valoare_ron: Decimal = Decimal("0")
