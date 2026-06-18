from __future__ import annotations

import os
from contextlib import redirect_stderr, redirect_stdout
from html import escape
from io import StringIO
from pathlib import Path
from re import sub
from textwrap import wrap

from ..models import Quote, format_money


def safe_filename(value: str) -> str:
    cleaned = sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "cliente"


class PdfEngine:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.output_dir = Path(os.environ.get("WVL_PDF_DIR", base_dir / "orcamentos"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(self, quote: Quote, include_cover: bool = True) -> Path:
        target = self.output_dir / f"Orcamento_{safe_filename(quote.client.name)}.pdf"
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self._render_weasyprint(target, quote, include_cover)
        except Exception:
            self._render_reportlab(target, quote, include_cover)
        return target

    def _render_weasyprint(self, target: Path, quote: Quote, include_cover: bool) -> None:
        from weasyprint import HTML

        HTML(string=self._html(quote, include_cover), base_url=str(self.base_dir)).write_pdf(target)

    def _render_reportlab(self, target: Path, quote: Quote, include_cover: bool) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        width, height = A4
        c = canvas.Canvas(str(target), pagesize=A4)
        c.setTitle(f"Orcamento WVL - {quote.client.name}")

        navy = colors.HexColor("#07111f")
        navy_2 = colors.HexColor("#0d1b2f")
        blue = colors.HexColor("#2563eb")
        emerald = colors.HexColor("#10b981")
        text = colors.HexColor("#101828")
        muted = colors.HexColor("#667085")
        line = colors.HexColor("#e5e7eb")
        soft = colors.HexColor("#f8fafc")
        soft_blue = colors.HexColor("#eef4ff")

        logo_path = next((p for p in (self.base_dir / "assets" / "logo.png", self.base_dir / "logo.png") if p.exists()), None)
        proposal_code = f"WVL-{quote.created_at.strftime('%Y%m%d')}-{safe_filename(quote.client.name)[:10].upper()}"

        def set_font(name: str, size: int, color=text):
            c.setFont(name, size)
            c.setFillColor(color)

        def draw_wrapped(value: str, x: float, y: float, max_chars: int, leading: float, font="Helvetica", size=9, color=text, max_lines: int | None = None) -> float:
            set_font(font, size, color)
            lines = wrap(value or "-", width=max_chars) or ["-"]
            if max_lines:
                lines = lines[:max_lines]
            for line_text in lines:
                c.drawString(x, y, line_text)
                y -= leading
            return y

        def draw_label_value(label: str, value: str, x: float, y: float, w: float, h: float):
            c.setFillColor(soft)
            c.roundRect(x, y - h, w, h, 8, fill=1, stroke=0)
            set_font("Helvetica-Bold", 7, blue)
            c.drawString(x + 10, y - 14, label.upper())
            draw_wrapped(value, x + 10, y - 29, max(12, int(w / 4.3)), 10, "Helvetica", 9, text, 2)

        def footer(page_no: int):
            c.setStrokeColor(line)
            c.line(16 * mm, 13 * mm, width - 16 * mm, 13 * mm)
            set_font("Helvetica", 7, muted)
            c.drawString(16 * mm, 8 * mm, "WVL Oficina | Proposta comercial")
            c.drawRightString(width - 16 * mm, 8 * mm, f"Pagina {page_no}")

        if include_cover:
            c.setFillColor(navy)
            c.rect(0, 0, width, height, fill=1, stroke=0)
            c.setFillColor(navy_2)
            c.roundRect(18 * mm, 18 * mm, width - 36 * mm, height - 36 * mm, 20, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#12315e"))
            c.circle(width - 28 * mm, height - 36 * mm, 72 * mm, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#0f766e"))
            c.circle(22 * mm, 26 * mm, 42 * mm, fill=1, stroke=0)

            if logo_path:
                c.drawImage(str(logo_path), 26 * mm, height - 44 * mm, width=28 * mm, height=22 * mm, preserveAspectRatio=True, mask="auto")
            set_font("Helvetica-Bold", 9, colors.HexColor("#bfdbfe"))
            c.drawString(26 * mm, height - 66 * mm, "PROPOSTA COMERCIAL EXECUTIVA")
            set_font("Helvetica-Bold", 38, colors.white)
            c.drawString(26 * mm, height - 92 * mm, "Orcamento WVL")
            y = draw_wrapped(f"Preparado para {quote.client.name}", 26 * mm, height - 110 * mm, 48, 17, "Helvetica", 14, colors.HexColor("#e5e7eb"), 2)
            set_font("Helvetica", 10, colors.HexColor("#bfdbfe"))
            c.drawString(26 * mm, y - 8, proposal_code)

            card_y = 80 * mm
            card_w = (width - 62 * mm) / 3
            for idx, (label, value) in enumerate(
                [
                    ("Data", quote.created_at.strftime("%d/%m/%Y")),
                    ("Status", quote.status.value),
                    ("Investimento", format_money(quote.total)),
                ]
            ):
                x = 26 * mm + idx * (card_w + 5 * mm)
                c.setFillColor(colors.Color(1, 1, 1, alpha=0.08))
                c.roundRect(x, card_y, card_w, 24 * mm, 10, fill=1, stroke=0)
                set_font("Helvetica-Bold", 7, colors.HexColor("#93c5fd"))
                c.drawString(x + 8, card_y + 15 * mm, label.upper())
                set_font("Helvetica-Bold", 12, colors.white)
                c.drawString(x + 8, card_y + 7 * mm, value)
            c.showPage()

        page_no = 2 if include_cover else 1

        def draw_content_header():
            if logo_path:
                c.drawImage(str(logo_path), 16 * mm, height - 26 * mm, width=22 * mm, height=14 * mm, preserveAspectRatio=True, mask="auto")
                x_text = 42 * mm
            else:
                x_text = 16 * mm
            set_font("Helvetica-Bold", 20, text)
            c.drawString(x_text, height - 22 * mm, "Proposta comercial")
            set_font("Helvetica", 8, muted)
            c.drawString(x_text, height - 28 * mm, f"{quote.created_at.strftime('%d/%m/%Y')} | {quote.status.value} | {proposal_code}")
            c.setFillColor(soft_blue)
            c.roundRect(width - 58 * mm, height - 32 * mm, 42 * mm, 18 * mm, 8, fill=1, stroke=0)
            set_font("Helvetica-Bold", 7, blue)
            c.drawCentredString(width - 37 * mm, height - 21 * mm, "TOTAL")
            set_font("Helvetica-Bold", 12, blue)
            c.drawCentredString(width - 37 * mm, height - 28 * mm, format_money(quote.total))

        draw_content_header()
        y = height - 46 * mm
        gap = 5 * mm
        card_w = (width - 32 * mm - 3 * gap) / 4
        draw_label_value("Cliente", quote.client.name, 16 * mm, y, card_w * 1.45, 24 * mm)
        draw_label_value("Veiculo", quote.client.vehicle or "-", 16 * mm + card_w * 1.45 + gap, y, card_w * .85, 24 * mm)
        draw_label_value("Placa", quote.client.plate or "-", 16 * mm + card_w * 2.3 + 2 * gap, y, card_w * .7, 24 * mm)
        draw_label_value("Contato", quote.client.phone or "-", 16 * mm + card_w * 3 + 3 * gap, y, card_w, 24 * mm)
        y -= 36 * mm

        columns = [
            ("Categoria", 16 * mm, 22 * mm),
            ("Descricao", 40 * mm, 70 * mm),
            ("Qtd.", 112 * mm, 13 * mm),
            ("Unitario", 127 * mm, 26 * mm),
            ("Desc.", 155 * mm, 18 * mm),
            ("Total", 175 * mm, 19 * mm),
        ]

        def draw_table_header(current_y: float) -> float:
            c.setFillColor(navy_2)
            c.roundRect(16 * mm, current_y - 10 * mm, width - 32 * mm, 10 * mm, 6, fill=1, stroke=0)
            set_font("Helvetica-Bold", 7, colors.white)
            for label, x, w_col in columns:
                if label == "Categoria":
                    continue
                if label in {"Qtd.", "Unitario", "Desc.", "Total"}:
                    c.drawRightString(x + w_col - 2, current_y - 6.5 * mm, label.upper())
                else:
                    c.drawString(18 * mm, current_y - 6.5 * mm, label.upper())
            return current_y - 13 * mm

        def classify(item):
            raw_desc = item.description
            if raw_desc.lower().startswith("servico -"):
                return "Servicos", raw_desc.split(" - ", 1)[1], emerald
            if raw_desc.lower().startswith("produto -"):
                return "Produtos", raw_desc.split(" - ", 1)[1], blue
            return "Itens", raw_desc, muted

        grouped = {"Servicos": [], "Produtos": [], "Itens": []}
        for item in quote.items:
            section, clean_desc, color = classify(item)
            grouped[section].append((item, clean_desc, color))

        def draw_section(section_title: str, rows: list[tuple], current_y: float, current_page: int) -> tuple[float, int]:
            if not rows:
                return current_y, current_page
            if current_y < 78 * mm:
                footer(current_page)
                c.showPage()
                current_page += 1
                draw_content_header()
                current_y = height - 46 * mm
            accent = emerald if section_title == "Servicos" else blue if section_title == "Produtos" else muted
            c.setFillColor(accent)
            c.roundRect(16 * mm, current_y - 8 * mm, 24 * mm, 8 * mm, 4, fill=1, stroke=0)
            set_font("Helvetica-Bold", 8, colors.white)
            c.drawCentredString(28 * mm, current_y - 5.6 * mm, section_title.upper())
            current_y -= 12 * mm
            current_y = draw_table_header(current_y)
            for row_index, (item, clean_desc, _color) in enumerate(rows):
                desc_lines = wrap(clean_desc, 48) or ["-"]
                row_h = max(11 * mm, (len(desc_lines) * 4.4 + 6) * mm)
                if current_y - row_h < 54 * mm:
                    footer(current_page)
                    c.showPage()
                    current_page += 1
                    draw_content_header()
                    current_y = height - 46 * mm
                    c.setFillColor(accent)
                    c.roundRect(16 * mm, current_y - 8 * mm, 24 * mm, 8 * mm, 4, fill=1, stroke=0)
                    set_font("Helvetica-Bold", 8, colors.white)
                    c.drawCentredString(28 * mm, current_y - 5.6 * mm, section_title.upper())
                    current_y -= 12 * mm
                    current_y = draw_table_header(current_y)

                c.setFillColor(soft if row_index % 2 else colors.white)
                c.roundRect(16 * mm, current_y - row_h, width - 32 * mm, row_h, 5, fill=1, stroke=0)
                desc_y = current_y - 6.5 * mm
                for line_text in desc_lines[:4]:
                    set_font("Helvetica", 8.6, text)
                    c.drawString(18 * mm, desc_y, line_text)
                    desc_y -= 4.4 * mm
                set_font("Helvetica", 8.4, text)
                c.drawRightString(columns[2][1] + columns[2][2] - 2, current_y - 7 * mm, str(item.quantity))
                c.drawRightString(columns[3][1] + columns[3][2] - 2, current_y - 7 * mm, format_money(item.unit_price))
                c.drawRightString(columns[4][1] + columns[4][2] - 2, current_y - 7 * mm, format_money(item.discount))
                set_font("Helvetica-Bold", 8.5, text)
                c.drawRightString(columns[5][1] + columns[5][2] - 2, current_y - 7 * mm, format_money(item.subtotal))
                c.setStrokeColor(line)
                c.line(16 * mm, current_y - row_h, width - 16 * mm, current_y - row_h)
                current_y -= row_h
            return current_y - 6 * mm, current_page

        set_font("Helvetica-Bold", 12, text)
        c.drawString(16 * mm, y, "Itens da proposta")
        y -= 10 * mm
        for section_name in ("Servicos", "Produtos", "Itens"):
            y, page_no = draw_section(section_name, grouped[section_name], y, page_no)

        y -= 8 * mm
        if y < 78 * mm:
            footer(page_no)
            c.showPage()
            page_no += 1
            draw_content_header()
            y = height - 48 * mm

        totals_x = width - 76 * mm
        c.setFillColor(soft_blue)
        c.roundRect(totals_x, y - 32 * mm, 60 * mm, 32 * mm, 10, fill=1, stroke=0)
        for idx, (label, value, bold) in enumerate(
            [
                ("Subtotal", format_money(quote.subtotal), False),
                ("Impostos", format_money(quote.taxes), False),
                ("Total", format_money(quote.total), True),
            ]
        ):
            yy = y - (8 + idx * 8) * mm
            set_font("Helvetica-Bold" if bold else "Helvetica", 8 if not bold else 10, blue if bold else muted)
            c.drawString(totals_x + 8, yy, label)
            c.drawRightString(totals_x + 56 * mm, yy, value)

        terms_y = y - 42 * mm
        c.setFillColor(soft)
        c.roundRect(16 * mm, terms_y - 28 * mm, width - 32 * mm, 28 * mm, 8, fill=1, stroke=0)
        set_font("Helvetica-Bold", 9, text)
        c.drawString(20 * mm, terms_y - 8 * mm, "Termos comerciais")
        draw_wrapped(quote.notes, 20 * mm, terms_y - 15 * mm, 96, 4.2 * mm, "Helvetica", 8.2, muted, 3)

        sig_top = terms_y - 42 * mm
        if sig_top < 50 * mm:
            footer(page_no)
            c.showPage()
            page_no += 1
            draw_content_header()
            sig_top = height - 62 * mm
        c.setFillColor(colors.white)
        c.roundRect(16 * mm, sig_top - 34 * mm, width - 32 * mm, 34 * mm, 8, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#d0d5dd"))
        c.roundRect(16 * mm, sig_top - 34 * mm, width - 32 * mm, 34 * mm, 8, fill=0, stroke=1)
        set_font("Helvetica-Bold", 9, text)
        c.drawString(20 * mm, sig_top - 8 * mm, "Assinaturas")
        c.setStrokeColor(colors.HexColor("#334155"))
        c.setLineWidth(1.2)
        line_y = sig_top - 22 * mm
        c.line(28 * mm, line_y, 86 * mm, line_y)
        c.line(124 * mm, line_y, 182 * mm, line_y)
        c.setLineWidth(1)
        set_font("Helvetica-Bold", 8, text)
        c.drawCentredString(57 * mm, line_y - 6 * mm, "WVL Oficina")
        c.drawCentredString(153 * mm, line_y - 6 * mm, "Cliente")
        set_font("Helvetica", 7, muted)
        c.drawCentredString(57 * mm, line_y - 11 * mm, "Responsavel pela proposta")
        c.drawCentredString(153 * mm, line_y - 11 * mm, "Aceite do cliente")
        footer(page_no)
        c.save()

    def _logo_uri(self) -> str:
        for candidate in (self.base_dir / "assets" / "logo.png", self.base_dir / "logo.png"):
            if candidate.exists():
                return candidate.as_uri()
        return ""

    def _html(self, quote: Quote, include_cover: bool) -> str:
        rows = "\n".join(
            f"""
            <tr>
                <td class="desc">{escape(item.description)}</td>
                <td>{item.quantity}</td>
                <td>{format_money(item.unit_price)}</td>
                <td>{format_money(item.discount)}</td>
                <td class="money">{format_money(item.subtotal)}</td>
            </tr>
            """
            for item in quote.items
        )
        cover = ""
        logo = self._logo_uri()
        if include_cover:
            cover = f"""
            <section class="cover">
                <div class="brand">
                    {'<img src="' + logo + '" alt="WVL">' if logo else '<strong>WVL</strong>'}
                    <span>Proposta comercial executiva</span>
                </div>
                <h1>Orcamento WVL</h1>
                <p>Preparado para <strong>{escape(quote.client.name)}</strong></p>
                <div class="cover-meta">
                    <span>{quote.created_at.strftime('%d/%m/%Y')}</span>
                    <span>Status: {quote.status.value}</span>
                    <span>Total: {format_money(quote.total)}</span>
                </div>
            </section>
            """
        return f"""
        <!doctype html>
        <html lang="pt-BR">
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 18mm 16mm 20mm;
                    @bottom-center {{
                        content: "Pagina " counter(page) " de " counter(pages);
                        color: #667085;
                        font-size: 9pt;
                    }}
                }}
                * {{ box-sizing: border-box; }}
                body {{
                    font-family: Inter, "Segoe UI", Arial, sans-serif;
                    color: #101828;
                    margin: 0;
                    font-size: 10.5pt;
                    line-height: 1.45;
                }}
                .cover {{
                    min-height: 250mm;
                    padding: 18mm 12mm;
                    background: linear-gradient(135deg, #07111f 0%, #0d1b2f 60%, #12315e 100%);
                    color: white;
                    page-break-after: always;
                    border-radius: 18px;
                }}
                .brand {{ display: flex; align-items: center; gap: 14px; color: #d0d5dd; }}
                .brand img {{ width: 74px; height: auto; }}
                .cover h1 {{ font-size: 46pt; letter-spacing: 0; margin: 48mm 0 8mm; }}
                .cover p {{ font-size: 16pt; color: #e4e7ec; }}
                .cover-meta {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 34mm; }}
                .cover-meta span {{ border: 1px solid rgba(255,255,255,.18); border-radius: 12px; padding: 14px; }}
                header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }}
                header img {{ width: 72px; }}
                h2 {{ font-size: 22pt; margin: 0; color: #0b1220; }}
                .muted {{ color: #667085; }}
                .client-grid {{
                    display: grid;
                    grid-template-columns: 1.4fr 1fr 1fr;
                    gap: 10px;
                    margin: 18px 0 20px;
                }}
                .box {{ background: #f8fafc; border: 1px solid #eaecf0; border-radius: 12px; padding: 12px; }}
                .label {{ display: block; color: #667085; font-size: 8.5pt; text-transform: uppercase; margin-bottom: 4px; }}
                table {{ width: 100%; border-collapse: collapse; page-break-inside: auto; }}
                tr {{ page-break-inside: avoid; page-break-after: auto; }}
                th {{
                    background: #0f172a;
                    color: white;
                    text-align: right;
                    padding: 10px;
                    font-size: 8.5pt;
                    text-transform: uppercase;
                    letter-spacing: .04em;
                }}
                th:first-child {{ text-align: left; border-radius: 10px 0 0 10px; }}
                th:last-child {{ border-radius: 0 10px 10px 0; }}
                td {{ padding: 11px 10px; border-bottom: 1px solid #eef2f6; text-align: right; vertical-align: top; }}
                tbody tr:nth-child(even) td {{ background: #f9fafb; }}
                .desc {{ text-align: left; width: 46%; }}
                .money {{ font-weight: 700; color: #0f172a; }}
                .totals {{ margin-left: auto; margin-top: 18px; width: 260px; }}
                .total-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #eaecf0; }}
                .grand {{ font-size: 15pt; color: #155eef; font-weight: 800; border: 0; }}
                .terms {{ margin-top: 22px; background: #f8fafc; border-radius: 12px; padding: 14px; }}
                .signatures {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 34px; }}
                .signature {{ border-top: 1px solid #98a2b3; text-align: center; padding-top: 8px; color: #667085; }}
            </style>
        </head>
        <body>
            {cover}
            <header>
                <div>
                    <h2>Orcamento comercial</h2>
                    <div class="muted">WVL Oficina | {quote.created_at.strftime('%d/%m/%Y')} | {quote.status.value}</div>
                </div>
                {'<img src="' + logo + '" alt="WVL">' if logo else '<strong>WVL</strong>'}
            </header>
            <section class="client-grid">
                <div class="box"><span class="label">Cliente</span>{escape(quote.client.name)}</div>
                <div class="box"><span class="label">Veiculo</span>{escape(quote.client.vehicle or "-")}</div>
                <div class="box"><span class="label">Contato</span>{escape(quote.client.phone or "-")}</div>
            </section>
            <table>
                <thead>
                    <tr>
                        <th>Descricao</th><th>Qtd.</th><th>Unitario</th><th>Desconto</th><th>Total</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
            <section class="totals">
                <div class="total-row"><span>Subtotal</span><strong>{format_money(quote.subtotal)}</strong></div>
                <div class="total-row"><span>Impostos</span><strong>{format_money(quote.taxes)}</strong></div>
                <div class="total-row grand"><span>Total</span><span>{format_money(quote.total)}</span></div>
            </section>
            <section class="terms">
                <strong>Termos comerciais</strong>
                <p>{escape(quote.notes)}</p>
            </section>
            <section class="signatures">
                <div class="signature">Assinatura WVL</div>
                <div class="signature">Assinatura do cliente</div>
            </section>
        </body>
        </html>
        """
