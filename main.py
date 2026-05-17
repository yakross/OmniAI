"""
OMNI-AI · Interfaz de Terminal
================================
Ejecuta: python main.py
"""

import os, sys
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv("config/.env")

def get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key or key == "TU_CLAVE_AQUI":
        print("\n" + "="*60)
        print("  ⚠️  GROQ_API_KEY no configurada")
        print("="*60)
        print("\n  1. Ve a: https://console.groq.com/keys")
        print("  2. Crea una cuenta GRATIS")
        print("  3. Genera una API Key")
        print("  4. Pégala en config/.env:\n")
        print("     GROQ_API_KEY=gsk_TU_CLAVE_AQUI\n")
        print("="*60)
        key = input("\n  O pégala aquí ahora → ").strip()
        if key:
            # Guardar para futuras sesiones
            env_path = Path("config/.env")
            content = env_path.read_text() if env_path.exists() else ""
            if "GROQ_API_KEY" not in content:
                with open(env_path, "a") as f:
                    f.write(f"\nGROQ_API_KEY={key}\n")
            print("  ✅ Clave guardada en config/.env\n")
    return key


BANNER = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║          ██████  ███    ███ ███    ██ ██                 ║
║         ██    ██ ████  ████ ████   ██ ██                 ║
║         ██    ██ ██ ████ ██ ██ ██  ██ ██                 ║
║         ██    ██ ██  ██  ██ ██  ██ ██ ██                 ║
║          ██████  ██      ██ ██   ████ ██                 ║
║                                                          ║
║          IA General · Auto-aprendizaje · RAG             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""

HELP = """
╔══════════════════════════════════════════════════════════╗
║  COMANDOS DISPONIBLES                                    ║
╠══════════════════════════════════════════════════════════╣
║  /aprender <url o texto>  →  Absorber conocimiento nuevo ║
║  /aprender <ruta/archivo> →  Aprender de un archivo      ║
║  /estado                  →  Ver stats del sistema       ║
║  /limpiar                 →  Limpiar pantalla            ║
║  /reflexionar             →  Forzar auto-reflexión       ║
║  /ayuda                   →  Mostrar esta ayuda          ║
║  /salir                   →  Salir                       ║
╠══════════════════════════════════════════════════════════╣
║  Para CHATEAR: simplemente escribe tu mensaje            ║
║  Para APRENDER de una web: /aprender https://...         ║
╚══════════════════════════════════════════════════════════╝
"""


def main():
    print(BANNER)

    # ── Inicializar IA ────────────────────────────────────────────────────────
    api_key = get_api_key()
    if not api_key:
        print("❌ No se puede iniciar sin API key.")
        sys.exit(1)

    # Importar aquí para que el banner aparezca primero
    sys.path.insert(0, str(Path(__file__).parent))
    from core.brain import OmniAI

    ai = OmniAI(groq_api_key=api_key)
    print(HELP)

    last_question = ""
    last_answer   = ""

    # ── Loop principal ────────────────────────────────────────────────────────
    while True:
        try:
            user_input = input("  Tú → ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  👋 ¡Hasta luego! La IA recuerda todo para la próxima sesión.\n")
            break

        if not user_input:
            continue

        # ── Comandos especiales ───────────────────────────────────────────────

        if user_input.lower() in ["/salir", "/exit", "/quit"]:
            print("\n  👋 ¡Hasta luego! La IA recuerda todo para la próxima sesión.\n")
            break

        elif user_input.lower() == "/ayuda":
            print(HELP)

        elif user_input.lower() == "/estado":
            print(ai.status())

        elif user_input.lower() == "/limpiar":
            os.system("cls" if os.name == "nt" else "clear")
            print(BANNER)

        elif user_input.lower() == "/reflexionar":
            if last_question and last_answer:
                print("\n  🔄 Reflexionando sobre la última respuesta...")
                note = ai.improver.reflect(last_question, last_answer)
                print(f"\n  💡 Nota de auto-mejora:\n  {note}\n")
            else:
                print("\n  ⚠️  Necesitas al menos una conversación primero.\n")

        elif user_input.lower().startswith("/aprender "):
            source = user_input[len("/aprender "):].strip()
            print(f"\n  📥 Absorbiendo: {source[:80]}...")
            result = ai.learn(source)
            print(f"  {result}\n")

        # ── Feedback explícito ────────────────────────────────────────────────

        elif user_input.lower().startswith("/feedback "):
            feedback = user_input[len("/feedback "):].strip()
            if last_question and last_answer:
                note = ai.improver.reflect(last_question, last_answer, feedback=feedback)
                print(f"\n  ✅ Feedback registrado. Auto-nota generada:\n  {note}\n")
            else:
                print("\n  ⚠️  No hay respuesta reciente para evaluar.\n")

        # ── Chat normal ───────────────────────────────────────────────────────

        else:
            print(f"\n  OMNI → ", end="", flush=True)
            answer = ai.chat(user_input)
            print(answer)
            print()
            last_question = user_input
            last_answer   = answer


if __name__ == "__main__":
    main()
