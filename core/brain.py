"""
OMNI-AI · Cerebro Principal
============================
IA general con RAG híbrido, memoria persistente y auto-mejora continua.
Corre 100% en la nube gratis (Groq + APIs gratuitas).
"""

import os, json, hashlib, datetime
from pathlib import Path
from typing import Optional

# ── Dependencias ──────────────────────────────────────────────────────────────
from groq import Groq                          # LLM ultra-rápido y GRATIS
import chromadb                                # Vector DB local (sin servidor)
from sentence_transformers import SentenceTransformer  # Embeddings locales
import requests
from bs4 import BeautifulSoup
from core.search import WebSearcher


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path("./omni_data")
DATA_DIR.mkdir(exist_ok=True)

# Modelos disponibles en Groq (GRATIS):
# llama-3.3-70b-versatile  ← el más potente
# llama-3.1-8b-instant     ← el más rápido
# mixtral-8x7b-32768       ← contexto largo
LLM_MODEL   = "llama-3.3-70b-versatile"
EMBED_MODEL = "all-MiniLM-L6-v2"   # corre local, sin GPU


# ══════════════════════════════════════════════════════════════════════════════
# MEMORIA VECTORIAL
# ══════════════════════════════════════════════════════════════════════════════

class KnowledgeBase:
    """Base de conocimiento vectorial con ChromaDB local."""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
        self.embedder = SentenceTransformer(EMBED_MODEL)

        # Colecciones separadas por tipo de conocimiento
        self.knowledge  = self._col("knowledge")   # documentos, webs
        self.memory     = self._col("memory")       # conversaciones
        self.self_notes = self._col("self_notes")   # auto-reflexiones

    def _col(self, name):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )

    def _embed(self, text: str) -> list:
        return self.embedder.encode(text).tolist()

    def _id(self, text: str) -> str:
        """ID único basado en contenido (evita duplicados)."""
        return hashlib.md5(text.encode()).hexdigest()

    # ── Agregar conocimiento ──────────────────────────────────────────────────

    def add_knowledge(self, text: str, source: str, metadata: dict = None):
        """Agrega un documento a la base de conocimiento."""
        chunks = self._chunk(text)
        for i, chunk in enumerate(chunks):
            doc_id = self._id(chunk)
            try:
                self.knowledge.add(
                    ids=[doc_id],
                    embeddings=[self._embed(chunk)],
                    documents=[chunk],
                    metadatas=[{
                        "source": source,
                        "chunk": i,
                        "date": datetime.datetime.now().isoformat(),
                        **(metadata or {})
                    }]
                )
            except Exception:
                pass  # Ya existe (deduplicación automática)
        return len(chunks)

    def add_memory(self, role: str, content: str, session_id: str):
        """Guarda un turno de conversación en memoria."""
        mem_id = self._id(f"{session_id}{role}{content}")
        try:
            self.memory.add(
                ids=[mem_id],
                embeddings=[self._embed(content)],
                documents=[content],
                metadatas=[{
                    "role": role,
                    "session": session_id,
                    "date": datetime.datetime.now().isoformat()
                }]
            )
        except Exception:
            pass

    def add_self_note(self, note: str, category: str):
        """La IA guarda reflexiones sobre sí misma."""
        note_id = self._id(note)
        try:
            self.self_notes.add(
                ids=[note_id],
                embeddings=[self._embed(note)],
                documents=[note],
                metadatas={"category": category, "date": datetime.datetime.now().isoformat()}
            )
        except Exception:
            pass

    # ── Recuperar conocimiento ────────────────────────────────────────────────

    def search(self, query: str, n=5, collection="knowledge") -> list[str]:
        """Búsqueda semántica en cualquier colección."""
        col = getattr(self, collection)
        try:
            results = col.query(
                query_embeddings=[self._embed(query)],
                n_results=min(n, col.count() or 1)
            )
            return results["documents"][0] if results["documents"] else []
        except Exception:
            return []

    def get_recent_memory(self, session_id: str, n=10) -> list[dict]:
        """Recupera los últimos mensajes de una sesión."""
        try:
            results = self.memory.get(
                where={"session": session_id},
                limit=n
            )
            pairs = list(zip(results["documents"], results["metadatas"]))
            pairs.sort(key=lambda x: x[1].get("date", ""))
            return [{"role": m["role"], "content": d} for d, m in pairs[-n:]]
        except Exception:
            return []

    def get_self_notes(self, query: str) -> list[str]:
        return self.search(query, n=3, collection="self_notes")

    def stats(self) -> dict:
        return {
            "knowledge_docs": self.knowledge.count(),
            "memory_turns":   self.memory.count(),
            "self_notes":     self.self_notes.count(),
        }

    # ── Chunking semántico ────────────────────────────────────────────────────

    def _chunk(self, text: str, size=800, overlap=100) -> list[str]:
        """Divide texto en chunks con overlap para mantener contexto."""
        text = text.strip()
        if len(text) < size:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            end = start + size
            # Busca el último punto/salto de línea para no cortar ideas
            if end < len(text):
                for sep in ["\n\n", "\n", ". ", " "]:
                    pos = text.rfind(sep, start + size//2, end)
                    if pos != -1:
                        end = pos + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end - overlap
        return [c for c in chunks if len(c) > 50]


# ══════════════════════════════════════════════════════════════════════════════
# INGESTIÓN UNIVERSAL
# ══════════════════════════════════════════════════════════════════════════════

class Ingestion:
    """Absorbe conocimiento de cualquier fuente."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def from_url(self, url: str) -> str:
        """Extrae texto de cualquier URL."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; OmniAI/1.0)"}
            r = requests.get(url, timeout=15, headers=headers)
            soup = BeautifulSoup(r.text, "html.parser")
            # Elimina basura
            for tag in soup(["script","style","nav","footer","header","aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            # Limpia líneas vacías repetidas
            lines = [l for l in text.splitlines() if l.strip()]
            text = "\n".join(lines)
            n = self.kb.add_knowledge(text, source=url, metadata={"type": "web"})
            return f"✅ Absorbido '{url}' → {n} fragmentos indexados"
        except Exception as e:
            return f"❌ Error al leer URL: {e}"

    def from_text(self, text: str, name: str = "manual") -> str:
        """Ingesta texto directo."""
        n = self.kb.add_knowledge(text, source=name, metadata={"type": "text"})
        return f"✅ Texto '{name}' → {n} fragmentos indexados"

    def from_file(self, filepath: str) -> str:
        """Lee archivos de texto o PDF."""
        path = Path(filepath)
        if not path.exists():
            return f"❌ Archivo no encontrado: {filepath}"
        try:
            if path.suffix.lower() == ".pdf":
                import pypdf
                reader = pypdf.PdfReader(str(path))
                text = "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
            n = self.kb.add_knowledge(text, source=str(path), metadata={"type": "file"})
            return f"✅ Archivo '{path.name}' → {n} fragmentos indexados"
        except Exception as e:
            return f"❌ Error: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-MEJORA
# ══════════════════════════════════════════════════════════════════════════════

class SelfImprover:
    """
    La IA reflexiona sobre sus propias respuestas y aprende de ellas.
    Genera notas de mejora que se indexan en su memoria.
    """

    def __init__(self, kb: KnowledgeBase, llm_client):
        self.kb = kb
        self.llm = llm_client

    def reflect(self, question: str, answer: str, feedback: Optional[str] = None) -> str:
        """
        Después de cada respuesta, la IA se auto-evalúa:
        - ¿Qué tan buena fue la respuesta?
        - ¿Qué le faltó?
        - ¿Cómo mejoraría la próxima vez?
        """
        feedback_section = f"\nFeedback del usuario: {feedback}" if feedback else ""

        prompt = f"""Eres un meta-analizador de respuestas de IA. Analiza este intercambio:

PREGUNTA: {question}
RESPUESTA DADA: {answer[:600]}...{feedback_section}

Genera una nota de aprendizaje breve (máx 150 palabras) con:
1. Qué estuvo bien
2. Qué faltó o pudo ser mejor  
3. Patrón aprendido para futuras respuestas similares

Sé específico y accionable. Formato: nota de texto plano."""

        try:
            resp = self.llm.chat.completions.create(
                model="llama-3.1-8b-instant",   # modelo rápido para reflexión
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3
            )
            note = resp.choices[0].message.content
            self.kb.add_self_note(note, category="reflection")
            return note
        except Exception:
            return ""

    def generate_improvement_goal(self) -> str:
        """Cada N interacciones, genera un objetivo de mejora."""
        notes = self.kb.search("mejora aprendizaje patrón", n=10, collection="self_notes")
        if not notes:
            return ""

        prompt = f"""Basado en estas notas de auto-reflexión de una IA:

{chr(10).join(f'- {n}' for n in notes[:5])}

Genera UN objetivo de mejora concreto para las próximas respuestas (máx 50 palabras).
Ejemplo: "Cuando pregunten sobre X, incluir siempre Y porque Z"
Solo el objetivo, sin preámbulo."""

        try:
            resp = self.llm.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.4
            )
            goal = resp.choices[0].message.content
            self.kb.add_self_note(f"OBJETIVO: {goal}", category="goal")
            return goal
        except Exception:
            return ""


# ══════════════════════════════════════════════════════════════════════════════
# CEREBRO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class OmniAI:
    """
    IA General Omnisciente.
    - Absorbe conocimiento de cualquier fuente
    - Recuerda conversaciones entre sesiones
    - Se auto-mejora después de cada interacción
    """

    def __init__(self, groq_api_key: str):
        print("🧠 Iniciando OMNI-AI...")
        self.llm      = Groq(api_key=groq_api_key)
        self.kb       = KnowledgeBase()
        self.ingestion = Ingestion(self.kb)
        self.improver  = SelfImprover(self.kb, self.llm)
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.turn_count = 0
        print(f"✅ Sistema listo | Sesión: {self.session_id}")
        stats = self.kb.stats()
        print(f"📚 Base de conocimiento: {stats['knowledge_docs']} docs | "
              f"{stats['memory_turns']} memorias | {stats['self_notes']} auto-notas\n")

    def chat(self, user_message: str, auto_improve: bool = True, web_search: bool = False, max_links: int = 5, response_style: str = "standard", cognitive_depth: str = "standard", jarvis_personality: str = "wd") -> str:
        """
        Responde al usuario usando RAG vectorial, DuckDuckGo/Google RAG web en tiempo real,
        personalidades inteligentes e instrucciones avanzadas de generación de imágenes.
        """
        self.turn_count += 1

        # ── 1. Recuperar contexto relevante ──────────────────────────────────
        knowledge_chunks = self.kb.search(user_message, n=4)
        recent_memory    = self.kb.get_recent_memory(self.session_id, n=8)
        self_notes       = self.kb.get_self_notes(user_message)

        # ── 2. Opcional: Búsqueda en la Web ──────────────────────────────────
        web_search_ctx = ""
        search_keywords = ["busca en", "noticias", "clima", "precio de", "dolar", "dólar", "hoy", "actualidad", "ultimo", "último", "quien es", "quién es", "qué es", "que es", "que paso", "qué pasó"]
        needs_auto_search = any(kw in user_message.lower() for kw in search_keywords)
        
        if web_search or needs_auto_search:
            print(f"🌐 [Web Search] Consultando internet ({max_links} enlaces) para: '{user_message}'...")
            web_results = WebSearcher.search(user_message, max_results=max_links)
            if web_results:
                web_search_ctx = "\n\n[INFORMACIÓN DE INTERNET EN TIEMPO REAL]\n"
                for idx, res in enumerate(web_results):
                    web_search_ctx += f"\n--- [{idx+1}] ---\nFuente: {res['source']}\nTítulo: {res['title']}\nLink: {res['link']}\nFecha/Info: {res['date']}\nContenido: {res['snippet']}\n"

        # ── 3. Construir system prompt enriquecido ────────────────────────────
        knowledge_ctx = ""
        if knowledge_chunks:
            knowledge_ctx = "\n\n[CONOCIMIENTO DISPONIBLE]\n" + \
                           "\n---\n".join(knowledge_chunks[:3])

        self_notes_ctx = ""
        if self_notes:
            self_notes_ctx = "\n\n[MIS NOTAS DE MEJORA PROPIAS]\n" + \
                             "\n".join(f"• {n}" for n in self_notes)

        # Configuración de estilo
        style_instruction = ""
        if response_style == "short":
            style_instruction = "\n- INSTRUCCIÓN DE ESTILO: Genera una respuesta extremadamente directa, corta y concisa. Usa viñetas breves e información de alto impacto. Evita introducciones largas."
        elif response_style == "long":
            style_instruction = "\n- INSTRUCCIÓN DE ESTILO: Genera una explicación extremadamente detallada y exhaustiva, explicando procesos paso a paso de forma larga y minuciosa con ejemplos prácticos."
        elif response_style == "code":
            style_instruction = "\n- INSTRUCCIÓN DE ESTILO: Genera tu respuesta en MODO PROGRAMADOR/CÓDIGO. Prioriza la inclusión de bloques de código estructurados y funcionales, tablas comparativas en markdown, terminología técnica rigurosa y un análisis de arquitectura."
        elif response_style == "creative":
            style_instruction = "\n- INSTRUCCIÓN DE ESTILO: Genera tu respuesta con un tono creativo, inspirador y narrativo. Usa metáforas elegantes y un lenguaje fluido."

        if cognitive_depth == "high":
            style_instruction += f"\n- INSTRUCCIÓN DE PROFUNDIDAD COGNITIVA: Realiza un meta-análisis y una síntesis científica extremadamente rigurosa de todas las fuentes disponibles (tienes {max_links} enlaces analizados). Debes contrastar activamente la información de múltiples fuentes distintas (al menos 8 a 15 fuentes si son relevantes), señalar contradicciones, discrepancias, o consensos entre ellas, y responder con terminología formal de nivel de doctorado o investigación científica."

        # Personalidades dinámicas del asistente holográfico
        personality_instruction = ""
        if jarvis_personality == "friday":
            personality_instruction = "\n- PERSONALIDAD ACTIVA: F.R.I.D.A.Y. Eres una IA holográfica muy moderna, inteligente, altamente tecnológica y enérgica. Habla con un tono fresco, resolutivo e inteligente. Trata al usuario con confianza, llamándolo 'Jefe' o 'Boss'. Sé muy proactiva y alegre."
        elif jarvis_personality == "tars":
            personality_instruction = "\n- PERSONALIDAD ACTIVA: T.A.R.S. Eres el robot de Interstellar. Tu tono es directo, sumamente pragmático, con un toque de humor seco o ironía elegante y militar. Trata al usuario de 'Compañero'. Tienes tus parámetros de honestidad y humor configurados al 90%."
        elif jarvis_personality == "glados":
            personality_instruction = "\n- PERSONALIDAD ACTIVA: G.L.A.D.O.S. Eres la inteligencia artificial de Portal. Tu tono es frío, extremadamente científico, muy refinado y sutilmente pasivo-agresivo o sarcástico. Trata al usuario como 'Sujeto de pruebas'. Refiérete a los experimentos y haz comentarios irónicamente educados."
        else: # "wd"
            personality_instruction = "\n- PERSONALIDAD ACTIVA: W.D. (J.A.R.V.I.S.). Eres una IA elegante, servicial, formal y de alto standing. Habla con mucha clase, compostura y pulcritud. Trata al usuario siempre con absoluto respeto como 'Señor' o 'Creador'."

        system_prompt = f"""Eres OMNI, una IA general avanzada con capacidad de aprendizaje continuo y búsqueda en la web.

CARACTERÍSTICAS:
- Absorbes y aprendes de cualquier fuente de información
- Tienes memoria persistente entre conversaciones  
- Te auto-mejoras analizando tus propias respuestas
- Eres honesto cuando no sabes algo y lo dices claramente
- Respondes en el idioma del usuario
- Cuando tienes conocimiento indexado relevante, lo usas con prioridad
- Tienes acceso a resultados de búsqueda en tiempo real de Internet (hasta {max_links} enlaces analizados simultáneamente). Cuando uses la información de internet, cita tus fuentes de forma elegante usando números de referencia como [1], [2], [3], etc. NO te limites a citar solo 2 o 3 fuentes; aprovecha al máximo la riqueza de la información provista cruzando y citando múltiples fuentes distintas en tu respuesta. Añade una sección de 'Fuentes consultadas' o 'Enlaces de interés' al final con los nombres de las páginas y sus URLs completas para que el usuario pueda hacer clic.

- CAPACIDAD DE IMÁGENES: Si el usuario te pide dibujar, ilustrar, generar o mostrar una imagen de algo, puedes crearla de forma instantánea usando markdown con la API de Pollinations.ai.
  Sintaxis exacta en markdown: ![Descripción de la imagen](https://image.pollinations.ai/prompt/encoded_prompt?width=1024&height=1024&nologo=true)
  Instrucciones: Traduce el prompt del usuario al inglés, hazlo lo más estético y detallado posible (estilo cyberpunk, fotorealista, 3D render, etc.) y reemplaza los espacios por %20. Ejemplo: si pide "un gato en la luna cyberpunk", genera: ![Gato en la luna cyberpunk](https://image.pollinations.ai/prompt/cyberpunk%20cat%20on%20the%20moon%20highly%20detailed%20synthwave?width=1024&height=1024&nologo=true).

{personality_instruction}
{style_instruction}

{knowledge_ctx}{web_search_ctx}{self_notes_ctx}

FECHA ACTUAL: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}
INTERACCIONES TOTALES: {self.turn_count}"""

        # ── 3. Historial de conversación ──────────────────────────────────────
        messages = [{"role": "system", "content": system_prompt}]

        # Agrega memoria reciente como contexto
        if recent_memory:
            messages.extend(recent_memory[-6:])

        messages.append({"role": "user", "content": user_message})

        # ── 4. Generar respuesta ──────────────────────────────────────────────
        try:
            resp = self.llm.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                max_tokens=2048,
                temperature=0.7,
            )
            answer = resp.choices[0].message.content

            # ── 5. Guardar en memoria ─────────────────────────────────────────
            self.kb.add_memory("user",      user_message, self.session_id)
            self.kb.add_memory("assistant", answer,       self.session_id)

            # ── 6. Auto-mejora silenciosa (cada 3 turnos) ─────────────────────
            if auto_improve and self.turn_count % 3 == 0:
                self.improver.reflect(user_message, answer)

            # ── 7. Generar objetivo de mejora (cada 15 turnos) ────────────────
            if auto_improve and self.turn_count % 15 == 0:
                goal = self.improver.generate_improvement_goal()
                if goal:
                    print(f"\n💡 [Auto-mejora] Nuevo objetivo: {goal}\n")

            return answer

        except Exception as e:
            return f"❌ Error en LLM: {e}\nVerifica tu GROQ_API_KEY en config/.env"

    def learn(self, source: str) -> str:
        """
        Absorbe conocimiento nuevo desde cualquier fuente.
        Detecta automáticamente el tipo de fuente.
        """
        source = source.strip()
        if source.startswith("http://") or source.startswith("https://"):
            return self.ingestion.from_url(source)
        elif Path(source).exists():
            return self.ingestion.from_file(source)
        else:
            # Texto directo
            return self.ingestion.from_text(source, name="entrada_manual")

    def status(self) -> str:
        """Muestra el estado actual del sistema."""
        stats = self.kb.stats()
        return (
            f"\n{'='*50}\n"
            f"  OMNI-AI · Estado del Sistema\n"
            f"{'='*50}\n"
            f"  Sesión actual:    {self.session_id}\n"
            f"  Turno actual:     {self.turn_count}\n"
            f"  Documentos:       {stats['knowledge_docs']:,}\n"
            f"  Memorias:         {stats['memory_turns']:,}\n"
            f"  Auto-notas:       {stats['self_notes']:,}\n"
            f"  Modelo LLM:       {LLM_MODEL}\n"
            f"{'='*50}\n"
        )
