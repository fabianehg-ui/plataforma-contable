"""
Enriquecedor que consulta la API de Apitude (https://apitude.co).

Apitude es un agregador de servicios de datos públicos colombianos que expone
una API unificada con consulta del RUT DIAN (entre muchos otros).

Documentación oficial:
    https://apitude.co/es/docs/services/dian-rut-validation-co/

El servicio funciona en dos pasos:
    1. POST a /api/v1.0/requests/dian-rut-validation-co/ con el NIT
       → devuelve un request_id
    2. GET a /api/v1.0/requests/dian-rut-validation-co/<request_id>/
       → devuelve los datos cuando estén listos (puede tardar segundos)

Configuración:
    Definir variable de entorno APITUDE_API_KEY con la clave de API.
    Obtener la clave en https://apitude.co
"""

from __future__ import annotations
import os
import time
from datetime import datetime
from typing import Optional

from .base import Enriquecedor, DatosEnriquecidos, EnriquecedorError


class ApitudeEnriquecedor(Enriquecedor):
    """Consulta el RUT vía API de Apitude.
    
    NOTA: Esta implementación es un esqueleto basado en la documentación
    pública de Apitude. La estructura exacta del payload de respuesta
    debe verificarse con consultas reales una vez se obtengan credenciales.
    """
    
    nombre = 'apitude'
    
    BASE_URL = 'https://apitude.co/api/v1.0/requests'
    SERVICIO_RUT = 'dian-rut-validation-co'
    
    def __init__(self, api_key: Optional[str] = None, timeout: int = 30,
                 max_intentos_polling: int = 10, intervalo_polling: float = 1.0):
        """
        Args:
            api_key: clave de Apitude. Si es None, lee de APITUDE_API_KEY.
            timeout: timeout HTTP por request (segundos).
            max_intentos_polling: cuántas veces consultar el resultado del request_id.
            intervalo_polling: cuánto esperar entre consultas (segundos).
        """
        self.api_key = api_key or os.getenv('APITUDE_API_KEY')
        self.timeout = timeout
        self.max_intentos_polling = max_intentos_polling
        self.intervalo_polling = intervalo_polling
    
    def disponible(self) -> bool:
        return bool(self.api_key)
    
    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        if not self.disponible():
            return None
        
        try:
            import requests
        except ImportError:
            raise EnriquecedorError(
                "La librería 'requests' es necesaria para ApitudeEnriquecedor. "
                "Instalar con: pip install requests",
                fuente='apitude', recuperable=False,
            )
        
        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
        }
        
        # Paso 1: crear request
        try:
            resp = requests.post(
                f'{self.BASE_URL}/{self.SERVICIO_RUT}/',
                headers=headers,
                json={'document_number': nit},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise EnriquecedorError(f"Error de red: {e}", fuente='apitude')
        
        if resp.status_code == 401:
            raise EnriquecedorError(
                "API key inválida o expirada", fuente='apitude', recuperable=False,
            )
        if resp.status_code == 402:
            raise EnriquecedorError(
                "Saldo insuficiente en Apitude", fuente='apitude', recuperable=False,
            )
        if resp.status_code == 429:
            raise EnriquecedorError(
                "Rate limit superado", fuente='apitude', recuperable=True,
            )
        if not resp.ok:
            raise EnriquecedorError(
                f"Apitude devolvió HTTP {resp.status_code}: {resp.text[:200]}",
                fuente='apitude',
            )
        
        request_id = resp.json().get('request_id')
        if not request_id:
            raise EnriquecedorError(
                "Respuesta de Apitude sin request_id", fuente='apitude',
            )
        
        # Paso 2: polling del resultado
        url_resultado = f'{self.BASE_URL}/{self.SERVICIO_RUT}/{request_id}/'
        
        for intento in range(self.max_intentos_polling):
            time.sleep(self.intervalo_polling)
            try:
                resp_get = requests.get(url_resultado, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                raise EnriquecedorError(f"Error de red en polling: {e}", fuente='apitude')
            
            if not resp_get.ok:
                continue
            
            data = resp_get.json()
            estado = data.get('status')
            
            # Aún procesándose
            if estado in ('pending', 'processing', None):
                continue
            
            # Resultado disponible
            return self._parsear_respuesta(nit, data)
        
        raise EnriquecedorError(
            f"Apitude no respondió tras {self.max_intentos_polling} intentos",
            fuente='apitude', recuperable=True,
        )
    
    def _parsear_respuesta(self, nit: str, payload: dict) -> Optional[DatosEnriquecidos]:
        """Convierte el JSON de Apitude en DatosEnriquecidos.
        
        IMPORTANTE: la estructura exacta debe verificarse cuando tengas la
        primera respuesta real. Apitude puede haber cambiado el shape.
        """
        result = payload.get('result', {})
        if not result or result.get('status') == 404:
            return None
        
        data = result.get('data', {})
        if not data:
            return None
        
        # Mapeo tentativo de campos según la documentación pública
        return DatosEnriquecidos(
            nit=nit,
            fuente='apitude',
            fecha_consulta=datetime.utcnow(),
            tipo_persona=self._inferir_tipo_persona(data),
            estado=data.get('estado') or data.get('status'),
            razon_social=data.get('razon_social') or data.get('nombre_completo'),
            primer_nombre=data.get('primer_nombre'),
            segundo_nombre=data.get('segundo_nombre'),
            primer_apellido=data.get('primer_apellido'),
            segundo_apellido=data.get('segundo_apellido'),
            direccion=data.get('direccion'),
            codigo_dpto=data.get('codigo_departamento'),
            codigo_municipio=data.get('codigo_municipio'),
            email=data.get('email'),
            telefono=data.get('telefono'),
            actividad_ciiu=data.get('codigo_ciiu') or data.get('actividad_economica'),
            payload_crudo=data,
            confiabilidad=0.95,  # Apitude consulta directo a la DIAN
        )
    
    @staticmethod
    def _inferir_tipo_persona(data: dict) -> Optional[str]:
        if data.get('tipo_persona'):
            return data['tipo_persona'].lower()
        if data.get('razon_social') and not data.get('primer_nombre'):
            return 'juridica'
        if data.get('primer_nombre') or data.get('primer_apellido'):
            return 'natural'
        return None
