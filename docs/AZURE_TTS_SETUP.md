# Configuración de Azure TTS (Microsoft Edge TTS)

## ¿Por qué Azure TTS?

Microsoft cambió su API de Edge TTS y ahora requiere autenticación. La librería `edge-tts` gratuita ya no funciona de manera confiable. Azure Cognitive Services TTS es la API oficial de Microsoft y ofrece:

- ✅ **Alta calidad de audio** (mejor que Google TTS)
- ✅ **Voces naturales** con IA neural
- ✅ **Tier gratuito generoso**: 500,000 caracteres/mes gratis
- ✅ **API oficial y confiable**

## Paso 1: Crear Cuenta Azure (Gratis)

1. Ve a [portal.azure.com](https://portal.azure.com)
2. Crea una cuenta gratuita (requiere tarjeta de crédito pero NO te cobran)
3. Obtienes $200 USD de crédito gratis por 30 días
4. El tier gratuito de Speech Services es permanente

## Paso 2: Crear Recurso de Speech Services

1. En Azure Portal, busca "Speech Services"
2. Click en "Create" o "Crear"
3. Completa el formulario:
   - **Subscription**: Tu suscripción
   - **Resource Group**: Crea uno nuevo (ej: "chinosrs-resources")
   - **Region**: Selecciona una región cercana (ej: "East US")
   - **Name**: Nombre único (ej: "chinosrs-tts")
   - **Pricing Tier**: Selecciona **"Free F0"** (500K caracteres/mes gratis)
4. Click en "Review + Create" y luego "Create"

## Paso 3: Obtener API Key

1. Una vez creado el recurso, ve a "Keys and Endpoint"
2. Copia **KEY 1** (o KEY 2, cualquiera funciona)
3. Anota la **REGION** (ej: "eastus")

## Paso 4: Configurar en ChinoSRS

1. Abre tu archivo `.env` en el proyecto
2. Agrega las siguientes líneas:

```env
# Azure TTS Configuration
AZURE_TTS_KEY=tu_key_aqui_pegada
AZURE_TTS_REGION=eastus
```

3. Reemplaza `tu_key_aqui_pegada` con tu KEY 1
4. Reemplaza `eastus` con tu región si es diferente

## Paso 5: Usar Azure TTS

Ahora puedes usar Edge TTS (que automáticamente usará Azure):

```bash
# Usar Azure TTS (automático cuando usas --engine edge)
python main.py audio --engine edge --csv outputs/vocab.csv

# O explícitamente con --engine azure
python main.py audio --engine azure --csv outputs/vocab.csv
```

## Tier Gratuito - Límites

- **500,000 caracteres/mes** gratis
- Aproximadamente **10,000-15,000 palabras** chinas
- Suficiente para generar audio de **2,500-3,000 entradas** de vocabulario al mes
- Si necesitas más, el costo es muy bajo: $1 USD por 1 millón de caracteres

### Rate Limiting

Azure TTS tiene límites de velocidad:
- **Tier gratuito**: 20 solicitudes por minuto
- **Tier de pago**: 200 solicitudes por minuto

**Política de Reintentos Automática:**
- ✅ Hasta 5 reintentos automáticos
- ✅ Backoff exponencial (1s, 2s, 4s, 8s, 16s)
- ✅ Delay de 150ms entre solicitudes exitosas
- ✅ Máximo 30 segundos de espera por reintento

## Ejemplo de Uso

```bash
# Configurar .env
AZURE_TTS_KEY=a1b2c3d4e5f6g7h8i9j0
AZURE_TTS_REGION=eastus

# Generar audio
python main.py audio --engine edge --csv outputs/hsk1.csv
```

## Solución de Problemas

### Error: "Azure TTS requires AZURE_TTS_KEY"
- Verifica que tu archivo `.env` tenga la key configurada
- Asegúrate de que el archivo `.env` esté en la raíz del proyecto

### Error: HTTP 401 Unauthorized
- Tu API key es inválida o expiró
- Verifica que copiaste la key completa
- Genera una nueva key en Azure Portal

### Error: HTTP 403 Forbidden
- Tu región está mal configurada
- Verifica que `AZURE_TTS_REGION` coincida con la región de tu recurso

## Alternativa: Google TTS (Sin Configuración)

Si no quieres configurar Azure, puedes usar Google TTS que funciona sin API key:

```bash
python main.py audio --engine gtts --csv outputs/vocab.csv
```

**Ventajas de Google TTS:**
- ✅ Sin configuración
- ✅ Gratis e ilimitado
- ✅ Funciona inmediatamente

**Desventajas:**
- ❌ Calidad de audio inferior
- ❌ Voz menos natural
- ❌ Puede ser más lento

## Recursos

- [Azure Portal](https://portal.azure.com)
- [Documentación Azure Speech Services](https://docs.microsoft.com/azure/cognitive-services/speech-service/)
- [Precios Azure TTS](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/)
