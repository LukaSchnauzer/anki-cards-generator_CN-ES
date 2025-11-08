# ChinoSRS - Sistema de Repetición Espaciada para Chino

Un pipeline completo para generar tarjetas Anki de alta calidad para el aprendizaje de vocabulario chino, con enriquecimiento impulsado por IA, generación de audio y plantillas de tarjetas inteligentes.

---

## 📋 Dependencias

### Requeridas:
- **Python 3.8+**
- **Anki Desktop** con add-on **AnkiConnect** (código: `2055492159`)
- **API Key de OpenAI** (solo para generación de vocabulario)

### Opcional:
- Cuenta de OpenAI con créditos disponibles

---

## 🚀 Inicio Rápido

```bash
# 1. Generar CSV de vocabulario con enriquecimiento IA
python main.py vocab --input data/complete.json --output outputs/vocab.csv

# 2. Validar calidad del CSV generado
python main.py validate-csv --csv outputs/vocab.csv

# 3. Normalizar pinyin (si es necesario)
python main.py normalize-pinyin --input outputs/vocab.csv --output outputs/vocab.csv

# 4. Validar cobertura (opcional)
python main.py validate-coverage --json data/complete.json --csv outputs/vocab.csv

# 5. Generar archivos de audio
python main.py audio --engine gtts --csv outputs/vocab.csv

# 6. Validar archivos de audio
python main.py validate-audio --csv outputs/vocab.csv

# 7. Crear mazo de Anki
python main.py anki --csv outputs/vocab.csv --limit 10
```

---

## 📋 Flujos de Trabajo e Instrucciones de Uso

### Orden Recomendado de Ejecución

Sigue estos pasos en orden para mejores resultados:

```
1. Generar  →  2. Validar  →  3. Normalizar  →  4. Validar    →  5. Generar  →  6. Validar  →  7. Crear
   CSV           CSV           Pinyin           Cobertura       Audio         Audio         Mazo
   (Enriquec.)   (Calidad)     (Opcional)       (Opcional)      (TTS)         (Archivos)    (Tarjetas)
```

---

## 🔧 Instrucciones Detalladas

### Paso 1: Generar CSV de Vocabulario 📚

Genera un CSV de vocabulario enriquecido desde un archivo JSON usando IA.

**Comando:**
```bash
python main.py vocab --input data/complete.json --output outputs/vocab.csv
```

**Opciones:**
- `--input`: Archivo JSON con vocabulario (requerido)
- `--output`: Ruta del archivo CSV de salida (default: outputs/vocab.csv)
- `--limit`: Limitar número de entradas a procesar

**Ejemplos:**
```bash
# Generar 100 entradas de vocabulario
python main.py vocab --input data/complete.json --output outputs/hsk.csv --limit 100

# Procesar todo el vocabulario HSK 1-6
python main.py vocab --input data/complete.json --output outputs/hsk_complete.csv
```

**⏱️ Tiempo**: Este paso puede tomar **varias horas** dependiendo del número de entradas y el tiempo de procesamiento de IA.

**Salida**: Archivo CSV con vocabulario enriquecido incluyendo:
- Hanzi, Pinyin, Definición
- Oraciones de ejemplo (3 por entrada)
- Tips, patrones, colocaciones
- Etiquetas POS, registro, frecuencia

**⚙️ Configuración Requerida**:

Este workflow requiere una API Key de OpenAI. Configúrala creando un archivo `.env` en la raíz del proyecto:

```bash
# .env
OPENAI_API_KEY=tu-api-key-aqui
```

**Nota**: El archivo `.env` está incluido en `.gitignore` y nunca será subido al repositorio.

---

### Paso 2: Generar Archivos de Audio 🔊

Genera archivos de audio para las oraciones en chino usando Text-to-Speech.

**Comando:**
```bash
# Google TTS (rápido, gratis, sin configuración)
python main.py audio --engine gtts --csv outputs/vocab.csv

# Azure TTS (alta calidad, voces variadas, requiere API key)
python main.py audio --engine azure --csv outputs/vocab.csv
```

**Opciones:**
- `--engine`: Motor TTS a usar
  - `gtts` - Google TTS (default, sin configuración, gratis)
  - `azure` - Azure TTS (requiere API key, alta calidad, voces variadas)
