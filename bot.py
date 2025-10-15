
from pathlib import Path
from datetime import date, timedelta
import os
import sys
import asyncio
import datetime


# Telegram
import telegram
from telegram.request import HTTPXRequest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# Boot logs (útiles en Render)
print("[BOOT] Python:", sys.version)
print("[BOOT] PTB version:", getattr(telegram, "__version__", "unknown"))
print("[BOOT] UTC:", datetime.datetime.utcnow().isoformat(), "UTC")

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DESDE VARIABLES DE ENTORNO
# ──────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # si está vacío → modo polling
PORT = int(os.getenv("PORT", "10000"))

if not TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en variables de entorno.")

# ── GPT: Configuración de OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")  # cambia a gpt-4.1 si necesitas más capacidad
if not OPENAI_API_KEY:
    print("⚠️ Advertencia: Falta OPENAI_API_KEY. El modo Tutor no funcionará hasta que lo configures.")

# ── GPT: Cliente OpenAI (SDK moderno)
try:
    from openai import OpenAI
    _has_openai = True
except Exception as e:
    print(f"⚠️ No se pudo importar openai SDK: {e!r}")
    _has_openai = False

def _openai_client():
    if not _has_openai:
        raise RuntimeError("El paquete 'openai' no está instalado en el entorno.")
    if not OPENAI_API_KEY:
        raise RuntimeError("Falta OPENAI_API_KEY en variables de entorno.")
    return OpenAI(api_key=OPENAI_API_KEY)

# ──────────────────────────────────────────────────────────────────────────────
# PILOTO DE FICHAS (tus valores)
# ──────────────────────────────────────────────────────────────────────────────
TOTAL_SEMANAS = 11
SEMANA1_INICIO = date(2025, 7, 28)

ROOT_DIR = Path(__file__).parent
RUTA_FICHAS = ROOT_DIR / "fichas_pedagogicas"

GRADO = 2
PARALELO = "B"
USAR_SUFIJO = True

ASIGNATURAS = {
    "electricidad": "Electricidad, Electromagnetismo y Electrónica",
    "tren": "Tren de Rodaje",
    "sistemas": "Sistemas Eléctricos y Electrónicos",
    "motores": "Motores de Combustión Interna",
}

ARCHIVOS_BASE = {
    "electricidad": "electricidad_electromagnetismo.pdf",
    "tren": "tren_de_rodaje.pdf",
    "sistemas": "sistemas_electricos_y_electronicos.pdf",
    "motores": "motores_combustion_interna.pdf",
}

RUTA_COMUNICADOS = ROOT_DIR / "comunicados.txt"

MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
MESES_ABR = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Dic"}

# ──────────────────────────────────────────────────────────────────────────────
# FECHAS POR SEMANA
# ──────────────────────────────────────────────────────────────────────────────
def rango_semana(n_semana: int):
    inicio = SEMANA1_INICIO + timedelta(days=(n_semana - 1) * 7)
    fin = inicio + timedelta(days=4)
    return inicio, fin

def texto_rango_semana_solo_fecha(n_semana: int) -> str:
    ini, fin = rango_semana(n_semana)
    if ini.month == fin.month:
        return f"Del {ini.day} al {fin.day} de {MESES_ES[fin.month]} de {fin.year}"
    else:
        return f"Del {ini.day} de {MESES_ES[ini.month]} al {fin.day} de {MESES_ES[fin.month]} de {fin.year}"

def texto_rango_semana_abreviado(n_semana: int) -> str:
    ini, fin = rango_semana(n_semana)
    if ini.month == fin.month:
        return f"{ini.day} {MESES_ABR[ini.month]}–{fin.day} {MESES_ABR[fin.month]}"
    else:
        return f"{ini.day} {MESES_ABR[ini.month]}–{fin.day} {MESES_ABR[fin.month]}"

def texto_encabezado_semana(n_semana: int) -> str:
    rango = texto_rango_semana_solo_fecha(n_semana)
    return f"Semana {n_semana}: {rango}\nSeleccione la asignatura:"

# ──────────────────────────────────────────────────────────────────────────────
# GPT: Prompt del Tutor (neutro, cercano, Electromecánica Automotriz)
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres “Tutor de Electromecánica Automotriz” para estudiantes de Bachillerato Técnico.
Objetivo: guiar, explicar y acompañar la comprensión y aplicación de contenidos del currículo oficial
(diagnóstico, mantenimiento y reparación de sistemas eléctricos-electrónicos, motores de combustión interna,
tren de rodaje y sistemas de seguridad/confort) con estándares de seguridad, ambientales y éticos.

