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
# BANCO
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
# FUNÇÕES
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
# GERAR PDF
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

        validade = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")

        pdf.set_font("Arial", "B", 18)
        pdf.cell(190, 10, APP_NOME, ln=True, align="C")

        pdf.set_font("Arial", "", 12)
        pdf.cell(190, 8, "ORCAMENTO DE SERVICOS MECANICOS", ln=True, align="C")
        pdf.cell(190, 8, f"Validade ate {validade}", ln=True, align="C")

        pdf.ln(10)

        pdf.set_font("Arial", "", 11)
        pdf.cell(190, 8, f"Cliente: {cliente}", ln=True)
        pdf.cell(190, 8, f"Telefone: {telefone}", ln=True)
        pdf.cell(190, 8, f"Veiculo: {veiculo}", ln=True)
        pdf.cell(190, 8, f"Placa: {placa}", ln=True)
        pdf.cell(190, 8, f"Data: {data_orc}", ln=True)

        pdf.ln(8)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 8, "MAO DE OBRA", ln=True)

        pdf.set_font("Arial", "", 11)
        for i in itens_mao:
            pdf.cell(190, 7,
                     f"{i.get('descricao','')} - R$ {safe_float(i.get('valor',0)):.2f}",
                     ln=True)

        pdf.ln(5)

        pdf.set_font("Arial", "B", 12)
        pdf.cell(190, 8, "PECAS", ln=True)

        pdf.set_font("Arial", "", 11)
        for i in itens_pecas:
            pdf.cell(190, 7,
                     f"{i.get('descricao','')} - R$ {safe_float(i.get('valor',0)):.2f}",
                     ln=True)

        pdf.ln(10)

        pdf.set_font("Arial", "B", 14)
        pdf.cell(190, 10, f"TOTAL: R$ {total:.2f}", ln=True)

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
# DOWNLOAD (CELULAR OK)
# ======================================

@app.route("/download/<path:nome>")
def download(nome):

    caminho = os.path.join("orcamentos", nome)

    if not os.path.exists(caminho):
        return "Arquivo nao encontrado", 404

    return send_file(
        caminho,
        as_attachment=True,
        download_name=nome
    )

# ======================================
# HISTÓRICO
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
# RUN
# ======================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)