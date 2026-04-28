# 🩹 Parche UI — Agregar PILA opcional al módulo Nómina

> Aplica este parche en `pages/3_💼_Nómina.py` (o el nombre exacto de tu página de Nómina).

---

## 📌 Contexto

Estamos eliminando los íconos PILA y Provisiones de la pantalla principal. La planilla PILA pasa a ser un **archivo opcional dentro del módulo Nómina** que sirve como insumo para validar las provisiones contra lo realmente pagado en aportes.

El SQL `setup_desactivar_pila_y_provisiones.sql` ya desactiva ambos módulos. Falta solo agregar el uploader en la página de Nómina.

---

## 🎯 Cambios a aplicar (3 bloques)

### Bloque 1 — Sección de uploaders

**Busca** en tu página algo como esto (puede variar el nombre del file_uploader):

```python
archivo_nomina = st.file_uploader(
    "Planilla de nómina (.xls)",
    type=["xls", "xlsx"],
    key="archivo_nomina",
)
```

**Reemplaza por** (dos columnas con un uploader cada una):

```python
col_n1, col_n2 = st.columns(2)
with col_n1:
    st.markdown("**📋 Planilla de Nómina** (obligatorio)")
    archivo_nomina = st.file_uploader(
        "NOMINA_CASATRECE_<MES>.xls",
        type=["xls", "xlsx"],
        help="Planilla mensual con devengados, deducciones, incapacidades.",
        key="archivo_nomina",
    )
with col_n2:
    st.markdown("**📎 Planilla PILA pagada** (opcional)")
    archivo_pila = st.file_uploader(
        "Planilla PILA del mes (.xls / .xlsx)",
        type=["xls", "xlsx"],
        help="Planilla de seguridad social pagada en el mes. "
             "Se usa para validar provisiones vs aportes reales pagados.",
        key="archivo_pila",
    )
```

---

### Bloque 2 — Llamada al procesador

**Busca** la llamada actual al procesador (parecida a esto):

```python
df_plano, log, resumen = procesar_nomina(
    archivo_nomina=archivo_nomina,
    anio=int(anio),
    mes=int(mes_idx),
)
```

**Reemplaza por:**

```python
df_plano, log, resumen = procesar_nomina(
    archivo_nomina=archivo_nomina,
    archivo_pila=archivo_pila,   # ← nuevo: opcional, puede ser None
    anio=int(anio),
    mes=int(mes_idx),
)
```

> **Importante:** mientras el procesador no soporte el parámetro `archivo_pila`, esta línea fallará. Para evitarlo, durante la transición usa esta versión defensiva:

```python
import inspect
kwargs = dict(
    archivo_nomina=archivo_nomina,
    anio=int(anio),
    mes=int(mes_idx),
)
# Solo pasa archivo_pila si el procesador lo acepta
sig = inspect.signature(procesar_nomina)
if "archivo_pila" in sig.parameters:
    kwargs["archivo_pila"] = archivo_pila
df_plano, log, resumen = procesar_nomina(**kwargs)
```

Esto deja la UI lista, sin romper nada hasta que actualices el procesador.

---

### Bloque 3 — Aviso explicativo (opcional)

**Antes de los uploaders**, agrega esta nota informativa:

```python
st.info(
    "📋 **Cómo funciona ahora:**\n\n"
    "- La **planilla de nómina** genera Comp 11 (causación quincenal) y "
    "Comp 9 (provisiones del último día del mes).\n"
    "- Si subes la **planilla PILA pagada**, el sistema valida lo "
    "provisionado vs lo realmente pagado en aportes y genera líneas de "
    "ajuste automáticas en Comp 9 con detalle 'AJUSTE PILA'.\n"
    "- PILA es **opcional**: puedes procesar solo la nómina si aún no "
    "tienes la planilla pagada del mes."
)
```

---

## ✅ Checklist de despliegue

```
1) Ejecutar en Supabase
   └─ sql/setup_desactivar_pila_y_provisiones.sql

2) Verificar en la plataforma
   └─ Configuración → Módulos
       ├─ ❌ PILA debe aparecer desactivado
       ├─ ❌ Provisiones debe aparecer desactivado
       └─ ✅ Nómina sigue activo

3) Aplicar este parche en pages/3_💼_Nómina.py
   ├─ Bloque 1: agregar uploader PILA
   ├─ Bloque 2: pasar archivo_pila al procesador (versión defensiva)
   └─ Bloque 3: agregar aviso explicativo

4) Commit + push
   └─ Railway redespliega solo

5) Validar en producción
   ├─ La pantalla principal ya NO muestra los íconos 📎 PILA ni Provisiones
   ├─ Al entrar a Nómina aparecen 2 uploaders (Nómina obligatorio, PILA opcional)
   └─ Procesar marzo 2026 sin PILA: debe seguir cuadrando $18.315.182 en 107 líneas
```

---

## 📂 Archivos viejos a eliminar del repo (cuando confirmes que todo funciona)

```bash
# Páginas viejas
git rm "pages/2_📎_PILA.py"            # o el nombre exacto que tenga
git rm "pages/4_📊_Provisiones.py"     # o el nombre exacto que tenga

# Procesadores viejos (si existen y ya no se usan en otros módulos)
git rm core/procesadores/procesador_pila.py
git rm core/procesadores/procesador_provisiones.py
```

> ⚠️ **Antes de borrar**, verifica que ningún otro módulo importe esos procesadores. Si los importan, deja los archivos pero comenta el contenido o vacía su lógica.

---

## 🎯 Próximo paso (cuando lo necesites)

El procesador de Nómina aún no usa el `archivo_pila`. Cuando quieras que el sistema **lea PILA y genere las líneas de ajuste automático en Comp 9**, lo abordamos en la siguiente iteración. Por ahora la UI queda lista y el archivo se sube pero se ignora.

Si me adjuntas:
- `procesador_nomina.py` actual
- Un archivo PILA de ejemplo de Casa UnoTres SAS

…te entrego el procesador actualizado con la lógica de ajuste automático completa.
