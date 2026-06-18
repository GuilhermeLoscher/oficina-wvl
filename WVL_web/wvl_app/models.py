from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Iterable


CENT = Decimal("0.01")


class QuoteStatus(StrEnum):
    DRAFT = "Rascunho"
    SENT = "Enviado"
    APPROVED = "Aprovado"
    DONE = "Concluido"


def money(value: str | int | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        raw = value
    else:
        text = str(value).strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        raw = Decimal(text or "0")
    return raw.quantize(CENT, rounding=ROUND_HALF_UP)


def format_money(value: Decimal) -> str:
    quantized = value.quantize(CENT, rounding=ROUND_HALF_UP)
    text = f"{quantized:,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass(frozen=True)
class Client:
    id: int | None
    name: str
    phone: str = ""
    vehicle: str = ""
    plate: str = ""


@dataclass(frozen=True)
class Product:
    id: int | None
    description: str
    unit_price: Decimal
    unit_cost: Decimal = Decimal("0.00")


@dataclass
class QuoteItem:
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0.00")
    unit_cost: Decimal = Decimal("0.00")
    discount: Decimal = Decimal("0.00")

    @property
    def subtotal(self) -> Decimal:
        total = (self.quantity * self.unit_price) - self.discount
        return max(total, Decimal("0.00")).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def cost_total(self) -> Decimal:
        return (self.quantity * self.unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def profit(self) -> Decimal:
        return (self.subtotal - self.cost_total).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Quote:
    client: Client
    items: list[QuoteItem] = field(default_factory=list)
    created_at: date = field(default_factory=date.today)
    status: QuoteStatus = QuoteStatus.DRAFT
    tax_rate: Decimal = Decimal("0.00")
    notes: str = "Validade da proposta: 7 dias. Pecas e servicos conforme disponibilidade."

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.items), Decimal("0.00")).quantize(CENT)

    @property
    def taxes(self) -> Decimal:
        return (self.subtotal * self.tax_rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        return (self.subtotal + self.taxes).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def profit(self) -> Decimal:
        return sum((item.profit for item in self.items), Decimal("0.00")).quantize(CENT)

    @property
    def margin_percent(self) -> Decimal:
        if self.total <= 0:
            return Decimal("0.00")
        return (self.profit / self.total * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def quote_from_rows(client: Client, rows: Iterable[dict[str, str]], tax_rate: Decimal, status: QuoteStatus) -> Quote:
    items = [
        QuoteItem(
            description=row["description"],
            quantity=Decimal(row["quantity"].replace(",", ".")),
            unit_price=money(row["unit_price"]),
            unit_cost=money(row.get("unit_cost", "0")),
            discount=money(row.get("discount", "0")),
        )
        for row in rows
        if row.get("description", "").strip()
    ]
    return Quote(client=client, items=items, tax_rate=tax_rate, status=status)
