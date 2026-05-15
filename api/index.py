import asyncio, io, json, logging, os, re, uuid
from pathlib import Path

import httpx
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

HUBDEV_TOKEN  = os.getenv("HUBDEV_TOKEN", "206629495DtZhNyBxGl373063288")
HUBDEV_URL    = "https://ws.hubdodesenvolvedor.com.br/v2/cpf/"
DELAY_SEGUNDOS = 1.2

TMP_DIR = Path("/tmp/consulta_cpf")
TMP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Consulta CPF — Logos Tech")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Helpers de persistência ───────────────────────────────────────────────────

def _job_path(job_id: str) -> Path:
    return TMP_DIR / f"{job_id}.json"

def _read_job(job_id: str) -> dict | None:
    p = _job_path(job_id)
    return json.loads(p.read_text()) if p.exists() else None

def _write_job(job_id: str, data: dict) -> None:
    _job_path(job_id).write_text(json.dumps(data, ensure_ascii=False))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/upload")
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
        raise HTTPException(400, f"Coluna 'cpf' não encontrada. Colunas: {list(df.columns)}")

    cpfs: list[str] = (
        df[col_map["cpf"]]
        .dropna().astype(str).str.strip()
        .str.replace(r"\D", "", regex=True)
        .loc[lambda s: s.str.len() > 0]
        .tolist()
    )
    if not cpfs:
        raise HTTPException(400, "Nenhum CPF válido encontrado.")

    job_id = uuid.uuid4().hex
    _write_job(job_id, {"status": "queued", "total": len(cpfs), "done": 0, "rows": [], "cpfs": cpfs})
    background_tasks.add_task(_run_job, job_id)
    return {"job_id": job_id, "total": len(cpfs)}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado.")
    return {k: v for k, v in job.items() if k != "cpfs"}


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "Job não encontrado.")
    if job["status"] not in ("done", "error"):
        raise HTTPException(409, "Ainda processando.")

    df = pd.DataFrame(job["rows"])
    if df.empty:
        raise HTTPException(422, "Sem resultados para exportar.")

    df = df.rename(columns={
        "cpf": "CPF", "nome": "Nome",
        "data_nascimento": "Data de Nascimento",
        "situacao": "Situação Cadastral",
        "data_inscricao": "Data de Inscrição",
        "comprovante": "Comprovante",
        "comprovante_data": "Data Comprovante",
        "erro": "Erro/Obs",
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=resultado_consulta_cpf.xlsx"},
    )


# ── Background task ───────────────────────────────────────────────────────────

async def _run_job(job_id: str) -> None:
    job = _read_job(job_id)
    if not job:
        return
    cpfs = job.pop("cpfs", [])
    job["status"] = "running"
    _write_job(job_id, {"cpfs": cpfs, **job})

    async with httpx.AsyncClient(timeout=450) as client:
        for cpf in cpfs:
            result = await _consultar_cpf(client, cpf)
            job = _read_job(job_id)
            job["rows"].append(result)
            job["done"] += 1
            _write_job(job_id, job)
            logger.info("Job %s — %d/%d | %s | %s", job_id, job["done"], job["total"], cpf,
                        "OK" if not result.get("erro") else result["erro"])
            if job["done"] < job["total"]:
                await asyncio.sleep(DELAY_SEGUNDOS)

    job = _read_job(job_id)
    job["status"] = "done"
    _write_job(job_id, job)


async def _consultar_cpf(client: httpx.AsyncClient, cpf: str) -> dict:
    url = f"{HUBDEV_URL}?cpf={cpf}&data=&token={HUBDEV_TOKEN}"
    base = {"cpf": _fmt_cpf(cpf), "nome": None, "data_nascimento": None,
            "situacao": None, "data_inscricao": None,
            "comprovante": None, "comprovante_data": None, "erro": None}
    try:
        resp = await client.get(url)
        data = resp.json()
        if data.get("return") == "OK":
            r = data["result"]
            return {**base,
                    "nome":             r.get("nome_da_pf"),
                    "data_nascimento":  r.get("data_nascimento"),
                    "situacao":         r.get("situacao_cadastral"),
                    "data_inscricao":   r.get("data_inscricao"),
                    "comprovante":      r.get("comprovante_emitido"),
                    "comprovante_data": r.get("comprovante_emitido_data")}
        return {**base, "situacao": "ERRO", "erro": data.get("message", "Retorno NOK")}
    except Exception as exc:
        return {**base, "situacao": "ERRO", "erro": str(exc)[:150]}


def _fmt_cpf(cpf: str) -> str:
    s = re.sub(r"\D", "", str(cpf))
    return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}" if len(s) == 11 else cpf
