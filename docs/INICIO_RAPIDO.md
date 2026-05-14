# ⚡ Inicio Rápido - Plataforma Contable Web

**Comienza a usar Plataforma Contable en 5 minutos** ⏱️

---

## 🎯 Antes de Empezar

Necesitas tener:
- ✅ Python 3.9 o superior
- ✅ Git instalado
- ✅ 5 minutos libres
- ✅ Una conexión a internet (para la versión en nube)

---

## 📥 Paso 1: Descargar el Código

```bash
# Clona el repositorio
git clone https://github.com/fabianehg-ui/plataforma-contable.git

# Entra a la carpeta
cd plataforma-contable
```

---

## 🔧 Paso 2: Configurar el Entorno

```bash
# Crea un ambiente virtual
python -m venv venv

# Activa el ambiente
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate            # Windows
```

---

## 📦 Paso 3: Instalar Dependencias

```bash
# Instala todos los requerimientos
pip install -r requirements.txt
```

⏳ **Tiempo esperado:** 1-2 minutos

---

## 🔑 Paso 4: Configurar Credenciales

```bash
# Copia el archivo de ejemplo
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edita secrets.toml con tus credenciales de Supabase
```

**¿Dónde consigo las credenciales?**
1. Crea cuenta en [Supabase.com](https://supabase.com)
2. Crea un proyecto nuevo
3. Ve a Settings → API → Copy the API key
4. Pega en `secrets.toml`

Ver: [CONFIGURACION.md](./CONFIGURACION.md)

---

## 🚀 Paso 5: Ejecutar la Plataforma

```bash
# Inicia la aplicación
streamlit run Home.py
```

✅ **¡Listo!** Tu plataforma está en:
```
http://localhost:8501
```

---

## 🎬 Tu Primer Login

1. Abre http://localhost:8501
2. Verás la página de inicio
3. Haz clic en **"Registrarse"** para crear tu cuenta
4. Usa email + contraseña
5. ¡Bienvenido! 🎉

---

## 📚 Próximos Pasos

### Explorar Módulos
- **Caja Menor** - Control de efectivo
- **PILA** - Gestión de nómina
- **Compras DIAN** (próximamente)
- **Nómina** (próximamente)
- **Provisiones** (próximamente)

### Configurar tu Empresa
1. Ve a ⚙️ Configuración
2. Ingresa datos de tu empresa
3. Sube tu PUC (Plan Contable)
4. ¡Listo!

### Usar tu Primer Módulo
1. Selecciona **Caja Menor**
2. Sube un archivo Excel con egresos
3. ¡Genera tu plano contable!

---

## ⚡ Comandos Útiles

```bash
# Ejecutar en puerto específico
streamlit run Home.py --server.port 8080

# Con reloading desactivado
streamlit run Home.py --logger.level=debug

# Ver todas las opciones
streamlit run --help
```

---

## 🐛 Solución Rápida de Problemas

### ❌ Error: "No module named 'streamlit'"
```bash
# Asegúrate de activar el entorno virtual
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instala nuevamente
pip install -r requirements.txt
```

### ❌ Error: "Connection refused to Supabase"
```
✅ Verifica que secrets.toml tenga las credenciales correctas
✅ Comprueba tu conexión a internet
✅ Revisa que el proyecto en Supabase esté activo
```

### ❌ Puerto 8501 ya está en uso
```bash
# Usa un puerto diferente
streamlit run Home.py --server.port 8502
```

---

## 📖 Documentación Completa

- **[Instalación Completa](./INSTALACION.md)** - Detalles avanzados
- **[Configuración](./CONFIGURACION.md)** - Secrets y variables
- **[Arquitectura](./ARQUITECTURA.md)** - Cómo funciona
- **[FAQ](./FAQ.md)** - Preguntas frecuentes

---

## 🎓 Videotutoriales (Próximamente)

- 📹 Cómo instalar
- 📹 Tu primer login
- 📹 Usar Caja Menor
- 📹 Usar PILA
- 📹 Generar reportes

---

## ✨ Características Principales

✅ **Multi-usuario** - Múltiples usuarios en la misma plataforma  
✅ **Multi-empresa** - Gestiona varias empresas  
✅ **Seguridad** - Autenticación segura con Supabase  
✅ **Datos en la nube** - Acceso desde cualquier dispositivo  
✅ **Automatizado** - Procesos automáticos y eficientes  

---

## 🆘 ¿Algo No Funciona?

1. **Revisa [FAQ.md](./FAQ.md)**
2. **Abre un [Issue en GitHub](https://github.com/fabianehg-ui/plataforma-contable/issues)**
3. **Contacta:** fabianehg@gmail.com

---

## 🎉 ¡Felicidades!

Ya tienes Plataforma Contable funcionando. Ahora:

1. 📚 Lee la documentación completa
2. 🧪 Prueba los módulos disponibles
3. ⚙️ Configura tu empresa
4. 📊 Genera tus primeros reportes

---

**Última actualización:** 2026-05-14  
[⬆ Volver a Documentación](./README.md)
