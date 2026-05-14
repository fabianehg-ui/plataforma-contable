# ❓ Preguntas Frecuentes - Plataforma Contable Web

Las respuestas a tus preguntas más comunes.

---

## 📋 Tabla de Contenidos

1. [General](#general)
2. [Instalación y Setup](#instalación-y-setup)
3. [Uso de Herramientas](#uso-de-herramientas)
4. [Datos y Seguridad](#datos-y-seguridad)
5. [Soporte y Problemas](#soporte-y-problemas)
6. [Servicios Premium](#servicios-premium)

---

## 🔷 General

### ¿Qué es Plataforma Contable Web?

Es una solución integral para gestionar:
- 📊 Contabilidad (Caja Menor, Nómina)
- 🎯 Tributaria (Impuestos, DIAN)
- 📈 Reportes financieros
- ⚙️ Automatización de procesos

### ¿Cuánto cuesta?

**La plataforma es gratuita.**

Costos opcionales:
- **Hosting en nube:** $5-10 USD/mes
- **Asesoría tributaria:** $0-350 USD por consulta
- **Herramientas personalizadas:** Según especificaciones

### ¿Quién puede usar la plataforma?

✅ Empresas pequeñas (1-10 empleados)  
✅ Empresas medianas (10-100 empleados)  
✅ Autónomos/Independientes  
✅ Contadores y asesores  
✅ Estudiantes de contabilidad  

### ¿Necesito ser técnico para usarla?

**No.** La interfaz es amigable y no requiere conocimientos técnicos.

### ¿Es legal usar esta plataforma?

**Sí.** Cumple con normativas de protección de datos y está diseñada para cumplimiento tributario.

### ¿Qué idiomas soporta?

Actualmente: **Español**

Planeado: **Inglés, Portugués** (Q3 2026)

---

## 🔧 Instalación y Setup

### ¿Cuáles son los requisitos mínimos?

**Para versión en nube:**
- ✅ Navegador web (Chrome, Firefox, Edge)
- ✅ Conexión a internet
- ✅ Nada más

**Para versión local:**
- ✅ Python 3.9+
- ✅ 2GB RAM
- ✅ 500MB espacio disco

### ¿Cuánto tarda la instalación?

**Versión nube:** 2 minutos (solo registrarse)  
**Versión local:** 5-10 minutos (con guía)

### ¿Es difícil instalar la versión local?

No, la guía [INICIO_RAPIDO.md](./INICIO_RAPIDO.md) te lleva paso a paso. Incluso sin experiencia técnica.

### ¿Puedo usar ambas versiones (nube y local)?

Sí, cada una guarda sus datos por separado. Perfecta para tener respaldo.

### ¿Necesito internet para la versión local?

No, solo para descargar/instalar.

### ¿Puedo usar en Mac, Linux y Windows?

**Sí, en los tres sistemas operativos.**

### ¿Es segura la instalación?

**Totalmente.** El código es open source, puedes revisar qué hace exactamente.

---

## 💼 Uso de Herramientas

### ¿Cómo uso Caja Menor?

1. Ve al módulo "Caja Menor"
2. Sube tu archivo Excel con egresos
3. Haz clic en "Procesar"
4. Descarga los resultados

[Ver guía completa](./HERRAMIENTAS_CONTABLES.md#caja-menor)

### ¿Qué formato debe tener mi archivo Excel?

Debe tener estas columnas:
- **Fecha** (DD/MM/YYYY)
- **Descripción** (Texto)
- **Valor** (Número)
- **Cuenta** (Código PUC)

### ¿Cuál es el tamaño máximo de archivo?

- **Excel:** hasta 25MB
- **PDF:** hasta 50MB

Esto permite procesar miles de transacciones.

### ¿Puedo procesar múltiples archivos?

Sí, pero es recomendable uno a la vez para mejor control.

### ¿Cuánto tarda procesar?

- **Archivos pequeños:** 5-10 segundos
- **Archivos medianos:** 30-60 segundos
- **Archivos grandes:** 1-3 minutos

### ¿Qué pasa si hay errores en mi archivo?

El sistema te muestra exactamente qué está mal antes de procesar. Puedes corregir y reintentar.

### ¿Puedo modificar datos después de procesar?

Sí. Descarga el resultado, modifica y vuelve a subir.

### ¿PILA funciona con todos los bancos?

No necesita bancos específicos. Funciona con cualquier formato de planilla estándar.

---

## 🔒 Datos y Seguridad

### ¿Dónde guarda mis datos?

En **Supabase** (infraestructura en nube europea).

- 🔐 Encriptado en tránsito (HTTPS)
- 🔐 Encriptado en reposo
- 🔐 Copias de seguridad automáticas

### ¿Quién puede ver mis datos?

**Solo tú.** Datos completamente privados y protegidos.

### ¿Qué datos guarda?

Solo lo que tú subas:
- Archivos procesados
- Configuración de empresa
- Usuarios autorizados
- Transacciones registradas

### ¿Es GDPR compliant?

**Sí.** Cumple con regulaciones europeas de protección de datos.

### ¿Puedo descargar todos mis datos?

**Sí, siempre.** Acceso completo a tu información.

### ¿Qué pasa si cierro mi cuenta?

Tus datos se eliminan automáticamente en 30 días (salvo que requieras una copia).

### ¿Tiene autenticación de dos factores (2FA)?

📋 **Próximamente.** Planeado para Q3 2026.

### ¿Puedo cambiar mi contraseña?

**Sí.** En cualquier momento desde tu perfil.

---

## 🐛 Soporte y Problemas

### ¿Qué pasa si algo no funciona?

1. Revisa [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
2. Busca en [FAQ.md](./FAQ.md) (este archivo)
3. Contacta: fabianehg@gmail.com
4. Abre un [Issue en GitHub](https://github.com/fabianehg-ui/plataforma-contable/issues)

### ¿Cuál es el tiempo de respuesta?

- **Errores críticos:** 24 horas
- **Soporte general:** 48 horas
- **Consultas:** 72 horas

### ¿Hay soporte por teléfono?

**Via WhatsApp:** +57 3xx-xxx-xxxx (lunes-viernes 9am-5pm)

### ¿Tengo acceso a logs y reportes?

Sí, desde tu panel de control.

### ¿Dónde reporto bugs?

[GitHub Issues](https://github.com/fabianehg-ui/plataforma-contable/issues)

### ¿Puedo sugerir nuevas funcionalidades?

**Sí, claro.** Contacta a: fabianehg@gmail.com

### ¿Hay comunidad o foro?

📋 **Próximamente.** Planeado un foro en Q2 2026.

---

## 💎 Servicios Premium

### ¿Qué son los servicios premium?

Servicios adicionales pagos:
- 🎯 **Herramientas personalizadas** - Según tu negocio
- 📋 **Asesoría tributaria** - Expertos certificados
- 🔧 **Soporte prioritario** - Atención 24/7
- 📊 **Reportes avanzados** - Análisis profundo

### ¿Cuánto cuesta una herramienta personalizada?

Depende de la complejidad: $500-5000 USD

Se cotiza después de entender tus necesidades.

### ¿Cómo contrato asesoría tributaria?

1. Email: tributaria@plataforma-contable.com
2. Describe qué necesitas
3. Recibe propuesta con horarios
4. Confirma y realiza consulta

### ¿Incluye la asesoría implementación?

Sí, la asesoría incluye:
- Consulta experta
- Recomendaciones
- Ayuda en implementación

### ¿Cuál es el costo de soporte 24/7?

**$99 USD/mes** o **$900 USD/año**

Incluye:
- ✅ Atención priorizada
- ✅ Soporte telefónico
- ✅ Revisión de procesos
- ✅ Capacitación del equipo

### ¿Cómo contrato soporte?

Email: soporte@plataforma-contable.com

---

## 📞 Contacto Rápido

| Tema | Contacto |
|------|----------|
| 🆘 Emergencia técnica | +57 3xx-xxx-xxxx |
| 📧 Consulta general | fabianehg@gmail.com |
| 💼 Servicios premium | soporte@plataforma-contable.com |
| 🏛️ Asesoría tributaria | tributaria@plataforma-contable.com |
| 🐛 Reporte de bug | GitHub Issues |

---

## 🔗 Enlaces Útiles

- [Documentación principal](./README.md)
- [Inicio Rápido](./INICIO_RAPIDO.md)
- [Herramientas Contables](./HERRAMIENTAS_CONTABLES.md)
- [Herramientas Tributarias](./HERRAMIENTAS_TRIBUTARIAS.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
- [GitHub](https://github.com/fabianehg-ui/plataforma-contable)

---

**Última actualización:** 2026-05-14

¿No encontraste lo que buscas? → [Contacta](../DEPLOY.md)
