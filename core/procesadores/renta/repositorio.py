"""
Repositorio para persistir y recuperar liquidaciones de Renta en Supabase.

Tablas que utiliza:
  - renta_liquidaciones: una fila por empresa/año, con el JSON completo del Form 110
  - renta_partidas_conciliatorias: catálogo configurable por empresa de partidas
                                    conciliatorias estándar (depreciaciones, etc.)
"""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Optional, Any
import json
import logging

from .modelo_form110 import Formulario110

log = logging.getLogger(__name__)


class RepositorioRenta:
    """
    Wrapper sobre el cliente Supabase para CRUD de liquidaciones.

    Espera recibir un cliente Supabase ya inicializado (típicamente del módulo
    de auth del repo Railway). No intenta inicializar Supabase por sí mismo.

    Uso:
        from auth.supabase_client import get_supabase
        repo = RepositorioRenta(supabase=get_supabase())

        # Guardar una liquidación
        repo.guardar_liquidacion(
            empresa_id="uuid-empresa",
            nit="900533491-5",
            ano_gravable=2025,
            formulario=f110,
            estado="borrador",
        )

        # Recuperar
        liq = repo.obtener_liquidacion(empresa_id, ano_gravable=2025)
    """

    TABLA_LIQUIDACIONES = "renta_liquidaciones"
    TABLA_PARTIDAS = "renta_partidas_conciliatorias"

    ESTADOS_VALIDOS = ("borrador", "revisado", "presentado", "anulado")

    def __init__(self, supabase: Any) -> None:
        """
        Args:
            supabase: cliente Supabase ya autenticado (objeto retornado por
                      `create_client(url, key)` del SDK supabase-py).
        """
        if supabase is None:
            raise ValueError("RepositorioRenta requiere un cliente Supabase válido")
        self.sb = supabase

    # ============================================================
    # LIQUIDACIONES
    # ============================================================

    def guardar_liquidacion(
        self,
        empresa_id: str,
        nit: str,
        ano_gravable: int,
        formulario: Formulario110,
        estado: str = "borrador",
        notas: Optional[str] = None,
        usuario_id: Optional[str] = None,
    ) -> dict:
        """
        Guarda (o actualiza si ya existe) la liquidación de una empresa para un año.

        El upsert se hace por la llave compuesta (empresa_id, ano_gravable).
        """
        if estado not in self.ESTADOS_VALIDOS:
            raise ValueError(f"Estado inválido: {estado}. Válidos: {self.ESTADOS_VALIDOS}")

        datos_form110 = formulario.to_dict()

        # Serializar a JSON-safe (los Decimal y otros se convierten a str/float)
        datos_json = json.loads(json.dumps(datos_form110, default=str))

        registro = {
            "empresa_id": empresa_id,
            "nit": nit,
            "ano_gravable": ano_gravable,
            "datos_form110_json": datos_json,
            "estado": estado,
            "notas": notas,
            "usuario_id_modificacion": usuario_id,
            "fecha_modificacion": datetime.utcnow().isoformat(),
        }

        # Casillas clave indexadas para búsqueda rápida
        registro["casilla_44_patrimonio_bruto"] = datos_form110.get("casilla_44_total_patrimonio_bruto", 0)
        registro["casilla_46_patrimonio_liquido"] = datos_form110.get("casilla_46_total_patrimonio_liquido", 0)
        registro["casilla_72_renta_liquida_ordinaria"] = datos_form110.get("casilla_72_renta_liquida_ordinaria", 0)
        registro["casilla_99_total_impuesto_a_cargo"] = datos_form110.get("casilla_99_total_impuesto_a_cargo", 0)
        registro["casilla_113_total_saldo_a_pagar"] = datos_form110.get("casilla_113_total_saldo_a_pagar", 0)
        registro["casilla_114_total_saldo_a_favor"] = datos_form110.get("casilla_114_total_saldo_a_favor", 0)

        try:
            response = (
                self.sb.table(self.TABLA_LIQUIDACIONES)
                .upsert(registro, on_conflict="empresa_id,ano_gravable")
                .execute()
            )
            log.info("Liquidación guardada: empresa=%s año=%s estado=%s", empresa_id, ano_gravable, estado)
            return response.data[0] if response.data else registro
        except Exception as e:
            log.exception("Error guardando liquidación")
            raise RuntimeError(f"No se pudo guardar la liquidación: {e}") from e

    def obtener_liquidacion(self, empresa_id: str, ano_gravable: int) -> Optional[dict]:
        """
        Recupera la liquidación de una empresa para un año específico.
        Retorna None si no existe.
        """
        try:
            response = (
                self.sb.table(self.TABLA_LIQUIDACIONES)
                .select("*")
                .eq("empresa_id", empresa_id)
                .eq("ano_gravable", ano_gravable)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            log.exception("Error obteniendo liquidación")
            raise RuntimeError(f"No se pudo obtener la liquidación: {e}") from e

    def listar_liquidaciones(self, empresa_id: str) -> list[dict]:
        """Lista todas las liquidaciones de una empresa (todos los años)."""
        try:
            response = (
                self.sb.table(self.TABLA_LIQUIDACIONES)
                .select("*")
                .eq("empresa_id", empresa_id)
                .order("ano_gravable", desc=True)
                .execute()
            )
            return response.data or []
        except Exception as e:
            log.exception("Error listando liquidaciones")
            raise RuntimeError(f"No se pudieron listar las liquidaciones: {e}") from e

    def eliminar_liquidacion(self, empresa_id: str, ano_gravable: int) -> None:
        """Elimina una liquidación (sólo permitido si está en borrador)."""
        actual = self.obtener_liquidacion(empresa_id, ano_gravable)
        if actual is None:
            return
        if actual.get("estado") == "presentado":
            raise PermissionError("No se puede eliminar una liquidación ya presentada a la DIAN")

        self.sb.table(self.TABLA_LIQUIDACIONES).delete().eq(
            "empresa_id", empresa_id
        ).eq("ano_gravable", ano_gravable).execute()
        log.info("Liquidación eliminada: empresa=%s año=%s", empresa_id, ano_gravable)

    # ============================================================
    # PARTIDAS CONCILIATORIAS (catálogo por empresa)
    # ============================================================

    def listar_partidas_empresa(self, empresa_id: str, ano_gravable: int) -> list[dict]:
        """Lista las partidas conciliatorias de una empresa para un año."""
        try:
            response = (
                self.sb.table(self.TABLA_PARTIDAS)
                .select("*")
                .eq("empresa_id", empresa_id)
                .eq("ano_gravable", ano_gravable)
                .order("orden")
                .execute()
            )
            return response.data or []
        except Exception as e:
            log.exception("Error listando partidas")
            raise RuntimeError(f"No se pudieron listar las partidas: {e}") from e

    def guardar_partida(
        self,
        empresa_id: str,
        ano_gravable: int,
        codigo: str,
        nombre: str,
        valor: float,
        tipo: str,  # 'aumenta' | 'disminuye'
        base_legal: Optional[str] = None,
        notas: Optional[str] = None,
        orden: int = 0,
    ) -> dict:
        """Guarda una partida conciliatoria (upsert por codigo+empresa+año)."""
        if tipo not in ("aumenta", "disminuye"):
            raise ValueError("tipo debe ser 'aumenta' o 'disminuye'")

        registro = {
            "empresa_id": empresa_id,
            "ano_gravable": ano_gravable,
            "codigo": codigo,
            "nombre": nombre,
            "valor": float(valor),
            "tipo": tipo,
            "base_legal": base_legal,
            "notas": notas,
            "orden": orden,
        }

        try:
            response = (
                self.sb.table(self.TABLA_PARTIDAS)
                .upsert(registro, on_conflict="empresa_id,ano_gravable,codigo")
                .execute()
            )
            return response.data[0] if response.data else registro
        except Exception as e:
            log.exception("Error guardando partida")
            raise RuntimeError(f"No se pudo guardar la partida: {e}") from e

    def eliminar_partida(self, empresa_id: str, ano_gravable: int, codigo: str) -> None:
        """Elimina una partida del catálogo de la empresa para un año."""
        self.sb.table(self.TABLA_PARTIDAS).delete().eq("empresa_id", empresa_id).eq(
            "ano_gravable", ano_gravable
        ).eq("codigo", codigo).execute()
