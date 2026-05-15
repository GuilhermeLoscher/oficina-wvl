from flask import Flask, render_template, request, jsonify, send_file
from fpdf import FPDF
from datetime import datetime, timedelta
import sqlite3
import os
import unicodedata

app = Flask(__name__)

APP_NOME = "OFICINA WVL"

# ======================================
# PASTA PDF
# ======================================

if not os.path.exists("orcamentos"):
    os.makedirs("orcamentos")

# ======================================
# BANCO SQLITE
# ======================================

conn = sqlite3.connect("oficina.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    veiculo TEXT,
    placa TEXT,
    total REAL,
    data TEXT
)
""")

conn.commit()

# ======================================
# FUNÇÕES AUXILIARES
# ======================================

def safe_float(v):
    try:
        return float(v)
    except:
        return 0

def limpar_nome(nome):
    nome = unicodedata.normalize("NFKD", nome)
    nome = nome.encode("ASCII", "ignore").decode("ASCII")
    return nome.replace(" ", "_")

# ======================================
# HOME
# ======================================

@app.route("/")
def home():
    return render_template("index.html")

# ======================================
# GERAR PDF (LAYOUT ORIGINAL RESTAURADO)
# ======================================

@app.route("/gerar_pdf", methods=["POST"])
def gerar_pdf():

    try:
        dados = request.get_json(force=True)

        cliente = dados.get("cliente", "")
        telefone = dados.get("telefone", "")
        veiculo = dados.get("veiculo", "")
        placa = dados.get("placa", "")
        data_orc = dados.get("data", "")

        itens_mao = dados.get("itens_mao") or []
        itens_pecas = dados.get("itens_pecas") or []

        total_mao = sum(safe_float(i.get("valor", 0)) for i in itens_mao)
        total_peca = sum(safe_float(i.get("valor", 0)) for i in itens_pecas)
        total = total_mao + total_peca

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        validade = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")

        # ======================================
        # LOGO + CABEÇALHO
        # ======================================

        if os.path.exists("static/logo.png"):
            pdf.image("static/logo.png", x=12, y=10, w=28)

        pdf.set_xy(45, 12)
        pdf.set_font("Arial", "B", 22)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(140, 10, APP_NOME, ln=True, align="C")

        pdf.set_x(45)
        pdf.set_font("Arial", "", 11)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(140, 7, "ORCAMENTO DE SERVICOS MECANICOS", ln=True, align="C")

        pdf.set_x(45)
        pdf.cell(140, 7, f"Validade ate {validade}", ln=True, align="C")

        pdf.ln(10)

        pdf.set_draw_color(180, 180, 180)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())

        pdf.ln(8)

        # ======================================
        # DADOS CLIENTE
        # ======================================

        pdf.set_fill_color(60, 90, 130)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 9, "DADOS DO CLIENTE", ln=True, fill=True)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", "", 11)
        pdf.set_fill_color(245, 245, 245)

        pdf.cell(95, 9, f"Cliente: {cliente}", border=1, fill=True)
        pdf.cell(95, 9, f"Telefone: {telefone}", border=1, ln=True, fill=True)

        pdf.cell(95, 9, f"Veiculo: {veiculo}", border=1, fill=True)
        pdf.cell(95, 9, f"Placa: {placa}", border=1, ln=True, fill=True)

        pdf.cell(190, 9, f"Data: {data_orc}", border=1, ln=True, fill=True)

        pdf.ln(8)

        # ======================================
        # LINHA (FORMATAÇÃO ORIGINAL)
        # ======================================

        def linha(descricao, valor):

            largura_desc = 145
            largura_val = 45
            altura = 8

            x = pdf.get_x()
            y = pdf.get_y()

            pdf.multi_cell(largura_desc, altura, descricao, border=1)

            altura_total = pdf.get_y() - y

            pdf.set_xy(x + largura_desc, y)
            pdf.cell(largura_val, altura_total, valor, border=1, ln=True, align="R")

        # ======================================
        # MÃO DE OBRA
        # ======================================

        pdf.set_fill_color(70, 120, 90)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 9, "MÃO DE OBRA", ln=True, fill=True)

        pdf.set_text_color(0, 0, 0)

        for i in itens_mao:
            linha(i.get("descricao", ""), f"R$ {safe_float(i.get('valor',0)):.2f}")

        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(145, 9, "Subtotal Mão de Obra", border=1, fill=True)
        pdf.cell(45, 9, f"R$ {total_mao:.2f}", border=1, ln=True, align="R", fill=True)

        pdf.ln(6)

        # ======================================
        # PEÇAS
        # ======================================

        pdf.set_fill_color(70, 100, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 9, "PEÇAS", ln=True, fill=True)

        pdf.set_text_color(0, 0, 0)

        for i in itens_pecas:
            linha(i.get("descricao", ""), f"R$ {safe_float(i.get('valor',0)):.2f}")

        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(145, 9, "Subtotal Peças", border=1, fill=True)
        pdf.cell(45, 9, f"R$ {total_peca:.2f}", border=1, ln=True, align="R", fill=True)

        pdf.ln(10)

        # ======================================
        # TOTAL GERAL
        # ======================================

        pdf.set_fill_color(90, 90, 90)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 16)

        pdf.cell(145, 12, "TOTAL GERAL", border=1, fill=True)
        pdf.cell(45, 12, f"R$ {total:.2f}", border=1, ln=True, align="R", fill=True)

        pdf.ln(18)

        pdf.set_draw_color(150, 150, 150)
        pdf.line(60, pdf.get_y(), 150, pdf.get_y())

        pdf.ln(4)

        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(190, 7, "Assinatura do Cliente", ln=True, align="C")

        # ======================================
        # SALVAR
        # ======================================

        nome_pdf = f"orcamentos/{limpar_nome(cliente)}.pdf"
        pdf.output(nome_pdf)

        cursor.execute("""
            INSERT INTO historico (cliente, veiculo, placa, total, data)
            VALUES (?, ?, ?, ?, ?)
        """, (cliente, veiculo, placa, total, data_orc))

        conn.commit()

        return jsonify({
            "status": "ok",
            "arquivo": os.path.basename(nome_pdf)
        })

    except Exception as e:
        print("ERRO PDF:", str(e))
        return jsonify({
            "status": "erro",
            "erro": str(e)
        }), 500

# ======================================
# DOWNLOAD (IPHONE OK)
# ======================================

@app.route("/download/<path:nome>")
def download(nome):

    caminho = os.path.join("orcamentos", nome)

    if not os.path.exists(caminho):
        return "Arquivo nao encontrado", 404

    return send_file(caminho, as_attachment=True, download_name=nome)

# ======================================
# HISTORICO
# ======================================

@app.route("/historico")
def historico():

    cursor.execute("""
        SELECT cliente, veiculo, placa, total, data
        FROM historico
        ORDER BY id DESC
    """)

    return jsonify(cursor.fetchall())

# ======================================
# RUN LOCAL
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)