- `--csv`: Archivo CSV a procesar (requerido)

**🔑 Configuración de Azure TTS:**
Para usar `--engine azure`, necesitas configurar Azure TTS:
1. Crea cuenta gratuita en [Azure Portal](https://portal.azure.com)
2. Crea recurso "Speech Services" (tier gratuito: 500K caracteres/mes)
3. Agrega tu API key al archivo `.env`:
   ```env
   AZURE_TTS_KEY=tu_key_aqui
```
   AZURE_TTS_REGION=eastus
   ```
4. Ver guía completa: [docs/AZURE_TTS_SETUP.md](docs/AZURE_TTS_SETUP.md)

**⚠️ Nota Importante:** El parámetro `--csv` es obligatorio. Debes especificar qué archivo CSV procesar.

**Ejemplos:**
```bash
# Generar audio con Google TTS (rápido, sin configuración)
python main.py audio --engine gtts --csv outputs/hsk.csv

# Generar audio con Azure TTS (mejor calidad, voces variadas)
python main.py audio --engine azure --csv outputs/vocab.csv
```

**⏱️ Tiempo**: Usualmente toma **5-15 minutos** para 100 entradas (4 archivos de audio por entrada: 1 palabra + 3 frases).

**📊 Progress Tracking**: El script muestra progreso en tiempo real con:
- Porcentaje completado
- Tiempo transcurrido
- Tiempo estimado restante (ETA)
- Velocidad de procesamiento
- Resumen final con estadísticas

**Salida**: Archivos MP3 de audio en el directorio `resources/audios/`:
- `word_{hanzi}_{hash}.mp3` - Audio de la palabra sola
- `{sentence}_{hash}.mp3` - Audio de frases de ejemplo

---

### Paso 3: Crear Mazo de Anki 🎴

Convierte el CSV a tarjetas Anki con tres tipos de tarjetas por entrada.

**Comando:**
```bash
python main.py anki --csv outputs/vocab.csv --limit 10 --force-recreate
```

**Opciones:**
- `--csv`: Archivo CSV de entrada (requerido)
- `--limit`: Limitar número de entradas a procesar
- `--force-recreate`: Forzar recreación de modelos de tarjetas (usar cuando cambien las plantillas)

**Ejemplos:**
```bash
# Crear 10 tarjetas de prueba
python main.py anki --csv outputs/test.csv --limit 10 --force-recreate

# Crear mazo completo sin recrear modelos
python main.py anki --csv outputs/vocab.csv

# Crear 50 tarjetas con modelos frescos
python main.py anki --csv outputs/hsk.csv --limit 50 --force-recreate
```

**⏱️ Tiempo**: Muy rápido, usualmente **menos de 1 minuto** para 100 entradas.

**Salida**: 3 tarjetas Anki por entrada de vocabulario (SentenceCard, PatternCard, AudioCard) en el mazo "Chino SRS".

**⚠️ Prerequisitos:**
- Anki debe estar ejecutándose
- El add-on AnkiConnect debe estar instalado
- Los archivos de audio deben existir en `resources/audios/`

---

### Paso 4: Validar Calidad del CSV ✓

Valida la calidad del CSV generado para detectar problemas antes de crear las tarjetas.

**Comando:**
```bash
python main.py validate-csv --csv outputs/vocab.csv
```

**Opciones:**
- `--csv`: Archivo CSV a validar (requerido)
- `--errors-only`: Mostrar solo errores críticos (ocultar warnings)
- `--export-clean`: Exportar CSV limpio sin filas problemáticas
- `--remove-severity`: Qué filas remover: `errors` (solo errores) o `all` (errores + warnings). Default: `errors`

**Validaciones incluidas:**
- ✅ Campos requeridos presentes y no vacíos
- ✅ Conteo correcto de oraciones (3 esperadas)
- ✅ Conteo correcto de colocaciones (3-5 esperadas)
- ✅ Hanzi aparece en las oraciones de ejemplo
- ✅ Formato de definición (longitud apropiada)
- ✅ Formato de pinyin (minúsculas, marcas tonales)
- ✅ Etiquetas HSK y frecuencia presentes
- ✅ **Cobertura de limpieza de pinyin** (detecta pinyin que no será limpiado)
- ✅ Formato de colocaciones correcto

**Ejemplos:**
```bash
# Validar CSV completo
python main.py validate-csv --csv outputs/hsk_vocab_full.csv

# Ver solo errores críticos
python main.py validate-csv --csv outputs/vocab.csv --errors-only

# Exportar CSV limpio (remover solo errores)
python main.py validate-csv --csv outputs/vocab.csv \
  --export-clean outputs/vocab_clean.csv

# Remover todas las filas con problemas (errores + warnings)
python main.py validate-csv --csv outputs/vocab.csv \
  --export-clean outputs/vocab_clean.csv \
  --remove-severity all
```

**Salida de ejemplo:**
```
================================================================================
VALIDATION RESULTS
================================================================================
Total rows:    1000
Errors:        5
Warnings:      23
Total issues:  28
================================================================================

ISSUES FOUND:
[ERROR] Row 145 (测试) - example_sentence: '测试' no aparece en ninguna oracion
[WARN] Row 267 (词汇) - example_sentence[2]: Posible pinyin fuera de parentesis (no sera limpiado)
[WARN] Row 389 (汉字) - collocations: Esperadas 3-5 colocaciones, encontradas 2

ℹ️  Removing rows with ERRORS only (5 rows)

✅ Exported 995 clean rows to: outputs/vocab_clean.csv
   Removed 5 problematic rows
```

**Flujo de trabajo recomendado:**
1. Validar CSV y exportar versión limpia
2. Usar CSV limpio para generar audio y tarjetas
3. Usar `validate-coverage` para identificar entradas faltantes
4. Re-procesar entradas faltantes con `vocab`

---

### Paso 5: Normalizar Pinyin en CSV 🔧

Normaliza diferentes formatos de pinyin a formato estándar con diacríticos.

**Comando:**
```bash
python main.py normalize-pinyin --input outputs/vocab.csv --output outputs/vocab_normalized.csv
```

**Opciones:**
- `--input`: Archivo CSV de entrada (requerido)
- `--output`: Archivo CSV de salida (requerido)
- `--dry-run`: Mostrar cambios sin escribir archivo de salida

**Formatos soportados:**
- ✅ `lu:3 xing2` → `lǔ xíng` (formato con dos puntos)
- ✅ `lu:4` → `lù` (dos puntos + número)
- ✅ `mei2fa3r5` → `méi fǎ r` (sílabas pegadas)
- ✅ `ni3hao3` → `nǐ hǎo` (números sin espacios)
- ✅ `lv3` → `lǚ` (v → ü)
- ✅ `ju1`, `qu2`, `xu3`, `yu4` → `jǖ`, `qǘ`, `xǚ`, `yǜ` (conversión automática ü)
- ✅ `r5`, `zi5` → `r`, `zi` (tono neutral eliminado)
- ✅ `tān wánr5` → `tān wánr` (diacríticos + número mixto)
- ✅ `hútòngr5` → `hútòngr` (formato mixto con tono neutral)

**Ejemplos:**
```bash
# Ver cambios sin modificar archivo (dry-run)
python main.py normalize-pinyin \
  --input outputs/vocab_retry.csv \
  --output outputs/vocab_normalized.csv \
  --dry-run

# Normalizar y guardar
python main.py normalize-pinyin \
  --input outputs/vocab_retry.csv \
  --output outputs/vocab_normalized.csv

# Normalizar in-place (mismo archivo)
python main.py normalize-pinyin \
  --input outputs/vocab.csv \
  --output outputs/vocab.csv
```

**Salida de ejemplo:**
```
Reading CSV: outputs/vocab_retry.csv

================================================================================
NORMALIZATION RESULTS
================================================================================
Total rows:     150
Rows changed:   45
Rows unchanged: 105
================================================================================

CHANGES DETECTED:
--------------------------------------------------------------------------------
  Row 2 (履行)
    Before: lu:3 xing2
    After:  lǔ xíng
  
  Row 15 (绿)
    Before: lu:4
    After:  lù
  
  Row 23 (没法儿)
    Before: mei2fa3r5
    After:  méi fǎ r
  
  ... and 42 more changes

✅ Normalized CSV written to: outputs/vocab_normalized.csv
```

**Reglas de normalización:**
1. **Colocación de marcas tonales**: `a` o `e` tienen prioridad, en `ou` la `o` lleva la marca, de lo contrario la última vocal
2. **Conversión automática ü**: `ju`, `qu`, `xu`, `yu` siempre se convierten a `jü`, `qü`, `xü`, `yü`
3. **Tono neutral**: Tono 5 se elimina (轻声)
4. **Preservación**: Mayúsculas iniciales y espacios se mantienen

---

### Paso 6: Validar Cobertura JSON vs CSV ✓

Verifica qué entradas del JSON original fueron generadas exitosamente en el CSV.

**Comando:**
```bash
python main.py validate-coverage --json resources/complete.json --csv outputs/vocab.csv
```

**Opciones:**
- `--json`: Archivo JSON de entrada (requerido)
- `--csv`: Archivo CSV generado (requerido)
- `--show-missing`: Mostrar lista de entradas faltantes
- `--export-missing`: Exportar entradas faltantes a JSON para re-procesamiento

**Ejemplos:**
```bash
# Validación básica
python main.py validate-coverage --json resources/complete.json --csv outputs/vocab.csv

# Ver lista de faltantes
python main.py validate-coverage --json resources/complete.json --csv outputs/vocab.csv --show-missing

# Exportar faltantes para re-procesar
python main.py validate-coverage --json resources/complete.json --csv outputs/vocab.csv --export-missing missing.json

# Re-procesar solo las faltantes
python main.py vocab --input missing.json --output outputs/vocab_retry.csv
```

**Salida de ejemplo:**
```
============================================================
COVERAGE VALIDATION RESULTS
============================================================
Total entries in JSON:     11000
Total entries in CSV:      10847
Missing entries:           153
Coverage:                  98.61%
============================================================

⚠️  153 entries from JSON were not generated in CSV

✅ Exported 153 missing entries to: missing.json
```

**Flujo de trabajo recomendado:**
1. Generar vocabulario inicial
2. Validar cobertura y exportar faltantes
3. Re-procesar solo las entradas faltantes
4. Combinar CSVs (si es necesario)

---

### Paso 6: Validar Archivos de Audio 🔊

Verifica que todos los archivos de audio requeridos existan para las entradas del CSV.

**Comando:**
```bash
python main.py validate-audio --csv outputs/vocab.csv
```

**Opciones:**
- `--csv`: Archivo CSV a validar (requerido)
- `--audio-dir`: Directorio de audio (default: resources/audios)
- `--show-missing`: Mostrar lista de archivos faltantes
- `--export-missing`: Exportar lista de faltantes a archivo de texto

**Archivos validados por entrada:**
- ✅ 1 archivo de audio de palabra: `word_{hanzi}_{hash}.mp3`
- ✅ 3 archivos de audio de oraciones: `{sentence}_{hash}.mp3`
- ✅ Total: 4 archivos por entrada

**Ejemplos:**
```bash
# Validación básica
python main.py validate-audio --csv outputs/vocab.csv

# Ver lista de archivos faltantes
python main.py validate-audio --csv outputs/vocab.csv --show-missing

# Exportar lista de faltantes
python main.py validate-audio --csv outputs/vocab.csv --export-missing missing_audio.txt

# Usar directorio de audio personalizado
python main.py validate-audio --csv outputs/vocab.csv --audio-dir /path/to/audios
```

**Salida de ejemplo:**
```
================================================================================
AUDIO VALIDATION RESULTS
================================================================================
Total audio files expected:  4000
Missing audio files:         12
Coverage:                    99.70%
================================================================================

WARNING: 12 audio files are missing!

MISSING AUDIO FILES:
  Row 145 (测试) - word
    Expected: resources/audios/word_测试_a1b2c3d4.mp3
  Row 267 (词汇) - sentence[2]
    Expected: resources/audios/这是一个例句。_e5f6g7h8.mp3
```

**Nota importante:**
- La validación usa la misma lógica de limpieza de pinyin que la generación de audio
- Los hashes se calculan sobre texto **sin pinyin** en paréntesis
- Si hay archivos faltantes, re-ejecuta la generación de audio para esas entradas

---

### Paso 7: Exportar Mazo de Anki (Opcional) 📋

Exporta el contenido del mazo de Anki a JSON para respaldo o análisis.

**Comando:**
```bash
python main.py dump --deck "Chino SRS" --output backup.json
```

**Opciones:**
- `--deck`: Nombre del mazo (default: "Chino SRS")
- `--output`: Archivo JSON de salida

**Ejemplo:**
```bash
# Respaldar tu mazo
python main.py dump --deck "Chino SRS" --output backups/deck_2024.json
```

---

## 📁 Estructura del Proyecto

```
ChinoSRS/
├── main.py                      # 🎯 Orquestador CLI principal
├── README.md                    # 📖 Este archivo
├── requirements.txt             # Dependencias Python
├── .env                         # 🔐 API Keys (NO subir a git)
├── .gitignore                   # Protege .env y otros archivos
├── anki-venv/                   # Entorno virtual Python
│
├── data/
│   └── complete.json           # 📚 Vocabulario HSK 1-6 completo
│
├── src/
│   ├── generate_vocab_csv.py   # Enriquecimiento de vocab con IA
│   ├── csv_to_anki.py          # Convertidor CSV a Anki
│   │
│   ├── anki/                   # Módulos de integración Anki
│   │   ├── api.py             # Funciones AnkiConnect
│   │   ├── models.py          # Definiciones de modelos de tarjetas
│   │   └── hints.py           # Lógica de generación de pistas
│   │
│   ├── audio/                  # Scripts de generación de audio
│   │   ├── generate_audio.py   # 🎯 Script principal TTS
│   │   └── engines/            # Motores TTS modulares
│   │       ├── gtts_engine.py  # Google TTS
│   │       └── azure_engine.py # Azure TTS (Microsoft)
│   │
│   ├── templates/              # Plantillas HTML de tarjetas
│   │   ├── sentence_card_front.html
│   │   ├── sentence_card_back.html
│   │   ├── pattern_card_front.html
│   │   ├── pattern_card_back.html
│   │   ├── audio_card_front.html
│   │   └── audio_card_back.html
│   │
│   └── utils/                  # Scripts de utilidad
│       ├── dump_deck.py       # Herramienta de exportación de mazo
│       ├── validate_csv.py    # ✓ Validación de calidad de CSV
│       ├── validate_audio.py  # ✓ Validación de archivos de audio
│       ├── validate_coverage.py # ✓ Validación de cobertura JSON vs CSV
│       └── normalize_pinyin_csv.py # 🔧 Normalización de formatos de pinyin
│
├── outputs/                    # Archivos CSV generados
└── resources/
    └── audios/                # Archivos de audio generados
```

---

## 📚 Datos Incluidos

### Vocabulario HSK Completo

El repositorio incluye el archivo `resources/complete.json` que contiene **vocabulario HSK completo** con **11,494 entradas**:

#### HSK Antiguo (2010) - 5,000 palabras
- **HSK 1**: 150 palabras
- **HSK 2**: 150 palabras  
- **HSK 3**: 299 palabras
- **HSK 4**: 601 palabras
- **HSK 5**: 1,300 palabras
- **HSK 6**: 2,500 palabras

#### HSK Nuevo (2021) - 10,993 palabras
- **HSK 1**: 511 palabras
- **HSK 2**: 755 palabras
- **HSK 3**: 959 palabras
- **HSK 4**: 972 palabras
- **HSK 5**: 1,061 palabras
- **HSK 6**: 1,126 palabras
- **HSK 7+**: 5,609 palabras

#### Distribución por Frecuencia
- **Top 1K**: 759 palabras (más comunes)
- **Top 3K**: 1,528 palabras
- **Top 5K**: 1,382 palabras
- **Top 10K**: 2,873 palabras
- **Raras**: 4,859 palabras
- **Sin frecuencia**: 93 palabras

**Fuente**: [Complete HSK Vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary)

Este archivo JSON está listo para ser procesado por el generador de vocabulario.

---

## 🎴 Tipos de Tarjetas

Cada entrada de vocabulario genera **3 tipos de tarjetas**:

### 1. 🀄️ SentenceCard
- **Frente**: Oración de ejemplo → "¿Qué es [hanzi]?"
- **Reverso**: Hanzi, pinyin, significado, audio, ejemplo, tips
- **Propósito**: Aprender palabra en contexto

### 2. 🧩 PatternCard
- **Frente**: Oración con eliminación cloze [___]
- **Reverso**: Parte faltante, traducción, audio, significado, patrón
- **Propósito**: Practicar recuerdo de palabra

### 3. 🔊 AudioCard
- **Frente**: Reproductor de audio (autoplay)
- **Reverso**: Hanzi, pinyin, oración, audio, significado
- **Propósito**: Entrenar comprensión auditiva

**Todas las tarjetas incluyen:**
- ✨ Pistas progresivas de 3 fases
- 🔊 Audio de alta calidad
- 🎨 Diseño moderno y responsivo
- 📱 Cajas de pistas con click para cerrar

---

## 🛠️ Instalación

### 1. Clonar el repositorio
```bash
git clone <repo-url>
cd ChinoSRS
```

### 2. Crear entorno virtual
```bash
python -m venv anki-venv
```

### 3. Activar entorno virtual
- **Windows**: `anki-venv\Scripts\activate`
- **Linux/Mac**: `source anki-venv/bin/activate`

### 4. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 5. Configurar API Key de OpenAI

**⚠️ Requerido para el Paso 1 (Generación de Vocabulario)**

El workflow de generación de vocabulario utiliza la API de OpenAI para enriquecer las entradas con ejemplos, tips y patrones. Necesitas una API Key válida.

**Pasos:**

1. Obtén tu API Key en: https://platform.openai.com/api-keys
2. Copia el archivo de ejemplo y edítalo:

```bash
# En la raíz del proyecto
cp .env.example .env

# O en Windows
copy .env.example .env
```

3. Edita el archivo `.env` y agrega tu API Key:

```bash
OPENAI_API_KEY=sk-tu-api-key-aqui
```

4. Asegúrate de tener créditos en tu cuenta de OpenAI

**Nota de Seguridad:** 
- El archivo `.env` está incluido en `.gitignore` y **nunca será subido al repositorio**
- Puedes usar `.env.example` como plantilla

### 6. Instalar AnkiConnect
1. Abrir Anki
2. Herramientas → Complementos → Obtener Complementos
3. Código: `2055492159`
4. Reiniciar Anki

---

## 📊 Ejemplo de Flujo Completo

### Escenario: Crear 50 tarjetas de vocabulario HSK

```bash
# Paso 1: Generar vocabulario (puede tomar 1-2 horas)
python main.py vocab --input data/complete.json --output outputs/hsk3.csv --limit 50

# Esperar a que termine...

# Paso 2: Generar audio (5-10 minutos)
python main.py audio --engine gtts --csv outputs/hsk3.csv

# Paso 3: Crear mazo de Anki (< 1 minuto)
python main.py anki --csv outputs/hsk3.csv --force-recreate

# ¡Listo! Abre Anki para revisar tus tarjetas
```

---

## 🎯 Características

- ✅ **Enriquecimiento con IA**: Generación automática de ejemplos, tips, patrones
- ✅ **Motores de Audio Duales**: Google TTS (rápido) + Edge TTS (calidad)
- ✅ **Generación Inteligente de Tarjetas**: 3 tipos de tarjetas por entrada con diferentes oraciones
- ✅ **Pistas Progresivas**: Sistema de pistas de 3 fases para mejor aprendizaje
- ✅ **UI Moderna**: Plantillas de tarjetas hermosas y responsivas
- ✅ **Arquitectura Modular**: Base de código limpia y mantenible
- ✅ **Orquestador CLI**: Interfaz de línea de comandos fácil de usar
- ✅ **Procesamiento por Lotes**: Manejo eficiente de grandes conjuntos de datos
- ✅ **Vocabulario HSK Completo**: 5,000 palabras HSK 1-6 incluidas

---

## 🔧 Configuración

### Variables de Entorno

**Requeridas:**
- `OPENAI_API_KEY` - **API Key de OpenAI** (requerida para Paso 1: generación de vocabulario)
  - Obtener en: https://platform.openai.com/api-keys
  - Configurar en archivo `.env` en la raíz del proyecto
  - Formato: `OPENAI_API_KEY=sk-...`

**Opcionales:**
- `ANKI_CONNECT_URL` - URL de AnkiConnect (default: `http://localhost:8765`)
- `ANKI_DECK_NAME` - Nombre del mazo destino (default: `"Chino SRS"`)
- `ANKI_AUDIO_DIR` - Ruta del directorio de audio (default: `resources/audios`)

**Ejemplo de archivo `.env`:**
```bash
# ============================================
# OpenAI API Configuration
# ============================================
# Required for vocabulary generation workflow (Step 1)
OPENAI_API_KEY=sk-your-api-key-here

# ============================================
# Anki Configuration (Optional)
# ============================================
# AnkiConnect URL - Default: http://localhost:8765
ANKI_CONNECT_URL=http://localhost:8765

# Deck name - Default: "Chino SRS"
ANKI_DECK_NAME=Chino SRS

# Audio directory - Default: resources/audios
# ANKI_AUDIO_DIR=resources/audios
```

**Nota**: Puedes copiar `.env.example` a `.env` y editar los valores.

---

## 🐛 Solución de Problemas

### AnkiConnect no responde
- ✓ Asegúrate de que Anki esté ejecutándose
- ✓ Verifica que el add-on AnkiConnect esté instalado
- ✓ Verifica la URL: http://localhost:8765

### Archivos de audio no encontrados
- ✓ Ejecuta la generación de audio antes de crear tarjetas
- ✓ Verifica que el directorio `resources/audios/` exista
- ✓ Verifica que el CSV tenga la columna `example_sentence`

### Error de tarjetas duplicadas
- ✓ Elimina las tarjetas existentes en el mazo de Anki primero
- ✓ O usa un archivo CSV diferente para pruebas

### Errores de importación
- ✓ Asegúrate de estar en el directorio raíz del proyecto
- ✓ Activa el entorno virtual
- ✓ Reinstala las dependencias: `pip install -r requirements.txt`

### Errores de Unicode en Windows
- ✓ Usa PowerShell en lugar de CMD
- ✓ O ejecuta: `chcp 65001` antes de ejecutar comandos

### Error de API Key de OpenAI
- ✓ Verifica que el archivo `.env` exista en la raíz del proyecto
- ✓ Verifica que la API Key sea válida
- ✓ Asegúrate de que el formato sea: `OPENAI_API_KEY=sk-...`

---

## 📝 Tips y Mejores Prácticas

### Para Generación de Vocabulario
- Comienza con lotes pequeños (10-20 entradas) para probar
- Usa el parámetro `--limit` para controlar el tiempo de procesamiento
- Mantén el JSON de entrada bien formateado
- Asegúrate de tener créditos suficientes en tu cuenta de OpenAI

### Para Generación de Audio
- Google TTS (`gtts`) es más rápido y confiable
- Edge TTS (`edge`) tiene mejor calidad pero puede fallar ocasionalmente
- Genera audio antes de crear tarjetas de Anki
- Usa `--csv` para especificar qué archivo procesar

### Para Creación de Mazo de Anki
- Usa `--force-recreate` cuando modifiques las plantillas
- Usa `--limit` para pruebas antes de crear el mazo completo
- Mantén Anki ejecutándose durante la creación de tarjetas

---

## 🔍 Herramientas de Validación

### Validación de Calidad (validate-csv)

Detecta problemas comunes en el CSV generado:

**Validaciones implementadas:**
- ✅ Campos requeridos vacíos
- ✅ Conteo incorrecto de oraciones/traducciones
- ✅ Desbalance entre oraciones CN y traducciones ES
- ✅ Conteo incorrecto de colocaciones (3-5 esperadas)
- ✅ Hanzi no aparece en oraciones de ejemplo
- ✅ Definiciones muy cortas o muy largas
- ✅ Pinyin en mayúsculas o con números
- ✅ Etiquetas HSK/frecuencia faltantes
- ✅ **Pinyin fuera de paréntesis** (no será limpiado)
- ✅ **Pinyin en corchetes/llaves** (no será limpiado)
- ✅ **Colocaciones sin paréntesis** (formato incorrecto)

**Uso recomendado:**
```bash
# Después de generar el CSV
python main.py validate-csv --csv outputs/vocab.csv

# Ver solo errores críticos
python main.py validate-csv --csv outputs/vocab.csv --errors-only
```

### Normalización de Pinyin (normalize-pinyin)

Normaliza diferentes formatos de pinyin a formato estándar con diacríticos:

**Formatos soportados:**
- ✅ `lu:3 xing2` → `lǔ xíng` (formato con dos puntos)
- ✅ `mei2fa3r5` → `méi fǎ r` (sílabas pegadas)
- ✅ `ni3hao3` → `nǐ hǎo` (números sin espacios)
- ✅ `lv3` → `lǚ` (v → ü automático)
- ✅ `ju1`, `qu2`, `xu3`, `yu4` → conversión automática a ü
- ✅ `tān wánr5` → `tān wánr` (diacríticos + número mixto)
- ✅ Tono neutral (5) eliminado

**Uso recomendado:**
```bash
# Ver cambios sin modificar (dry-run)
python main.py normalize-pinyin --input outputs/vocab.csv --output outputs/vocab_normalized.csv --dry-run

# Aplicar normalización
python main.py normalize-pinyin --input outputs/vocab.csv --output outputs/vocab.csv
```

### Validación de Archivos de Audio (validate-audio)

Verifica que todos los archivos de audio existan:

**Validaciones implementadas:**
- ✅ Audio de palabra (word_{hanzi}_{hash}.mp3)
- ✅ Audio de 3 oraciones ({sentence}_{hash}.mp3)
- ✅ Usa misma lógica de limpieza de pinyin
- ✅ Calcula hashes correctamente

**Uso recomendado:**
```bash
# Después de generar audio
python main.py validate-audio --csv outputs/vocab.csv

# Ver archivos faltantes
python main.py validate-audio --csv outputs/vocab.csv --show-missing

# Exportar lista de faltantes
python main.py validate-audio --csv outputs/vocab.csv --export-missing missing_audio.txt
```

### Validación de Cobertura (validate-coverage)

Verifica qué entradas del JSON fueron generadas exitosamente:

**Funcionalidades:**
- ✅ Compara JSON de entrada vs CSV generado
- ✅ Calcula porcentaje de cobertura
- ✅ Lista entradas faltantes
- ✅ Exporta faltantes a JSON para re-procesamiento

**Flujo de trabajo:**
```bash
# 1. Validar cobertura
python main.py validate-coverage --json resources/complete.json --csv outputs/vocab.csv --export-missing missing.json

# 2. Re-procesar solo las faltantes
python main.py vocab --input missing.json --output outputs/vocab_retry.csv

# 3. Combinar CSVs (manualmente o con script)
```

---

## 📚 Referencias

### Herramientas y Add-ons
- **[AnkiConnect](https://ankiweb.net/shared/info/2055492159)**: - Add-on para comunicación con Anki
- **[OpenAI API](https://platform.openai.com/docs/api-reference/introduction)**: - Documentación de la API de OpenAI
- **[gTTS](https://pypi.org/project/gTTS/)**: - Google Text-to-Speech Python
- **[Edge-TTS](https://pypi.org/project/edge-tts/)**: - Microsoft Edge Text-to-Speech

### Fuentes de Datos
- **[Vocabulario HSK](https://github.com/drkameleon/complete-hsk-vocabulary)**: - Fuente del archivo complete.json con vocabulario HSK 1-6

### Recursos de Aprendizaje
- **[Anki Manual](https://docs.ankiweb.net/)**: - Documentación oficial de Anki
- **[HSK Official](https://www.chinesetest.cn/HSK)**: - Información sobre los niveles HSK
- **[Chinese Grammar Wiki](https://resources.allsetlearning.com/chinese/grammar/)**: - Recurso de gramática china

---

## 👨‍💻 Autor

**Juan Montero**

Creado con asistencia de IA Generativa (Claude Sonnet 4.5)

---

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas! Por favor abre un issue o PR.

---

## 📧 Soporte

Para preguntas o problemas, por favor abre un issue en GitHub.
