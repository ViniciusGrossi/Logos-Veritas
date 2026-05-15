import os, re, logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import httpx
from dotenv import load_dotenv
from pathlib import Path

# Tenta carregar o .env da raiz do projeto (um nível acima da pasta /api)
base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fallback para o diretório atual
    load_dotenv()

HUBDEV_TOKEN = os.getenv("HUBDEV_TOKEN")
HUBDEV_URL   = "https://ws.hubdodesenvolvedor.com.br/v2/cpf/"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Serve o arquivo index.html na raiz.
    Isso ajuda no desenvolvimento local.
    """
    try:
        # Tenta ler da raiz (onde o arquivo está agora)
        path = os.path.join(os.getcwd(), "index.html")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Arquivo index.html não encontrado na raiz do projeto.</h1>"
    except Exception as e:
        return f"<h1>Erro ao carregar interface: {str(e)}</h1>"

@app.get("/api/consultar")
async def consultar(cpf: str = Query(...)):
    if not HUBDEV_TOKEN:
        return {
            "cpf": cpf, 
            "nome": None, 
            "situacao": "ERRO", 
            "erro": "Configuração Pendente: HUBDEV_TOKEN não encontrado no servidor."
        }

    cpf_clean = re.sub(r"\D", "", cpf)
    if len(cpf_clean) != 11:
        return {"cpf": cpf, "nome": None, "situacao": "ERRO", "erro": "CPF Inválido"}

    url = f"{HUBDEV_URL}?cpf={cpf_clean}&data=&token={HUBDEV_TOKEN}"
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            data = resp.json()
            
            if data.get("return") == "OK":
                r = data["result"]
                return {
                    "cpf": _fmt_cpf(cpf_clean),
                    "nome": r.get("nome_da_pf"),
                    "data_nascimento": r.get("data_nascimento"),
                    "situacao": r.get("situacao_cadastral"),
                    "data_inscricao": r.get("data_inscricao"),
                    "comprovante": r.get("comprovante_emitido"),
                    "comprovante_data": r.get("comprovante_emitido_data"),
                    "erro": None
                }
            else:
                return {
                    "cpf": _fmt_cpf(cpf_clean), 
                    "nome": None, 
                    "situacao": "ERRO", 
                    "erro": data.get("message", "Não encontrado")
                }
    except Exception as e:
        return {"cpf": _fmt_cpf(cpf_clean), "nome": None, "situacao": "ERRO", "erro": str(e)}

def _fmt_cpf(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
