"""Interface language. Source strings are English; `tr()` swaps in the Spanish text when
Spanish is active (Settings → Language, or the system language on "auto").

Plain module state (no Qt objects), so worker threads can call `tr()` too, e.g. for the
labels in output file names. Strings with values use `{name}` placeholders:
tr("{n} files", n=3). To change a translation, edit ES below."""
from __future__ import annotations

LANGUAGES = [("auto", "Automatic (system)"), ("en", "English"), ("es", "Español")]

_lang = "en"


def system_language() -> str:
    try:
        from PySide6.QtCore import QLocale
        langs = QLocale.system().uiLanguages()
    except Exception:
        return "en"
    return "es" if langs and langs[0].lower().startswith("es") else "en"


def set_language(choice: str):
    global _lang
    _lang = system_language() if choice == "auto" else choice if choice in ("en", "es") else "en"


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    if _lang == "es":
        text = ES.get(text, text)
    return text.format(**kw) if kw else text


def trn(n: int, one: str, many: str, **kw) -> str:
    """Singular/plural: trn(2, "{n} page", "{n} pages") -> "2 pages"."""
    return tr(one if n == 1 else many, n=n, **kw)


def file_label(text: str, **kw) -> str:
    """Words that go into output file names ("Photo Compressed.jpg"); looked up as "file:<text>"."""
    if _lang == "es":
        text = ES.get("file:" + text, text)
    return text.format(**kw) if kw else text


