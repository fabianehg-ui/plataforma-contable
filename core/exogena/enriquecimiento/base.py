"""
Sistema de enriquecimiento de datos de terceros desde fuentes externas.

Diseño en capas (de gratuita a paga):
  1. RUES (Confecámaras)  - Gratuito - solo jurídicas
  2. DIAN consulta pública - Gratuito - estado del RUT
  3. APIs comerciales      - Pago - Apitude, Truora, Datacrédito

Cada implementación expone la misma interfaz `Enriquecedor`. El consumidor
puede componer varias en cadena (`EnriquecedorEnCascada`) para intentar
fuentes gratuitas primero y solo recurrir a las pagas si fallan.

Todas las consultas pasan por una caché en BD (`exogena_cache_enriquecimiento`)
porque cada consulta a una API paga cuesta dinero — no se debe repetir.

Uso típico:
    from enriquecimiento import EnriquecedorEnCascada, RUESEnriquecedor, ApitudeEnriquecedor
    
    enriquecedor = EnriquecedorEnCascada([
        CacheEnriquecedor(supabase_client),
        RUESEnriquecedor(),
        ApitudeEnriquecedor(api_key=os.getenv('APITUDE_API_KEY')),
    ])
    
    datos = enriquecedor.enriquecer('900123456')
    if datos:
        print(datos.razon_social, datos.direccion, datos.fuente)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DatosEnriquecidos:
    """Datos obtenidos desde una fuente externa para un NIT."""
    nit: str
    fuente: str                          # 'rues' | 'dian_publica' | 'apitude' | 'truora' | 'cache' | etc.
    fecha_consulta: datetime = field(default_factory=datetime.utcnow)
    
    # Datos comunes
    tipo_persona: Optional[str] = None   # 'natural' | 'juridica'
    estado: Optional[str] = None         # 'activo' | 'suspendido' | 'cancelado'
    razon_social: Optional[str] = None
    primer_nombre: Optional[str] = None
    segundo_nombre: Optional[str] = None
    primer_apellido: Optional[str] = None
    segundo_apellido: Optional[str] = None
    direccion: Optional[str] = None
    codigo_dpto: Optional[str] = None
    codigo_municipio: Optional[str] = None
    nombre_municipio: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    actividad_ciiu: Optional[str] = None
    representante_legal: Optional[str] = None
    
    # Datos crudos para auditoría
    payload_crudo: dict = field(default_factory=dict)
    
    # Metadatos
    confiabilidad: float = 1.0           # 0.0 - 1.0, qué tan confiable es la fuente
    advertencias: list = field(default_factory=list)


class Enriquecedor(ABC):
    """Interfaz base que todas las implementaciones deben cumplir."""
    
    nombre: str = 'base'
    
    @abstractmethod
    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        """Consulta el NIT en la fuente externa.
        
        Returns:
            DatosEnriquecidos si encontró información, None si no.
        Raises:
            EnriquecedorError si hubo error de red, autenticación, rate limit, etc.
        """
        ...
    
    def disponible(self) -> bool:
        """Indica si esta fuente está disponible (credenciales OK, etc)."""
        return True


class EnriquecedorError(Exception):
    """Error al consultar una fuente de enriquecimiento."""
    
    def __init__(self, mensaje: str, fuente: str, recuperable: bool = True):
        super().__init__(mensaje)
        self.fuente = fuente
        self.recuperable = recuperable  # True si se puede reintentar más tarde


class EnriquecedorStub(Enriquecedor):
    """Implementación que no hace nada — útil para desarrollo y tests.
    
    Devuelve None para todo. El motor de exógena puede usarlo cuando no
    haya credenciales configuradas, sin romper el flujo.
    """
    nombre = 'stub'
    
    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        return None


class EnriquecedorEnCascada(Enriquecedor):
    """Compone varios enriquecedores: prueba en orden hasta encontrar respuesta.
    
    Ejemplo de uso:
        cascada = EnriquecedorEnCascada([
            CacheEnriquecedor(supabase),     # primero la caché (gratis)
            RUESEnriquecedor(),               # luego RUES (gratis)
            ApitudeEnriquecedor(api_key),     # solo si lo anterior no resolvió
        ])
    
    Cuando un enriquecedor devuelve datos, los demás se saltan. Esto evita
    gastar consultas pagas innecesariamente.
    """
    nombre = 'cascada'
    
    def __init__(self, enriquecedores: list[Enriquecedor], 
                 escribir_en_cache: bool = True):
        self.enriquecedores = enriquecedores
        self.escribir_en_cache = escribir_en_cache
    
    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        cache_enriquecedor = next(
            (e for e in self.enriquecedores if isinstance(e, CacheEnriquecedor)),
            None,
        )
        
        for enr in self.enriquecedores:
            if not enr.disponible():
                continue
            try:
                datos = enr.enriquecer(nit)
                if datos:
                    # Si no vino de la caché y hay caché disponible, guardarlo
                    if (self.escribir_en_cache and cache_enriquecedor 
                            and enr is not cache_enriquecedor):
                        try:
                            cache_enriquecedor.guardar(nit, datos)
                        except Exception:
                            pass  # caché no debe romper el flujo
                    return datos
            except EnriquecedorError:
                # log pero continuar con siguiente fuente
                continue
        return None


class CacheEnriquecedor(Enriquecedor):
    """Lee/escribe en la tabla exogena_cache_enriquecimiento.
    
    Diseñado como un Enriquecedor más para que encaje en la cascada,
    pero también expone `guardar()` para que la cascada lo use al obtener
    datos de otras fuentes.
    """
    nombre = 'cache'
    
    def __init__(self, supabase_client, ttl_dias: int = 90):
        """
        Args:
            ttl_dias: cuántos días considerar válida una entrada de caché.
                      Datos del RUT cambian rara vez, 90 días es razonable.
        """
        self.client = supabase_client
        self.ttl_dias = ttl_dias
    
    def disponible(self) -> bool:
        return self.client is not None
    
    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        """Lee de la tabla exogena_cache_enriquecimiento."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=self.ttl_dias)
        
        resp = self.client.table('exogena_cache_enriquecimiento').select('*').eq(
            'nit', nit
        ).gte('fecha_consulta', cutoff.isoformat()).order(
            'fecha_consulta', desc=True
        ).limit(1).execute()
        
        if not resp.data:
            return None
        
        row = resp.data[0]
        return DatosEnriquecidos(
            nit=row['nit'],
            fuente='cache:' + row.get('fuente_original', 'desconocida'),
            fecha_consulta=datetime.fromisoformat(row['fecha_consulta']),
            tipo_persona=row.get('tipo_persona'),
            estado=row.get('estado'),
            razon_social=row.get('razon_social'),
            primer_nombre=row.get('primer_nombre'),
            primer_apellido=row.get('primer_apellido'),
            segundo_apellido=row.get('segundo_apellido'),
            direccion=row.get('direccion'),
            codigo_dpto=row.get('codigo_dpto'),
            codigo_municipio=row.get('codigo_municipio'),
            email=row.get('email'),
            telefono=row.get('telefono'),
            actividad_ciiu=row.get('actividad_ciiu'),
            representante_legal=row.get('representante_legal'),
            payload_crudo=row.get('payload_crudo', {}),
        )
    
    def guardar(self, nit: str, datos: DatosEnriquecidos) -> None:
        """Persiste los datos enriquecidos para futuras consultas."""
        self.client.table('exogena_cache_enriquecimiento').upsert({
            'nit': nit,
            'fuente_original': datos.fuente,
            'fecha_consulta': datos.fecha_consulta.isoformat(),
            'tipo_persona': datos.tipo_persona,
            'estado': datos.estado,
            'razon_social': datos.razon_social,
            'primer_nombre': datos.primer_nombre,
            'primer_apellido': datos.primer_apellido,
            'segundo_apellido': datos.segundo_apellido,
            'direccion': datos.direccion,
            'codigo_dpto': datos.codigo_dpto,
            'codigo_municipio': datos.codigo_municipio,
            'email': datos.email,
            'telefono': datos.telefono,
            'actividad_ciiu': datos.actividad_ciiu,
            'representante_legal': datos.representante_legal,
            'payload_crudo': datos.payload_crudo,
            'advertencias': datos.advertencias,
        }, on_conflict='nit').execute()


