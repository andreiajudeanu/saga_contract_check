import os
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Config:
    firma_cif: str
    efactura_dir: Path
    contracte_dir: Path
    import_dir: Path
    log_dir: Path
    data_start: date
    toleranta_pret: Decimal = Decimal("0.01")
    prag_potrivire: int = 85
    simboluri: str = "ascii"
    lungime_max_mesaj: int = 250
    format_data: str = "%d.%m.%Y"
    cif_in_nume_fisier: str = "furnizor"
    gestiune: str = ""
    activitate: str = ""
    cont: str = ""
    tip_deducere: str = ""
    claude_model: str = "claude-sonnet-5-5"
    prag_incredere: float = 0.8


def load_env(path: Path) -> None:
    """Incarca KEY=valoare din .env in os.environ (fara sa suprascrie variabilele deja setate)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load(path: Path) -> Config:
    load_env(path.with_name(".env"))
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    f, d, p, s, c = raw["firma"], raw["foldere"], raw["procesare"], raw["saga"], raw.get("claude", {})
    return Config(
        firma_cif=f["cif"],
        efactura_dir=Path(d["efactura_saga"]),
        contracte_dir=Path(d["contracte_pdf"]),
        import_dir=Path(d["import_saga"]),
        log_dir=Path(d["log"]),
        data_start=p["data_start"],
        toleranta_pret=Decimal(str(p.get("toleranta_pret_lei", "0.01"))),
        prag_potrivire=int(p.get("prag_potrivire", 85)),
        simboluri=p.get("simboluri", "ascii"),
        lungime_max_mesaj=int(p.get("lungime_max_mesaj", 250)),
        format_data=s.get("format_data", "%d.%m.%Y"),
        cif_in_nume_fisier=s.get("cif_in_nume_fisier", "furnizor"),
        gestiune=s.get("gestiune", ""),
        activitate=s.get("activitate", ""),
        cont=s.get("cont", ""),
        tip_deducere=s.get("tip_deducere", ""),
        claude_model=c.get("model", "claude-sonnet-5-5"),
        prag_incredere=float(c.get("prag_incredere", 0.8)),
    )
