

from pathlib import Path
from datetime import date, timedelta
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DESDE VARIABLES DE ENTORNO
# ──────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # se define después del 1er deploy
PORT = int(os.getenv("PORT", "10000"))  # Render usa un puerto dinámico

if not TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en variables de entorno.")

# Cantidad de semanas disponibles en el piloto
TOTAL_SEMANAS = 7

# Semana 1: lunes 28 de julio de 2025
SEMANA1_INICIO = date(2025, 7, 28)

# Raíz de fichas (carpeta junto a este bot.py)
ROOT_DIR = Path(__file__).parent
RUTA_FICHAS = ROOT_DIR / "fichas_pedagogicas"

# Identidad del curso para sufijo de archivos
GRADO = 2
PARALELO = "B"
USAR_SUFIJO = True

# Mapa de asignaturas
ASIGNATURAS = {
    "electricidad": "Electricidad, Electromagnetismo y Electrónica",
    "tren": "Tren de Rodaje",
    "sistemas": "Sistemas Eléctricos y Electrónicos",
    "motores": "Motores de Combustión Interna",
}

# Nombres base (sin sufijo) esperados en cada semana
ARCHIVOS_BASE = {
    "electricidad": "electricidad_electromagnetismo.pdf",
    "tren": "tren_de_rodaje.pdf",
    "sistemas": "sistemas_electricos_y_electronicos.pdf",
    "motores": "motores_combustion_interna.pdf",
}

# Ruta del archivo de comunicados
RUTA_COMUNICADOS = ROOT_DIR / "comunicados.txt"

# Meses
MESES_ES = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
MESES_ABR = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

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
# HELPERS DE UI
# ──────────────────────────────────────────────────────────────────────────────
def etiqueta_grado_paralelo() -> str:
    return f"{GRADO}º {PARALELO}"

def kb_menu_principal() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Fichas Pedagógicas", callback_data="fichas")],
        [InlineKeyboardButton("📢 Comunicados", callback_data="comunicados")],
        [InlineKeyboardButton("📝 Evaluaciones", callback_data="evaluaciones")],
    ])

def kb_semanas() -> InlineKeyboardMarkup:
    keyboard = []
    for n in range(1, TOTAL_SEMANAS + 1):
        etiqueta = f"Semana {n} ({texto_rango_semana_abreviado(n)})"
        keyboard.append([InlineKeyboardButton(etiqueta, callback_data=f"sem:{n}")])
    keyboard.append([InlineKeyboardButton("🔙 Regresar al Menú Principal", callback_data="back:main")])
    return InlineKeyboardMarkup(keyboard)

def kb_asignaturas(semana: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(ASIGNATURAS["electricidad"], callback_data=f"ficha:{semana}:electricidad")],
        [InlineKeyboardButton(ASIGNATURAS["tren"],          callback_data=f"ficha:{semana}:tren")],
        [InlineKeyboardButton(ASIGNATURAS["sistemas"],      callback_data=f"ficha:{semana}:sistemas")],
        [InlineKeyboardButton(ASIGNATURAS["motores"],       callback_data=f"ficha:{semana}:motores")],
        [InlineKeyboardButton("🔙 Regresar a Selección de Semanas", callback_data="back:weeks")],
    ])

def kb_volver_asignaturas(semana: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Regresar a Asignaturas", callback_data=f"back:subjects:{semana}")]])

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

    # Si usas sufijo, probamos varias variantes (S/s y B/b) para Linux (case-sensitive)
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

    # fallback al nombre base sin sufijo
    return carpeta / base

# ──────────────────────────────────────────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido al Asistente Virtual del curso. Elige una opción:",
        reply_markup=kb_menu_principal()
    )

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in {"menu", "start", "back:main"}:
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
        gp = etiqueta_grado_paralelo()
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

# ──────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN: webhook si hay URL, si no polling
# ──────────────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))

    # DEBUG opcional
    print(f"[DEBUG] WEBHOOK_URL env = {WEBHOOK_URL!r}")
    print(f"[DEBUG] PORT env = {PORT}")

    if WEBHOOK_URL:
        path = "webhook"                               # ruta explícita
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
        print("📡 Iniciando en modo POLLING...")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