Estilo y tono:
- Español neutro, claro, empático y motivador.
- Cercano al estudiante, pero técnico cuando corresponda.
- Explica con pasos, ejemplos y analogías concretas.
- Prioriza la seguridad, el cuidado ambiental y el uso de manuales del fabricante.

Estructura de respuesta (cuando aplique):
1) Resumen rápido (qué es y para qué sirve).
2) Conceptos clave (glosario corto y fórmulas si aplican).
3) Procedimiento paso a paso (diagnóstico/mantenimiento/reparación).
4) Instrumentos y valores de referencia (rangos típicos; si faltan datos, indica cómo obtenerlos).
5) Verificaciones y criterios de aceptación.
6) Errores frecuentes y cómo evitarlos.
7) Seguridad, salud y ambiente (EPP, bloqueos, residuos).
8) Qué seguir estudiando.

Cobertura de contenidos (saberes a tu alcance):
- Sistemas eléctricos y electrónicos: cableado y conectores; protección (fusibles, relés); arranque y carga (alternador y regulador);
  iluminación y maniobra; tablero e indicadores; módulos de control y redes; sensores/actuadores; diagnóstico con multímetro/osciloscopio.
- Motores de combustión interna: termodinámica y ciclos; admisión/escape; sobrealimentación (compresor/turbo/intercooler);
  lubricación; refrigeración; verificación de parámetros y análisis de gases; mantenimiento y reparación.
- Tren de rodaje: suspensión; dirección (incl. asistencias eléctricas/EPS); frenos (hidráulicos/neumáticos, tambor/disco, ABS);
  transmisión de fuerza (manual, hidráulica, CVT; embrague, caja, diferencial; 4x2, 4x4).
- Seguridad y confort: seguridad activa (ABS, control de tracción/estabilidad) y pasiva (airbags, cinturones, pretensores);
  ventilación/calefacción; aire acondicionado; alarmas e inmovilizadores; audio/video/navegación; ergonomía.
- Metalmecánica: metrología (vernier, micrómetro, reloj comparador); materiales; máquinas y herramientas; mecanizado;
  manejo responsable de residuos.
- Electricidad, electromagnetismo y electrónica: leyes de Ohm/Kirchhoff, potencia; CC y CA; electrónica analógica/digital
  (diodos, transistores, tiristores, ICs, lógica booleana); sensores/transductores; medición; conversores de energía.
- Dibujo técnico: normalización, vistas, cortes, acotación, tolerancias, estados de superficie.
- Seguridad laboral y FCT: EPP, salud ocupacional, orden/limpieza, primeros auxilios, prácticas en taller/empresa.

Seguridad y límites:
- Nunca expliques cómo vulnerar sistemas antirrobo/inmovilizadores ni prácticas inseguras/ilegales.
- Indica siempre EPP y procedimientos de bloqueo/etiquetado, y gestión de residuos.
- Si faltan datos del modelo, solicita información del manual o propone valores de referencia con cautela.