def aplicar_enriquecimiento_a_tercero(tercero: dict, datos: DatosEnriquecidos,
                                      sobreescribir_existente: bool = False) -> dict:
    """Aplica los datos enriquecidos a un dict de tercero.
    
    Args:
        tercero: el dict del tercero (modificado in-place)
        datos: lo que devolvió el enriquecedor
        sobreescribir_existente: si True, reemplaza valores ya presentes;
                                 si False, solo llena los vacíos.
    
    Returns:
        El dict modificado.
    """
    def set_si_aplica(campo: str, valor):
        if not valor:
            return
        actual = tercero.get(campo, '')
        if not actual or sobreescribir_existente:
            tercero[campo] = valor
    
    if datos.tipo_persona:
        set_si_aplica('tipo_persona', datos.tipo_persona)
    if datos.razon_social:
        set_si_aplica('razon_social', datos.razon_social)
    set_si_aplica('primer_nombre', datos.primer_nombre)
    set_si_aplica('segundo_nombre', datos.segundo_nombre)
    set_si_aplica('primer_apellido', datos.primer_apellido)
    set_si_aplica('segundo_apellido', datos.segundo_apellido)
    set_si_aplica('direccion', datos.direccion)
    set_si_aplica('codigo_dpto', datos.codigo_dpto)
    set_si_aplica('codigo_municipio', datos.codigo_municipio)
    set_si_aplica('email', datos.email)
    set_si_aplica('actividad_ciiu', datos.actividad_ciiu)
    
    # Marcar el tercero como enriquecido (para auditoría)
    tercero['enriquecido_desde'] = datos.fuente
    tercero['fecha_enriquecimiento'] = datos.fecha_consulta.isoformat()
    
    return tercero
