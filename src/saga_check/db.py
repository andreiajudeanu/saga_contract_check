"""Acces la Supabase (Postgres + Storage). Scriptul ruleaza cu service key, pe PC-ul cu SAGA."""
import os
from datetime import UTC, date, datetime
from decimal import Decimal

from supabase import Client, create_client

from .extract import ArticolExtras, ContractExtras
from .matcher import normalize
from .models import CheckResult, Contract, ContractArticol, Invoice, normalize_cif

BUCKET = "contracte"


def _dec(v) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _date(v) -> date | None:
    return date.fromisoformat(v) if v else None


def articole_plan(existing: list[dict], extrase: list[ArticolExtras]):
    """La recitirea unui contract, articolele cu aceeasi denumire se actualizeaza pe loc (isi pastreaza
    id-ul, deci contul setat manual, maparile si cantitatile consumate); restul se insereaza/sterg.
    Intoarce (de_inserat, de_actualizat[(id, valori)], id-uri pastrate)."""
    by_name = {normalize(r["denumire"]): r["id"] for r in existing}
    new, update, keep = [], [], set()
    for a in extrase:
        values = {"denumire": a.denumire, "cod": a.cod, "um": a.um, "pret_unitar": a.pret_unitar_fara_tva,
                  "moneda": (a.moneda or "RON").upper(), "cantitate_max": a.cantitate_max}
        art_id = by_name.get(normalize(a.denumire))
        if art_id is not None and art_id not in keep:
            update.append((art_id, values))
            keep.add(art_id)
        else:
            new.append(values)
    return new, update, keep


