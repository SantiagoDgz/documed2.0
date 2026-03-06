# DocuMed 2.0

Aplicacion web de expedientes medicos digitales con backend en Python, base de datos SQLite, frontend HTML/CSS/JavaScript e integracion de funciones de apoyo con IA basada en reglas clinicas iniciales.

## 1) Estructura del proyecto

```text
documed2.0/
|-- app.py
|-- requirements.txt
|-- .gitignore
|-- database/
|   |-- schema.sql
|-- knowledge/
|   |-- triage_red_flags.md
|   |-- chronic_followup.md
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- register.html
|   |-- patients.html
|   |-- patient_detail.html
|   |-- edit_patient.html
|   |-- history.html
|   |-- ai_panel.html
|   |-- laboratories.html
|   |-- prescriptions.html
|-- static/
|   |-- css/
|   |   |-- styles.css
|   |-- js/
|       |-- app.js
```

## 2) Backend con Python

`app.py` se encarga de:

- Iniciar el servidor web con Flask.
- Conectar con la base de datos SQLite.
- Recibir informacion del formulario medico.
- Guardar, editar y eliminar pacientes.
- Enviar datos a las plantillas HTML para mostrarlos en pantalla.
- Ejecutar funciones de apoyo de IA para resumen, riesgo y seguimiento.

## 3) Base de datos de pacientes

La tabla `patients` incluye:

- `id` (identificador del paciente)
- `name`
- `age`
- `diagnosis`
- `treatment`
- `medical_notes`
- `consultation_date`
- `created_at`
- `updated_at`

## 4) Paginas HTML implementadas

- `index.html`: panel principal del medico, descripcion del sistema y accesos rapidos.
- `register.html`: formulario de registro de pacientes.
- `patients.html`: lista de pacientes en tabla con acciones de ver, editar y eliminar.
- `patient_detail.html`: expediente completo del paciente.
- `edit_patient.html`: edicion de expediente.
- `history.html`: historial medico cronologico.
- `ai_panel.html`: panel de inteligencia artificial con insights clinicos.
- `laboratories.html`: registro de laboratorios y chat IA para resumen de analisis.
- `prescriptions.html`: area de elaboracion y consulta de recetas medicas.

## 5) Estilo visual (CSS)

Se aplico la paleta solicitada:

- Fondo principal: `#05070F`
- Paneles: `#0A0F1E`
- Texto secundario: `#AEB4BC`
- Texto principal: `#E6E8EC`
- Interactivos: `#2FC6FF`
- Hover: `#66E0FF`
- Destacados: `#1A9CFF`

Incluye diseno responsivo para escritorio y movil.

## 6) Interactividad con JavaScript

`static/js/app.js` implementa:

- Validacion de campos obligatorios en formularios.
- Mensaje al guardar pacientes.
- Confirmacion antes de eliminar registros.
- Filtro rapido por nombre o diagnostico.
- Ordenamiento de la tabla por nombre, edad y fecha.

## 7) Integracion IA (fase inicial)

En `app.py` se incluyen funciones para:

- Resumir notas medicas largas.
- Detectar riesgo basico por palabras clave y edad.
- Generar recordatorios de seguimiento segun ultima consulta.

El panel IA usa resumen local por defecto para ahorrar consumo de API.
Si deseas usar Grok en tiempo real, usa el boton `Reanalizar con IA` en `ai_panel`.

Al reanalizar, el sistema usa cache por paciente en SQLite:

- Si el contenido medico no cambio, reutiliza el resumen guardado (sin nueva llamada).
- Si cambian `diagnosis`, `treatment` o `medical_notes`, se invalida el cache automaticamente.
- El panel muestra metricas de ejecucion: nuevos, cache y fallback local.

Tambien incluye un chat IA clinico para personal medico:

- Permite consultas medicas orientativas y seguimiento.
- Puede usar contexto de un paciente seleccionado para estimar riesgo.
- No entrega diagnostico definitivo ni recetas/prescripciones.
- Responde con enfoque en riesgo, sugerencias y alertas clinicas.

Nuevos modulos clinicos:

