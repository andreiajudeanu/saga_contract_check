"""Cursuri BNR (curs.bnr.ro; din 06.08.2026 nu mai sunt pe www.bnr.ro). Pentru o data fara curs (weekend, sarbatoare) se ia ultimul curs publicat inainte."""
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx

YEAR_URL = "https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml"
RECENT_URL = "https://curs.bnr.ro/nbrfxrates10days.xml"


class RateStore(Protocol):
    def get_rate(self, zi: date, moneda: str) -> Decimal | None: ...
    def save_rate(self, zi: date, moneda: str, curs: Decimal) -> None: ...


def parse_rates(xml: bytes) -> dict[date, dict[str, Decimal]]:
    # Namespace-ul s-a schimbat in timp (http:// -> https://www.bnr.ro/xsd); cautam dupa numele local.
    out: dict[date, dict[str, Decimal]] = {}
    root = ET.fromstring(xml)
    for cube in (e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "Cube"):
        zi = date.fromisoformat(cube.get("date"))
        rates = out.setdefault(zi, {})
        for r in (e for e in cube if e.tag.rsplit("}", 1)[-1] == "Rate"):
            mult = Decimal(r.get("multiplier", "1"))
            rates[r.get("currency")] = Decimal(r.text.strip()) / mult
    return out


def _http_get(url: str) -> bytes:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


class BnrRates:
    def __init__(self, store: RateStore | None = None, fetch: Callable[[str], bytes] = _http_get):
        self._store = store
        self._fetch = fetch
        self._loaded: set[str] = set()
        self._rates: dict[date, dict[str, Decimal]] = {}

    def _load(self, url: str) -> None:
        if url not in self._loaded:
            self._rates.update(parse_rates(self._fetch(url)))
            self._loaded.add(url)

    def _lookup(self, zi: date, moneda: str) -> Decimal | None:
        candidates = [d for d, r in self._rates.items() if d <= zi and moneda in r]
        return self._rates[max(candidates)][moneda] if candidates else None

    def rate(self, moneda: str, zi: date) -> Decimal:
        """RON pentru 1 unitate din `moneda`, valabil la data `zi`."""
        moneda = moneda.upper()
        if moneda == "RON":
            return Decimal(1)
        if self._store and (cached := self._store.get_rate(zi, moneda)) is not None:
            return cached
        self._load(YEAR_URL.format(year=zi.year))
        if not any(d >= zi for d in self._rates):
            self._load(RECENT_URL)  # arhiva anuala poate fi in urma cu cateva zile
        found = self._lookup(zi, moneda)
        if found is None and zi.month == 1:
            self._load(YEAR_URL.format(year=zi.year - 1))  # 1-2 ianuarie: ultimul curs e din decembrie
            found = self._lookup(zi, moneda)
        if found is None:
            raise LookupError(f"Nu exista curs BNR pentru {moneda} la {zi}")
        if self._store:
            self._store.save_rate(zi, moneda, found)
        return found

    def to_ron(self, amount: Decimal, moneda: str, zi: date) -> Decimal:
        return amount * self.rate(moneda, zi)

    def convert(self, amount: Decimal, din: str, in_: str, zi: date) -> Decimal:
        if din.upper() == in_.upper():
            return amount
        return amount * self.rate(din, zi) / self.rate(in_, zi)
