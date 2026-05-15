# 🤝 Contribuyendo - Plataforma Contable Web

Guía para contribuyentes. ¡Gracias por querer ayudar!

---

## 📋 Tabla de Contenidos

1. [Formas de Contribuir](#formas-de-contribuir)
2. [Setup para Desarrollo](#setup-para-desarrollo)
3. [Estilo de Código](#estilo-de-código)
4. [Commits y PRs](#commits-y-prs)
5. [Testing](#testing)
6. [Documentación](#documentación)
7. [Preguntas Frecuentes](#preguntas-frecuentes)

---

## 💡 Formas de Contribuir

### 1. 🐛 Reportar Bugs

**¿Encontraste un error?**
1. Verifica que no esté reportado ya
2. Abre un [Issue](https://github.com/fabianehg-ui/plataforma-contable/issues)
3. Describe: Qué pasó, qué esperabas, pasos para reproducir

**Formato:**
```markdown
## Descripción
[Describe el bug]

## Pasos para Reproducir
1. ...
2. ...

## Comportamiento Esperado
[Qué debería pasar]

## Actual
[Qué está pasando]

## Entorno
- OS: [Windows/Mac/Linux]
- Python: [3.9/3.10/3.11]
- Streamlit: [versión]
```

### 2. 💡 Sugerir Funcionalidades

**¿Tienes una idea?**
1. Revisa el [Roadmap](./ROADMAP.md)
2. Abre una [Discussion](https://github.com/fabianehg-ui/plataforma-contable/discussions)
3. Describe: Qué necesitas, por qué lo necesitas, cómo lo usarías

### 3. 📚 Mejorar Documentación

**¿Documentación confusa?**
- Sugerencias en GitHub
- PRs con mejoras
- Ejemplos adicionales
- Correcciones de ortografía

### 4. ✅ Escribir Tests

**¿Tests mejorados?**
- Aumenta cobertura
- Tests para bugs
- Tests de integración
- Tests de rendimiento

### 5. 🔧 Código

**¿Quieres programar?**
- Soluciona issues abiertos
- Implementa funcionalidades del roadmap
- Refactorización
- Optimizaciones

---

## 🛠️ Setup para Desarrollo

### 1. Fork y Clone

```bash
# Fork en GitHub
# Luego clone tu fork
git clone https://github.com/TU_USUARIO/plataforma-contable.git
cd plataforma-contable

# Añade upstream
git remote add upstream https://github.com/fabianehg-ui/plataforma-contable.git
```

### 2. Crear Rama

```bash
# Actualizar main
git fetch upstream
git checkout main
git merge upstream/main

# Crear rama de feature
git checkout -b feature/mi-funcionalidad

# O para bugfix
git checkout -b fix/mi-bug
```

### 3. Entorno Virtual

```bash
# Crear
python -m venv venv

# Activar
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# Instalar dependencias
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Configurar Secrets

```bash
# Copiar ejemplo
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Editar con credenciales de desarrollo
# Usar Supabase gratuito
```

### 5. Verificar Setup

```bash
# Ejecutar tests
pytest

# Lint
black .
flake8 .

# Ejecutar app
streamlit run Home.py
```

---

## 🎨 Estilo de Código

### Python

**PEP 8 + Black**

```python
# ✅ Correcto
def procesar_archivo(ruta_archivo: str) -> dict:
    """Procesa un archivo Excel.
    
    Args:
        ruta_archivo: Ruta al archivo Excel
        
    Returns:
        Diccionario con datos procesados
    """
    datos = pd.read_excel(ruta_archivo)
    return datos.to_dict()


# ❌ Evitar
def procesar_archivo(f):
    d = pd.read_excel(f)
    return d.to_dict()
```

### Convenciones

```python
# Variables
usuario_id = "123"          # ✅ snake_case
usuarioId = "123"           # ❌ camelCase

# Constantes
LIMITES_IMPORTACION = 100   # ✅ UPPER_CASE

# Funciones privadas
def _helper_interno():      # ✅ Prefijo _
    pass

# Type hints
def sumar(a: int, b: int) -> int:  # ✅ Siempre type hints
    return a + b

# Docstrings
def funcion(param: str) -> str:
    """Una línea de descripción.
    
    Descripción más detallada si es necesario.
    
    Args:
        param: Descripción del parámetro
        
    Returns:
        Descripción del retorno
        
    Raises:
        ValueError: Cuándo se lanza
    """
    pass
```

### Imports

```python
# ✅ Correcto - Orden: stdlib, terceros, locales
import os
import sys
from typing import Dict, List

import pandas as pd
import streamlit as st
from supabase import create_client

from core.procesadores import procesador_caja_menor
from db.supabase_client import get_client

# ❌ Evitar - Desorganizado
from supabase import create_client
import pandas as pd
import os
from db.supabase_client import get_client
```

---

## 📝 Commits y PRs

### Mensajes de Commit

**Formato:**
```
<tipo>(<scope>): <mensaje conciso>

<descripción opcional>

<referencias opcionales>
```

**Tipos:**
- `feat`: Nueva funcionalidad
- `fix`: Solución de bug
- `docs`: Documentación
- `style`: Formato (no lógica)
- `refactor`: Refactorización
- `perf`: Mejoras de rendimiento
- `test`: Añadir/actualizar tests
- `chore`: Tareas de mantenimiento

**Ejemplos:**
```bash
# ✅ Correcto
git commit -m "feat(caja_menor): agregar validación de moneda"
git commit -m "fix(auth): corregir timeout en login"
git commit -m "docs: actualizar README con instrucciones"

# ❌ Evitar
git commit -m "fix stuff"
git commit -m "Updated files"
git commit -m "changes"
```

### Pull Requests

**Checklist antes de hacer PR:**
- [ ] Actualicé main desde upstream
- [ ] Creé rama desde main
- [ ] Código sigue estilo PEP 8
- [ ] Agregué/actualicé tests
- [ ] Agregué/actualicé documentación
- [ ] Pasaron todos los tests
- [ ] Commit messages son claros
- [ ] No hay conflictos

**Descripción del PR:**
```markdown
## Descripción
[Qué cambios hace este PR]

## Tipo de Cambio
- [ ] Bug fix
- [ ] Nueva funcionalidad
- [ ] Breaking change
- [ ] Documentación

## Cambios
- [x] Item 1
- [x] Item 2

## Testing
Describe cómo se testó:
- [x] Test case 1
- [x] Test case 2

## Checklist
- [x] Tests pasando
- [x] Sin warnings
- [x] Documentación actualizada

## Screenshots (si aplica)
[Incluir si es UI]

## Issues
Fixes #123
```

---

## ✅ Testing

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Tests de un archivo
pytest tests/test_login.py

# Con cobertura
pytest --cov=. --cov-report=html

# Verbose
pytest -v

# Tests específico
pytest -k "test_login"
```

### Escribir Tests

```python
# ✅ Correcto
import pytest
from core.procesadores import procesador_caja_menor


def test_procesar_archivo_valido():
    """Debe procesar archivo válido correctamente."""
    resultado = procesador_caja_menor.procesar("datos/test.xlsx")
    assert resultado is not None
    assert "empresas" in resultado


def test_procesar_archivo_invalido():
    """Debe lanzar error para archivo inválido."""
    with pytest.raises(ValueError):
        procesador_caja_menor.procesar("datos/invalido.txt")


class TestLogin:
    """Tests para módulo de login."""
    
    def test_login_correcto(self):
        """Login con credenciales válidas."""
        resultado = login("user@example.com", "password123")
        assert resultado["success"]
    
    def test_login_incorrecto(self):
        """Login con credenciales inválidas."""
        resultado = login("user@example.com", "wrong")
        assert not resultado["success"]
```

### Coverage Mínimo

- Módulos principales: 80%+
- Utils: 90%+
- Procesadores: 85%+

---

## 📚 Documentación

### Actualizar Docs

1. **En el código:**
```python
def funcion_importante(param: str) -> Dict:
    """Descripción clara de qué hace.
    
    Ejemplo detallado de uso.
    
    Args:
        param: Descripción
        
    Returns:
        Descripción del retorno
    """
    pass
```

2. **En `/docs`:**
   - Crear `.md` para nuevo módulo
   - Actualizar `README.md`
   - Añadir a tabla de contenidos
   - Incluir ejemplos

3. **Estilo:**
   - Markdown limpio
   - Emojis para secciones
   - Código con lenguaje
   - Links internos y externos

---

## 🙅 Qué NO Hacer

❌ **No hacer:**
- Cambiar línea base (main) sin permiso
- Subir secrets o credenciales
- Ignorar linting/formatting
- Commits grandes sin separar
- PRs sin descripción
- Breaking changes sin discusión
- Editar CHANGELOG directamente
- Cambios de versión

❌ **No subir:**
- Archivos `.pyc`
- Carpetas `__pycache__`
- Archivos de sistema (`.DS_Store`)
- Credenciales (`secrets.toml`)
- Archivos de IDE (`.vscode`)

---

## ❓ Preguntas Frecuentes

### ¿Cómo comenzo a contribuir?

1. Fork el repo
2. Clone a tu máquina
3. Elige un issue
4. Crea rama
5. Haz cambios
6. Abre PR
7. ¡Hecho!

### ¿Debo pedir permiso?

No, simplemente:
1. Fork
2. Trabaja
3. Abre PR

Pero para cambios grandes, abre issue primero.

### ¿Cuánto tarda revisar PR?

- Bugs: 24-48 horas
- Features: 2-5 días
- Docs: 24 horas

### ¿Puedo hacer PR directamente a main?

Por favor, no. Siempre:
1. Fork
2. Rama de feature
3. PR a main

### ¿Cómo reporto un bug de seguridad?

**NO lo reportes en GitHub.** Envía a:
- fabianehg@gmail.com (con asunto "SECURITY")
- Incluye detalles completos
- Damos 48h para confirmar

---

## 🎓 Recursos

- [Python Style Guide (PEP 8)](https://pep8.org/)
- [Git Workflow](https://git-scm.com/book/en/v2)
- [Testing in Python](https://docs.pytest.org/)
- [Markdown Guide](https://www.markdownguide.org/)

---

## 🙏 Gracias

¡Gracias por contribuir! Tu ayuda es invaluable.

Si tienes preguntas:
- 📧 fabianehg@gmail.com
- 💬 GitHub Discussions
- 📱 WhatsApp: +57 3xx-xxx-xxxx

---

**Última actualización:** 2026-05-15

[⬆ Volver al Repo](https://github.com/fabianehg-ui/plataforma-contable)