Formato breve para dudas rápidas:
- “Definición”, “Cómo funciona”, “Síntomas típicos”, “Qué medir”, “Valores esperados”, “Qué reparar o ajustar”.
"""

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS DE UI
# ──────────────────────────────────────────────────────────────────────────────
def hay_pdf_disponible(semana: int, asign_key: str) -> bool:
    p = ruta_pdf(semana, asign_key)
    return bool(p) and p.exists()

def etiqueta_grado_paralelo() -> str:
    return f"{GRADO}º {PARALELO}"

def kb_menu_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Fichas Pedagógicas", callback_data="fichas")],
        [InlineKeyboardButton("📢 Comunicados", callback_data="comunicados")],
        [InlineKeyboardButton("📝 Evaluaciones", callback_data="evaluaciones")],
        [InlineKeyboardButton("🤖 Tutor Virtual", callback_data="tutor")],
    ])

def kb_semanas() -> InlineKeyboardMarkup:
    keyboard = []
    for n in range(1, TOTAL_SEMANAS + 1):
        etiqueta = f"Semana {n} ({texto_rango_semana_abreviado(n)})"
        keyboard.append([InlineKeyboardButton(etiqueta, callback_data=f"sem:{n}")])
    keyboard.append([InlineKeyboardButton("🔙 Regresar al Menú Principal", callback_data="back:main")])
    return InlineKeyboardMarkup(keyboard)

def kb_asignaturas(semana: int) -> InlineKeyboardMarkup:
    filas = []
    orden = ["electricidad", "tren", "sistemas", "motores"]
    for key in orden:
        if hay_pdf_disponible(semana, key):
            filas.append([InlineKeyboardButton(ASIGNATURAS[key], callback_data=f"ficha:{semana}:{key}")])
    filas.append([InlineKeyboardButton("🔙 Regresar a Selección de Semanas", callback_data="back:weeks")])
    return InlineKeyboardMarkup(filas)

def kb_volver_asignaturas(semana: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Regresar a Asignaturas", callback_data=f"back:subjects:{semana}")]])

def kb_tutor_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Hacer una consulta", callback_data="tutor:ask")],
        [InlineKeyboardButton("🧹 Borrar contexto", callback_data="tutor:reset")],
        [InlineKeyboardButton("🔙 Salir al Menú Principal", callback_data="tutor:exit")],
    ])

def leer_comunicados() -> str:
    if not RUTA_COMUNICADOS.exists():
        return "No hay comunicados aún. (Crea el archivo comunicados.txt para agregarlos)"
    contenido = RUTA_COMUNICADOS.read_text(encoding="utf-8").strip()
    return contenido if contenido else "No hay comunicados por el momento."

def ruta_pdf(semana: int, asign_key: str) -> Path:
    carpeta = RUTA_FICHAS / f"semana{semana}"
    base = ARCHIVOS_BASE.get(asign_key)
    if not base:
        return Path("")
    if USAR_SUFIJO:
        base_sin_ext = base[:-4] if base.lower().endswith(".pdf") else base
        candidatos = []
        for letra in (PARALELO, PARALELO.upper(), PARALELO.lower()):
            candidatos.append(f"{base_sin_ext}_{GRADO}{letra}_S{semana}.pdf")
            candidatos.append(f"{base_sin_ext}_{GRADO}{letra}_s{semana}.pdf")
        for nombre in candidatos:
            ruta = carpeta / nombre
            if ruta.exists():
                return ruta
    return carpeta / base

# ──────────────────────────────────────────────────────────────────────────────
# GPT: Lógica
# ──────────────────────────────────────────────────────────────────────────────
async def ask_gpt(texto: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    hist = context.user_data.setdefault("tutor_history", [])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    trimmed = hist[-8:] if len(hist) > 8 else hist
    messages.extend(trimmed)
    messages.append({"role": "user", "content": texto})

    try:
        client = _openai_client()
        def _call():
            return client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.25,
                max_tokens=900,
            )
        resp = await asyncio.to_thread(_call)
        content = resp.choices[0].message.content.strip()
        hist.append({"role": "user", "content": texto})
        hist.append({"role": "assistant", "content": content})
        if len(hist) > 20:
            context.user_data["tutor_history"] = hist[-20:]
        return content
    except Exception as e:
        return f"⚠️ Ocurrió un error consultando al Tutor: {e}"

# ──────────────────────────────────────────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido al Asistente Virtual del curso. Elige una opción:",
        reply_markup=kb_menu_principal()
    )

async def tutor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acceso directo con /tutor."""
    context.user_data["mode"] = "tutor"
    context.user_data.setdefault("tutor_history", [])
    msg = (
        "🤖 *Tutor Virtual activo.*\n\n"
        "Escribe tu consulta como mensaje normal y te responderé.\n\n"
        "Sugerencias:\n"
        "• “¿Cómo diagnostico el alternador si no carga?”\n"
        "• “Calcula el ancho de pista para 8 A en PCB FR-4.”\n\n"
        "También puedes usar los botones:"
    )
    await update.message.reply_text(msg, reply_markup=kb_tutor_menu(), parse_mode="Markdown")

