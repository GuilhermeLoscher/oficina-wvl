from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask, jsonify, render_template, request, send_file, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from wvl_app.controllers.quote_controller import QuoteController
from wvl_app.database import Database
from wvl_app.models import Client, Product, QuoteStatus, format_money, money


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("WVL_DATA_DIR", BASE_DIR / "data"))
PDF_DIR = Path(os.environ.get("WVL_PDF_DIR", BASE_DIR / "orcamentos"))
DB_PATH = DATA_DIR / "wvl.sqlite3"

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
db = Database(DB_PATH)
db.initialize()
controller = QuoteController(db, BASE_DIR)


def parse_decimal(value: str | int | float | None, fallback: str = "0") -> Decimal:
    try:
        return money(str(value if value is not None else fallback))
    except (InvalidOperation, ValueError):
        return money(fallback)


def quote_payload(data: dict):
    raw_items = data.get("items") or []
    item_rows = []
    for item in raw_items:
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        item_rows.append(
            {
                "description": description,
                "quantity": str(item.get("quantity") or "1"),
                "unit_price": str(item.get("unit_price") or "0"),
                "unit_cost": str(item.get("unit_cost") or "0"),
                "discount": str(item.get("discount") or "0"),
            }
        )

    status_text = data.get("status") or QuoteStatus.DRAFT.value
    if status_text not in {status.value for status in QuoteStatus}:
        status_text = QuoteStatus.DRAFT.value

    return controller.build_quote(
        client_name=str(data.get("client_name", "")).strip(),
        phone=str(data.get("phone", "")).strip(),
        vehicle=str(data.get("vehicle", "")).strip(),
        plate=str(data.get("plate", "")).strip(),
        status=QuoteStatus(status_text),
        tax_rate=parse_decimal(data.get("tax_rate")),
        item_rows=item_rows,
        notes=str(data.get("notes", "")).strip(),
    )


def quote_json(quote):
    return {
        "client_name": quote.client.name,
        "phone": quote.client.phone,
        "vehicle": quote.client.vehicle,
        "plate": quote.client.plate,
        "status": quote.status.value,
        "tax_rate": str(quote.tax_rate),
        "notes": quote.notes,
        "subtotal": format_money(quote.subtotal),
        "taxes": format_money(quote.taxes),
        "total": format_money(quote.total),
        "profit": format_money(quote.profit),
        "margin_percent": f"{quote.margin_percent}%",
        "items": [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "unit_cost": str(item.unit_cost),
                "discount": str(item.discount),
                "subtotal": format_money(item.subtotal),
            }
            for item in quote.items
        ],
    }


@app.get("/")
def home():
    return render_template(
        "index.html",
        statuses=[status.value for status in QuoteStatus],
        metrics=db.dashboard_metrics(),
        asset_version="20260618-2",
    )


@app.get("/api/bootstrap")
def bootstrap():
    return jsonify(
        {
            "metrics": db.dashboard_metrics(),
            "clients": [client.__dict__ for client in db.search_clients("", limit=12)],
            "products": [product.__dict__ | {"unit_price": str(product.unit_price), "unit_cost": str(product.unit_cost)} for product in db.search_products("", limit=12)],
            "history": db.list_quotes(limit=20),
            "statuses": [status.value for status in QuoteStatus],
        }
    )


@app.get("/api/clients")
def clients():
    query = request.args.get("q", "")
    return jsonify([client.__dict__ for client in controller.search_clients(query)])


@app.get("/api/products")
def products():
    query = request.args.get("q", "")
    result = []
    for product in controller.search_products(query):
        result.append(
            {
                "id": product.id,
                "description": product.description,
                "unit_price": str(product.unit_price),
                "unit_cost": str(product.unit_cost),
            }
        )
    return jsonify(result)


@app.post("/api/products")
def save_product():
    data = request.get_json(force=True)
    description = str(data.get("description", "")).strip()
    if not description:
        return jsonify({"error": "Informe a descricao do produto ou servico."}), 400
    product_id = db.upsert_product(
        Product(
            None,
            description,
            parse_decimal(data.get("unit_price")),
            parse_decimal(data.get("unit_cost")),
        )
    )
    return jsonify({"status": "ok", "id": product_id})


@app.post("/api/preview")
def preview():
    quote = quote_payload(request.get_json(force=True))
    return jsonify(quote_json(quote))


@app.post("/api/quotes")
def create_quote():
    data = request.get_json(force=True)
    quote = quote_payload(data)
    if not quote.client.name:
        return jsonify({"error": "Informe o cliente."}), 400
    if not quote.items:
        return jsonify({"error": "Inclua pelo menos um item."}), 400

    include_cover = bool(data.get("include_cover", True))
    path = controller.persist_and_render_pdf(quote, include_cover=include_cover)
    filename = path.name
    download_url = url_for("download", filename=filename)
    absolute_download_url = url_for("download", filename=filename, _external=True)
    phone = "".join(ch for ch in quote.client.phone if ch.isdigit())
    if phone and not phone.startswith("55"):
        phone = "55" + phone
    message = quote_plus(
        f"Ola, {quote.client.name}! Segue o orcamento WVL. "
        f"Total: {format_money(quote.total)}. Baixe o PDF aqui: {absolute_download_url}"
    )
    whatsapp = f"https://wa.me/{phone}?text={message}" if phone else f"https://wa.me/?text={message}"
    return jsonify(
        {
            "status": "ok",
            "quote": quote_json(quote),
            "filename": filename,
            "download_url": download_url,
            "absolute_download_url": absolute_download_url,
            "whatsapp_url": whatsapp,
            "metrics": db.dashboard_metrics(),
            "history": db.list_quotes(limit=20),
        }
    )


@app.get("/api/history")
def history():
    return jsonify(db.list_quotes(limit=100))


@app.get("/api/history/<int:quote_id>")
def load_history_quote(quote_id: int):
    try:
        return jsonify(quote_json(db.load_quote(quote_id)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@app.post("/api/backup")
def backup():
    path = db.backup()
    return jsonify({"status": "ok", "path": str(path)})


@app.get("/download/<path:filename>")
def download(filename: str):
    path = PDF_DIR / filename
    if not path.exists():
        return "Arquivo nao encontrado", 404
    return send_file(path, as_attachment=True, download_name=filename)


@app.get("/relatorio-mensal")
def monthly_report():
    path = db.export_monthly_workbook()
    return send_file(path, as_attachment=True, download_name=path.name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
