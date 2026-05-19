"""
core/dian_fe/modelos.py

Modelos de datos para Factura Electrónica de Venta DIAN.

Diseñados para JIPER SAS (restaurante con INC 8%, responsable de IVA)
pero generales para cualquier emisor.

Estructura jerárquica:

    Factura
      ├── emisor: ParteFE          (JIPER SAS — vendedor)
      ├── adquiriente: ParteFE     (cliente comprador)
      ├── resolucion: Resolucion   (la 18760000001 SETP)
      ├── lineas: list[LineaFactura]
      │     └── impuestos: list[ImpuestoLinea] (IVA, INC por línea)
      ├── impuestos_totales: list[ImpuestoTotal] (suma por tipo)
      ├── retenciones: list[Retencion]
      ├── descuentos_globales: list[Descuento]
      ├── medio_pago: MedioPago
      └── totales: TotalesFE

Convenciones:
  - Valores monetarios: Decimal con 2 decimales (COP no usa más)
  - Cantidades: Decimal con 6 decimales (DIAN exige hasta 6 para unitarios)
  - Porcentajes: Decimal (ej. 8.00 para 8%)
  - Fechas: datetime con timezone
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal


# ════════════════════════════════════════════════════════════════════════
# Códigos DIAN (tabla 13.x del Anexo Técnico)
# ════════════════════════════════════════════════════════════════════════

# Tipo de documento identificación (tabla 13.3)
TIPO_DOC_RC = "11"          # Registro civil
TIPO_DOC_TI = "12"          # Tarjeta identidad
TIPO_DOC_CC = "13"          # Cédula ciudadanía
TIPO_DOC_PERMISO = "21"     # Permiso especial
TIPO_DOC_CE = "22"          # Cédula extranjería
TIPO_DOC_NIT = "31"         # NIT
TIPO_DOC_PASAPORTE = "41"   # Pasaporte
TIPO_DOC_DEX = "42"         # Doc identificación extranjero
TIPO_DOC_PEP = "47"         # Permiso por protección temporal
TIPO_DOC_NIT_OTRO = "50"    # NIT otro país
TIPO_DOC_NUIP = "91"        # NUIP

# Tipo de organización (tabla 13.1.2)
ORG_JURIDICA = "1"          # Persona jurídica
ORG_NATURAL = "2"           # Persona natural

# Régimen fiscal / Responsabilidades (tabla 13.2.6)
RESP_IVA = "O-13"           # Responsable de IVA
RESP_NO_IVA = "R-99-PN"     # No responsable
RESP_GRAN_CONTRIB = "O-15"  # Gran contribuyente
RESP_AUTORRET_RENTA = "O-23"

# Códigos de tributo (tabla 13.2.6.1)
TRIBUTO_IVA = "01"
TRIBUTO_IC = "02"           # Impuesto al consumo
TRIBUTO_ICA = "03"
TRIBUTO_INC = "04"          # Impuesto Nacional al Consumo (restaurantes 8%)
TRIBUTO_ZZ = "ZZ"           # No aplica

# Tipo de factura (tabla 13.1.3)
TIPO_FACTURA_VENTA = "01"           # Factura electrónica de Venta
TIPO_FACTURA_EXPORTACION = "02"     # Factura electrónica de Exportación
TIPO_FACTURA_CONTINGENCIA = "03"    # Factura electrónica de contingencia
TIPO_DOCUMENTO_SOPORTE = "05"       # Documento soporte adquisiciones

# Medios de pago (tabla 13.1.6)
MEDIO_PAGO_EFECTIVO = "10"
MEDIO_PAGO_TARJETA_DEBITO = "42"
MEDIO_PAGO_TARJETA_CREDITO = "48"
MEDIO_PAGO_TRANSFERENCIA = "47"
MEDIO_PAGO_CONSIGNACION = "23"
MEDIO_PAGO_OTRO = "ZZZ"

# Forma de pago (tabla 13.1.5)
FORMA_PAGO_CONTADO = "1"
FORMA_PAGO_CREDITO = "2"

# Unidades de medida (tabla 13.1.x — más comunes para restaurante)
UNIDAD_UNIDAD = "94"        # Una "unidad" genérica
UNIDAD_KILOGRAMO = "KGM"
UNIDAD_LITRO = "LTR"
UNIDAD_PORCION = "94"       # Para platos


# ════════════════════════════════════════════════════════════════════════
# Resolución de numeración
# ════════════════════════════════════════════════════════════════════════

@dataclass
class Resolucion:
    """
    Resolución DIAN de autorización de numeración.

    Para el set de pruebas de JIPER:
      numero = "18760000001"
      prefijo = "SETP"
      rango_desde = 990000000
      rango_hasta = 995000000
      fecha_desde = 2019-01-19
      fecha_hasta = 2030-01-19
    """
    numero: str                       # Ej. "18760000001"
    prefijo: str                      # Ej. "SETP"
    rango_desde: int                  # Ej. 990000000
    rango_hasta: int                  # Ej. 995000000
    fecha_desde: datetime
    fecha_hasta: datetime
    clave_tecnica: str = ""           # Clave técnica del set (TestSetId-vinculada)

    def es_folio_valido(self, folio: int) -> bool:
        return self.rango_desde <= folio <= self.rango_hasta

    def numero_factura(self, folio: int) -> str:
        """Devuelve el número de factura completo: PREFIJOFOLIO (ej. SETP990000001)."""
        return f"{self.prefijo}{folio}"


# ════════════════════════════════════════════════════════════════════════
# Partes (emisor / adquiriente)
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ParteFE:
    """
    Una parte de la factura: vendedor o comprador.

    Para JIPER (emisor):
      nit="901038325", dv="1", razon_social="JIPER SAS"
      tipo_organizacion=ORG_JURIDICA
      tipo_documento_id=TIPO_DOC_NIT
      responsabilidades=["O-13"]  (responsable IVA)
      regimen_fiscal="48"  (responsable IVA)
      ...
    """
    # Identificación
    numero_documento: str             # NIT/CC sin DV
    tipo_documento_id: str            # TIPO_DOC_NIT, TIPO_DOC_CC, etc.
    dv: str = ""                      # Solo para NIT
    razon_social: str = ""
    nombre_comercial: Optional[str] = None

    # Organización
    tipo_organizacion: str = ORG_JURIDICA

    # Régimen
    responsabilidades: list[str] = field(default_factory=list)   # ["O-13", ...]
    regimen_fiscal_codigo: str = "48"  # 48=Responsable IVA, 49=No responsable

    # Dirección
    direccion: str = ""
    municipio_codigo: str = "05001"   # DANE — Medellín default
    municipio_nombre: str = "Medellín"
    departamento_codigo: str = "05"   # Antioquia
    departamento_nombre: str = "Antioquia"
    pais_codigo: str = "CO"
    pais_nombre: str = "Colombia"
    codigo_postal: str = ""

    # Contacto
    telefono: Optional[str] = None
    email: Optional[str] = None

    # Actividad económica (CIIU)
    actividad_economica: str = "5611"  # Default restaurante

    @property
    def es_persona_natural(self) -> bool:
        return self.tipo_organizacion == ORG_NATURAL

    @property
    def es_juridica(self) -> bool:
        return self.tipo_organizacion == ORG_JURIDICA

    @property
    def es_responsable_iva(self) -> bool:
        return RESP_IVA in self.responsabilidades or self.regimen_fiscal_codigo == "48"

    @property
    def identificacion_completa(self) -> str:
        """Devuelve NIT-DV o el documento tal cual."""
        if self.tipo_documento_id == TIPO_DOC_NIT and self.dv:
            return f"{self.numero_documento}-{self.dv}"
        return self.numero_documento


# ════════════════════════════════════════════════════════════════════════
# Items, líneas, impuestos
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ImpuestoLinea:
    """
    Un impuesto aplicado a UNA línea de la factura.

    Ej. IVA 19%: codigo="01", porcentaje=Decimal("19.00")
    Ej. INC 8%: codigo="04", porcentaje=Decimal("8.00")
    Ej. INC exento: codigo="04", porcentaje=Decimal("0.00")
    """
    codigo: str                       # TRIBUTO_IVA, TRIBUTO_INC, etc.
    nombre: str                       # "IVA", "INC", etc.
    porcentaje: Decimal               # Ej. Decimal("8.00")
    base_gravable: Decimal            # Sobre lo que se calcula
    valor: Decimal                    # base * porcentaje / 100

    @classmethod
    def inc_8_porciento(cls, base: Decimal) -> "ImpuestoLinea":
        """Helper para INC 8% típico de restaurante JIPER."""
        return cls(
            codigo=TRIBUTO_INC,
            nombre="INC",
            porcentaje=Decimal("8.00"),
            base_gravable=base,
            valor=(base * Decimal("0.08")).quantize(Decimal("0.01")),
        )

    @classmethod
    def iva_19_porciento(cls, base: Decimal) -> "ImpuestoLinea":
        """Helper para IVA 19%."""
        return cls(
            codigo=TRIBUTO_IVA,
            nombre="IVA",
            porcentaje=Decimal("19.00"),
            base_gravable=base,
            valor=(base * Decimal("0.19")).quantize(Decimal("0.01")),
        )

    @classmethod
    def iva_5_porciento(cls, base: Decimal) -> "ImpuestoLinea":
        return cls(
            codigo=TRIBUTO_IVA,
            nombre="IVA",
            porcentaje=Decimal("5.00"),
            base_gravable=base,
            valor=(base * Decimal("0.05")).quantize(Decimal("0.01")),
        )


@dataclass
class Descuento:
    """
    Descuento aplicado, por línea o global.

    DIAN distingue dos tipos:
      - allowanceChargeReasonCode con razón específica
      - amount: monto del descuento
      - baseAmount: sobre qué se aplica
    """
    es_descuento: bool = True         # True=descuento, False=cargo
    razon: str = ""                   # Descripción
    codigo_razon: str = "00"          # Tabla DIAN 13.2.5
    porcentaje: Optional[Decimal] = None
    monto: Decimal = Decimal("0.00")
    base: Decimal = Decimal("0.00")


@dataclass
class LineaFactura:
    """
    Una línea/producto en la factura.

    Cantidad x Precio_unitario = Subtotal_bruto
    Subtotal_bruto - Descuento_línea = Base_gravable
    Base_gravable + Impuestos = Total_línea
    """
    numero_linea: int                 # 1, 2, 3...

    # Producto/servicio
    codigo_producto: str              # Código interno (SKU)
    descripcion: str
    codigo_estandar: Optional[str] = None       # Código DIAN/UNSPSC
    tipo_codigo_estandar: str = "999"           # 001=UNSPSC, 999=propio

    # Cantidad y precio
    cantidad: Decimal = Decimal("1.000000")
    unidad: str = UNIDAD_UNIDAD                  # Tabla DIAN unidades
    precio_unitario: Decimal = Decimal("0.00")   # Sin impuestos

    # Subtotales calculados
    subtotal_bruto: Decimal = Decimal("0.00")    # cantidad * precio_unitario
    descuentos: list[Descuento] = field(default_factory=list)
    base_gravable: Decimal = Decimal("0.00")     # subtotal - descuentos
    impuestos: list[ImpuestoLinea] = field(default_factory=list)
    total_linea: Decimal = Decimal("0.00")       # base + suma de impuestos

    # Marca/notas opcionales
    marca: Optional[str] = None
    modelo: Optional[str] = None
    notas: Optional[str] = None

    def calcular_totales(self) -> None:
        """Calcula subtotal, base y total a partir de cantidad/precio/descuentos/impuestos."""
        self.subtotal_bruto = (self.cantidad * self.precio_unitario).quantize(Decimal("0.01"))

        descuento_total = sum((d.monto for d in self.descuentos), Decimal("0"))
        self.base_gravable = (self.subtotal_bruto - descuento_total).quantize(Decimal("0.01"))

        # Recalcular impuestos sobre la base gravable
        for imp in self.impuestos:
            imp.base_gravable = self.base_gravable
            imp.valor = (self.base_gravable * imp.porcentaje / Decimal("100")).quantize(Decimal("0.01"))

        impuestos_total = sum((i.valor for i in self.impuestos), Decimal("0"))
        self.total_linea = (self.base_gravable + impuestos_total).quantize(Decimal("0.01"))


# ════════════════════════════════════════════════════════════════════════
# Pago, retenciones
# ════════════════════════════════════════════════════════════════════════

@dataclass
class MedioPago:
    """Medio y forma de pago."""
    forma: str = FORMA_PAGO_CONTADO          # 1=contado, 2=crédito
    medio: str = MEDIO_PAGO_EFECTIVO          # 10=efectivo, 42=débito, etc.
    fecha_vencimiento: Optional[datetime] = None
    referencia: Optional[str] = None          # Número de transacción


@dataclass
class Retencion:
    """
    Retención practicada por el comprador al vendedor.

    Ej. Retención en la fuente 2.5% sobre 1.000.000 = 25.000
    """
    codigo: str                        # "06"=Renta, "05"=IVA, "07"=ICA
    nombre: str
    porcentaje: Decimal
    base_gravable: Decimal
    valor: Decimal


# ════════════════════════════════════════════════════════════════════════
# Totales agregados
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ImpuestoTotal:
    """Suma de un tipo de impuesto en toda la factura."""
    codigo: str
    nombre: str
    base_gravable: Decimal             # Suma de bases
    valor: Decimal                     # Suma de impuestos
    porcentaje: Decimal                # Tasa (si única)


@dataclass
class TotalesFE:
    """
    Totales calculados de la factura.

    Estructura LegalMonetaryTotal de UBL:
      LineExtensionAmount   = suma de bases gravables (sin impuestos)
      TaxExclusiveAmount    = suma de bases sujetas a impuesto
      TaxInclusiveAmount    = LineExtension + impuestos
      AllowanceTotalAmount  = suma de descuentos globales
      ChargeTotalAmount     = suma de cargos globales
      PrePaidAmount         = anticipos
      PayableAmount         = total a pagar
    """
    line_extension: Decimal = Decimal("0.00")
    tax_exclusive: Decimal = Decimal("0.00")
    tax_inclusive: Decimal = Decimal("0.00")
    allowance_total: Decimal = Decimal("0.00")
    charge_total: Decimal = Decimal("0.00")
    prepaid: Decimal = Decimal("0.00")
    payable: Decimal = Decimal("0.00")


# ════════════════════════════════════════════════════════════════════════
# Factura completa
# ════════════════════════════════════════════════════════════════════════

@dataclass
class Factura:
    """
    Factura Electrónica de Venta DIAN.

    Antes de generar XML, llamar a calcular_totales() para que
    los subtotales y totales queden coherentes.
    """
    # Identificación
    tipo_factura: str = TIPO_FACTURA_VENTA      # "01" venta
    folio: int = 0                              # Solo el número (ej. 990000001)
    fecha_emision: datetime = field(default_factory=datetime.now)
    fecha_vencimiento: Optional[datetime] = None
    moneda: str = "COP"

    # Resolución (necesaria para construir el número completo)
    resolucion: Optional[Resolucion] = None

    # Partes
    emisor: Optional[ParteFE] = None
    adquiriente: Optional[ParteFE] = None

    # Líneas
    lineas: list[LineaFactura] = field(default_factory=list)

    # Impuestos totales
    impuestos_totales: list[ImpuestoTotal] = field(default_factory=list)

    # Retenciones
    retenciones: list[Retencion] = field(default_factory=list)

    # Descuentos / cargos globales
    descuentos_globales: list[Descuento] = field(default_factory=list)
    cargos_globales: list[Descuento] = field(default_factory=list)

    # Pago
    medio_pago: MedioPago = field(default_factory=MedioPago)

    # Totales
    totales: TotalesFE = field(default_factory=TotalesFE)

    # Datos del software emisor (DIAN)
    software_id: str = ""                # SoftwareID asignado por DIAN
    software_security_code: str = ""     # PIN del software
    clave_tecnica: str = ""              # Clave técnica del set / producción
    ambiente: Literal["1", "2"] = "2"    # 1=prod, 2=habilitación

    # Notas adicionales
    notas: list[str] = field(default_factory=list)

    # CUFE (se calcula con cufe_calculator)
    cufe: str = ""

    @property
    def numero_factura(self) -> str:
        """Devuelve PREFIJOFOLIO (ej. SETP990000001)."""
        if self.resolucion:
            return self.resolucion.numero_factura(self.folio)
        return str(self.folio)

    def calcular_totales(self) -> None:
        """
        Recalcula todos los subtotales y agregados a partir de las líneas.

        Orden:
          1. Recalcular cada línea (cantidad*precio, descuentos, impuestos)
          2. Sumar impuestos por código a impuestos_totales
          3. Llenar TotalesFE
        """
        # 1) Cada línea
        for linea in self.lineas:
            linea.calcular_totales()

        # 2) Agregar impuestos por código
        impuestos_dict: dict[str, dict] = {}
        for linea in self.lineas:
            for imp in linea.impuestos:
                key = (imp.codigo, imp.porcentaje)
                if key not in impuestos_dict:
                    impuestos_dict[key] = {
                        "codigo": imp.codigo,
                        "nombre": imp.nombre,
                        "porcentaje": imp.porcentaje,
                        "base": Decimal("0"),
                        "valor": Decimal("0"),
                    }
                impuestos_dict[key]["base"] += imp.base_gravable
                impuestos_dict[key]["valor"] += imp.valor

        self.impuestos_totales = [
            ImpuestoTotal(
                codigo=d["codigo"], nombre=d["nombre"],
                porcentaje=d["porcentaje"],
                base_gravable=d["base"].quantize(Decimal("0.01")),
                valor=d["valor"].quantize(Decimal("0.01")),
            )
            for d in impuestos_dict.values()
        ]

        # 3) Totales agregados
        line_ext = sum((l.base_gravable for l in self.lineas), Decimal("0"))
        tax_total = sum((i.valor for i in self.impuestos_totales), Decimal("0"))
        descuento_global = sum((d.monto for d in self.descuentos_globales), Decimal("0"))
        cargo_global = sum((c.monto for c in self.cargos_globales), Decimal("0"))

        self.totales = TotalesFE(
            line_extension=line_ext.quantize(Decimal("0.01")),
            tax_exclusive=line_ext.quantize(Decimal("0.01")),
            tax_inclusive=(line_ext + tax_total).quantize(Decimal("0.01")),
            allowance_total=descuento_global.quantize(Decimal("0.01")),
            charge_total=cargo_global.quantize(Decimal("0.01")),
            prepaid=Decimal("0.00"),
            payable=(line_ext + tax_total - descuento_global + cargo_global).quantize(Decimal("0.01")),
        )
