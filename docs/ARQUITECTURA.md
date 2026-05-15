# 🏗️ Arquitectura - Plataforma Contable Web

Documentación técnica completa de la arquitectura del sistema.

---

## 📋 Tabla de Contenidos

1. [Visión General](#visión-general)
2. [Diagrama de Arquitectura](#diagrama-de-arquitectura)
3. [Componentes Principales](#componentes-principales)
4. [Flujo de Datos](#flujo-de-datos)
5. [Base de Datos](#base-de-datos)
6. [Seguridad](#seguridad)
7. [Escalabilidad](#escalabilidad)

---

## 🔷 Visión General

Plataforma Contable es una aplicación web moderna construida con:

- **Frontend:** Streamlit (Python)
- **Backend:** Supabase (PostgreSQL + Auth + Storage)
- **Lenguaje:** Python 3.9+
- **Deployment:** Railway o Render
- **Arquitectura:** Cliente-Servidor

---

## 📐 Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│                    Usuario Final                              │
│               (Navegador Web / App)                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                   HTTPS/SSL ↓
┌──────────────────────────────────────────────────────────────┐
│                      Streamlit Server                         │
│         (Railway / Render / Servidor Local)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Home.py (Landing Page)                  │   │
│  │  - Servicios                                        │   │
│  │  - Módulos                                          │   │
│  │  - Navegación                                       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Pages (Módulos)                           │   │
│  │  - Caja Menor                                       │   │
│  │  - PILA                                             │   │
│  │  - Nómina                                           │   │
│  │  - Compras DIAN                                     │   │
│  │  - Provisiones                                      │   │
│  │  - Configuración                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Core Logic (Procesadores)                   │   │
│  │  - procesador_caja_menor.py                         │   │
│  │  - procesador_pila.py                               │   │
│  │  - procesador_nómina.py                             │   │
│  │  - validadores.py                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Client Libraries                           │   │
│  │  - supabase_client.py (Conexión a BD)               │   │
│  │  - login.py (Autenticación)                         │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────────────────┘
                         │
                API REST (JSON) ↓
┌──────────────────────────────────────────────────────────────┐
│                    Supabase Backend                           │
│         (Cloud PostgreSQL + Auth + Storage)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Authentication (Supabase Auth)               │   │
│  │  - Email/Password                                   │   │
│  │  - JWT Tokens                                       │   │
│  │  - Session Management                              │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │     PostgreSQL Database                              │   │
│  │  - Usuarios (auth.users)                            │   │
│  │  - Empresas                                         │   │
│  │  - Transacciones                                    │   │
│  │  - Reportes                                         │   │
│  │  - Configuraciones                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │     Cloud Storage (Supabase Storage)                 │   │
│  │  - Archivos Excel subidos                           │   │
│  │  - Reportes generados                               │   │
│  │  - Documentos                                       │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 Componentes Principales

### 1. Frontend (Streamlit)

**Archivos:**
- `Home.py` - Landing page principal
- `app/pages/*.py` - Módulos individuales
- `.streamlit/config.toml` - Configuración UI

**Responsabilidades:**
- Interfaz de usuario
- Validación de entrada
- Visualización de datos
- Caching de datos
- Gestión de estado

### 2. Lógica de Negocio (Core)

**Archivos:**
- `core/procesadores/*.py` - Lógica de cada módulo
- `core/utils/*.py` - Funciones auxiliares

**Responsabilidades:**
- Procesamiento de archivos
- Cálculos contables
- Generación de reportes
- Validaciones de negocio

### 3. Autenticación (Auth)

**Archivos:**
- `auth/login.py` - Login con Supabase
- `auth/session.py` - Gestión de sesión

**Responsabilidades:**
- Login/Logout
- Registro de usuarios
- Token management
- Control de acceso

### 4. Base de Datos (DB)

**Archivos:**
- `db/supabase_client.py` - Cliente único
- Tablas en PostgreSQL

**Responsabilidades:**
- Conexión a Supabase
- Consultas a BD
- Transacciones
- Índices

### 5. Backend (Supabase)

**Componentes:**
- PostgreSQL Database
- JWT Authentication
- Cloud Storage
- Real-time subscriptions

---

## 🔄 Flujo de Datos

### Flujo 1: Usuario se registra

```
Usuario
   ↓
Home.py (Landing)
   ↓
Streamlit Auth Component
   ↓
supabase.auth.sign_up() → Supabase Auth
   ↓
BD: auth.users (Insert)
   ↓
Email de confirmación enviado
   ↓
Usuario accede a Home.py
```

### Flujo 2: Usuario usa Caja Menor

```
Usuario abre Caja Menor
   ↓
Sube archivo Excel
   ↓
1_💵_Caja_Menor.py recibe archivo
   ↓
Validación de formato
   ↓
procesador_caja_menor.py procesa datos
   ↓
Genera plano contable
   ↓
Guarda en BD (transacciones)
   ↓
Guarda en Storage (reporte)
   ↓
Usuario descarga resultado
```

### Flujo 3: Generar Reporte

```
Usuario solicita reporte
   ↓
pages/*.py consulta BD
   ↓
supabase_client.py ejecuta query
   ↓
BD retorna datos
   ↓
Core/utils.py procesa datos
   ↓
Streamlit visualiza (gráficos, tablas)
   ↓
Usuario puede descargar (Excel/PDF)
   ↓
Se guarda en Storage para auditoría
```

---

## 🗄️ Base de Datos

### Esquema ER

```
auth.users (Tabla de Supabase)
├── id (UUID)
├── email (VARCHAR)
├── password (hashed)
└── created_at (TIMESTAMP)

empresas
├── id (UUID) PRIMARY KEY
├── user_id (UUID) FOREIGN KEY → auth.users.id
├── nombre (VARCHAR)
├── nit (VARCHAR)
├── email (VARCHAR)
├── telefono (VARCHAR)
├── direccion (TEXT)
├── puc (TEXT) - Plan Contable
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

transacciones
├── id (UUID) PRIMARY KEY
├── empresa_id (UUID) FOREIGN KEY → empresas.id
├── fecha (DATE)
├── descripcion (TEXT)
├── monto (DECIMAL)
├── cuenta_contable (VARCHAR)
├── tipo (VARCHAR)
└── created_at (TIMESTAMP)

reportes
├── id (UUID) PRIMARY KEY
├── empresa_id (UUID) FOREIGN KEY → empresas.id
├── nombre (VARCHAR)
├── tipo (VARCHAR)
├── contenido (JSONB)
├── url_storage (VARCHAR)
└── created_at (TIMESTAMP)

configuracion
├── id (UUID) PRIMARY KEY
├── empresa_id (UUID) FOREIGN KEY → empresas.id
├── clave (VARCHAR)
├── valor (VARCHAR)
└── updated_at (TIMESTAMP)
```

### Índices

```sql
CREATE INDEX idx_empresas_user_id ON empresas(user_id);
CREATE INDEX idx_transacciones_empresa_id ON transacciones(empresa_id);
CREATE INDEX idx_transacciones_fecha ON transacciones(fecha);
CREATE INDEX idx_reportes_empresa_id ON reportes(empresa_id);
CREATE INDEX idx_configuracion_empresa_id ON configuracion(empresa_id);
```

---

## 🔐 Seguridad

### Capas de Seguridad

```
┌─────────────────────────────────────────┐
│  1. HTTPS/SSL (Transporte)              │
│     - Cifrado en tránsito                │
│     - Certificados verificados          │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  2. Autenticación (JWT Tokens)          │
│     - Login email/password              │
│     - Tokens con expiración             │
│     - Refresh tokens                    │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  3. Autorización (RLS)                  │
│     - Row Level Security en BD          │
│     - Users solo ven sus datos          │
│     - Multi-tenant isolation            │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  4. Encriptación (BD)                   │
│     - Datos sensibles encriptados       │
│     - Passwords hasheados               │
│     - Backups encriptados               │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  5. Validación (Input)                  │
│     - Validación en frontend            │
│     - Validación en backend             │
│     - SQL injection prevention          │
│     - XSS protection                    │
└─────────────────────────────────────────┘
```

### Políticas RLS (Row Level Security)

```sql
-- Usuarios solo ven sus propias empresas
CREATE POLICY "Users can only see their own companies"
ON empresas FOR SELECT
USING (auth.uid() = user_id);

-- Usuarios solo ven sus propias transacciones
CREATE POLICY "Users can only see their transactions"
ON transacciones FOR SELECT
USING (
  empresa_id IN (
    SELECT id FROM empresas WHERE user_id = auth.uid()
  )
);
```

---

## 📈 Escalabilidad

### Horizontal Scaling

```
Usuarios crecen → 
   ↓
Streamlit multi-instancia en Railway
   ↓
Load Balancer distribuye tráfico
   ↓
Supabase auto-escala automáticamente
```

### Vertical Scaling

```
Si rendimiento baja →
   ↓
Upgrade plan Railway
   ↓
Más CPU/RAM
   ↓
Connection pooling mejorado
   ↓
Caché distribuida
```

### Optimizaciones

```
1. Caching
   - @st.cache_data (datos)
   - @st.cache_resource (recursos)
   - Redis (futuro)

2. Indexación
   - Índices en BD
   - Índices en b��squedas

3. Paginación
   - Limitar resultados
   - Lazy loading

4. CDN
   - Archivos estáticos
   - Assets

5. Compresión
   - Gzip respuestas
   - Minify assets
```

---

## 🔄 Ciclo de Vida de una Solicitud

```
1. Usuario hace clic en botón
   ↓
2. Streamlit captura evento
   ↓
3. Validación frontend
   ↓
4. Llamada a API Supabase
   ↓
5. Supabase autentica (JWT)
   ↓
6. BD ejecuta query con RLS
   ↓
7. Resultado retorna
   ↓
8. Python procesa datos
   ↓
9. Streamlit renderiza UI
   ↓
10. Usuario ve resultado
```

---

## 📊 Monitoreo y Logs

### Logs Disponibles

```
1. Streamlit Logs
   - En local: stdout
   - En Railway: railroad logs

2. Supabase Logs
   - Queries ejecutadas
   - Errores de autenticación
   - Storage access

3. Application Logs
   - Errores de aplicación
   - Debug info
   - Performance metrics
```

---

## 🚀 Despliegue

### Proceso de Despliegue

```
Código en GitHub
   ↓
Push a main
   ↓
Railway webhook activa
   ↓
Build imagen Docker
   ↓
Instala dependencias
   ↓
Ejecuta Health Check
   ↓
Deploy a contenedor
   ↓
Tráfico redirigido
   ↓
App en vivo
```

---

## 📞 Contacto

¿Preguntas sobre arquitectura?
- 📧 fabianehg@gmail.com
- 🐛 [GitHub Issues](https://github.com/fabianehg-ui/plataforma-contable/issues)

---

**Última actualización:** 2026-05-15

[⬆ Volver a Documentación](./README.md)
