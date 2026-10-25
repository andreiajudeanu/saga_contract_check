"""Potrivirea unei linii de factura cu un articol din contract, dupa denumire."""
import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from .models import Contract, ContractArticol, InvoiceLine


def normalize(text: str) -> str:
    """Litere mici, fara diacritice si punctuatie: 'Servicii  Mentenanță-IT' -> 'servicii mentenanta it'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass
class Match:
    contract: Contract
    articol: ContractArticol
    scor: float


def match_line(
    line: InvoiceLine,
    contracts: list[Contract],
    prag: int,
    mapari: dict[str, int] | None = None,
) -> Match | None:
    """Ordine: mapare facuta de admin, cod articol identic, apoi cea mai buna denumire peste prag."""
    name = normalize(line.denumire)
    pairs = [(c, a) for c in contracts for a in c.articole]

    if mapari and (art_id := mapari.get(name)) is not None:
        for c, a in pairs:
            if a.id == art_id:
                return Match(c, a, 100.0)

    if line.cod:
        cod = normalize(line.cod)
        for c, a in pairs:
            if a.cod and normalize(a.cod) == cod:
                return Match(c, a, 100.0)

    # token_set_ratio da 100 si cand o denumire o include pe cealalta ("Hartie A4" in
    # "Hartie A4 premium"); la egalitate decide token_sort_ratio, care penalizeaza cuvintele in plus.
    best, best_key = None, (-1.0, -1.0)
    for c, a in pairs:
        other = normalize(a.denumire)
        key = (fuzz.token_set_ratio(name, other), fuzz.token_sort_ratio(name, other))
        if key[0] >= prag and key > best_key:
            best, best_key = Match(c, a, key[0]), key
    return best
