"""Extragerea termenilor dintr-un contract PDF cu Claude (structured outputs)."""
import base64

# Cresteti la orice schimbare a promptului sau a schemei: contractele deja citite se recitesc automat
# o singura data la urmatoarea rulare (amprenta salvata = sha256 PDF + versiune).
VERSIUNE_EXTRACTIE = "2"

import anthropic
from pydantic import BaseModel, Field

PROMPT = """Ești un asistent care extrage termenii comerciali dintr-un contract de achiziție românesc.
Contractul este cel atașat; noi suntem cumpărătorul, cealaltă parte este furnizorul.

Extrage:
- CIF/CUI-ul și numele furnizorului, numărul contractului;
- data de început și de sfârșit (YYYY-MM-DD; null dacă e pe durată nedeterminată sau nu apare);
- moneda contractului, plafonul valoric total FĂRĂ TVA (null dacă nu există);
- termenul de plată în zile și cota de TVA (procent), dacă sunt menționate;
- fiecare articol/serviciu cu preț unitar FĂRĂ TVA, moneda lui, UM, cod și cantitatea maximă (dacă există).
  Include articolele din anexe.

Reguli:
- Nu inventa valori. Dacă un câmp nu apare, pune null.
- Dacă un prețul este exprimat cu TVA, calculează-l fără TVA și menționează asta în `campuri_nesigure`.
- Pune în `campuri_nesigure` DOAR câmpurile a căror valoare extrasă ar putea fi greșită: text ilizibil,
  valori contradictorii între contract și anexă, act adițional care modifică prețul, formule de actualizare
  a prețului, preț exprimat ambiguu. Un câmp care apare clar în text NU e nesigur.
- Orice altă remarcă (de ex. că plafonul poate fi atins repede, că se poate factura și în lei, că o
  cantitate nu e limitată) merge în `observatii`, nu în `campuri_nesigure`.
- `incredere` (0-1) exprimă cât de sigur ești că valoarea extrasă e corectă."""


class ArticolExtras(BaseModel):
    denumire: str
    cod: str | None
    um: str | None
    pret_unitar_fara_tva: float
    moneda: str = Field(description="Cod ISO 4217, ex. RON, EUR")
    cantitate_max: float | None
    incredere: float


class CampNesigur(BaseModel):
    camp: str
    motiv: str


class ContractExtras(BaseModel):
    furnizor_cif: str | None
    furnizor_nume: str | None
    nr_contract: str | None
    data_start: str | None
    data_end: str | None
    moneda: str
    plafon_valoare_fara_tva: float | None
    termen_plata_zile: int | None
    cota_tva: float | None
    articole: list[ArticolExtras]
    campuri_nesigure: list[CampNesigur]
    observatii: list[str]
    incredere_generala: float


class ExtractionRefused(RuntimeError):
    pass


def extrage(pdf: bytes, client: anthropic.Anthropic, model: str) -> ContractExtras:
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode("ascii"),
                }},
                {"type": "text", "text": PROMPT},
            ],
        }],
        output_format=ContractExtras,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ExtractionRefused(f"extracție eșuată (stop_reason={response.stop_reason})")
    return response.parsed_output


def evalueaza(ex: ContractExtras, prag: float) -> list[str]:
    """Motivele pentru care contractul nu poate fi folosit automat; lista goala = status 'clar'."""
    motive = [f"{c.camp}: {c.motiv}" for c in ex.campuri_nesigure]
    if not ex.furnizor_cif:
        motive.append("CIF furnizor lipsă")
    if not ex.articole:
        motive.append("niciun articol cu preț")
    if ex.incredere_generala < prag:
        motive.append(f"încredere generală {ex.incredere_generala:.2f}")
    motive += [f"articol „{a.denumire}”: încredere {a.incredere:.2f}"
               for a in ex.articole if a.incredere < prag]
    return motive
