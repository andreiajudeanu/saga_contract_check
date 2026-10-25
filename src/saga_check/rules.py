"""Verificarea unei facturi fata de contractele furnizorului -> textul "bifei" din SAGA."""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .bnr import BnrRates
from .matcher import match_line
from .models import CheckResult, ConsumLinie, Contract, Invoice

CENT = Decimal("0.01")


@dataclass
class Settings:
    toleranta_pret: Decimal = Decimal("0.01")
    prag_potrivire: int = 85
    simboluri: str = "ascii"
    lungime_max_mesaj: int = 250

    @property
    def ok(self) -> str:
        return "✔" if self.simboluri == "unicode" else "[OK]"

    @property
    def x(self) -> str:
        return "✘" if self.simboluri == "unicode" else "[X]"


def fmt(amount: Decimal, moneda: str = "RON", semn: bool = False) -> str:
    """Format romanesc: 1250.5 -> '1.250,50 lei'."""
    q = amount.quantize(CENT, ROUND_HALF_UP)
    txt = f"{abs(q):,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    prefix = ("+" if q > 0 else "-" if q < 0 else "") if semn else ("-" if q < 0 else "")
    return f"{prefix}{txt} {'lei' if moneda.upper() == 'RON' else moneda.upper()}"


def _qty(q: Decimal) -> str:
    return f"{q.normalize():f}".replace(".", ",")


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def verifica(
    inv: Invoice,
    contracts: list[Contract],
    rates: BnrRates,
    s: Settings,
    consum_valoare: Callable[[int], Decimal],
    consum_cantitate: Callable[[int], Decimal],
    mapari: dict[str, int] | None = None,
) -> CheckResult:
    valoare_ron = rates.to_ron(inv.total_fara_tva, inv.moneda, inv.data).quantize(CENT)

    conturi: dict[int, str] = {}
    potrivite: set[int] = set()

    def fail(*abateri: str, linii: dict[int, str] | None = None, consum=None) -> CheckResult:
        msg = _truncate(f"{s.x} " + "; ".join(abateri), s.lungime_max_mesaj)
        return CheckResult(False, msg, linii or {}, conturi, potrivite, consum or [], valoare_ron)

    if not contracts:
        return fail("Fără contract pentru furnizor")
    active = [c for c in contracts if c.activ_la(inv.data)]
    if not active:
        return fail(f"Fără contract activ la {inv.data:%d.%m.%Y}")

    matches = {}
    for ln in inv.linii:
        if not ln.ajustare:
            matches[ln.nr_crt] = match_line(ln, active, s.prag_potrivire, mapari)
    unmatched = [n for n, m in matches.items() if m is None]
    conturi.update({n: m.articol.cont for n, m in matches.items() if m and m.articol.cont})
    potrivite.update(n for n, m in matches.items() if m)
    used = {m.contract.id: m.contract for m in matches.values() if m}

    neclare = [c for c in used.values() if c.status != "clar"]
    if not neclare and unmatched:
        neclare = [c for c in active if c.status != "clar"]
    if neclare:
        return fail("Contract neclar " + ", ".join(c.nr_contract or f"#{c.id}" for c in neclare)
                    + " – verificare necesară")

    abateri: list[str] = []
    linii_msg: dict[int, str] = {}
    consum: list[ConsumLinie] = []

    for n in unmatched:
        linii_msg[n] = "Articol neidentificat în contract"
    if unmatched:
        abateri.append("Articol neidentificat: linia " + ", ".join(map(str, unmatched)))

    for c in used.values():
        if inv.moneda.upper() not in ("RON", c.moneda.upper()):
            abateri.append(f"Monedă {inv.moneda} în loc de {c.moneda}" + (f" ({c.nr_contract})" if len(used) > 1 else ""))

    qty_per_art: dict[int, Decimal] = defaultdict(Decimal)
    val_per_contract: dict[int, Decimal] = defaultdict(Decimal)
    for ln in inv.linii:
        m = matches.get(ln.nr_crt)
        if m is None:
            continue
        c, a = m.contract, m.articol
        if not inv.este_storno:  # o nota de credit doar scade din plafoane
            diff = (rates.to_ron(ln.pret, inv.moneda, inv.data)
                    - rates.to_ron(a.pret_unitar, a.moneda, inv.data))
            if abs(diff) > s.toleranta_pret:
                linii_msg[ln.nr_crt] = f"Preț {fmt(diff, semn=True)}/unit. față de contract"
                abateri.append(f"Preț linia {ln.nr_crt}: {fmt(diff, semn=True)}/unit.")
        if (c.cota_tva is not None and ln.categorie_tva == "S"
                and ln.cota_tva != c.cota_tva):
            abateri.append(f"TVA linia {ln.nr_crt}: {_qty(ln.cota_tva)}% în loc de {_qty(c.cota_tva)}%")
        val = rates.convert(ln.valoare, inv.moneda, c.moneda, inv.data).quantize(CENT)
        qty_per_art[a.id] += ln.cantitate
        val_per_contract[c.id] += val
        consum.append(ConsumLinie(c.id, a.id, ln.cantitate, val))

    # Reducerile/majorarile de document intra in plafon doar cand factura tine de un singur contract.
    if len(used) == 1:
        c = next(iter(used.values()))
        for ln in inv.linii:
            if ln.ajustare:
                val = rates.convert(ln.valoare, inv.moneda, c.moneda, inv.data).quantize(CENT)
                val_per_contract[c.id] += val
                consum.append(ConsumLinie(c.id, None, Decimal(0), val))
                if ln.valoare > 0 and not inv.este_storno:
                    abateri.append(f"Majorare necontractată: {fmt(ln.valoare, inv.moneda, semn=True)}")

    for m in {m.articol.id: m for m in matches.values() if m}.values():
        a = m.articol
        if a.cantitate_max is not None and qty_per_art[a.id] > 0:
            total = consum_cantitate(a.id) + qty_per_art[a.id]
            if total > a.cantitate_max:
                abateri.append(f"Cantitate „{a.denumire[:30]}” depășită cu {_qty(total - a.cantitate_max)}")

    for c in used.values():
        if c.plafon_valoare is not None and val_per_contract[c.id] > 0:
            total = consum_valoare(c.id) + val_per_contract[c.id]
            if total > c.plafon_valoare:
                eticheta_plafon = f"Plafon {c.nr_contract}" if len(used) > 1 else "Plafon"
                abateri.append(f"{eticheta_plafon} depășit cu {fmt(total - c.plafon_valoare, c.moneda)}")

        if c.termen_plata_zile is not None and inv.scadenta and not inv.este_storno:
            zile = (inv.scadenta - inv.data).days
            if zile < c.termen_plata_zile:
                abateri.append(f"Scadență {zile} zile < {c.termen_plata_zile} din contract")

    if abateri:
        # Contractul in fata mesajului, ca in SAGA sa se vada direct la ce contract se refera abaterea.
        nrs = ", ".join(c.nr_contract or f"#{c.id}" for c in (used.values() if used else active))
        return fail(f"{nrs}: {abateri[0]}", *abateri[1:], linii=linii_msg, consum=consum)
    nrs = ", ".join(c.nr_contract or f"#{c.id}" for c in used.values())
    eticheta = "Storno conform contract" if inv.este_storno else "Conform contract"
    msg = _truncate(f"{s.ok} {eticheta} {nrs}".strip(), s.lungime_max_mesaj)
    return CheckResult(True, msg, {}, conturi, potrivite, consum, valoare_ron)
