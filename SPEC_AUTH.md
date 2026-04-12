# SPEC_AUTH.md — Sistema de Usuarios y Autenticación

## 1. Resumen

Añadir autenticación por usuario al sistema. Antes de logearse, solo se ve la pestaña Inicio con formularios de login/registro. Tras el login el servidor devuelve las preferencias guardadas del usuario (API Key Ollama + modelo). Se elimina la autenticación HTTP Basic Auth de Nginx (`racef1`/`100fuchupabien`).

## 2. Persistencia (Backend — SQLite)

Librería: `modernc.org/sqlite` (pure-Go, sin CGO).  
Fichero: `<DataDir>/rf2_users.db` (excluido de `cleanDataDir`).

### Tablas

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    is_verified   INTEGER NOT NULL DEFAULT 0,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    ollama_api_key TEXT   NOT NULL DEFAULT '',
    ollama_model   TEXT   NOT NULL DEFAULT '',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verification_codes (
    email      TEXT    NOT NULL,
    code       TEXT    NOT NULL,
    expires_at DATETIME NOT NULL
);
```

### Admin inicial

Al arrancar, si no existe `username = 'Mulder_admin'`, se inserta con:
- password hash: bcrypt de `100fuchupabien31416`
- `is_verified = 1`, `is_admin = 1`

## 3. API Endpoints

### Públicos (sin JWT)

| Método | Ruta | Body | Respuesta |
|--------|------|------|-----------|
| POST | `/api/auth/register` | `{username, email, password}` | 201 `{message}` |
| POST | `/api/auth/verify` | `{email, code}` | 200 `{message}` |
| POST | `/api/auth/login` | `{username, password}` | 200 `{token, username, ollama_api_key, ollama_model}` |
| GET | `/api/health` | — | 200 (sin cambios) |

### Protegidos (requieren `Authorization: Bearer <JWT>`)

| Método | Ruta | Body | Respuesta |
|--------|------|------|-----------|
| PUT | `/api/auth/config` | `{ollama_api_key, ollama_model}` | 200 `{message}` |
| POST | `/api/analyze_preparsed` | (sin cambios) | (sin cambios) |
| POST | `/api/analyze_preparsed_stream` | (sin cambios) | (sin cambios) |
| GET | `/api/models` | (sin cambios) | (sin cambios) |
| GET | `/api/tracks` | (sin cambios) | (sin cambios) |

### JWT

- Librería: `github.com/golang-jwt/jwt/v5`
- Secreto: variable de entorno `RF2_JWT_SECRET` (fallback a UUID generado al arrancar — no persiste entre reinicios, lo cual fuerza re-login).
- Expiración: 24 horas.
- Claims: `{user_id, username, is_admin, exp}`.

## 4. Verificación por email

El servidor genera un código de 6 dígitos numéricos aleatorios, lo guarda en `verification_codes` con expiración de 15 minutos, y lo envía al email proporcionado durante el registro.

Librería SMTP: `net/smtp` estándar de Go.  
Variables de entorno para SMTP:
- `RF2_SMTP_HOST` (ej. `smtp.gmail.com`)
- `RF2_SMTP_PORT` (ej. `587`)
- `RF2_SMTP_USER`
- `RF2_SMTP_PASS`
- `RF2_SMTP_FROM` (ej. `noreply@car-setup.com`)

Fallback: cuando no hay config SMTP, el código se devuelve en la respuesta del registro (solo para entorno de desarrollo).

## 5. Frontend — Flujo de autenticación

### Estado Zustand (useAppStore)

Nuevos campos:
- `jwt: string | null`
- `authUsername: string | null`
- `isLoggedIn: boolean` (derivado: `jwt !== null`)

Al hacer login exitoso:
1. Guardar `jwt` y `authUsername` en el store.
2. Rellenar `ollamaApiKey` y `selectedModel` con los valores devueltos por el servidor.
3. Inyectar `Authorization: Bearer <jwt>` en todas las llamadas Axios.

Al cerrar sesión:
1. Limpiar `jwt`, `authUsername`.
2. Volver al estado no autenticado.

### Visibilidad de pestañas (`_layout.tsx`)

- `isLoggedIn === false`: solo se renderiza `<Tabs.Screen name="index">`. Las demás llevan `href: null`.
- `isLoggedIn === true`: todas las pestañas visibles.

### Pantalla Inicio (`index.tsx`)

**No autenticado:** muestra dos formularios alternables:
- **Login**: campos usuario y contraseña + botón "Entrar".
- **Registro**: campos nombre de usuario, email, contraseña + botón "Registrarse".
  - Tras registrarse muestra paso 2: campo para código de verificación + botón "Verificar".
- Información de uso de la aplicación debajo.

**Autenticado:** muestra bienvenida, estado del servidor, instrucciones actualizadas del flujo completo (Datos → Análisis → Telemetría) y botón "Cerrar sesión".

### Auto-guardado de configuración Ollama

Cada vez que se lance un análisis, el frontend llama a `PUT /api/auth/config` con la API Key y modelo actuales para persistirlos en el servidor.

## 6. Sesiones comprimidas (frontend)

### Guardado
- Serializar el JSON de sesión.
- Comprimir con `pako` (gzip) — librería JS ligera ya compatible con navegador.
- Descargar como archivo `.rf2session` (blob comprimido gzip).
- Nombre por defecto: `<ld-basename>_<YYYY-MM-DD>.rf2session`.

### Carga
- Leer el archivo `.rf2session`.
- Descomprimir con `pako.ungzip`.
- Parsear JSON resultante y restaurar el estado.
- Mantener retrocompatibilidad: si el archivo empieza con `{` (JSON crudo), cargarlo directamente sin descomprimir (para sesiones antiguas guardadas como `.json`).

### Parámetros fijados
- La carga y guardado de parámetros fijados es 100% cliente (ya está así). Sin cambios.

## 7. Eliminación de autenticación legacy

- **Backend**: no hay lógica de Basic Auth en Go (era en Nginx). Sin cambios en código Go.
- **Nginx** (producción): eliminar `auth_basic` y `auth_basic_user_file` de los bloques `location`.
- **docs/deployment.md**: eliminar sección "HTTP Basic Auth" y actualizar comandos de verificación para no incluir `-u racef1:100fuchupabien`.
- **scripts/deploy.ps1**: eliminar flag `-u racef1:100fuchupabien` de las verificaciones curl.

## 8. Ficheros afectados

### Backend (Go)
- `services/backend_go/go.mod` — añadir `modernc.org/sqlite`, `golang-jwt/jwt/v5`
- `services/backend_go/internal/auth/db.go` — SQLite init, migrations, admin seed
- `services/backend_go/internal/auth/handlers.go` — Register, Verify, Login, UpdateConfig
- `services/backend_go/internal/auth/jwt.go` — GenerateToken, ParseToken
- `services/backend_go/internal/auth/email.go` — SendVerificationCode (SMTP o fallback)
- `services/backend_go/internal/middleware/auth.go` — JWTRequired middleware
- `services/backend_go/internal/config/config.go` — nuevos env vars (JWT_SECRET, SMTP_*)
- `services/backend_go/cmd/server/main.go` — init DB, seed admin, wiring rutas auth, proteger rutas

### Frontend (Expo)
- `apps/expo_app/src/store/useAppStore.ts` — campos jwt, authUsername, setters
- `apps/expo_app/src/api/client.ts` — inyección Bearer token, nuevas funciones auth
- `apps/expo_app/app/(tabs)/_layout.tsx` — guard de pestañas
- `apps/expo_app/app/(tabs)/index.tsx` — rediseño completo (login/register/home)
- `apps/expo_app/app/(tabs)/upload.tsx` — compresión/descompresión sesión
- `apps/expo_app/app/(tabs)/analysis.tsx` — auto-guardar config tras análisis
- `apps/expo_app/package.json` — añadir `pako` + `@types/pako`

### Docs
- `docs/deployment.md` — eliminar Basic Auth, actualizar verificación
- `scripts/deploy.ps1` — eliminar -u flag
- `AGENTS.md` — actualizar File Map y Key Implementation Patterns
- `docs/openapi.yaml` — añadir rutas /api/auth/*
