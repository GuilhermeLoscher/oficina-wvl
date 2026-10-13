from __future__ import annotations

import base64
import json
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..models import Quote


METADATA_KEY = "/WVLQuoteData"
MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_ITEMS = 500


class PdfImportError(ValueError):
    pass


def _quote_payload(quote: Quote, include_cover: bool) -> dict:
    return {
        "format_version": 1,
        "created_at": quote.created_at.isoformat(),
        "client_name": quote.client.name,
        "phone": quote.client.phone,
        "vehicle": quote.client.vehicle,
        "plate": quote.client.plate,
        "status": quote.status.value,
        "tax_rate": str(quote.tax_rate),
        "notes": quote.notes,
        "include_cover": include_cover,
        "items": [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "unit_cost": str(item.unit_cost),
                "discount": str(item.discount),
            }
            for item in quote.items
        ],
    }


def embed_quote_payload(path: Path, quote: Quote, include_cover: bool) -> None:
    encoded = base64.urlsafe_b64encode(
        json.dumps(_quote_payload(quote, include_cover), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    reader = PdfReader(str(path))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items() if value is not None}
    metadata[METADATA_KEY] = encoded
    writer.add_metadata(metadata)
    temporary = path.with_suffix(".metadata.pdf")
    try:
        with temporary.open("wb") as stream:
            writer.write(stream)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_payload(data: object) -> dict:
    if not isinstance(data, dict):
        raise PdfImportError("Os dados internos deste PDF são inválidos.")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise PdfImportError("Nenhum item editável foi encontrado neste PDF.")
    if len(items) > MAX_ITEMS:
        raise PdfImportError("Este PDF possui itens demais para importação.")

    clean_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        clean_items.append(
            {
                "description": description[:2000],
                "quantity": str(item.get("quantity") or "1"),
                "unit_price": str(item.get("unit_price") or "0"),
                "unit_cost": str(item.get("unit_cost") or "0"),
                "discount": str(item.get("discount") or "0"),
            }
        )
    if not clean_items:
        raise PdfImportError("Nenhum item editável foi encontrado neste PDF.")

    return {
        "client_name": str(data.get("client_name", "")).strip()[:300],
        "phone": str(data.get("phone", "")).strip()[:80],
        "vehicle": str(data.get("vehicle", "")).strip()[:200],
        "plate": str(data.get("plate", "")).strip()[:30],
        "status": str(data.get("status", "Rascunho")).strip(),
        "tax_rate": str(data.get("tax_rate") or "0"),
        "notes": str(data.get("notes", "")).strip()[:4000],
        "include_cover": bool(data.get("include_cover", True)),
        "items": clean_items,
    }


def _decode_metadata(reader: PdfReader) -> dict | None:
    encoded = (reader.metadata or {}).get(METADATA_KEY)
    if not encoded:
        return None
    try:
        decoded = base64.urlsafe_b64decode(str(encoded).encode("ascii")).decode("utf-8")
        return _validate_payload(json.loads(decoded))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise PdfImportError("Os dados editáveis deste PDF estão danificados.") from exc


_TEXT_REPAIRS = {
    "Or�amento": "Orçamento",
    "or�amento": "orçamento",
    "Servi�o": "Serviço",
    "servi�o": "serviço",
    "cap�": "capô",
    "repara��o": "reparação",
    "El�trica": "Elétrica",
    "el�trica": "elétrica",
    "far�is": "faróis",
    "Mec�nica": "Mecânica",
    "mec�nica": "mecânica",
    "Vidra�aria": "Vidraçaria",
    "vidra�aria": "vidraçaria",
    "Reservat�rio": "Reservatório",
    "reservat�rio": "reservatório",
    "�gua": "Água",
    "g�s": "gás",
}


def _repair_text(value: str) -> str:
    repaired = value
    for broken, correct in _TEXT_REPAIRS.items():
        repaired = repaired.replace(broken, correct)
    return repaired.replace("�", "?")


def _br_decimal(value: str) -> Decimal:
    try:
        return Decimal(value.replace(".", "").replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise PdfImportError("Um dos valores do PDF não pôde ser reconhecido.") from exc


def _next_value(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        if line.strip().upper() != label:
            continue
        for candidate in lines[index + 1 :]:
            candidate = candidate.strip()
            if candidate:
                return "" if candidate == "-" else _repair_text(candidate)
    return ""


def _legacy_payload(reader: PdfReader) -> tuple[dict, list[str]]:
    page_texts = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n".join(page_texts)
    detail_text = next((text for text in page_texts if "CLIENTE" in text and "DESCRICAO" in text), full_text)
    lines = detail_text.splitlines()

    row_pattern = re.compile(
        r"(?P<description>(?:Servi.o|Produto)\s*-\s*.*?)\s*"
        r"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
        r"R\$\s*(?P<unit>[\d.]+,\d{2})\s+"
        r"R\$\s*(?P<discount>[\d.]+,\d{2})\s+"
        r"R\$\s*(?P<total>[\d.]+,\d{2})",
        re.DOTALL,
    )
    items = []
    for match in row_pattern.finditer(full_text):
        description = re.sub(r"\s+", " ", match.group("description")).strip()
        description = re.sub(r"Pagina\s+\d+\s+de\s+\d+.*?DESCRICAO\s+QTD\.\s+UNITARIO\s+DESCONTO\s+TOTAL", " ", description)
        items.append(
            {
                "description": _repair_text(description),
                "quantity": match.group("quantity").replace(",", "."),
                "unit_price": str(_br_decimal(match.group("unit"))),
                "unit_cost": "0",
                "discount": str(_br_decimal(match.group("discount"))),
            }
        )
    if not items:
        raise PdfImportError("Não foi possível reconhecer os itens. Importe um PDF gerado pelo aplicativo WVL.")

    status = "Rascunho"
    for candidate in ("Concluido", "Aprovado", "Enviado", "Rascunho"):
        if re.search(rf"(?:Status:\s*|\|\s*){re.escape(candidate)}\b", full_text):
            status = candidate
            break

    subtotal_match = re.search(r"Subtotal\s+R\$\s*([\d.]+,\d{2})", full_text)
    taxes_match = re.search(r"Impostos\s+R\$\s*([\d.]+,\d{2})", full_text)
    tax_rate = Decimal("0")
    if subtotal_match and taxes_match:
        subtotal = _br_decimal(subtotal_match.group(1))
        taxes = _br_decimal(taxes_match.group(1))
        if subtotal:
            tax_rate = (taxes / subtotal * Decimal("100")).quantize(Decimal("0.01"))

    notes = ""
    notes_match = re.search(r"Termos comerciais\s*(.*?)\s*Assinatura", full_text, re.DOTALL)
    if notes_match:
        notes = _repair_text(re.sub(r"\s+", " ", notes_match.group(1)).strip())

    payload = _validate_payload(
        {
            "client_name": _next_value(lines, "CLIENTE") or "Orçamento importado",
            "phone": _next_value(lines, "CONTATO"),
            "vehicle": _next_value(lines, "VEICULO"),
            "plate": "",
            "status": status,
            "tax_rate": str(tax_rate),
            "notes": notes,
            "include_cover": "Proposta comercial executiva" in full_text,
            "items": items,
        }
    )
    warnings = ["PDF antigo importado por leitura visual. Revise placa, acentos e valores antes de enviar."]
    return payload, warnings


def import_quote_pdf(content: bytes) -> tuple[dict, list[str], str]:
    if not content or len(content) > MAX_PDF_BYTES:
        raise PdfImportError("O PDF deve ter no máximo 12 MB.")
    if not content.startswith(b"%PDF"):
        raise PdfImportError("O arquivo selecionado não é um PDF válido.")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise PdfImportError("PDFs protegidos por senha não podem ser importados.")
        if not reader.pages or len(reader.pages) > MAX_PDF_PAGES:
            raise PdfImportError("O PDF deve ter entre 1 e 20 páginas.")
        embedded = _decode_metadata(reader)
        if embedded:
            return embedded, [], "dados_internos"
        payload, warnings = _legacy_payload(reader)
        return payload, warnings, "leitura_visual"
    except PdfImportError:
        raise
    except Exception as exc:
        raise PdfImportError("Não foi possível ler este PDF. Use um arquivo gerado pelo aplicativo WVL.") from exc
