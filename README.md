# 🏢 Plataforma Contable Web

Versión web de la aplicación **Generador de Plano Contable**.
Multi-empresa, multi-usuario, con login seguro y gestión centralizada en la nube.

---

## 🧱 Arquitectura

- **Frontend + Backend:** Streamlit (Python)
- **Autenticación:** Supabase Auth (email + contraseña)
- **Base de datos:** Supabase PostgreSQL
- **Almacenamiento de archivos:** Supabase Storage
- **Hosting:** Railway (recomendado) o Render
- **Composición de código:** 98.5% Python, 1.5% Otros

---

## 📂 Estructura del Proyecto

```
plataforma-contable/
├── Home.py                          # Página de login y bienvenida
├── app/
│   └── pages/
│       ├── 1_💵_Caja_Menor.py       # ✅ Módulo migrado (funciona end-to-end)
│       ├── 2_🛒_Compras_DIAN.py     # ⏳ Placeholder
│       ├── 3_💼_Nómina.py           # ⏳ Placeholder
│       ├── 4_📝_Provisiones.py      # ⏳ Placeholder
│       ├── 5_📎_PILA.py             # ✅ Funcional
│       └── 6_⚙️_Configuración.py    # ⚙️ Configuración general
│
├── core/                            # Lógica de negocio (portada del .exe)
│   ├── procesadores/
│   │   └── procesador_caja_menor.py # Adaptado para archivos en memoria
│   └── utils/
│       └── configuracion_web.py     # Reemplaza configuracion.py
│
├── auth/
│   └── login.py                     # Flujo de login contra Supabase
│
├── db/
│   └── supabase_client.py          # Cliente único de Supabase
│
├── data/
│   ├── cuentas.xlsx                 # PUC de referencia
│   └── mapeos.xlsx                  # Reglas de mapeo
│
├── .streamlit/
│   ├── config.toml                  # Configuración de Streamlit
│   └── secrets.toml.example         # Plantilla de credenciales
│
├── requirements.txt                 # Dependencias Python
├── Procfile                         # Para Railway/Render
├── runtime.txt                      # Versión de Python
├── .gitignore
├── DEPLOY.md                        # Guía de despliegue paso a paso
└── README.md                        # Este archivo
```

---

## 🚀 Instalación Rápida (Local)

### Requisitos previos
- Python 3.9+
- Git
- Cuenta en Supabase (gratuita)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/fabianehg-ui/plataforma-contable.git
cd plataforma-contable

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno virtual
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate            # Windows

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Configurar credenciales
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edita secrets.toml con tus credenciales de Supabase

# 6. Ejecutar la aplicación
streamlit run Home.py
```

La aplicación estará disponible en: `http://localhost:8501`

---

## 🌐 Despliegue en la Web

Para desplegar tu aplicación en producción, consulta **[DEPLOY.md](./DEPLOY.md)** para la guía completa paso a paso.

### Resumen rápido:
1. **Crear cuenta en Supabase** (gratuita) y configurar base de datos
2. **Crear cuenta en Railway** y conectar el repo de GitHub
3. **Configurar variables de entorno** desde Railway
4. **Conectar dominio propio** (opcional)

**Costo aproximado:** $0–10 USD/mes

---

## 📦 Módulos y Estado

| Módulo | Estado | Descripción |
|---|---|---|
| **Caja Menor** | ✅ Funcional | Sube Excel de egresos → genera plano contable |
| **PILA** | ✅ Funcional | Sube PDF de planilla → extrae empleados y totales, descarga Excel |
| **Compras DIAN** | ⏳ Pendiente | Placeholder listo, lógica por migrar |
| **Nómina** | ⏳ Pendiente | Placeholder listo, lógica por migrar |
| **Provisiones** | ⏳ Pendiente | Placeholder listo, lógica por migrar |

### Flujo de migración:
Cada módulo se migra copiando el procesador del .exe actual a `core/procesadores/` 
y creando una página en `app/pages/` que sigue el patrón de **Caja Menor**.

---

## 🔐 Seguridad

- ✅ **Autenticación segura** mediante Supabase Auth
- ✅ **Contraseñas hasheadas** y almacenadas de forma segura
- ✅ **Variables de entorno** para credenciales sensibles
- ✅ **HTTPS** en producción
- ✅ **Acceso multi-usuario** con control de permisos

---

## 🛠️ Tecnologías

- **Python 3.9+**
- **Streamlit** - Framework web interactivo
- **Supabase** - Backend como servicio (autenticación + BD)
- **PostgreSQL** - Base de datos relacional
- **Pandas** - Manipulación de datos
- **Openpyxl** - Lectura/escritura de Excel
- **PyPDF2** - Procesamiento de PDF

---

## 📋 Funcionalidades Principales

- ✅ Login seguro con email y contraseña
- ✅ Gestión multi-empresa
- ✅ Multi-usuario con roles
- ✅ Subida de archivos (Excel, PDF)
- ✅ Generación de reportes
- ✅ Descarga de resultados en Excel
- ✅ Interfaz intuitiva y responsiva
- ✅ Almacenamiento en la nube

---

## 🐛 Problemas y Soluciones

### La aplicación no se conecta a Supabase
- Verifica que `secrets.toml` contenga las credenciales correctas
- Comprueba tu conexión a internet
- Revisa los logs de Supabase en el dashboard

### Error al subir archivos
- Asegúrate de que el archivo tiene el formato correcto (.xlsx o .pdf)
- Verifica que el tamaño del archivo no exceda los límites de Supabase Storage

### Errores en Railway/Render
- Revisa los logs de despliegue en el dashboard
- Verifica que las variables de entorno están configuradas correctamente
- Asegúrate de que el `requirements.txt` contiene todas las dependencias

---

## 📚 Documentación Adicional

- **[DEPLOY.md](./DEPLOY.md)** - Guía completa de despliegue
- **[Documentación de Streamlit](https://docs.streamlit.io/)** - Referencia oficial
- **[Documentación de Supabase](https://supabase.com/docs)** - Guía de Supabase

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:

1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/amazing-feature`)
3. Commit tus cambios (`git commit -m 'Add some amazing feature'`)
4. Push a la rama (`git push origin feature/amazing-feature`)
5. Abre un Pull Request

---

## 📄 Licencia

Este proyecto está disponible bajo la licencia que especifiques.

---

## 👤 Autor

**Fabian Herrera**  
GitHub: [@fabianehg-ui](https://github.com/fabianehg-ui)

---

## 📞 Soporte

Si tienes preguntas o encuentras problemas:

1. Revisa la sección **Problemas y Soluciones** arriba
2. Consulta la documentación en [DEPLOY.md](./DEPLOY.md)
3. Abre un [Issue](https://github.com/fabianehg-ui/plataforma-contable/issues) en GitHub
4. Contacta directamente al autor

---

## 🎯 Roadmap

- [ ] Migrar módulo Compras DIAN
- [ ] Migrar módulo Nómina
- [ ] Migrar módulo Provisiones
- [ ] Agregar más opciones de autenticación (Google, GitHub)
- [ ] Implementar panel de administración
- [ ] Agregar más reportes y visualizaciones
- [ ] Mejorar rendimiento con caché
- [ ] Agregar internacionalización (i18n)

---

**Última actualización:** 2026-05-14  
**Versión del repositorio:** Desarrollo activo
