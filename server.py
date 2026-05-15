"""
server.py — Backend FastAPI para consulta de CPF em lote via HubDev API.
Utiliza apenas a coluna 'cpf' da planilha.
"""

import asyncio
import io
import logging
import uuid
from pathlib import Path

import httpx
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HUBDEV_TOKEN = "206629495DtZhNyBxGl373063288"
HUBDEV_URL   = "https://ws.hubdodesenvolvedor.com.br/v2/cpf/"
DELAY_SEGUNDOS = 1.5   # Ajuste conforme necessário

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Consulta CPF — Logos Tech", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
RESULT_DIR = Path("resultados")
UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

jobs: dict[str, dict] = {}

STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "API Consulta CPF — Logos Tech"}

@app.post("/upload")
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "Somente arquivos .xlsx são aceitos.")

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(400, f"Erro ao ler planilha: {exc}")

    col_map = {c.strip().lower(): c for c in df.columns}
    if "cpf" not in col_map:
        raise HTTPException(400, "Coluna 'cpf' não encontrada na planilha.")

    cpf_col = col_map["cpf"]
    cpfs: list[str] = (
        df[cpf_col]
        .dropna()
        .astype(str)
        .str.strip()
        .str.replace(r"\D", "", regex=True)
        .loc[lambda s: s.str.len() > 0]
        .tolist()
    )

    if not cpfs:
        raise HTTPException(400, "Nenhum CPF válido encontrado.")

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "queued",
        "total": len(cpfs),
        "done": 0,
        "rows": [],
        "result_path": None,
    }

    background_tasks.add_task(_run_job, job_id, cpfs)
    return {"job_id": job_id, "total": len(cpfs)}

@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job não encontrado.")
    return jobs[job_id]

@app.get("/download/{job_id}")
async def download(job_id: str):
    if job_id not in jobs: raise HTTPException(404, "Job não encontrado.")
    job = jobs[job_id]
    if job["status"] not in ("done", "error"): raise HTTPException(409, "Ainda processando.")
    
    result_path = RESULT_DIR / f"{job_id}_resultado.xlsx"
    if not result_path.exists():
        df_result = pd.DataFrame(job["rows"])
        df_result = df_result.rename(columns={
            "cpf": "CPF",
            "nome": "Nome",
            "data_nascimento": "Data de Nascimento",
            "situacao": "Situação Cadastral",
            "data_inscricao": "Data de Inscrição",
            "comprovante": "Comprovante",
            "comprovante_data": "Data Comprovante",
            "erro": "Erro/Obs"
        })
        df_result.to_excel(result_path, index=False)
    
    return FileResponse(
        result_path, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="resultado_consulta_cpf.xlsx"
    )

async def _run_job(job_id: str, cpfs: list[str]):
    jobs[job_id]["status"] = "running"
    async with httpx.AsyncClient(timeout=450) as client:
        for cpf in cpfs:
            res = await _consultar_cpf(client, cpf)
            jobs[job_id]["rows"].append(res)
            jobs[job_id]["done"] += 1
            if jobs[job_id]["done"] < jobs[job_id]["total"]:
                await asyncio.sleep(DELAY_SEGUNDOS)
    jobs[job_id]["status"] = "done"

async def _consultar_cpf(client: httpx.AsyncClient, cpf: str) -> dict:
    url = f"{HUBDEV_URL}?cpf={cpf}&data=&token={HUBDEV_TOKEN}"
    try:
        resp = await client.get(url)
        data = resp.json()
        if data.get("return") == "OK":
            r = data["result"]
            return {
                "cpf": _fmt_cpf(cpf),
                "nome": r.get("nome_da_pf"),
                "data_nascimento": r.get("data_nascimento"),
                "situacao": r.get("situacao_cadastral"),
                "data_inscricao": r.get("data_inscricao"),
                "comprovante": r.get("comprovante_emitido"),
                "comprovante_data": r.get("comprovante_emitido_data"),
                "erro": None
            }
        else:
            return {"cpf": _fmt_cpf(cpf), "nome": None, "data_nascimento": None, "situacao": "ERRO", "erro": data.get("message", "Erro desconhecido")}
    except Exception as e:
        return {"cpf": _fmt_cpf(cpf), "nome": None, "data_nascimento": None, "situacao": "ERRO", "erro": str(e)}

def _fmt_cpf(cpf: str) -> str:
    s = str(cpf).replace(r"\D", "")
    if len(s) == 11:
        return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
    return cpf

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001)