- Laboratorios:
- Registro de estudios (resultado, unidades, rango, fecha, notas).
- Chat IA de laboratorio para resumen orientativo y riesgo sugerido.
- Fallback local cuando la IA externa no responde.
- Catalogo de parametros de laboratorio cargado segun formato clinico:
- Hematologia, Inmunologia, Bioquimica, Bacteriologia,
  Microbiologia, Uroanalisis, Parasitologia, Baciloscopia y Otros.
- Soporta opcion "Otro" para estudios fuera del catalogo.

- Recetas:
- Registro estructurado de prescripciones por paciente.
- Campos de medicamento, dosis, frecuencia, duracion e indicaciones.

El chat integra una base de conocimiento local (RAG simple):

- Lee archivos `.md` y `.txt` dentro de `knowledge/`.
- Recupera fragmentos relevantes segun la pregunta y contexto del paciente.
- Usa esas referencias para enriquecer respuesta IA y fallback local.
- Muestra en interfaz las referencias usadas en la ultima respuesta.

Para ampliar el conocimiento medico del sistema, agrega nuevas guias a `knowledge/`.
Recomendado: protocolos institucionales, red flags por especialidad y rutas de referencia.

Adicionalmente, existe un catalogo estructurado de enfermedades y severidad en:

- `knowledge/disease_risk_catalog.txt`

Formato por linea:

```text
termino|alto|nota opcional
termino|medio|nota opcional
```

El motor de riesgo usa este catalogo para reconocer mas patologias y ajustar el nivel
de riesgo automaticamente cuando detecta terminos clinicos relevantes.

Regla actual de clasificacion de riesgo:

- El riesgo se calcula en modo combinado: `diagnosis` + contexto clinico (`medical_notes`, `treatment`).
- Tambien considera senales de descompensacion y edad para priorizacion clinica.

Esto permite evolucionar hacia modelos de IA mas avanzados en siguientes iteraciones.

## 8) Flujo general

1. El medico abre la aplicacion.
2. El servidor Python carga la pagina principal.
3. Registra pacientes o consulta expedientes.
4. Los datos se guardan en SQLite.
5. Python procesa informacion clinica.
6. JavaScript mejora la experiencia en frontend.
7. El panel IA genera apoyo para seguimiento y priorizacion.

## 9) Ejecucion local

### Requisitos

- Python 3.10+

### Pasos

1. Crear y activar entorno virtual.
2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Configurar API key de Grok:

```bash
copy .env.example .env
```

Luego edita `.env` y coloca tu clave real en `GROK_API_KEY`.

Opcional: puedes definir el modelo de Grok en `.env`:

```env
GROK_MODEL=grok-3-mini
```

4. Ejecutar servidor:

```bash
python app.py
```

5. Abrir en navegador:

```text
http://127.0.0.1:5000
```

## 10) Despliegue en Render (produccion)

Este proyecto incluye configuracion para Render en `render.yaml`.

### Opcion A: despliegue automatico con `render.yaml`

1. Sube cambios a GitHub.
2. En Render, crea un nuevo servicio web conectado a este repositorio.
3. Render detectara `render.yaml` y configurara:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`

4. En variables de entorno de Render configura al menos:

```text
GROK_API_KEY=tu_api_key_real
```

`SECRET_KEY` se genera automaticamente por `render.yaml`.

### Opcion B: configuracion manual en Render

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Variables:
- `SECRET_KEY`: valor seguro
- `GROK_API_KEY`: tu clave
- `GROK_MODEL`: `grok-3-mini` (opcional)
- `GROK_PROVIDER`: `auto` (opcional)

### Notas importantes de datos

- En este proyecto se usa SQLite local (`database/patients.db`).
- En hosting tipo Render (disco efimero), la data puede perderse al redeploy/restart.
- Para persistencia real en produccion, migra a PostgreSQL administrado.

## 11) Objetivo del sistema

DocuMed 2.0 busca:

- Organizar expedientes medicos digitales.
- Ahorrar tiempo operativo al medico.
- Reducir errores administrativos.
- Facilitar acceso a informacion clinica.
- Apoyar decisiones medicas con tecnologia.
- Reducir uso de papel y favorecer sustentabilidad.

