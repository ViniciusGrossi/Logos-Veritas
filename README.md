# Consulta CPF em Lote — Logos Tech

Sistema de consulta de CPF em lote via API HubDev, com interface web moderna e exportação para Excel.

## Stack

- **Backend:** FastAPI + Python (serverless via Vercel)
- **Frontend:** HTML/CSS/JS puro (servido como estático pelo Vercel)
- **API:** [HubDev CPF](https://www.hubdodesenvolvedor.com.br/)

## Estrutura

```
├── api/
│   └── index.py       # FastAPI (todos os endpoints /api/*)
├── public/
│   └── index.html     # Interface web estática
├── vercel.json        # Configuração do Vercel
├── requirements.txt   # Dependências Python
├── .env.example       # Modelo de variáveis de ambiente
└── .gitignore
```

## Como usar

1. **Prepare a planilha:** crie um arquivo `.xlsx` com uma coluna chamada `cpf`
2. **Importe na interface:** arraste ou clique para selecionar
3. **Aguarde:** os resultados aparecem em tempo real conforme a API responde
4. **Exporte:** baixe o `.xlsx` com todos os dados ao final

## Deploy no Vercel

### 1. GitHub
```bash
git init
git add .
git commit -m "Adiciona projeto consulta CPF em lote"
git branch -M main
git remote add origin https://github.com/seu-usuario/seu-repo.git
git push -u origin main
```

### 2. Vercel
1. Acesse [vercel.com](https://vercel.com) → **Add New Project**
2. Importe o repositório do GitHub
3. Em **Environment Variables**, adicione:
   - `HUBDEV_TOKEN` = `seu_token_aqui`
4. Clique em **Deploy**

> ⚠️ **Plano Hobby do Vercel:** funções têm timeout de 60s. Para lotes grandes, considere o plano Pro (timeout de até 300s).

## Desenvolvimento local

```bash
pip install -r requirements.txt
uvicorn api.index:app --port 8001 --reload
```
Acesse `http://localhost:8001` — a interface estará disponível em `/public/index.html` (abra direto no navegador ou sirva com `python -m http.server`).