class SupabaseRepo:
    def __init__(self, client: Client | None = None):
        self.sb = client or create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # --- contracte -------------------------------------------------------
    def contracts_for_cif(self, cif: str) -> list[Contract]:
        rows = (self.sb.table("contracte").select("*, contract_articole(*)")
                .eq("furnizor_cif", normalize_cif(cif)).execute().data)
        return [Contract(
            id=r["id"], furnizor_cif=r["furnizor_cif"], nr_contract=r["nr_contract"] or "",
            data_start=_date(r["data_start"]), data_end=_date(r["data_end"]), moneda=r["moneda"],
            plafon_valoare=_dec(r["plafon_valoare"]), termen_plata_zile=r["termen_plata_zile"],
            cota_tva=_dec(r["cota_tva"]), status=r["status"],
            articole=[ContractArticol(
                id=a["id"], denumire=a["denumire"], pret_unitar=Decimal(str(a["pret_unitar"])),
                moneda=a["moneda"], cod=a["cod"] or "", um=a["um"] or "",
                cantitate_max=_dec(a["cantitate_max"]), cont=a.get("cont") or "",
            ) for a in r["contract_articole"]],
        ) for r in rows]

    def mapari(self, cif: str) -> dict[str, int]:
        rows = (self.sb.table("mapari_articole").select("denumire_factura, contract_articol_id")
                .eq("furnizor_cif", normalize_cif(cif)).execute().data)
        return {r["denumire_factura"]: r["contract_articol_id"] for r in rows}

    def contract_sha(self, pdf_path: str) -> str | None:
        rows = self.sb.table("contracte").select("pdf_sha256").eq("pdf_path", pdf_path).execute().data
        return rows[0]["pdf_sha256"] if rows else None

    def upload_pdf(self, pdf_path: str, data: bytes) -> None:
        self.sb.storage.from_(BUCKET).upload(
            pdf_path, data, {"content-type": "application/pdf", "upsert": "true"})

    def save_contract(self, pdf_path: str, sha: str, ex: ContractExtras | None, motive: list[str]) -> None:
        """Insereaza sau actualizeaza contractul si ii inlocuieste articolele."""
        row = {
            "pdf_path": pdf_path, "pdf_sha256": sha,
            "status": "neclar" if motive else "clar", "detalii_neclare": motive,
            "furnizor_cif": normalize_cif(ex.furnizor_cif) if ex else "",
            "furnizor_nume": ex.furnizor_nume if ex else None,
            "nr_contract": ex.nr_contract if ex else None,
            "data_start": ex.data_start if ex else None,
            "data_end": ex.data_end if ex else None,
            "moneda": (ex.moneda or "RON").upper() if ex else "RON",
            "plafon_valoare": ex.plafon_valoare_fara_tva if ex else None,
            "termen_plata_zile": ex.termen_plata_zile if ex else None,
            "cota_tva": ex.cota_tva if ex else None,
            "extras_la": datetime.now(UTC).isoformat(),
        }
        saved = self.sb.table("contracte").upsert(row, on_conflict="pdf_path").execute().data[0]
        existing = (self.sb.table("contract_articole").select("id, denumire")
                    .eq("contract_id", saved["id"]).execute().data)
        new, update, keep = articole_plan(existing, ex.articole if ex else [])
        for art_id, values in update:
            self.sb.table("contract_articole").update(values).eq("id", art_id).execute()
        if new:
            self.sb.table("contract_articole").insert(
                [{"contract_id": saved["id"], **values} for values in new]).execute()
        stale = [r["id"] for r in existing if r["id"] not in keep]
        if stale:
            self.sb.table("contract_articole").delete().in_("id", stale).execute()

    # --- facturi ---------------------------------------------------------
    def is_processed(self, inv: Invoice) -> bool:
        rows = (self.sb.table("facturi_procesate").select("id")
                .eq("furnizor_cif", inv.furnizor_cif).eq("nr", inv.nr)
                .eq("data", inv.data.isoformat()).execute().data)
        return bool(rows)

    def processed_message(self, inv: Invoice) -> str | None:
        rows = (self.sb.table("facturi_procesate").select("mesaj").eq("furnizor_cif", inv.furnizor_cif)
                .eq("nr", inv.nr).eq("data", inv.data.isoformat()).execute().data)
        return rows[0]["mesaj"] if rows else None

    def forget_processed(self, inv: Invoice) -> None:
        """Sterge evidenta unei facturi procesate (liniile de consum se sterg in cascada)."""
        (self.sb.table("facturi_procesate").delete().eq("furnizor_cif", inv.furnizor_cif)
         .eq("nr", inv.nr).eq("data", inv.data.isoformat()).execute())

    def consum_valoare(self, contract_id: int) -> Decimal:
        rows = self.sb.table("consum_contracte").select("valoare").eq("contract_id", contract_id).execute().data
        return Decimal(str(rows[0]["valoare"])) if rows else Decimal(0)

    def consum_cantitate(self, articol_id: int) -> Decimal:
        rows = (self.sb.table("consum_articole").select("cantitate")
                .eq("contract_articol_id", articol_id).execute().data)
        return Decimal(str(rows[0]["cantitate"])) if rows else Decimal(0)

    def save_processed(self, inv: Invoice, result: CheckResult, saga_path: str) -> None:
        fid = self.sb.table("facturi_procesate").insert({
            "furnizor_cif": inv.furnizor_cif, "nr": inv.nr, "data": inv.data.isoformat(),
            "valoare_fara_tva_ron": str(result.valoare_ron), "conform": result.conform,
            "mesaj": result.mesaj, "xml_original_path": inv.sursa, "saga_xml_path": saga_path,
        }).execute().data[0]["id"]
        if result.consum:
            self.sb.table("facturi_procesate_linii").insert([{
                "factura_id": fid, "contract_id": c.contract_id,
                "contract_articol_id": c.contract_articol_id,
                "cantitate": str(c.cantitate), "valoare_contract": str(c.valoare_contract),
            } for c in result.consum]).execute()

    # --- curs BNR (RateStore) -------------------------------------------
    def get_rate(self, zi: date, moneda: str) -> Decimal | None:
        rows = (self.sb.table("curs_bnr").select("curs").eq("data", zi.isoformat())
                .eq("moneda", moneda).execute().data)
        return Decimal(str(rows[0]["curs"])) if rows else None

    def save_rate(self, zi: date, moneda: str, curs: Decimal) -> None:
        self.sb.table("curs_bnr").upsert(
            {"data": zi.isoformat(), "moneda": moneda, "curs": str(curs)}).execute()

