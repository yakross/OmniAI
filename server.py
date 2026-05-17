"""
OMNI-AI · Servidor API (FastAPI)
=================================
Este servidor expone el cerebro de OMNI-AI como una API REST.
Permite conectar cualquier interfaz web (React, HTML/JS, Vue, etc.) a la IA.

Ejecución:
  1. Activa tu entorno virtual: venv\\Scripts\\activate
  2. Instala dependencias web: pip install fastapi uvicorn python-multipart
  3. Corre el servidor: uvicorn server:app --reload --port 8000
"""

import os
import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv("config/.env")

# Asegurar que el path del core de OMNI esté en el sistema
sys.path.insert(0, str(Path(__file__).parent))
from core.brain import OmniAI

app = FastAPI(
    title="🧠 OMNI-AI API",
    description="Servidor REST para el Cerebro General de OMNI-AI con RAG y Auto-aprendizaje",
    version="1.0.0"
)

# Permitir CORS para que tu frontend en React u otra web pueda consultarlo sin bloqueos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica el dominio de tu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir la interfaz gráfica estática desde la carpeta 'ui'
ui_path = Path("ui")
if ui_path.exists():
    app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

# Inicializar cerebro de OMNI-AI de forma global
# Se requiere que GROQ_API_KEY esté configurada en config/.env
api_key = os.getenv("GROQ_API_KEY", "")
if not api_key:
    print("\n⚠️  ¡ALERTA!: GROQ_API_KEY no configurada en config/.env.")
    print("La API iniciará, pero las llamadas a /chat fallarán hasta que configures la clave.\n")

ai = None
try:
    if api_key:
        ai = OmniAI(groq_api_key=api_key)
except Exception as e:
    print(f"❌ Error al iniciar el cerebro de OMNI-AI: {e}")


# ── MODELOS DE DATOS ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    auto_improve: Optional[bool] = True

class ChatResponse(BaseModel):
    answer: str
    session_id: str
    turn: int

class LearnTextRequest(BaseModel):
    text: str
    source_name: Optional[str] = "web_input"


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {
        "status": "online" if ai is not None else "missing_api_key",
        "message": "Servidor OMNI-AI API activo. Listo para conectar interfaces web.",
        "ui_url": "http://localhost:8000/ui",
        "docs_url": "/docs"
    }


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Envía una pregunta a OMNI-AI.
    Utiliza el RAG vectorial, historial persistente y auto-notas para responder.
    """
    global ai
    if ai is None:
        # Re-intentar inicialización si se configuró la clave después de arrancar
        current_key = os.getenv("GROQ_API_KEY", "")
        if current_key:
            try:
                ai = OmniAI(groq_api_key=current_key)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error al inicializar cerebro: {e}")
        else:
            raise HTTPException(
                status_code=500,
                detail="Cerebro no inicializado. Por favor configura tu GROQ_API_KEY en config/.env"
            )

    try:
        answer = ai.chat(request.message, auto_improve=request.auto_improve)
        return ChatResponse(
            answer=answer,
            session_id=ai.session_id,
            turn=ai.turn_count
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/text")
def learn_text_endpoint(request: LearnTextRequest):
    """ Enseña a OMNI-AI un fragmento de texto plano directo. """
    if ai is None:
        raise HTTPException(status_code=500, detail="Cerebro no inicializado.")
    
    try:
        result = ai.ingestion.from_text(request.text, name=request.source_name)
        return {"success": True, "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/url")
def learn_url_endpoint(url: str = Form(...)):
    """
    Enseña a OMNI-AI el contenido de una página web a partir de su URL.
    La procesa en tiempo real y extrae el texto limpio.
    """
    if ai is None:
        raise HTTPException(status_code=500, detail="Cerebro no inicializado.")
    
    try:
        result = ai.ingestion.from_url(url)
        return {"success": True, "message": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/learn/file")
async def learn_file_endpoint(file: UploadFile = File(...)):
    """
    Permite subir archivos (PDF o de Texto plano) para que OMNI-AI
    los absorba en su base de conocimiento local de ChromaDB.
    """
    if ai is None:
        raise HTTPException(status_code=500, detail="Cerebro no inicializado.")
    
    # Crear carpeta temporal de subidas
    temp_dir = Path("temp_uploads")
    temp_dir.mkdir(exist_ok=True)
    temp_filepath = temp_dir / file.filename
    
    try:
        # Guardar archivo subido localmente de forma temporal
        with open(temp_filepath, "wb") as f:
            f.write(await file.read())
        
        # Procesar con el cargador de archivos de OMNI
        result = ai.ingestion.from_file(str(temp_filepath))
        
        # Eliminar archivo temporal
        if temp_filepath.exists():
            os.remove(temp_filepath)
            
        return {"success": "✅" in result, "message": result}
    except Exception as e:
        if temp_filepath.exists():
            os.remove(temp_filepath)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
def status_endpoint():
    """ Devuelve el estado actual de la IA (estadísticas de memoria y RAG). """
    if ai is None:
        return {"status": "inactive", "message": "Cerebro no configurado"}
    
    try:
        stats = ai.kb.stats()
        return {
            "status": "active",
            "session_id": ai.session_id,
            "turn_count": ai.turn_count,
            "llm_model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            "database_stats": {
                "knowledge_documents": stats.get("knowledge_docs", 0),
                "conversation_memories": stats.get("memory_turns", 0),
                "self_improvement_notes": stats.get("self_notes", 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reflections")
def get_reflections_endpoint(query: str = "mejora aprendizaje patrón"):
    """
    Obtiene las notas de auto-reflexión y objetivos que la IA
    ha ido guardando sobre sí misma.
    """
    if ai is None:
        raise HTTPException(status_code=500, detail="Cerebro no inicializado.")
    
    try:
        notes = ai.kb.get_self_notes(query)
        return {"query": query, "reflections": notes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Iniciar servidor local en el puerto 8000
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
