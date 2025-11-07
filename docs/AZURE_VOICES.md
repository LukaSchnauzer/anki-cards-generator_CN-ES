# Voces Disponibles en Azure TTS

## 🎭 Voces Chinas Disponibles

ChinoSRS soporta **19 voces diferentes** de Azure Neural TTS para mandarín chino, con variedad de géneros, edades y estilos.

## 👩 Voces Femeninas (12 voces)

| Voz | Edad | Estilo | Descripción |
|-----|------|--------|-------------|
| `zh-CN-XiaoxiaoNeural` | Joven | Cálida | Voz femenina joven, cálida y amigable (default) |
| `zh-CN-XiaohanNeural` | Joven | Amigable | Voz femenina joven, amigable y clara |
| `zh-CN-XiaomengNeural` | Joven | Dulce | Voz femenina joven, dulce y tierna |
| `zh-CN-XiaomoNeural` | Joven | Gentil | Voz femenina joven, gentil y suave |
| `zh-CN-XiaoqiuNeural` | Joven | Profesional | Voz femenina joven, profesional y clara |
| `zh-CN-XiaoruiNeural` | Joven | Energética | Voz femenina joven, energética y vivaz |
| `zh-CN-XiaoshuangNeural` | Joven | Clara | Voz femenina joven, clara y precisa |
| `zh-CN-XiaoxuanNeural` | Joven | Dulce | Voz femenina joven, dulce y melodiosa |
| `zh-CN-XiaoyanNeural` | Joven | Estándar | Voz femenina joven, estándar y neutral |
| `zh-CN-XiaoyiNeural` | Joven | Natural | Voz femenina joven, natural y relajada |
| `zh-CN-XiaoyouNeural` | Niña | Infantil | Voz de niña, perfecta para vocabulario básico |
| `zh-CN-XiaozhenNeural` | Joven | Suave | Voz femenina joven, suave y delicada |

## 👨 Voces Masculinas (7 voces)

| Voz | Edad | Estilo | Descripción |
|-----|------|--------|-------------|
| `zh-CN-YunxiNeural` | Joven | Energético | Voz masculina joven, energética y dinámica |
| `zh-CN-YunyangNeural` | Joven | Profesional | Voz masculina joven, profesional y clara |
| `zh-CN-YunjianNeural` | Joven | Deportivo | Voz masculina joven, deportiva y activa |
| `zh-CN-YunxiaNeural` | Joven | Calmado | Voz masculina joven, calmada y serena |
| `zh-CN-YunfengNeural` | Maduro | Autoritario | Voz masculina madura, autoritaria y profunda |
| `zh-CN-YunhaoNeural` | Joven | Amigable | Voz masculina joven, amigable y cercana |
| `zh-CN-YunyeNeural` | Maduro | Profesional | Voz masculina madura, profesional y seria |

## ⚙️ Configuración

### Opción 1: Voz Fija (Default)

Usa siempre la misma voz (Xiaoxiao por defecto):

```env
AZURE_TTS_RANDOM_VOICE=false
```

### Opción 2: Voces Aleatorias (Recomendado)

Usa una voz diferente aleatoriamente para cada audio:

```env
AZURE_TTS_RANDOM_VOICE=true
```

**Ventajas de voces aleatorias:**
- ✅ **Mayor variedad**: Escuchas diferentes acentos y tonos
- ✅ **Mejor aprendizaje**: Te acostumbras a diferentes hablantes
- ✅ **Más natural**: Simula conversaciones reales con diferentes personas
- ✅ **Menos monotonía**: Más interesante durante el estudio

## ⚡ Control de Velocidad

Ajusta la velocidad del habla según tu nivel:

```env
# Principiantes (más lento)
AZURE_TTS_SPEED=0.8

# Normal (velocidad nativa)
AZURE_TTS_SPEED=1.0

# Avanzado (más rápido)
AZURE_TTS_SPEED=1.2

# Muy rápido (desafío)
AZURE_TTS_SPEED=1.5
```

**Recomendaciones por nivel:**
- **HSK 1-2**: `0.8` - 20% más lento para principiantes
- **HSK 3-4**: `1.0` - Velocidad normal
- **HSK 5-6**: `1.2` - 20% más rápido para avanzados

## 🎯 Configuración Recomendada

Para máximo beneficio en el aprendizaje:

```env
# Azure TTS Configuration
AZURE_TTS_KEY=tu_key_aqui
AZURE_TTS_REGION=eastus

# Voces aleatorias para variedad
AZURE_TTS_RANDOM_VOICE=true

# Velocidad según tu nivel
AZURE_TTS_SPEED=0.9  # Ajusta según necesites
```

## 📊 Ejemplos de Uso

### Ejemplo 1: Principiante con voces variadas
```env
AZURE_TTS_RANDOM_VOICE=true
AZURE_TTS_SPEED=0.8
```

### Ejemplo 2: Intermedio con voz fija
```env
AZURE_TTS_RANDOM_VOICE=false
AZURE_TTS_SPEED=1.0
```

### Ejemplo 3: Avanzado con desafío
```env
AZURE_TTS_RANDOM_VOICE=true
AZURE_TTS_SPEED=1.3
```

## 🔊 Calidad de Audio

Todas las voces son **Neural TTS** de última generación:
- ✅ Calidad de audio: 16kHz, 128kbps MP3
- ✅ Pronunciación precisa del mandarín
- ✅ Entonación natural
- ✅ Tonos correctos (fundamental para chino)

## 💡 Consejos

1. **Empieza con voces aleatorias**: Te ayudará a entender diferentes acentos
2. **Ajusta la velocidad gradualmente**: Empieza más lento y aumenta con el tiempo
3. **Prueba diferentes configuraciones**: Encuentra lo que funciona mejor para ti
4. **Regenera audio si cambias configuración**: Los archivos existentes no se modifican

## 🚀 Regenerar Audio con Nueva Configuración

Si cambias la configuración, elimina los audios existentes y regenera:

```bash
# Eliminar audios existentes
Remove-Item resources\audios\*.mp3

# Regenerar con nueva configuración
python main.py audio --engine edge --csv outputs/vocab.csv
```

O simplemente genera para nuevas entradas - los archivos existentes se conservan.
