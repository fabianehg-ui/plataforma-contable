# Plataforma Contable Web

Versión web de la aplicación Generador de Plano Contable.
Multi-empresa, multi-usuario, con login seguro.

## 🧱 Arquitectura

- **Frontend + Backend:** Streamlit (Python)
- **Autenticación:** Supabase Auth (email + contraseña)
- **Base de datos:** Supabase PostgreSQL
- **Almacenamiento de archivos:** Supabase Storage
- **Hosting:** Railway (recomendado) o Render

## 📂 Estructura

```
plataforma_web/
├── Home.py                     # Página de login y bienvenida
├── app/
│   └── pages/
│       ├── 1_💵_Caja_Menor.py   # Módulo migrado (funciona end-to-end)
│       ├── 2_🛒_Compras_DIAN.py (placeholder)
│       ├── 3_💼_Nómina.py       (placeholder)
│       ├── 4_📝_Provisiones.py  (placeholder)
│       ├── 5_📎_PILA.py         (placeholder)
│       └── 6_⚙️_Configuración.py
│
├── core/                       # Lógica de negocio (portada del .exe)
│   ├── procesadores/
│   │   └── procesador_caja_menor.py  # Adaptado para archivos en memoria
│   └── utils/
│       └── configuracion_web.py      # Reemplaza configuracion.py
│
├── auth/
│   └── login.py                # Flujo de login contra Supabase
│
├── db/
│   └── supabase_client.py      # Cliente único de Supabase
│
├── data/
│   ├── cuentas.xlsx            # PUC de referencia (se sube desde config)
│   └── mapeos.xlsx             # Reglas de mapeo
│
├── .streamlit/
│   ├── config.toml             # Configuración de Streamlit
│   └── secrets.toml.example    # Plantilla de credenciales
│
├── requirements.txt
├── Procfile                    # Para Railway/Render
├── runtime.txt
├── .gitignore
├── DEPLOY.md                   # Guía de despliegue paso a paso
└── README.md
```

## 🚀 Instalación rápida (local)

```bash
# 1. Clonar / descomprimir
cd plataforma_web

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate     # Linux/Mac
# venv\Scripts\activate       # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edita secrets.toml con tus credenciales de Supabase

# 5. Arrancar
streamlit run Home.py
```

## 🌐 Despliegue en la web

Ver **DEPLOY.md** para la guía completa paso a paso.

Resumen:
1. Crear cuenta en Supabase (gratis) y configurar base de datos
2. Crear cuenta en Railway y conectar el repo de GitHub
3. Configurar variables de entorno
4. Conectar dominio propio

Costo aproximado: $0–10 USD/mes.

## 📦 Módulos

| Módulo | Estado | Descripción |
|---|---|---|
| Caja Menor | ✅ Funcional | Sube Excel de egresos → genera plano contable |
| PILA | ✅ Funcional | Sube PDF de planilla → extrae empleados y totales, descarga Excel |
| Compras DIAN | ⏳ Pendiente | Placeholder listo, lógica por migrar |
| Nómina | ⏳ Pendiente | Placeholder listo |
| Provisiones | ⏳ Pendiente | Placeholder listo |

Cada módulo se migra copiando el procesador del .exe actual a `core/procesadores/`
y creando una página en `app/pages/` que sigue el patrón de Caja Menor.