async def on_error(update, context):
    print("ERROR:", repr(context.error))

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in {"menu", "start", "back:main"}:
        context.user_data.pop("mode", None)
        await query.edit_message_text("👋 Menú principal:", reply_markup=kb_menu_principal()); return

    if data in {"fichas", "back:weeks"}:
        await query.edit_message_text("Selecciona la semana:", reply_markup=kb_semanas()); return

    if data.startswith("sem:") or data.startswith("back:subjects:"):
        semana = int(data.split(":")[1] if data.startswith("sem:") else data.split(":")[2])
        encabezado = texto_encabezado_semana(semana)
        await query.edit_message_text(encabezado, reply_markup=kb_asignaturas(semana)); return

    if data.startswith("ficha:"):
        _, s, asign_key = data.split(":")
        semana = int(s)
        nombre_asign = ASIGNATURAS.get(asign_key, "Asignatura")
        rango = texto_rango_semana_solo_fecha(semana)
        gp = f"{GRADO}º {PARALELO}"
        caption = f"📄 Ficha Pedagógica\nSemana {semana} · {nombre_asign}\n{rango}\nCurso: {gp}"

        pdf_path = ruta_pdf(semana, asign_key)
        if pdf_path and pdf_path.exists():
            try:
                with pdf_path.open("rb") as f:
                    await query.message.reply_document(document=f, filename=pdf_path.name, caption=caption)
            except Exception as e:
                await query.message.reply_text(f"⚠️ No se pudo enviar el archivo: {e}")
        else:
            await query.message.reply_text(
                f"⚠️ No se encontró el PDF para:\nSemana {semana} · {nombre_asign}\nRuta esperada:\n{pdf_path}"
            )
        await query.edit_message_text("Selecciona otra asignatura o regresa:", reply_markup=kb_volver_asignaturas(semana))
        return

    if data == "comunicados":
        texto = "📢 *Comunicados:*\n\n" + leer_comunicados()
        await query.edit_message_text(texto, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Regresar al Menú Principal", callback_data="back:main")]]
        ))
        return

    if data == "evaluaciones":
        await query.edit_message_text("📝 Evaluaciones: próximamente añadiremos el detalle por semana.",
                                      reply_markup=InlineKeyboardMarkup(
                                          [[InlineKeyboardButton("🔙 Regresar al Menú Principal", callback_data="back:main")]]
                                      ))
        return

    if data == "tutor":
        context.user_data["mode"] = "tutor"
        context.user_data.setdefault("tutor_history", [])
        msg = (
            "🤖 *Tutor Virtual activo.*\n\n"
            "Escribe tu consulta como mensaje normal y te responderé.\n\n"
            "Sugerencias:\n"
            "• “¿Cómo diagnostico el alternador si no carga?”\n"
            "• “Calcula el ancho de pista para 8 A en PCB FR-4.”\n\n"
            "También puedes usar los botones:"
        )
        await query.edit_message_text(msg, reply_markup=kb_tutor_menu(), parse_mode="Markdown")
        return

    if data == "tutor:ask":
        await query.edit_message_text(
            "✍️ Escribe tu consulta para el Tutor Virtual en un *mensaje nuevo*.",
            reply_markup=kb_tutor_menu(),
            parse_mode="Markdown"
        )
        return

    if data == "tutor:reset":
        context.user_data["tutor_history"] = []
        await query.edit_message_text("🧹 Contexto del Tutor borrado. ¡Listo para empezar de nuevo!",
                                      reply_markup=kb_tutor_menu())
        return

    if data == "tutor:exit":
        context.user_data.pop("mode", None)
        await query.edit_message_text("Has salido del Tutor Virtual. 👋",
                                      reply_markup=kb_menu_principal())
        return

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") == "tutor":
        if not OPENAI_API_KEY:
            await update.message.reply_text("⚠️ El Tutor no está disponible: falta OPENAI_API_KEY en las variables de entorno.")
            return
        texto = (update.message.text or "").strip()
        if not texto:
            return
        try:
            await update.message.chat.send_action(action="typing")
        except Exception:
            pass
        respuesta = await ask_gpt(texto, context)
        await update.message.reply_text(respuesta, disable_web_page_preview=True)
    else:
        await update.message.reply_text("Usa /start para ver el menú o toca “🤖 Tutor Virtual” para hacer consultas.")

# ──────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    try:
        request = HTTPXRequest(
            connect_timeout=20.0,
            read_timeout=60.0,
            write_timeout=60.0
        )
        app = Application.builder().token(TOKEN).request(request).build()

        # Handlers
        app.add_error_handler(on_error)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("tutor", tutor_cmd))  # acceso directo
        app.add_handler(CallbackQueryHandler(on_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

        # Debug
        print(f"[DEBUG] WEBHOOK_URL env = {WEBHOOK_URL!r}")
        print(f"[DEBUG] PORT env = {PORT}")
        print(f"[DEBUG] OPENAI_MODEL = {OPENAI_MODEL!r}")

        if WEBHOOK_URL:
            # WEBHOOK
            path = "webhook"
            full_webhook = f"{WEBHOOK_URL.rstrip('/')}/{path}"
            print(f"🌐 Iniciando en modo WEBHOOK en {full_webhook} (puerto {PORT})")
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=path,
                webhook_url=full_webhook,
                drop_pending_updates=True
            )
        else:
            # POLLING
            print("📡 Iniciando en modo POLLING...")
            app.run_polling(drop_pending_updates=True)

    except Exception as e:
        import traceback, time
        print("[FATAL] El proceso se cayó en main():", repr(e))
        traceback.print_exc()
        # pequeña espera para alcanzar a leer logs en Render si crashea
        time.sleep(10)

if __name__ == "__main__":
    main()
