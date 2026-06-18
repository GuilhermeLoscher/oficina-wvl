from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from ..database import Database
from ..models import Client, Quote, QuoteStatus, quote_from_rows
from ..services.pdf_engine import PdfEngine


class QuoteController:
    def __init__(self, db: Database, base_dir: Path):
        self.db = db
        self.pdf_engine = PdfEngine(base_dir)

    def search_clients(self, text: str):
        return self.db.search_clients(text, limit=12)

    def search_products(self, text: str):
        return self.db.search_products(text, limit=12)

    def build_quote(
        self,
        client_name: str,
        phone: str,
        vehicle: str,
        plate: str,
        status: QuoteStatus,
        tax_rate: Decimal,
        item_rows: list[dict[str, str]],
        notes: str,
    ) -> Quote:
        quote = quote_from_rows(
            client=Client(None, client_name, phone, vehicle, plate),
            rows=item_rows,
            tax_rate=tax_rate,
            status=status,
        )
        quote.notes = notes.strip() or quote.notes
        return quote

    def persist_and_render_pdf(self, quote: Quote, include_cover: bool) -> Path:
        self.db.save_quote(quote)
        return self.pdf_engine.render(quote, include_cover=include_cover)
