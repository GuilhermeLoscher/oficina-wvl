from __future__ import annotations

import os
import re
import webbrowser
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover
    pg = None

from PyQt6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..controllers.quote_controller import QuoteController
from ..database import Database
from ..models import Quote, QuoteStatus, format_money, money
from ..workers import TaskWorker


class MainWindow(QMainWindow):
    headers = ["Descricao", "Qtd.", "Preco", "Custo", "Desconto", "Total"]

    def __init__(self, db: Database, base_dir: Path):
        super().__init__()
        self.db = db
        self.base_dir = base_dir
        self.controller = QuoteController(db, base_dir)
        self.thread_pool = QThreadPool.globalInstance()
        self.client_cache = {}
        self.product_cache = {}
        self.last_pdf_path: Path | None = None
        self.send_whatsapp_after_pdf = False

        self.setWindowTitle("WVL Orcamentos Premium")
        self.resize(1360, 820)
        self.setMinimumSize(1180, 720)
        icon = base_dir / "assets" / "icone.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.client_timer = QTimer(self)
        self.client_timer.setSingleShot(True)
        self.client_timer.timeout.connect(self.refresh_client_suggestions)

        self.product_timer = QTimer(self)
        self.product_timer.setSingleShot(True)
        self.product_timer.timeout.connect(self.refresh_product_suggestions)

        self.build_ui()
        self.refresh_dashboard()
        self.add_empty_row()
        self.update_totals()

    def build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        root.setMinimumHeight(840)
        shell = QVBoxLayout(root)
        shell.setContentsMargins(22, 18, 22, 18)
        shell.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("WVL Orcamentos")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Propostas comerciais com controle financeiro em tempo real")
        subtitle.setObjectName("Muted")
        title.setMinimumWidth(0)
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        title_box = QVBoxLayout()
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.status_combo = QComboBox()
        self.status_combo.addItems([status.value for status in QuoteStatus])
        self.status_combo.currentTextChanged.connect(self.paint_status_tracker)
        self.status_combo.setFixedSize(116, 40)

        self.btn_pdf = QPushButton("Gerar PDF")
        self.btn_pdf.setObjectName("PrimaryButton")
        self.btn_pdf.clicked.connect(self.generate_pdf)
        self.btn_pdf.setFixedSize(104, 40)
        self.btn_new = QPushButton("Novo")
        self.btn_new.setObjectName("GhostButton")
        self.btn_new.clicked.connect(self.reset_form)
        self.btn_new.setFixedSize(78, 40)
        self.btn_pdf_whatsapp = QPushButton("PDF + WhatsApp")
        self.btn_pdf_whatsapp.setObjectName("WhatsAppButton")
        self.btn_pdf_whatsapp.clicked.connect(self.generate_pdf_and_whatsapp)
        self.btn_pdf_whatsapp.setFixedSize(132, 40)
        self.btn_manage = QPushButton("Cadastros")
        self.btn_manage.clicked.connect(self.open_catalog_dialog)
        self.btn_manage.setFixedSize(96, 40)
        self.btn_history = QPushButton("Historico")
        self.btn_history.clicked.connect(self.open_history_dialog)
        self.btn_history.setFixedSize(88, 40)
        self.btn_export = QPushButton("Exportar mes")
        self.btn_export.clicked.connect(self.export_month)
        self.btn_export.setFixedSize(104, 40)

        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(self.status_combo)
        top.addWidget(self.btn_manage)
        top.addWidget(self.btn_history)
        top.addWidget(self.btn_export)
        top.addWidget(self.btn_new)
        top.addWidget(self.btn_pdf)
        top.addWidget(self.btn_pdf_whatsapp)
        shell.addLayout(top)

        self.status_tracker = QHBoxLayout()
        self.status_labels: list[QLabel] = []
        for status in QuoteStatus:
            label = QLabel(status.value)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName("StatusPill")
            label.setFixedHeight(36)
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.mousePressEvent = lambda _event, value=status.value: self.status_combo.setCurrentText(value)
            self.status_tracker.addWidget(label)
            self.status_labels.append(label)
        shell.addLayout(self.status_tracker)

        content = QGridLayout()
        content.setColumnStretch(0, 7)
        content.setColumnStretch(1, 3)
        content.setSpacing(16)

        self.form_card = self.card()
        form_layout = QGridLayout(self.form_card)
        self.form_card.setFixedHeight(366)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(11)
        form_layout.setColumnStretch(0, 2)
        form_layout.setColumnStretch(1, 2)
        form_layout.setColumnStretch(2, 1)
        form_layout.setColumnStretch(3, 1)
        self.client = QLineEdit()
        self.client.setPlaceholderText("Buscar ou cadastrar cliente")
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("Telefone")
        self.vehicle = QLineEdit()
        self.vehicle.setPlaceholderText("Veiculo")
        self.plate = QLineEdit()
        self.plate.setPlaceholderText("Placa")
        self.service_desc = QLineEdit()
        self.service_desc.setPlaceholderText("Descricao do servico")
        self.service_price = QLineEdit()
        self.service_price.setPlaceholderText("Valor")
        self.service_cost = QLineEdit()
        self.service_cost.setPlaceholderText("Custo")
        self.product_search = QLineEdit()
        self.product_search.setPlaceholderText("Buscar produto ou digitar descricao")
        self.product_price = QLineEdit()
        self.product_price.setPlaceholderText("Valor")
        self.product_cost = QLineEdit()
        self.product_cost.setPlaceholderText("Custo")
        self.tax_rate = QLineEdit("0")
        self.tax_rate.setPlaceholderText("Imposto %")
        self.include_cover = QCheckBox("Capa premium")
        self.include_cover.setChecked(True)
        self.pdf_template = QComboBox()
        self.pdf_template.addItems(["Executivo", "Compacto", "Sem capa"])
        self.pdf_template.setFixedHeight(36)
        for field in (
            self.client,
            self.phone,
            self.vehicle,
            self.plate,
            self.service_desc,
            self.service_price,
            self.service_cost,
            self.product_search,
            self.product_price,
            self.product_cost,
            self.tax_rate,
        ):
            field.setFixedHeight(36)

        form_layout.addWidget(self.labeled_field("Cliente", self.client), 0, 0, 1, 2)
        form_layout.addWidget(self.labeled_field("Telefone", self.phone), 0, 2, 1, 1)
        form_layout.addWidget(self.labeled_field("Imposto %", self.tax_rate), 0, 3, 1, 1)
        form_layout.addWidget(self.labeled_field("Veiculo", self.vehicle), 1, 0, 1, 2)
        form_layout.addWidget(self.labeled_field("Placa", self.plate), 1, 2, 1, 1)
        form_layout.addWidget(self.cover_field(), 1, 3, 1, 1)
        form_layout.addWidget(self.labeled_field("Servico", self.service_desc), 2, 0, 1, 2)
        form_layout.addWidget(self.labeled_field("Valor servico", self.service_price), 2, 2, 1, 1)
        form_layout.addWidget(self.labeled_field("Custo servico", self.service_cost), 2, 3, 1, 1)
        form_layout.addWidget(self.labeled_field("Produto", self.product_search), 3, 0, 1, 2)
        form_layout.addWidget(self.labeled_field("Valor produto", self.product_price), 3, 2, 1, 1)
        form_layout.addWidget(self.labeled_field("Custo produto", self.product_cost), 3, 3, 1, 1)
        add_service = QPushButton("Adicionar servico")
        add_service.setObjectName("SuccessButton")
        add_service.setFixedHeight(36)
        add_service.clicked.connect(self.add_service_from_fields)
        self.btn_add_product_inline = QPushButton("Adicionar produto")
        self.btn_add_product_inline.setObjectName("PrimaryButton")
        self.btn_add_product_inline.setFixedHeight(36)
        self.btn_add_product_inline.clicked.connect(self.add_product_from_search)
        form_layout.addWidget(add_service, 4, 0, 1, 2)
        form_layout.addWidget(self.btn_add_product_inline, 4, 2, 1, 2)

        self.items = QTableWidget(0, len(self.headers))
        self.items.setHorizontalHeaderLabels(self.headers)
        self.items.setAlternatingRowColors(True)
        self.items.verticalHeader().setVisible(False)
        self.items.verticalHeader().setDefaultSectionSize(42)
        self.items.setMinimumHeight(148)
        self.items.setShowGrid(False)
        self.items.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(self.headers)):
            self.items.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.items.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.items.itemChanged.connect(self.update_totals)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        add_line = QPushButton("Adicionar linha")
        add_line.clicked.connect(self.add_empty_row)
        add_line.setFixedHeight(40)
        remove_line = QPushButton("Remover linha")
        remove_line.setObjectName("DangerButton")
        remove_line.clicked.connect(self.remove_selected_row)
        remove_line.setFixedHeight(40)
        btn_row.addWidget(add_line)
        btn_row.addWidget(remove_line)
        btn_row.addStretch()

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(16)
        left.addWidget(self.form_card)
        left.addWidget(self.items, 1)
        left.addLayout(btn_row)
        left_widget = QWidget()
        left_widget.setLayout(left)
        content.addWidget(left_widget, 0, 0)

        self.side_card = self.card()
        self.side_card.setMinimumWidth(360)
        self.side_card.setMaximumWidth(392)
        side_layout = QVBoxLayout(self.side_card)
        side_layout.setContentsMargins(16, 14, 16, 14)
        side_layout.setSpacing(7)

        dashboard = QGridLayout()
        dashboard.setSpacing(10)
        self.metric_revenue = self.metric_card("Aprovado", "R$ 0,00", "AccentBlue")
        self.metric_conversion = self.metric_card("Conversao", "0%", "AccentGreen")
        self.metric_open = self.metric_card("Em aberto", "R$ 0,00", "AccentAmber")
        self.metric_count = self.metric_card("Orcamentos", "0", "AccentSlate")
        dashboard.addWidget(self.metric_revenue, 0, 0)
        dashboard.addWidget(self.metric_conversion, 0, 1)
        dashboard.addWidget(self.metric_open, 1, 0)
        dashboard.addWidget(self.metric_count, 1, 1)

        chart_title = QLabel("Pulso comercial")
        chart_title.setObjectName("PanelTitle")
        if pg:
            self.chart = pg.PlotWidget()
            self.chart.setFixedHeight(58)
            self.chart.setMinimumWidth(0)
            self.chart.setBackground("#101b2d")
            self.chart.showGrid(x=False, y=True, alpha=0.12)
            self.chart.getAxis("bottom").setTicks([[(1, "Aprov."), (2, "Aberto"), (3, "Qtd.")]])
            self.chart.getAxis("left").setPen("#46566f")
            self.chart.getAxis("bottom").setPen("#46566f")
            self.chart.setMenuEnabled(False)
        else:
            self.chart = QLabel("Instale pyqtgraph para visualizar graficos.")
            self.chart.setObjectName("Muted")

        side_title = QLabel("Resumo financeiro")
        side_title.setObjectName("PanelTitle")
        self.total_label = QLabel("R$ 0,00")
        self.total_label.setObjectName("TotalLabel")
        self.margin_label = QLabel("Margem: 0% | Lucro: R$ 0,00")
        self.margin_label.setObjectName("MarginOk")
        self.margin_label.setMinimumWidth(0)
        self.margin_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Termos, validade, condicoes comerciais e observacoes")
        self.notes.setText("Validade da proposta: 7 dias. Pagamento conforme combinado. Pecas sujeitas a disponibilidade.")
        self.notes.setFixedHeight(70)
        self.pdf_path_label = QLabel("Nenhum PDF gerado nesta sessao.")
        self.pdf_path_label.setObjectName("PdfPath")
        self.pdf_path_label.setWordWrap(True)
        self.btn_open_pdf = QPushButton("Abrir PDF")
        self.btn_open_pdf.setFixedHeight(34)
        self.btn_open_pdf.setEnabled(False)
        self.btn_open_pdf.clicked.connect(self.open_last_pdf)
        self.btn_open_folder = QPushButton("Abrir pasta")
        self.btn_open_folder.setFixedHeight(34)
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self.open_pdf_folder)
        self.btn_whatsapp = QPushButton("Enviar WhatsApp")
        self.btn_whatsapp.setObjectName("WhatsAppButton")
        self.btn_whatsapp.setFixedHeight(34)
        self.btn_whatsapp.setEnabled(False)
        self.btn_whatsapp.clicked.connect(self.open_whatsapp)
        pdf_buttons = QHBoxLayout()
        pdf_buttons.setSpacing(8)
        pdf_buttons.addWidget(self.btn_open_pdf)
        pdf_buttons.addWidget(self.btn_open_folder)
        side_layout.addLayout(dashboard)
        side_layout.addWidget(chart_title)
        side_layout.addWidget(self.chart)
        side_layout.addWidget(side_title)
        side_layout.addWidget(QLabel("Total"))
        side_layout.addWidget(self.total_label)
        side_layout.addWidget(self.margin_label)
        side_layout.addWidget(QLabel("Termos"))
        side_layout.addWidget(self.notes, 1)
        side_layout.addWidget(QLabel("PDF"))
        side_layout.addWidget(self.pdf_path_label)
        side_layout.addLayout(pdf_buttons)
        side_layout.addWidget(self.btn_whatsapp)
        content.addWidget(self.side_card, 0, 1)

        shell.addLayout(content, 1)
        scroll = QScrollArea()
        scroll.setObjectName("RootScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        self.client.textChanged.connect(lambda: self.client_timer.start(160))
        self.product_search.textChanged.connect(lambda: self.product_timer.start(160))
        self.product_search.returnPressed.connect(self.add_product_from_search)
        self.service_desc.returnPressed.connect(self.add_service_from_fields)
        self.service_price.returnPressed.connect(self.add_service_from_fields)
        self.product_price.returnPressed.connect(self.add_product_from_search)
        self.tax_rate.textChanged.connect(self.update_totals)
        self.paint_status_tracker()

    def card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        return frame

    def labeled_field(self, label_text: str, widget: QWidget) -> QWidget:
        box = QWidget()
        box.setObjectName("FieldBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")
        label.setFixedHeight(15)
        layout.addWidget(label)
        layout.addWidget(widget)
        box.setFixedHeight(55)
        return box

    def cover_field(self) -> QWidget:
        box = QWidget()
        box.setObjectName("FieldBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel("PDF")
        label.setObjectName("FieldLabel")
        label.setFixedHeight(15)
        layout.addWidget(label)
        layout.addWidget(self.include_cover)
        layout.addWidget(self.pdf_template)
        box.setFixedHeight(92)
        return box

    def closeEvent(self, event) -> None:
        self.client_timer.stop()
        self.product_timer.stop()
        super().closeEvent(event)

    def metric_card(self, title: str, value: str, accent: str) -> QFrame:
        frame = self.card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("Muted")
        number = QLabel(value)
        number.setObjectName(accent)
        number.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        frame.setFixedHeight(64)
        layout.addWidget(label)
        layout.addWidget(number)
        frame.value_label = number  # type: ignore[attr-defined]
        return frame

    def refresh_dashboard(self) -> None:
        metrics = self.db.dashboard_metrics()
        self.metric_revenue.value_label.setText(self.compact_money(metrics["revenue"]))  # type: ignore[attr-defined]
        self.metric_conversion.value_label.setText(metrics["conversion"])  # type: ignore[attr-defined]
        self.metric_open.value_label.setText(self.compact_money(metrics["open_value"]))  # type: ignore[attr-defined]
        self.metric_count.value_label.setText(metrics["quote_count"])  # type: ignore[attr-defined]
        if pg and hasattr(self, "chart"):
            revenue = self._metric_number(metrics["revenue"])
            open_value = self._metric_number(metrics["open_value"])
            quote_count = Decimal(metrics["quote_count"] or "0")
            scale = max(revenue, open_value, Decimal("1")) / Decimal("100")
            values = [float(revenue / scale), float(open_value / scale), float(quote_count)]
            self.chart.clear()
            self.chart.setYRange(0, max(5, max(values) * 1.2), padding=0)
            self.chart.addItem(pg.BarGraphItem(x=[1, 2, 3], height=values, width=0.52, brush="#2563eb"))

    def _metric_number(self, formatted: str) -> Decimal:
        text = formatted.replace("R$", "").strip().replace(".", "").replace(",", ".")
        return Decimal(text or "0")

    def compact_money(self, formatted: str) -> str:
        value = self._metric_number(formatted)
        if value >= Decimal("1000000"):
            return f"R$ {(value / Decimal('1000000')).quantize(Decimal('0.1'))} mi".replace(".", ",")
        if value >= Decimal("1000"):
            return f"R$ {(value / Decimal('1000')).quantize(Decimal('0.1'))} mil".replace(".", ",")
        return formatted

    def refresh_client_suggestions(self) -> None:
        clients = self.controller.search_clients(self.client.text())
        self.client_cache = {client.name: client for client in clients}
        completer = QCompleter(list(self.client_cache.keys()))
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.activated.connect(self.fill_client)
        self.client.setCompleter(completer)

    def refresh_product_suggestions(self) -> None:
        products = self.controller.search_products(self.product_search.text())
        self.product_cache = {product.description: product for product in products}
        completer = QCompleter(list(self.product_cache.keys()))
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.activated.connect(self.add_product_from_completion)
        self.product_search.setCompleter(completer)

    def fill_client(self, name: str) -> None:
        client = self.client_cache.get(name)
        if not client:
            return
        self.client.setText(client.name)
        self.phone.setText(client.phone)
        self.vehicle.setText(client.vehicle)
        self.plate.setText(client.plate)

    def add_product_from_completion(self, text: str) -> None:
        self.product_search.setText(text)
        product = self.product_cache.get(text)
        if product:
            self.product_price.setText(str(product.unit_price))
            self.product_cost.setText(str(product.unit_cost))

    def add_product_from_search(self) -> None:
        text = self.product_search.text().strip()
        if not text:
            self.product_search.setFocus()
            return
        product = self.product_cache.get(text)
        price = self.product_price.text().strip()
        cost = self.product_cost.text().strip()
        row = self.first_empty_row()
        if row is None:
            row = self.add_empty_row()
        if product:
            values = [
                product.description,
                "1",
                price or str(product.unit_price),
                cost or str(product.unit_cost),
                "0.00",
                "",
            ]
        else:
            values = [f"Produto - {text}", "1", price or "0.00", cost or "0.00", "0.00", ""]
        if not self.validate_price_cost(values[2], values[3]):
            return
        for col, value in enumerate(values):
            self.set_cell(row, col, value, editable=col != 5)
        self.product_search.clear()
        self.product_price.clear()
        self.product_cost.clear()
        self.product_search.setFocus()
        self.update_totals()

    def add_service_from_fields(self) -> None:
        text = self.service_desc.text().strip()
        if not text:
            self.service_desc.setFocus()
            return
        row = self.first_empty_row()
        if row is None:
            row = self.add_empty_row()
        values = [
            f"Servico - {text}",
            "1",
            self.service_price.text().strip() or "0.00",
            self.service_cost.text().strip() or "0.00",
            "0.00",
            "",
        ]
        if not self.validate_price_cost(values[2], values[3]):
            return
        for col, value in enumerate(values):
            self.set_cell(row, col, value, editable=col != 5)
        self.service_desc.clear()
        self.service_price.clear()
        self.service_cost.clear()
        self.service_desc.setFocus()
        self.update_totals()

    def add_empty_row(self) -> int:
        row = self.items.rowCount()
        self.items.insertRow(row)
        self.items.setRowHeight(row, 42)
        for col, value in enumerate(["", "1", "0.00", "0.00", "0.00", ""]):
            self.set_cell(row, col, value, editable=col != 5)
        return row

    def first_empty_row(self) -> int | None:
        for row in range(self.items.rowCount()):
            if not self.cell(row, 0):
                return row
        return None

    def set_cell(self, row: int, col: int, value: str, editable: bool = True) -> None:
        item = QTableWidgetItem(value)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if col in (1, 2, 3, 4, 5):
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.items.setItem(row, col, item)

    def remove_selected_row(self) -> None:
        rows = sorted({idx.row() for idx in self.items.selectedIndexes()}, reverse=True)
        if not rows and self.items.rowCount():
            rows = [self.items.rowCount() - 1]
        for row in rows:
            self.items.removeRow(row)
        if self.items.rowCount() == 0:
            self.add_empty_row()
        self.update_totals()

    def current_tax_rate(self) -> Decimal:
        try:
            return Decimal(self.tax_rate.text().replace(",", ".") or "0")
        except InvalidOperation:
            return Decimal("0")

    def collect_rows(self) -> list[dict[str, str]]:
        rows = []
        for row in range(self.items.rowCount()):
            rows.append(
                {
                    "description": self.cell(row, 0),
                    "quantity": self.cell(row, 1) or "0",
                    "unit_price": self.cell(row, 2) or "0",
                    "unit_cost": self.cell(row, 3) or "0",
                    "discount": self.cell(row, 4) or "0",
                }
            )
        return rows

    def cell(self, row: int, col: int) -> str:
        item = self.items.item(row, col)
        return item.text().strip() if item else ""

    def quote_from_ui(self) -> Quote:
        return self.controller.build_quote(
            client_name=self.client.text().strip(),
            phone=self.phone.text().strip(),
            vehicle=self.vehicle.text().strip(),
            plate=self.plate.text().strip(),
            status=QuoteStatus(self.status_combo.currentText()),
            tax_rate=self.current_tax_rate(),
            item_rows=self.collect_rows(),
            notes=self.notes.toPlainText(),
        )

    def update_totals(self) -> None:
        self.items.blockSignals(True)
        try:
            quote = self.quote_from_ui()
            for row, item in enumerate(quote.items):
                if row < self.items.rowCount():
                    self.set_cell(row, 5, format_money(item.subtotal), editable=False)
            self.total_label.setText(format_money(quote.total))
            self.margin_label.setText(f"Margem: {quote.margin_percent}% | Lucro: {format_money(quote.profit)}")
            self.margin_label.setObjectName("MarginRisk" if quote.margin_percent < Decimal("18") else "MarginOk")
            self.margin_label.style().unpolish(self.margin_label)
            self.margin_label.style().polish(self.margin_label)
        except (InvalidOperation, ValueError):
            self.margin_label.setText("Revise os valores monetarios")
            self.margin_label.setObjectName("MarginRisk")
        finally:
            self.items.blockSignals(False)

    def paint_status_tracker(self) -> None:
        current = self.status_combo.currentIndex()
        for idx, label in enumerate(self.status_labels):
            label.setProperty("active", idx <= current)
            label.style().unpolish(label)
            label.style().polish(label)

    def validate_quote(self, quote: Quote) -> bool:
        if not quote.client.name:
            QMessageBox.warning(self, "Cliente obrigatorio", "Informe ou selecione um cliente.")
            return False
        if not quote.items:
            QMessageBox.warning(self, "Itens obrigatorios", "Inclua pelo menos um item no orcamento.")
            return False
        return True

    def generate_pdf(self) -> None:
        self.send_whatsapp_after_pdf = False
        quote = self.quote_from_ui()
        if not self.validate_quote(quote):
            return
        self.btn_pdf.setEnabled(False)
        self.btn_pdf.setText("Gerando...")
        include_cover = self.include_cover.isChecked() and self.pdf_template.currentText() != "Sem capa"
        worker = TaskWorker(self.controller.persist_and_render_pdf, quote, include_cover)
        worker.signals.finished.connect(self.on_pdf_ready)
        worker.signals.failed.connect(self.on_pdf_failed)
        self.thread_pool.start(worker)

    def generate_pdf_and_whatsapp(self) -> None:
        self.send_whatsapp_after_pdf = True
        quote = self.quote_from_ui()
        if not self.validate_quote(quote):
            return
        self.btn_pdf.setEnabled(False)
        self.btn_pdf_whatsapp.setEnabled(False)
        self.btn_pdf.setText("Gerando...")
        include_cover = self.include_cover.isChecked() and self.pdf_template.currentText() != "Sem capa"
        worker = TaskWorker(self.controller.persist_and_render_pdf, quote, include_cover)
        worker.signals.finished.connect(self.on_pdf_ready)
        worker.signals.failed.connect(self.on_pdf_failed)
        self.thread_pool.start(worker)

    def on_pdf_ready(self, path: Path) -> None:
        self.btn_pdf.setEnabled(True)
        self.btn_pdf_whatsapp.setEnabled(True)
        self.btn_pdf.setText("Gerar PDF")
        self.last_pdf_path = path
        self.pdf_path_label.setText(str(path))
        self.btn_open_pdf.setEnabled(True)
        self.btn_open_folder.setEnabled(True)
        self.btn_whatsapp.setEnabled(True)
        self.refresh_dashboard()
        QApplication.clipboard().setText(str(path))
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            self.show_pdf_message(path)
        if self.send_whatsapp_after_pdf:
            self.send_whatsapp_after_pdf = False
            self.open_whatsapp()

    def on_pdf_failed(self, message: str) -> None:
        self.btn_pdf.setEnabled(True)
        self.btn_pdf_whatsapp.setEnabled(True)
        self.btn_pdf.setText("Gerar PDF")
        QMessageBox.critical(self, "Falha ao gerar PDF", message)

    def show_pdf_message(self, path: Path) -> None:
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("PDF gerado")
        message.setText("PDF gerado com sucesso")
        message.setInformativeText(f"O caminho foi copiado para a area de transferencia.\n\n{path}")
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.setStyleSheet(
            """
            QMessageBox {
                background: #101b2d;
            }
            QMessageBox QLabel {
                color: #e5e7eb;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                background: #1c2a3f;
                color: #ffffff;
                border: 1px solid #2c3a52;
                border-radius: 8px;
                min-width: 72px;
                min-height: 32px;
                padding: 0 14px;
            }
            """
        )
        message.exec()

    def reset_form(self) -> None:
        self.client.clear()
        self.phone.clear()
        self.vehicle.clear()
        self.plate.clear()
        self.service_desc.clear()
        self.service_price.clear()
        self.service_cost.clear()
        self.product_search.clear()
        self.product_price.clear()
        self.product_cost.clear()
        self.tax_rate.setText("0")
        self.notes.setText("Validade da proposta: 7 dias. Pagamento conforme combinado. Pecas sujeitas a disponibilidade.")
        self.include_cover.setChecked(True)
        self.pdf_template.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.items.setRowCount(0)
        self.add_empty_row()
        self.update_totals()

    def open_last_pdf(self) -> None:
        if self.last_pdf_path and self.last_pdf_path.exists():
            os.startfile(self.last_pdf_path)

    def open_pdf_folder(self) -> None:
        folder = self.last_pdf_path.parent if self.last_pdf_path else self.base_dir / "orcamentos"
        folder.mkdir(exist_ok=True)
        os.startfile(folder)

    def whatsapp_url(self) -> str:
        phone = re.sub(r"\D+", "", self.phone.text())
        if phone and not phone.startswith("55"):
            phone = "55" + phone
        pdf_text = str(self.last_pdf_path) if self.last_pdf_path else "PDF ainda nao gerado"
        message = (
            f"Olá, {self.client.text().strip() or 'cliente'}! "
            "Segue o orçamento WVL. "
            f"Total: {self.total_label.text()}. "
            f"Arquivo: {pdf_text}"
        )
        base = f"https://wa.me/{phone}" if phone else "https://wa.me/"
        return f"{base}?text={quote(message)}"

    def open_whatsapp(self) -> None:
        url = self.whatsapp_url()
        opened = QDesktopServices.openUrl(QUrl(url))
        if not opened:
            webbrowser.open(url, new=2)

    def validate_price_cost(self, price_text: str, cost_text: str) -> bool:
        try:
            price = money(price_text or "0")
            cost = money(cost_text or "0")
        except Exception:
            QMessageBox.warning(self, "Valor invalido", "Revise o preco e o custo.")
            return False
        if cost > price and price > 0:
            if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                return True
            QMessageBox.warning(self, "Margem negativa", "O custo esta maior que o preco. Revise antes de adicionar.")
            return False
        return True

    def open_catalog_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cadastros")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        client_name = QLineEdit(self.client.text())
        phone = QLineEdit(self.phone.text())
        vehicle = QLineEdit(self.vehicle.text())
        plate = QLineEdit(self.plate.text())
        product_desc = QLineEdit(self.product_search.text())
        product_price = QLineEdit(self.product_price.text())
        product_cost = QLineEdit(self.product_cost.text())
        form.addRow("Cliente", client_name)
        form.addRow("Telefone", phone)
        form.addRow("Veiculo", vehicle)
        form.addRow("Placa", plate)
        form.addRow("Produto/servico", product_desc)
        form.addRow("Preco", product_price)
        form.addRow("Custo", product_cost)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        def save():
            from ..models import Client, Product

            if client_name.text().strip():
                self.db.upsert_client(Client(None, client_name.text(), phone.text(), vehicle.text(), plate.text()))
            if product_desc.text().strip():
                self.db.upsert_product(Product(None, product_desc.text(), money(product_price.text() or "0"), money(product_cost.text() or "0")))
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def open_history_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Historico de orcamentos")
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["ID", "Data", "Cliente", "Status", "Total", "Margem"])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        rows = self.db.list_quotes()
        for row_data in rows:
            row = table.rowCount()
            table.insertRow(row)
            for col, key in enumerate(["id", "created_at", "name", "status", "total", "margin_percent"]):
                table.setItem(row, col, QTableWidgetItem(str(row_data[key])))
        layout.addWidget(table)
        buttons_row = QHBoxLayout()
        load_btn = QPushButton("Reabrir")
        duplicate_btn = QPushButton("Duplicar")
        clear_btn = QPushButton("Limpar historico")
        clear_btn.setObjectName("DangerButton")
        buttons_row.addWidget(load_btn)
        buttons_row.addWidget(duplicate_btn)
        buttons_row.addWidget(clear_btn)
        layout.addLayout(buttons_row)

        def selected_id() -> int | None:
            row = table.currentRow()
            if row < 0:
                return None
            return int(table.item(row, 0).text())

        def load_quote():
            quote_id = selected_id()
            if quote_id is not None:
                self.load_quote_into_form(self.db.load_quote(quote_id))
                dialog.accept()

        def duplicate_quote():
            quote_id = selected_id()
            if quote_id is not None:
                quote_obj = self.db.load_quote(quote_id)
                quote_obj.status = QuoteStatus.DRAFT
                self.load_quote_into_form(quote_obj)
                dialog.accept()

        def clear_history():
            self.db.clear_quotes()
            table.setRowCount(0)
            self.refresh_dashboard()

        load_btn.clicked.connect(load_quote)
        duplicate_btn.clicked.connect(duplicate_quote)
        clear_btn.clicked.connect(clear_history)
        dialog.resize(760, 420)
        dialog.exec()

    def load_quote_into_form(self, quote_obj: Quote) -> None:
        self.reset_form()
        self.client.setText(quote_obj.client.name)
        self.phone.setText(quote_obj.client.phone)
        self.vehicle.setText(quote_obj.client.vehicle)
        self.plate.setText(quote_obj.client.plate)
        self.status_combo.setCurrentText(quote_obj.status.value)
        self.notes.setText(quote_obj.notes)
        self.items.setRowCount(0)
        for quote_item in quote_obj.items:
            row = self.add_empty_row()
            for col, value in enumerate([quote_item.description, str(quote_item.quantity), str(quote_item.unit_price), str(quote_item.unit_cost), str(quote_item.discount), ""]):
                self.set_cell(row, col, value, editable=col != 5)
        self.update_totals()

    def export_month(self) -> None:
        path = self.db.export_monthly_workbook()
        QMessageBox.information(self, "Planilha mensal", f"Planilha atualizada:\n{path}")
