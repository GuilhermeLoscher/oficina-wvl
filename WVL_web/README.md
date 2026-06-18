# WVL Web PWA

Versao PWA do sistema WVL Orcamentos.

## Executar localmente

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Nesta maquina, tambem deixei um atalho:

```powershell
.\run_local.ps1
```

Acesse `http://localhost:5000`.

## Recursos

- Cadastro e busca de clientes/produtos
- Criacao de orcamentos com servicos, produtos, impostos e descontos
- Historico em SQLite
- Geracao e download de PDF
- Relatorio mensal em Excel
- Manifesto PWA e service worker para instalacao no celular

## Render

Use `WVL_DATA_DIR` e `WVL_PDF_DIR` se configurar Disk persistente no Render.