ES = {
    # ------------------------------------------------------------ radial menu
    "Convert": "Convertir",
    "Tools": "Herramientas",
    "Unsupported": "No compatible",
    "Drop here": "Soltá acá",
    "{n} files": "{n} archivos",
    "{n} images → 1 PDF": "{n} imágenes → 1 PDF",
    "Compress": "Comprimir",
    "Resize": "Tamaño",
    "Crop": "Recortar",
    "Edit": "Editar",
    "Annotate": "Anotar",
    "Redact": "Tapar",
    "Add BG": "Fondo",
    "Metadata": "Metadatos",
    "Split": "Dividir",
    "Rotate": "Rotar",
    "Merge": "Unir",
    "Protect": "Proteger",
    "Extract": "Extraer",
    "Shrink file size": "Achicar el archivo",
    "View · remove GPS": "Ver · quitar GPS",
    "Hide private info": "Ocultar datos privados",
    "Trim to a ratio": "Ajustar a una proporción",
    "Light · colour · rotate": "Luz · color · rotar",
    "Arrows · text · steps": "Flechas · texto · pasos",
    "Gradient backdrop": "Fondo degradado",
    "Change dimensions": "Cambiar dimensiones",
    "One PDF per page": "Un PDF por página",
    "Turn pages 90°": "Girar páginas 90°",
    "Join into one PDF": "Unir en un PDF",
    "Add a password": "Poner contraseña",
    "Save embedded images": "Guardar las imágenes",
    "Small, universal": "Liviano, universal",
    "Lossless · transparency": "Sin pérdida · transparencia",
    "Smallest for web": "El más liviano para web",
    "iPhone format": "Formato de iPhone",
    "Print · archival": "Imprenta · archivo",
    "Next-gen, tiny": "Moderno, mínimo",
    "Uncompressed": "Sin comprimir",
    "Document": "Documento",
    "Windows icon": "Ícono de Windows",
    "Legacy web": "Web antigua",
    "Editable Word": "Word editable",
    "Plain text": "Texto plano",
    "Plays everywhere": "Se reproduce en todos lados",
    "QuickTime · Apple": "QuickTime · Apple",
    "For the web": "Para la web",
    "Audio only": "Solo el audio",
    "Audio · Apple": "Audio · Apple",
    "Audio · uncompressed": "Audio · sin comprimir",
    "Audio · lossless": "Audio · sin pérdida",
    "Audio · open format": "Audio · formato abierto",

    # ------------------------------------------------------------ app, tray, notifications
    "No permission to write next to this file. Try a folder you own, or set Settings → Save results → subfolder.":
        "No hay permiso para escribir junto a este archivo. Probá con una carpeta tuya, o elegí "
        "Ajustes → Guardar resultados → subcarpeta.",
    "This file doesn't look like an image Banana can read.":
        "Este archivo no parece una imagen que Banana pueda leer.",
    "The file was moved or deleted.": "El archivo se movió o se borró.",
    "{app} — press {key} while dragging a file": "{app}: apretá {key} mientras arrastrás un archivo",
    "Enabled": "Activado",
    "Open a file…": "Abrir un archivo…",
    "Settings…": "Ajustes…",
    "How to use": "Cómo se usa",
    "Quit {app}": "Salir de {app}",
    "Banana is already running": "Banana ya está abierto",
    "Drag any file and press {key}. It lives in the tray.":
        "Arrastrá cualquier archivo y apretá {key}. Está en la barra de menús.",
    "Combining {n} images…": "Combinando {n} imágenes…",
    "Converting to {fmt}…": "Convirtiendo a {fmt}…",
    "Merging…": "Uniendo…",
    "Compressing…": "Comprimiendo…",
    "Splitting…": "Dividiendo…",
    "Rotating…": "Rotando…",
    "Extracting images…": "Extrayendo imágenes…",
    "Couldn't open {name}": "No se pudo abrir {name}",
    "Working…": "Procesando…",
    "Couldn't finish": "No se pudo terminar",
    "Choose file(s) for Banana": "Elegí archivos para Banana",
    "Banana is running": "Banana está abierto",
    "Drag any file, then press {key}.": "Arrastrá cualquier archivo y apretá {key}.",
    "Undone": "Deshecho",
    "Moved {n} file to the {bin}": "Se movió {n} archivo a la {bin}",
    "Moved {n} files to the {bin}": "Se movieron {n} archivos a la {bin}",
    "Recycle Bin": "Papelera de reciclaje",
    "Trash": "Papelera",
    "Open": "Abrir",
    "Show in folder": "Mostrar en carpeta",
    "Undo": "Deshacer",
    "Close (Esc)": "Cerrar (Esc)",
    "This PDF is password-protected. Remove the password first.":
        "Este PDF tiene contraseña. Quitásela primero.",
    "No images found in this PDF.": "Este PDF no tiene imágenes.",
    "FFmpeg isn't available, so video and audio can't be converted.":
        "FFmpeg no está disponible, así que no se puede convertir video ni audio.",
    "This file doesn't look like a video or audio file.": "Este archivo no parece un video ni un audio.",
    "FFmpeg couldn't process this file.": "FFmpeg no pudo procesar este archivo.",
    "This video has no sound.": "Este video no tiene sonido.",
    "This file has no video.": "Este archivo no tiene video.",

    # ------------------------------------------------------------ result summaries
    "Nothing was written": "No se guardó nada",
    "{n} files → 1 {fmt}": "{n} archivos → 1 {fmt}",
    "{n} pages → {m} {fmt}s": "{n} páginas → {m} {fmt}",
    "{n} files → {fmt}": "{n} archivos → {fmt}",
    "{n} page": "{n} página",
    "{n} pages": "{n} páginas",
    "{pct}% smaller": "{pct}% más chico",
    "{pct}% larger": "{pct}% más grande",
    "same size": "mismo tamaño",
    "Compressed": "Comprimido",
    "Compressed {n} files": "{n} archivos comprimidos",
    "already well compressed": "ya estaba bien comprimido",
    "Cropped": "Recortado",
    "Resized": "Redimensionado",
    "Edited": "Editado",
    "Cropped {n} images": "{n} imágenes recortadas",
    "Resized {n} images": "{n} imágenes redimensionadas",
    "Edited {n} images": "{n} imágenes editadas",
    "Background added": "Fondo agregado",
    "Annotated": "Anotado",
    "Redacted": "Tapado",
    "burned into pixels": "grabado en los píxeles",
    "Metadata removed": "Metadatos quitados",
    "private copy": "copia privada",
    "Split into {n} PDFs": "Dividido en {n} PDF",
    "Merged {n} PDFs": "{n} PDF unidos",
    "Rotated 90°": "Rotado 90°",
    "Password protected": "Protegido con contraseña",
    "encrypted": "cifrado",
    "Extracted {n} image": "{n} imagen extraída",
    "Extracted {n} images": "{n} imágenes extraídas",

    # ------------------------------------------------------------ output file names
    # (masculine: they describe the file, e.g. "Foto comprimido.jpg")
    "file:Compressed": "comprimido",
    "file:Combined": "combinado",
    "file:page {n}": "página {n}",
    "file:No Location": "sin ubicación",
    "file:Clean": "limpio",
    "file:Merged": "unido",
    "file:Protected": "protegido",
    "file:{name} images": "{name} imágenes",
    "file:page {p} image {i}": "página {p} imagen {i}",
    "file:Rotated": "rotado",
    "file:Cropped": "recortado",
    "file:With Background": "con fondo",
    "file:Annotated": "anotado",
    "file:Redacted": "tapado",
    "file:Edited": "editado",

    # ------------------------------------------------------------ tool windows
    "Reset": "Restablecer",
    "Cancel": "Cancelar",
    "Save": "Guardar",
    "Apply": "Aplicar",
    "Redo": "Rehacer",
    "Size": "Tamaño",
    "W": "Ancho",
    "H": "Alto",
    # crop
    "Crop Image": "Recortar imagen",
    "Aspect ratio": "Proporción",
    "Free": "Libre",
    "Original": "Original",
    "Rotate 90°": "Rotar 90°",
    "Double-click the image to reset": "Doble clic en la imagen para restablecer",
    "rotated {deg}°": "rotado {deg}°",
    "Cropping…": "Recortando…",
    # add background
    "Background": "Fondo",
    "Banana": "Banana", "Sunset": "Atardecer", "Prism": "Prisma", "Peach": "Durazno", "Aurora": "Aurora", "Mint": "Menta",
    "Ocean": "Océano", "Dusk": "Crepúsculo", "Lemon": "Limón", "Night": "Noche", "Rose": "Rosa",
    "Custom colour": "Color a elección",
    "Background colour": "Color de fondo",
    "Padding": "Margen",
    "Corners": "Esquinas",
    "Shadow": "Sombra",
    "Angle": "Ángulo",
    "Auto": "Auto",
    "Copy": "Copiar",
    "Copy the result to the clipboard": "Copiar el resultado al portapapeles",
    "Copied ✓": "Copiado ✓",
    "Save with Background": "Guardar con fondo",
    "Output": "Resultado",
    "Adding background…": "Agregando fondo…",
    # annotate
    "Type, then Enter": "Escribí y apretá Enter",
    "➜ Arrow": "➜ Flecha",
    "▢ Box": "▢ Recuadro",
    "◯ Circle": "◯ Círculo",
    "✎ Pen": "✎ Lápiz",
    "▬ Marker": "▬ Resaltador",
    "T Text": "T Texto",
    "① Step": "① Paso",
    "{n} arrow": "{n} flecha", "{n} arrows": "{n} flechas",
    "{n} box": "{n} recuadro", "{n} boxes": "{n} recuadros",
    "{n} circle": "{n} círculo", "{n} circles": "{n} círculos",
    "{n} stroke": "{n} trazo", "{n} strokes": "{n} trazos",
    "{n} highlight": "{n} resaltado", "{n} highlights": "{n} resaltados",
    "{n} label": "{n} texto", "{n} labels": "{n} textos",
    "{n} step": "{n} paso", "{n} steps": "{n} pasos",
    "Saving annotations…": "Guardando anotaciones…",
    # redact
    "Black box": "Recuadro negro",
    "Pixelate": "Pixelar",
    "Blur": "Desenfocar",
    "Drag over anything you want hidden. It's burned into the pixels — it can't be undone in the copy.":
        "Arrastrá sobre lo que quieras ocultar. Queda grabado en los píxeles: no se puede deshacer en la copia.",
    "{n} area hidden": "{n} zona oculta",
    "{n} areas hidden": "{n} zonas ocultas",
    "{n} area blacked out": "{n} zona tapada en negro",
    "{n} areas blacked out": "{n} zonas tapadas en negro",
    "{n} area pixelated": "{n} zona pixelada",
    "{n} areas pixelated": "{n} zonas pixeladas",
    "{n} area blurred": "{n} zona desenfocada",
    "{n} areas blurred": "{n} zonas desenfocadas",
    "Redacting…": "Tapando…",
    # edit
    "Brightness": "Brillo",
    "Contrast": "Contraste",
    "Saturation": "Saturación",
    "Warmth": "Calidez",
    "Sharpness": "Nitidez",
    "brightness": "brillo",
    "contrast": "contraste",
    "saturation": "saturación",
    "warmth": "calidez",
    "sharpness": "nitidez",
    "✦ Auto": "✦ Auto",
    "Automatic light and colour": "Luz y color automáticos",
    "⇋ Flip": "⇋ Espejar",
    "⇵ Flip": "⇵ Espejar",
    "B&&W": "B&&N",
    "Hold to compare": "Mantené para comparar",
    "flipped": "espejado",
    "B&W": "B&N",
    "Applying edits…": "Aplicando cambios…",
    # metadata
    "No personal metadata found.": "No se encontraron metadatos personales.",
    "Camera": "Cámara",
    "Taken": "Tomada",
    "Software": "Software",
    "Exposure": "Exposición",
    "Aperture": "Apertura",
    "Location": "Ubicación",
    "title": "título",
    "author": "autor",
    "creator": "creador",
    "producer": "productor",
    "Pages": "Páginas",
    "Open map": "Abrir mapa",
    "⚠  This photo reveals where it was taken.": "⚠  Esta foto revela dónde fue tomada.",
    "Show all {n} fields": "Mostrar los {n} campos",
    "Field": "Campo",
    "Value": "Valor",
    "Remove location only": "Quitar solo la ubicación",
    "Remove all metadata": "Quitar todos los metadatos",
    "removed {n} field": "se quitó {n} campo",
    "removed {n} fields": "se quitaron {n} campos",
    " incl. GPS location": ", con la ubicación GPS",
    "Removing metadata…": "Quitando metadatos…",
    "Removing location…": "Quitando ubicación…",
    "GPS removed, camera info kept": "GPS quitado, se conservan los datos de la cámara",
    # compress
    "Original size": "Tamaño original",
    "Max {px} px": "Máx. {px} px",
    "Quality": "Calidad",
    "Target size": "Tamaño objetivo",
    "Make each file under": "Que cada archivo pese menos de",
    "Convert to WebP (usually the smallest)": "Convertir a WebP (suele ser el más liviano)",
    "This PNG looks like a photo. PNG keeps only 256 colours when compressed, so WebP looks better and is much smaller.":
        "Este PNG parece una foto. Al comprimirlo, PNG solo conserva 256 colores; "
        "en WebP se ve mejor y pesa mucho menos.",
    "Compress {n} files": "Comprimir {n} archivos",
    "quality ≈ {q}": "calidad ≈ {q}",
    "≈ {pct}% smaller · {fmt}": "≈ {pct}% más chico · {fmt}",
    "Already well compressed — try a smaller size or WebP":
        "Ya está bien comprimido: probá con un tamaño menor o con WebP",
    "target {label}": "objetivo {label}",
    "quality {q}": "calidad {q}",
    # video compress
    "Compress video": "Comprimir video",
    "High": "Alta",
    "Medium": "Media",
    "Small file": "Liviana",
    "Keep the sound": "Mantener el sonido",
    "Long videos can take a while: the notification shows the progress.":
        "Los videos largos pueden tardar: la notificación muestra el avance.",
    "no sound": "sin sonido",
    "Compressing video…": "Comprimiendo video…",
    # resize
    "Presets — percent or longest side in px": "Atajos: porcentaje o lado mayor en px",
    "Exact size": "Tamaño exacto",
    "Keep proportions": "Mantener proporciones",
    "Resize {n} files": "Redimensionar {n} archivos",
    "Resizing…": "Redimensionando…",
    # protect
    "Password-protect PDF": "Proteger PDF con contraseña",
    "Password": "Contraseña",
    "Confirm": "Confirmar",
    "Show": "Mostrar",
    "AES-256 encryption. Anyone opening the PDF will need this password.":
        "Cifrado AES-256. Quien abra el PDF va a necesitar esta contraseña.",
    "Use at least 4 characters.": "Usá al menos 4 caracteres.",
    "Passwords don't match yet.": "Las contraseñas todavía no coinciden.",
    "Looks good · {strength} password": "Bien · contraseña {strength}",
    "strong": "fuerte",
    "okay": "aceptable",
    "weak": "débil",
    "Encrypting…": "Cifrando…",

    # ------------------------------------------------------------ settings & welcome
    "Settings": "Ajustes",
    "Language": "Idioma",
    "Automatic (system)": "Automático (sistema)",
    "Open the menu with": "Abrir el menú con",
    "…pressed while you’re dragging a file": "…apretado mientras arrastrás un archivo",
    "Menu shape": "Forma del menú",
    "Round": "Redonda",
    "Save results": "Guardar resultados",
    "Next to the original": "Junto al original",
    "In a “Banana” subfolder": "En una subcarpeta “Banana”",
    "JPG / WebP quality": "Calidad JPG / WebP",
    "PDF → image resolution": "Resolución PDF → imagen",
    "150 dpi · small": "150 dpi · liviano",
    "200 dpi · balanced": "200 dpi · equilibrado",
    "300 dpi · print": "300 dpi · imprenta",
    "Start Banana with Windows": "Iniciar Banana con Windows",
    "Open Banana at login": "Abrir Banana al iniciar sesión",
    "Enable full liquid glass…": "Activar el vidrio líquido completo…",
    "Lets the glass refract the windows behind it (Screen Recording permission)":
        "Permite que el vidrio refracte las ventanas de atrás (permiso de Grabación de pantalla)",
    "Banana {v}  ·  originals are never modified": "Banana {v}  ·  los originales nunca se modifican",
    "Based on DragShift · MIT License": "Basado en DragShift · licencia MIT",
    "Done": "Listo",
    "Welcome to Banana": "Bienvenido a Banana",
    "Start dragging any file": "Empezá a arrastrar cualquier archivo",
    "in Finder or on the desktop": "en el Finder o en el escritorio",
    "in your file manager (Thunar, Nautilus…)": "en tu gestor de archivos (Thunar, Nautilus…)",
    "in File Explorer or on the desktop": "en el Explorador de archivos o en el escritorio",
    "Press {key}": "Apretá {key}",
    "the glass menu opens right under your cursor": "el menú de vidrio se abre justo debajo del cursor",
    "Drop it on a slice": "Soltalo sobre una opción",
    "the result is saved next to the original": "el resultado se guarda junto al original",
    "Tap {key} again": "Volvé a apretar {key}",
    "to switch between Convert and Tools": "para cambiar entre Convertir y Herramientas",
    "You're on a Wayland session: the Shift-while-dragging trigger needs X11 (e.g. XFCE). Right-click a file → Open With → Banana still works.":
        "Estás en una sesión Wayland: el atajo de Shift al arrastrar necesita X11 (por ejemplo XFCE). "
        "Clic derecho en un archivo → Abrir con → Banana sigue funcionando.",
    "Start with Windows": "Iniciar con Windows",
    "Open at login": "Abrir al iniciar sesión",
    "Got it": "Entendido",
}
