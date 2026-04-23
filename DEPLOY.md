# 🚀 Guía de Despliegue

Esta guía te lleva desde el código en tu PC hasta una URL pública funcionando con tu dominio propio.

**Tiempo estimado:** 60-90 minutos la primera vez.
**Costo:** $0 durante el desarrollo. $5-10 USD/mes en producción con dominio.

---

## 📋 Checklist general

1. ✅ Crear cuenta en Supabase y configurar la base de datos
2. ✅ Probar la aplicación localmente
3. ✅ Subir el código a GitHub
4. ✅ Crear cuenta en Railway y desplegar
5. ✅ Comprar dominio y conectarlo

---

## 1️⃣ Configurar Supabase

Supabase es tu backend: base de datos + autenticación + almacenamiento.

### 1.1 Crear proyecto

1. Ve a [supabase.com](https://supabase.com) y crea cuenta (gratis).
2. Click en **"New project"**.
3. Configuración:
   - **Name:** `plataforma-contable`
   - **Database Password:** genera una fuerte y guárdala
   - **Region:** elige la más cercana (ej. South America - São Paulo)
   - **Plan:** Free
4. Espera 1-2 minutos mientras se crea el proyecto.

### 1.2 Ejecutar el schema SQL

1. En el panel de Supabase, ve a **SQL Editor** (ícono `</>` en el menú lateral).
2. Click en **"New query"**.
3. Abre el archivo `db/schema.sql` de este proyecto y copia TODO el contenido.
4. Pégalo en el editor y click en **"Run"** (o Ctrl+Enter).
5. Verifica que no haya errores. Deberías ver "Success. No rows returned."

### 1.3 Crear tu primer usuario

1. En el panel, ve a **Authentication → Users**.
2. Click en **"Add user" → "Create new user"**.
3. Ingresa tu email y una contraseña (mínimo 8 caracteres).
4. **IMPORTANTE:** Marca la casilla **"Auto Confirm User"** para que no pida confirmar por correo.
5. Click en **"Create user"**.

### 1.4 Crear tu primera empresa (seed)

1. Ve otra vez a **SQL Editor → New query**.
2. Pega esto (reemplaza tu email):
   ```sql
   do $$
   declare mi_id uuid;
   begin
       select id into mi_id from auth.users where email = 'TU-EMAIL@example.com';
       if mi_id is not null then
           perform public.crear_empresa_con_admin('901.630.218-1', 'OASIS URBANOS S.A.S');
           perform public.crear_empresa_con_admin('900.000.000-0', 'GRUPO DE LOLITA');
       end if;
   end $$;
   ```
3. Click en **"Run"**.

### 1.5 Obtener las credenciales

1. Ve a **Project Settings → API** (ícono de engranaje abajo).
2. Anota estos dos valores, los vas a necesitar:
   - **Project URL** (algo como `https://xxxxx.supabase.co`)
   - **anon / public key** (una cadena JWT larga)
   - **service_role key** (otra cadena JWT, mantenla SECRETA)

---

## 2️⃣ Probar localmente

### 2.1 Instalar Python y dependencias

```bash
# Entra al directorio del proyecto
cd plataforma_web

# Crea entorno virtual
python -m venv venv

# Activa el entorno
# En Windows:
venv\Scripts\activate
# En Mac/Linux:
source venv/bin/activate

# Instala dependencias
pip install -r requirements.txt
```

### 2.2 Configurar credenciales

```bash
# Copia la plantilla de secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edita el archivo con tus credenciales de Supabase
# (el paso 1.5 de arriba)
```

Rellena `.streamlit/secrets.toml` con los valores de tu proyecto.

### 2.3 Arrancar la app

```bash
streamlit run Home.py
```

Se abrirá `http://localhost:8501`. Inicia sesión con el usuario que creaste en el paso 1.3.

Deberías ver:
- El formulario de login ✅
- Tras loguearte, el dashboard con tus dos empresas en el selector del sidebar ✅
- En el menú lateral, el módulo "💵 Caja Menor" funcional ✅

---

## 3️⃣ Subir el código a GitHub

### 3.1 Crear el repo

1. Ve a [github.com](https://github.com) y crea cuenta si no tienes.
2. Click en **"New repository"**.
3. Configuración:
   - **Name:** `plataforma-contable`
   - **Visibility:** Private (recomendado para código privado)
4. Crear.

### 3.2 Subir el código

```bash
cd plataforma_web

git init
git add .
git commit -m "Versión inicial plataforma web"

git branch -M main
git remote add origin https://github.com/TU-USUARIO/plataforma-contable.git
git push -u origin main
```

**⚠️ MUY IMPORTANTE:** Verifica que `.streamlit/secrets.toml` NO se haya subido. Debería estar bloqueado por `.gitignore`. Si se subió, bórralo del repo y regenera tus keys de Supabase inmediatamente.

---

## 4️⃣ Desplegar en Railway

Railway es el hosting. Tier gratuito al inicio, luego ~$5 USD/mes.

### 4.1 Crear cuenta

1. Ve a [railway.app](https://railway.app) y crea cuenta con GitHub.
2. Te dan $5 USD de crédito gratis para empezar.

### 4.2 Desplegar desde el repo

1. En Railway, click en **"New Project" → "Deploy from GitHub repo"**.
2. Selecciona tu repo `plataforma-contable`.
3. Railway detecta que es Python y empieza a construir.

### 4.3 Configurar el comando de inicio

Railway puede no adivinar el comando. Configúralo así:

1. En tu servicio, ve a **Settings → Deploy**.
2. En **"Custom Start Command"** pon:
   ```
   streamlit run Home.py --server.port $PORT --server.address 0.0.0.0
   ```

### 4.4 Configurar variables de entorno

Streamlit lee `st.secrets` desde variables de entorno en producción.

1. En Railway, ve a tu servicio → **Variables**.
2. Agrega estas:
   ```
   supabase__url = https://TU-PROYECTO.supabase.co
   supabase__anon_key = tu-anon-key
   supabase__service_key = tu-service-key
   app__auth_mode = supabase
   app__session_timeout_minutes = 60
   ```
   Nota los **doble guiones bajos** (`__`) que representan las secciones TOML.

### 4.5 Generar dominio temporal

1. En Railway, ve a **Settings → Networking → Public Networking**.
2. Click en **"Generate Domain"**.
3. Te da una URL tipo `plataforma-contable.up.railway.app`.
4. Ábrela en el navegador y confirma que todo funciona.

---

## 5️⃣ Conectar tu dominio propio

### 5.1 Comprar el dominio

**Recomendación:** Cloudflare Registrar (vende al precio de costo). Alternativas: Namecheap, Porkbun.

Ejemplo: `micontabilidad.com` cuesta ~$10 USD/año.

### 5.2 Conectar en Railway

1. En Railway → **Settings → Networking → Custom Domain**.
2. Ingresa tu dominio, ej: `app.micontabilidad.com`.
3. Railway te da un registro CNAME para crear, algo como:
   ```
   app.micontabilidad.com  CNAME  xxx.up.railway.app
   ```

### 5.3 Crear el CNAME en tu proveedor

**Si usas Cloudflare:**
1. Ve a tu dominio en Cloudflare → **DNS → Records**.
2. Click en **"Add record"**.
3. Tipo: `CNAME`, Name: `app`, Target: `xxx.up.railway.app`.
4. **Proxy status:** DNS only (nube gris, NO naranja) al menos al inicio.
5. Save.

Espera 5-10 minutos y verifica. Railway genera el SSL automáticamente.

---

## 6️⃣ Configurar Supabase para tu dominio

Cuando el dominio ya funciona, ajusta Supabase para aceptarlo:

1. En Supabase → **Authentication → URL Configuration**.
2. En **"Site URL"** pon: `https://app.micontabilidad.com`.
3. En **"Redirect URLs"** agrega la misma.
4. Save.

---

## ✅ Verificación final

Abre `https://app.micontabilidad.com` y:

- [ ] Ves el formulario de login
- [ ] Te logueas correctamente
- [ ] Ves tus empresas en el sidebar
- [ ] El módulo Caja Menor procesa un Excel de prueba
- [ ] La descarga del plano funciona

---

## 💰 Costos mensuales estimados

| Servicio | Uso | Costo |
|---|---|---|
| Supabase Free | < 500 MB DB, < 1 GB storage | $0 |
| Railway Hobby | 1 servicio, tráfico bajo | $5 |
| Dominio (prorrateado) | $10/año | $0.85 |
| **TOTAL** | | **~$6 USD/mes** |

Si la app crece:
- Supabase Pro: +$25/mes (cuando pases de 500 MB)
- Railway con más recursos: $5-20/mes según tráfico

---

## 🆘 Problemas comunes

**"No such file or directory: requirements.txt"**
→ Asegúrate de que en Railway el root directory esté en la raíz del repo.

**"ModuleNotFoundError" al iniciar**
→ Revisa `requirements.txt`, agrega lo que falte, y haz push a GitHub.

**"Cannot connect to Supabase"**
→ Revisa que las variables de entorno estén bien escritas con doble guión bajo.

**"RLS policy violation" al insertar**
→ El usuario no pertenece a la empresa o no tiene rol suficiente. Revisa la tabla `usuario_empresa`.

**La app se duerme y tarda en arrancar**
→ Railway tier gratuito tiene cold starts. Sube al plan Hobby ($5/mes) para eliminar esto.
