-- ============================================================
-- 017_catalogos_plantilla_y_siembra.sql
-- Estructura de catálogos por defecto para INTEGRAL:
--   * Plantillas globales (PUC, comprobantes, tipos IVA/retención,
--     conceptos, terceros base) que se COPIAN a cada empresa nueva.
--   * Directorio global de terceros (autocompletar NIT).
--   * Función cn_inicializar_empresa() + TRIGGER en empresas.
-- Idempotente. Aplica desde Supabase → SQL Editor → Run.
-- Fecha: 2026-07-18
-- ============================================================

CREATE TABLE IF NOT EXISTS public.cn_plan_cuentas_plantilla (
    codigo      text PRIMARY KEY,
    nombre      text NOT NULL,
    naturaleza  char(1),
    tipo_cuenta char(1),
    maneja_nit  boolean DEFAULT false,
    maneja_cc   boolean DEFAULT false,
    maneja_base boolean DEFAULT false,
    nivel       int
);
TRUNCATE public.cn_plan_cuentas_plantilla;
INSERT INTO public.cn_plan_cuentas_plantilla (codigo,nombre,naturaleza,tipo_cuenta,maneja_nit,maneja_cc,maneja_base,nivel) VALUES
('11','DISPONIBLE','D',NULL,false,false,false,2),
('1105','CAJA','D',NULL,false,false,false,4),
('110505','CAJA GENERAL','D',NULL,false,false,false,6),
('110510','CAJAS MENORES','D',NULL,false,false,false,6),
('110515','MONEDA EXTRANJERA','D',NULL,false,false,false,6),
('1110','BANCOS','D',NULL,false,false,false,4),
('111005','BANCOS MONEDA NACIONAL','D',NULL,false,false,false,6),
('1120','CUENTAS DE AHORROS','D',NULL,false,false,false,4),
('112005','BANCOS','D',NULL,false,false,false,6),
('112010','CORPORAC. DE AHORRO Y VIVIENDA','D',NULL,false,false,false,6),
('112015','ORGANISMOS COOPERATIVOS FINANC','D',NULL,false,false,false,6),
('12','INVERSIONES','D',NULL,false,false,false,2),
('1205','INVERSION EN ACCIONES','D',NULL,false,false,false,4),
('120550','ACCIONES ACT. FINANCIERA','D',NULL,false,false,false,6),
('120599','AJUS.INFL. EN ACCIONES','D',NULL,false,false,false,6),
('1215','INVERSION EN BONOS','D',NULL,false,false,false,4),
('121505','BONOS PUBLICOS MONEDA NACIONAL','D',NULL,false,false,false,6),
('1225','INVERSION EN CERTIFICADOS','D',NULL,false,false,false,4),
('122505','CERTIF. DE DEPOSITO A TERMINO','D',NULL,false,false,false,6),
('1235','INVERIONS EN TITULOS','D',NULL,false,false,false,4),
('123540','TITULOS DE AHORRO NAL.(T.A.N)','D',NULL,false,false,false,6),
('1255','OBLIGATORIAS','D',NULL,false,false,false,4),
('125505','BONOS DE FINANCIAMIENTO ESPECI','D',NULL,false,false,false,6),
('13','DEUDORES','D','C',true,false,false,2),
('1305','CLIENTES','D','C',true,false,false,4),
('130505','NACIONALES','D','C',true,false,false,6),
('130510','DEL EXTERIOR','D','C',true,false,false,6),
('1325','CXC A SOCIOS Y ACCIONISTAS','D','C',true,false,false,4),
('132505','CXC A SOCIOS','D','C',true,false,false,6),
('132510','CXC A ACCIONISTAS','D','C',true,false,false,6),
('1355','ANTIC.IMPTOS Y CONTRIB. O SALD','D','C',true,false,false,4),
('135505','ANTICIPO DE IMPUESTOS DE RENTA','D','C',true,false,false,6),
('135515','RETENCION EN LA FUENTE POR COB','D','C',true,false,false,6),
('1365','CUENTAS POR COBRAR A TRABAJADO','D','C',true,false,false,4),
('1370','PRESTAMOS A PARTICULARES','D','C',true,false,false,4),
('137005','PREST.PARTIC.GARANTIA REAL.','D','C',true,false,false,6),
('137010','PREST.PARTIC.GARANTIA PERSONAL','D','C',true,false,false,6),
('1399','PROVISION DEUDORES','D','C',true,false,false,4),
('139905','PROVISION CLIENTES','D','C',true,false,false,6),
('139960','PROVISION CXC TRABAJADORES','D','C',true,false,false,6),
('14','INVENTARIOS','D',NULL,false,false,false,2),
('1405','MATERIAS PRIMAS','D',NULL,false,false,false,4),
('140505','INVENTARIO MATERIAS PRIMAS','D',NULL,false,false,false,6),
('140599','AJUS.INLF.INVENT MAT.PRIMAS','D',NULL,false,false,false,6),
('1410','PRODUCTOS EN PROCESO','D',NULL,false,false,false,4),
('141001','INV. PRODUCTOS EN PROCESO','D',NULL,false,false,false,6),
('141099','AJUS.INFL.INVENT.PROD.PROCESO','D',NULL,false,false,false,6),
('1415','OBRAS EN CONSTRUCC.EN CURSO','D',NULL,false,false,false,4),
('141501','INV.OBRAS EN CONSTR.EN CURSO','D',NULL,false,false,false,6),
('141599','AJUS.INFL.INV.OBRAS EN CONS','D',NULL,false,false,false,6),
('1430','INV.PRODUCTOS TERMINADOS','D',NULL,false,false,false,4),
('143005','INV.PRODUC.TERMIN.MANUFACTUR.','D',NULL,false,false,false,6),
('143099','AJUS.INFL.INV.PROD.TERM.','D',NULL,false,false,false,6),
('143505','MERCANCIAS NACIONALES','D',NULL,false,false,false,6),
('143599','AJUS.INFL. INVENTARIOS','D',NULL,false,false,false,6),
('15','PROPIEDADES PLANTA Y EQUIPO','D',NULL,false,false,false,2),
('1504','TERRENOS','D',NULL,false,false,false,4),
('150405','COSTO TERRENOS URBANOS','D',NULL,false,false,false,6),
('150410','COSTO TERRENOS RURALES','D',NULL,false,false,false,6),
('150499','AJUS.INFL. TERRENOS','D',NULL,false,false,false,6),
('1516','CONSTRUCCIONES Y EDIFICACIONES','D',NULL,false,false,false,4),
('151605','COSTO EDIFICIOS','D',NULL,false,false,false,6),
('151610','COSTO OFICINAS','D',NULL,false,false,false,6),
('151615','COSTO ALMACENES','D',NULL,false,false,false,6),
('151699','AJUS.INFL. COSTO CONST.Y EDIF.','D',NULL,false,false,false,6),
('1520','MAQUINARIA Y EQUIPO','D',NULL,false,false,false,4),
('152005','COSTO MAQUINARIA Y EQUIPO','D',NULL,false,false,false,6),
('152099','AJUS.INFL. COSTO MAQ Y EQU.','D',NULL,false,false,false,6),
('1524','EQUIPO DE OFICINA','D',NULL,false,false,false,4),
('152405','COSTO MUEBLES Y ENSERES','D',NULL,false,false,false,6),
('152410','COSTO EQUIPOS','D',NULL,false,false,false,6),
('152495','COSTO OTROS','D',NULL,false,false,false,6),
('152499','AJUS.INFL. EQUIP. OFICINA','D',NULL,false,false,false,6),
('1528','EQUIPO COMPUTAC.Y COMUNICAC.','D',NULL,false,false,false,4),
('152805','COSTO EQUIPO PROCESAM.DATOS','D',NULL,false,false,false,6),
('152810','COSTO EQUIPO TELECOMUNICACION','D',NULL,false,false,false,6),
('152815','COSTO EQUIPOS DE RADIO','D',NULL,false,false,false,6),
('152825','COSTO LINEAS TELEFONICAS','D',NULL,false,false,false,6),
('152895','OTROS','D',NULL,false,false,false,6),
('152899','AJUS.INFL.EQ.COMP.Y.COMUN','D',NULL,false,false,false,6),
('1540','FLOTA Y EQUIPO DE TRANSPORTE','D',NULL,false,false,false,4),
('154005','COSTO AUTOS CAMIONET Y CAMP.','D',NULL,false,false,false,6),
('154008','COSTO CAMIONES VOLQ.Y FURGONES','D',NULL,false,false,false,6),
('154010','COSTO TRACTOMULAS Y REMOLQUES','D',NULL,false,false,false,6),
('154015','COSTO BUSES Y BUSETAS','D',NULL,false,false,false,6),
('154030','COSTO MOTOCICLETAS','D',NULL,false,false,false,6),
('154099','AJUST INFL. FLOTA Y EQU TRANS','D',NULL,false,false,false,6),
('1592','DEPRECIACION ACUMULADA','D',NULL,false,false,false,4),
('159205','DEPREC. CONSTRUC. Y EDIFICAC.','D',NULL,false,false,false,6),
('159210','DEPREC. MAQ. Y EQUIPO','D',NULL,false,false,false,6),
('159215','DEP. EQUIPO DE OFICINA','D',NULL,false,false,false,6),
('159235','DEP FLOTA Y EQU. DE TRANSP','D',NULL,false,false,false,6),
('159299','AJUS. POR INFL. DEPRECIACCON','D',NULL,false,false,false,6),
('17','DIFERIDOS','D',NULL,false,false,false,2),
('1705','GASTOS PAGADOS POR ANTICIPADO','D',NULL,false,false,false,4),
('170505','INTERESES PREPAGADOS','D',NULL,false,false,false,6),
('170510','HONORARIOS PREPAGADOS','D',NULL,false,false,false,6),
('170515','COMISIONES PREPAGADOS','D',NULL,false,false,false,6),
('170520','SEGUROS Y FIANZAS PREPAGADOS','D',NULL,false,false,false,6),
('170525','ARRENDAMIENTOS PREPAGADOS','D',NULL,false,false,false,6),
('170535','MANTENIMIENT EQUIP.PREPAGADOS','D',NULL,false,false,false,6),
('170540','SERVICIOS PREPAGADOS','D',NULL,false,false,false,6),
('170545','SUSCRIPCIONES PREPAGADAS','D',NULL,false,false,false,6),
('1710','CARGOS DIFERIDOS','D',NULL,false,false,false,4),
('171016','PROGRAMAS PARA COMPUT.SOFTWARE','D',NULL,false,false,false,6),
('171020','UTILES Y PAPELERIA DIFERIDA','D',NULL,false,false,false,6),
('171044','PUBLIC,PROPAG Y AVISOS DIFERID','D',NULL,false,false,false,6),
('171099','AJUSTES INFLACION CARGO.DIFER.','D',NULL,false,false,false,6),
('18','OTROS ACTIVOS','D',NULL,false,false,false,2),
('1805','BIENES DE ARTE Y CULTURA','D',NULL,false,false,false,4),
('180505','OBRAS DE ARTE','D',NULL,false,false,false,6),
('180510','BIBLIOTECAS','D',NULL,false,false,false,6),
('180595','OTROS','D',NULL,false,false,false,6),
('180599','AJUSTES INFLACION OTROS ACTIV.','D',NULL,false,false,false,6),
('21','OBLIGACIONES FINANCIERAS','C',NULL,false,false,false,2),
('2105','BANCOS NACIONALES','C',NULL,false,false,false,4),
('210505','SOBREGIROS','C',NULL,false,false,false,6),
('210510','PAGARES','C',NULL,false,false,false,6),
('2110','BANCOS DEL EXTERIOR','C',NULL,false,false,false,4),
('211005','SOBREGIROS','C',NULL,false,false,false,6),
('211010','PAGARES','C',NULL,false,false,false,6),
('22','PROVEEDORES','C',NULL,false,false,false,2),
('2205','PROVEEDORES NACIONALES','C','C',true,false,false,4),
('220515','PROVEEDORES DE MERCANCIAS','C','C',true,false,false,6),
('2210','PROVEEDORES DEL EXTERIOR','C',NULL,false,false,false,4),
('221005','PROVEEDORES DEL EXTERIOR','C',NULL,false,false,false,6),
('23','CUENTAS POR PAGAR','C',NULL,false,false,false,2),
('2355','DEUDAS CON ACCIONIST.O SOCIOS','C',NULL,false,false,false,4),
('235505','DEUDAS CON ACCIONISTAS','C',NULL,false,false,false,6),
('235510','DEUDAS CON SOCIOS','C',NULL,false,false,false,6),
('2365','RETENCION EN LA FUENTE','C','C',true,false,true,4),
('236597','PAGOS DE RETEFUENTE','C','C',true,false,true,6),
('2370','RETENCIONES Y APORTES DE NOMIN','C',NULL,false,false,false,4),
('237095','OTROS','C',NULL,false,false,false,6),
('24','IMPUESTOS, GRAVAMENES Y TASAS','C',NULL,false,false,false,2),
('2404','DE RENTA Y COMPLEMENTARIOS','C',NULL,false,false,false,4),
('240405','VIGENCIA FISCAL VIGENTE','C',NULL,false,false,false,6),
('240410','VIGENCIAS FISCALES VIGENTES','C',NULL,false,false,false,6),
('2408','IMPTO SOBRE LAS VTAS POR PAGAR','C',NULL,false,false,true,4),
('240805','IVA RECAUDADO','C',NULL,false,false,true,6),
('240810','IVA VALORES DESCONTADOS','C',NULL,false,false,true,6),
('240897','PAGOS DE IVA','C',NULL,false,false,true,6),
('25','OBLIGACIONES LABORALES','C',NULL,false,false,false,2),
('2510','CESANTIAS CONSOLIDADAS','C',NULL,false,false,false,4),
('251005','LEY LABORAL ANTERIOR','C',NULL,false,false,false,6),
('251010','LEY 50/1990 Y NORMAS POST.','C',NULL,false,false,false,6),
('251097','PAGOS DE CESANTIAS','C',NULL,false,false,false,6),
('26','PASIVOS ESTIMADOS Y PROVIS.','C',NULL,false,false,false,2),
('2610','PROV. PARA OBLIGAC. LABOR.','C',NULL,false,false,false,4),
('261005','PROVISION CESANTIAS','C',NULL,false,false,false,6),
('261010','PROVISION INT. CESANTIAS','C',NULL,false,false,false,6),
('261015','PROVISION VACACIONES','C',NULL,false,false,false,6),
('261020','PROVISION PRIMA  SERVICIOS','C',NULL,false,false,false,6),
('261025','PROVISION PRESTACIONES EXTRAL.','C',NULL,false,false,false,6),
('261030','PROVISION VIATICOS','C',NULL,false,false,false,6),
('261095','OTRAS PROVISIONES','C',NULL,false,false,false,6),
('2630','PARA MANTENIMIENTO Y REPARACI.','C',NULL,false,false,false,4),
('263005','PARA MANT.Y REPAR.TERRENOS','C',NULL,false,false,false,6),
('263010','PARA MANT.Y REPAR.EDIFICACION.','C',NULL,false,false,false,6),
('263015','PARA MANT.Y REPAR.MAQ.Y EQUIPO','C',NULL,false,false,false,6),
('263095','PARA MANT.Y REPAR.OTROS','C',NULL,false,false,false,6),
('31','CAPITAL SOCIAL','C',NULL,false,false,false,2),
('3105','CAPITAL SUSCRITO Y PAGADO','C',NULL,false,false,false,4),
('310505','CAPITAL AUTORIZADO','C',NULL,false,false,false,6),
('310515','CAPITAL SUSCRITO','C',NULL,false,false,false,6),
('32','SUPERAVIT DE CAPITAL','C',NULL,false,false,false,2),
('33','RESERVAS','C',NULL,false,false,false,2),
('3305','RESERVAS OBLIGATORIAS','C',NULL,false,false,false,4),
('330505','RESERVA LEGAL','C',NULL,false,false,false,6),
('330595','OTRAS RESERVAS','C',NULL,false,false,false,6),
('34','REVALORIZACION DE PATRIMONIO','C',NULL,false,false,false,2),
('3405','AJUSTE POR INFL. DE PATRIMONIO','C',NULL,false,false,false,4),
('340505','REVAL. DE CAPITAL SOCIAL','C',NULL,false,false,false,6),
('340510','REVAL. DE SUPERAVIT DE CAPITAL','C',NULL,false,false,false,6),
('340520','REVAL.DE RESULT EJEC.ANTERIOR.','C',NULL,false,false,false,6),
('36','RESULTADOS DEL EJERCICIO','C',NULL,false,false,false,2),
('3605','UTILIDAD DE EJERCICIO','C',NULL,false,false,false,4),
('360505','UTILIDAD DEL EJERCICIO','C',NULL,false,false,false,6),
('3610','PERDIDA DE EJERCICIO','C',NULL,false,false,false,4),
('361005','PERDIDA DEL EJERCICIO','C',NULL,false,false,false,6),
('37','RESULTADOS DE EJERC. ANTERIORE','C',NULL,false,false,false,2),
('3705','UTILIDADES O EXCED. ACUMULADOS','C',NULL,false,false,false,4),
('370501','UTILIDADES ACUMULADAS','C',NULL,false,false,false,6),
('38','SUPERAVIR POR VALORIZACION','C',NULL,false,false,false,2),
('3805','SUPERAVIT DE INVERSIONES','C',NULL,false,false,false,4),
('380505','SUPERAVIT DE INVERS.ACCIONES','C',NULL,false,false,false,6),
('3810','SUPERAVIT PROP PLANTA Y EQU.','C',NULL,false,false,false,4),
('381004','SUPERAVIT POR TERRENOS','C',NULL,false,false,false,6),
('381012','SUPERAVIT POR MAQ.Y EQUIPO','C',NULL,false,false,false,6),
('41','INGRESOS OPERACIONALES','C',NULL,false,false,false,2),
('4135','CCIO AL POR MAYOR Y MENOR','C',NULL,false,false,false,4),
('413522','VTA PRODUCTOS AGROPECUARIOS','C',NULL,false,false,false,6),
('413524','VTA PRODUCTOS TEXTILES-CUEROS','C',NULL,false,false,false,6),
('413526','VTA DE PAPEL Y CARTON','C',NULL,false,false,false,6),
('413536','VTA DE ELECTRODOM.Y MUEBLES','C',NULL,false,false,false,6),
('413542','VTA MAT DE CONSTRUCCION','C',NULL,false,false,false,6),
('413599','AJUS. INFL. INGR. VTAS','C',NULL,false,false,false,6),
('4175','DEVOL REBAJAS DSCTOS EN VTAS','C',NULL,false,false,false,4),
('417505','DEVOLUCIONES EN VENTAS','C',NULL,false,false,false,6),
('417510','DESCUENTOS EN VENTAS','C',NULL,false,false,false,6),
('417599','AJUSTES POR INFLACION','C',NULL,false,false,false,6),
('42','INGRESOS NO OPERACIONALES','C',NULL,false,false,false,2),
('4210','INGR. NO OPER. FINANCIEROS','C',NULL,false,false,false,4),
('421005','INGRESOS POR INTERESES','C',NULL,false,false,false,6),
('421095','OTROS INGRESOS FINANCIEROS','C',NULL,false,false,false,6),
('421099','AJUS. INFL. INGR. FINANCIEROS','C',NULL,false,false,false,6),
('47','AJUSTES POR INFLACION','C',NULL,false,false,false,2),
('4705','CORRECCION MONETARIA','C',NULL,false,false,false,4),
('470505','C.M. INVERSIONES (CR)','C',NULL,false,false,false,6),
('470510','C.M. INVENTARIOS (CR)','C',NULL,false,false,false,6),
('470515','C.M. PROPIEDAD PLANTA Y EQUIPO','C',NULL,false,false,false,6),
('470520','C.M. INTANGIBLES (CR)','C',NULL,false,false,false,6),
('470525','C.M. ACTIVOS DIFERIDOS','C',NULL,false,false,false,6),
('470530','C.M. OTROS ACTIVOS','C',NULL,false,false,false,6),
('470540','C.M. PATRIMONIO','C',NULL,false,false,false,6),
('470550','C.M. DEPREC. ACUMULADA','C',NULL,false,false,false,6),
('470565','C.M. ING. OPERACIONALES (DB)','C',NULL,false,false,false,6),
('470568','C.M. DEVOLUC.EN VENTAS (CR)','C',NULL,false,false,false,6),
('470570','C.M. ING. NO OPERACIONALS.(DB)','C',NULL,false,false,false,6),
('470575','C.M. GTOS OPERAC. ADMON (CR)','C',NULL,false,false,false,6),
('470580','C.M. GTOS OPERAC. VENTAS (CR)','C',NULL,false,false,false,6),
('470585','C.M. GTOS NO OPERAC. (CR)','C',NULL,false,false,false,6),
('470590','C.M. COMPRAS (CR)','C',NULL,false,false,false,6),
('470591','C.M. DEVOLUC.EN COMPRAS (DB)','C',NULL,false,false,false,6),
('51','OPERACIONALES DE ADMINISTRACIO','D',NULL,false,false,false,2),
('5105','GASTOS DEL PERSONAL','D',NULL,false,false,false,4),
('510503','SALARIO INTEGRAL','D',NULL,false,false,false,6),
('510506','SUELDOS','D',NULL,false,false,false,6),
('510512','JORNALES','D',NULL,false,false,false,6),
('510515','HORAS EXTRAS Y RECARGOS','D',NULL,false,false,false,6),
('510518','COMISIONES GTOS DE PERSONAL','D',NULL,false,false,false,6),
('510521','VIATICOS','D',NULL,false,false,false,6),
('510524','INCAPACIDADES','D',NULL,false,false,false,6),
('510527','AUXILIO DE TRANSPORTE','D',NULL,false,false,false,6),
('510530','CESANTIAS','D',NULL,false,false,false,6),
('510533','INTERESES SOBRE CESANTIAS','D',NULL,false,false,false,6),
('510536','PRIMA DE SERVICIOS','D',NULL,false,false,false,6),
('510539','VACACIONES','D',NULL,false,false,false,6),
('510542','PRIMAS EXTRALEGALES','D',NULL,false,false,false,6),
('510545','AUXILIOS','D',NULL,false,false,false,6),
('510548','BONIFICACIONES','D',NULL,false,false,false,6),
('510551','DOTACION Y SUMIN. A TRABAJADOR','D',NULL,false,false,false,6),
('510554','SEGUROS','D',NULL,false,false,false,6),
('510560','INDEMNIZACIONES LABORALES','D',NULL,false,false,false,6),
('510563','CAPACITACION AL PERSONAL','D',NULL,false,false,false,6),
('510566','GASTOS DEPORTIVOS Y RECREACION','D',NULL,false,false,false,6),
('510569','APORTES AL I.S.S.','D',NULL,false,false,false,6),
('510570','APORTES FONDOS PENSIO-CESANT.','D',NULL,false,false,false,6),
('510572','APORTES CAJAS DE COMP. FAMILIA','D',NULL,false,false,false,6),
('510575','APORTES AL I.C.B.F','D',NULL,false,false,false,6),
('510578','APORTES AL SENA','D',NULL,false,false,false,6),
('510584','GASTOS MEDICOS Y DROGAS','D',NULL,false,false,false,6),
('510595','OTROS GTOS DE PERSONAL','D',NULL,false,false,false,6),
('510599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5110','GASTOS HONORARIOS DE ADMON.','D',NULL,false,false,false,4),
('511005','GASTOS HONOR.JUANTA DIRECTIVA','D',NULL,false,false,false,6),
('511015','GASTOS HONOR.AUDITORIA EXTERNA','D',NULL,false,false,false,6),
('511025','GASTOS HONOR.ASESORIA JURIDIC.','D',NULL,false,false,false,6),
('511030','GASTOS HONOR.ASESORIA FINANC.','D',NULL,false,false,false,6),
('511099','AJUSTES POR INFLACION HONORAR.','D',NULL,false,false,false,6),
('5120','GTOS DE ARRENDAMIENTOS','D',NULL,false,false,false,4),
('512005','ARRENDMTO TERRENOS','D',NULL,false,false,false,6),
('512010','ARRENDMTO CONSTRUC. Y EDIFIC.','D',NULL,false,false,false,6),
('512015','ARRENDMTO MAQUINARIA Y EQUIPO','D',NULL,false,false,false,6),
('512020','ARRENDMTO EQUIPO DE OFICINA','D',NULL,false,false,false,6),
('512025','ARRENDMTO EQ.COMP.Y COMUNICAC.','D',NULL,false,false,false,6),
('512040','ARRENDMTO FLOTA Y EQ.TRANSP.','D',NULL,false,false,false,6),
('512099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5130','SEGUROS','D',NULL,false,false,false,4),
('513005','SEGURO MANEJO','D',NULL,false,false,false,6),
('513010','SEGURO CUMPLIMIENTO','D',NULL,false,false,false,6),
('513025','SEGURO INCENDIO','D',NULL,false,false,false,6),
('513030','SEGURO TERREMOTO','D',NULL,false,false,false,6),
('513035','SEGURO SUSTRACION Y HURTO','D',NULL,false,false,false,6),
('513040','SEGURO FLOTA Y EQ. TRANSPORTE','D',NULL,false,false,false,6),
('513095','OTROS SEGUROS','D',NULL,false,false,false,6),
('513099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5135','GASTOS POR SERVICIOS','D',NULL,false,false,false,4),
('513505','ASEO Y VIGILANCIA','D',NULL,false,false,false,6),
('513510','TEMPORALES','D',NULL,false,false,false,6),
('513515','ASISTENCIA TECNICA','D',NULL,false,false,false,6),
('513520','PROCESAMIENTO ELECTRON.DATOS','D',NULL,false,false,false,6),
('513525','ACUEDUCTO Y ALCANTARILLADO','D',NULL,false,false,false,6),
('513530','ENERGIA ELECTRICA','D',NULL,false,false,false,6),
('513535','TELEFONO','D',NULL,false,false,false,6),
('513540','CORREO, PORTES Y TELEGRAMAS','D',NULL,false,false,false,6),
('513545','FAX Y TELEX','D',NULL,false,false,false,6),
('513550','TRANSPORTES, FLETES Y ACARREOS','D',NULL,false,false,false,6),
('513599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5140','GASTOS LEGALES','D',NULL,false,false,false,4),
('514005','GASTOS LEGALES-NOTARIALES','D',NULL,false,false,false,6),
('514015','GASTOS LEGALES-TRAMIT.LICENC.','D',NULL,false,false,false,6),
('514099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5145','GTOS MANTMTO Y REPARACIONES','D',NULL,false,false,false,4),
('514505','MANTMTO TERRENOS','D',NULL,false,false,false,6),
('514510','MANTMTO CONSTRUC Y EDIFIC.','D',NULL,false,false,false,6),
('514520','MANTMTO EQUIPO DE OFICINA','D',NULL,false,false,false,6),
('514525','MANTMTO EQUIPO COMP.Y COMUNIC.','D',NULL,false,false,false,6),
('514599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5155','GASTOS DE VIAJES','D',NULL,false,false,false,4),
('515505','ALOJAMIENTO Y MANUTENCION','D',NULL,false,false,false,6),
('515515','PASAJES AEREOS','D',NULL,false,false,false,6),
('515599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5195','GASTOS DIVERSOS','D',NULL,false,false,false,4),
('519520','GASTOS DE REPRES. Y REL PUBL.','D',NULL,false,false,false,6),
('519595','OTROS GTOS DIVERSOS','D',NULL,false,false,false,6),
('519599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('52','OPERACIONALES DE VENTA','D',NULL,false,false,false,2),
('5205','GASTOS DE PERSONAL','D',NULL,false,false,false,4),
('520503','SALARIO INTEGRAL','D',NULL,false,false,false,6),
('520506','SUELDOS','D',NULL,false,false,false,6),
('520518','COMISIONES','D',NULL,false,false,false,6),
('520521','VIATICOS','D',NULL,false,false,false,6),
('520530','CESANTIAS','D',NULL,false,false,false,6),
('520533','INTERESES SOBRE CESANTIAS','D',NULL,false,false,false,6),
('520536','PRIMA DE SERVICIO','D',NULL,false,false,false,6),
('520539','VACACIONES','D',NULL,false,false,false,6),
('520599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5210','HONORARIOS POR VENTAS','D',NULL,false,false,false,4),
('521010','REVISORIA FISCAL','D',NULL,false,false,false,6),
('521099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5215','GASTOS POR IMPUESTOS','D',NULL,false,false,false,4),
('521505','INDUSTRIA Y COMERCIO','D',NULL,false,false,false,6),
('521599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5235','SERVICIOS','D',NULL,false,false,false,4),
('523505','ASEO Y VIGILANCIA','D',NULL,false,false,false,6),
('523550','TRANSPORTE, FLETES Y ACARREOS','D',NULL,false,false,false,6),
('523560','PROPAGANDA Y PUBLICIDAD','D',NULL,false,false,false,6),
('523599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5240','GASTOS LEGALES','D',NULL,false,false,false,4),
('524005','NOTARIALES','D',NULL,false,false,false,6),
('524015','TRAMITES Y LICENCIAS','D',NULL,false,false,false,6),
('524099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5260','DEPRECIACIONES','D',NULL,false,false,false,4),
('526005','CONSTRUCCIONES Y EDIFICACIONES','D',NULL,false,false,false,6),
('526010','C.M. COSTO AUTOS CAMPEROS (CR)','D',NULL,false,false,false,6),
('526015','EQUIPO DE OFICINA','D',NULL,false,false,false,6),
('526035','FLOTA Y EQUIPO DE TRANSPORTE','D',NULL,false,false,false,6),
('526099','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5295','DIVERSOS','D',NULL,false,false,false,4),
('529510','LIBROS,SUSCRIPCIONES,PERIODICO','D',NULL,false,false,false,6),
('529530','UTILES, PAPELERIA Y FOTOCOPIAS','D',NULL,false,false,false,6),
('529535','COMBUSTIBLES Y LUBRICANTES','D',NULL,false,false,false,6),
('529545','TAXIS Y BUSES','D',NULL,false,false,false,6),
('529565','PARQUEADEROS','D',NULL,false,false,false,6),
('529595','OTROS','D',NULL,false,false,false,6),
('529599','AJUSTE POR INFLACION','D',NULL,false,false,false,6),
('5299','PROVISIONES','D',NULL,false,false,false,4),
('529910','GTO PROVISION DEUDORES','D',NULL,false,false,false,6),
('529999','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('53','GASTOS NO OPERACIONALES','D',NULL,false,false,false,2),
('5305','GASTOS FINANCIEROS','D',NULL,false,false,false,4),
('530505','GASTOS BANCARIOS','D',NULL,false,false,false,6),
('530515','COMISIONES FINANCIERAS','D',NULL,false,false,false,6),
('530520','INTERESES FINANCIEROS','D',NULL,false,false,false,6),
('530599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('5395','GASTOS DIVERSOS','D',NULL,false,false,false,4),
('539595','OTROS GTOS DIVERSOS NO OPERAC.','D',NULL,false,false,false,6),
('539599','AJUSTE INFL. GTOS DIVERSOS','D',NULL,false,false,false,6),
('62','COMPRAS','D',NULL,false,false,false,2),
('6205','COMPRAS DE MERCANCIAS','D',NULL,false,false,false,4),
('620505','MERCANCIAS PARA LA VENTA','D',NULL,false,false,false,6),
('620599','AJUSTE INFL. COMPRAS DE MCIA.','D',NULL,false,false,false,6),
('6225','DEV. REBAJAS Y DSCTOS COMPRAS','D',NULL,false,false,false,4),
('622505','DEVOL. COMP. DE MERCANCIAS','D',NULL,false,false,false,6),
('622599','AJUSTES POR INFLACION','D',NULL,false,false,false,6),
('72','MANO DE OBRA','D',NULL,false,false,false,2),
('7205','MANO DE OBRA','D',NULL,false,false,false,4),
('720506','SUELDOS','D',NULL,false,false,false,6),
('720512','JORNALES','D',NULL,false,false,false,6),
('720515','HORAS EXTRAS','D',NULL,false,false,false,6),
('720599','AJUSTES POR INFLACION','D',NULL,false,false,false,6);

CREATE TABLE IF NOT EXISTS public.cn_comprobantes_plantilla (codigo text PRIMARY KEY, nombre text NOT NULL);
INSERT INTO public.cn_comprobantes_plantilla (codigo,nombre) VALUES ('1','Recibo de caja'),('2','Comprobante de egreso'),('3','Causación / factura de compra'),('4','Nota de contabilidad'),('5','Venta / factura'),('9','Ajuste PILA') ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cn_tipos_iva_plantilla (codigo text PRIMARY KEY, nombre text, tarifa numeric(7,4), cuenta text, tipo char(1));
INSERT INTO public.cn_tipos_iva_plantilla VALUES ('IVA19','IVA 19% descontable (compras)',19,'240820','C'),('IVA5','IVA 5% descontable (compras)',5,'240820','C'),('IVA0','IVA 0% / excluido',0,NULL,'C'),('IVA19V','IVA 19% generado (ventas)',19,'240810','V'),('IVA5V','IVA 5% generado (ventas)',5,'240810','V') ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cn_tipos_retencion_plantilla (codigo text PRIMARY KEY, nombre text, tarifa numeric(7,4), base_calculo text, base_uvt numeric(10,2), cuenta text, clase text);
INSERT INTO public.cn_tipos_retencion_plantilla VALUES ('RFCOMP','ReteFuente compras 2.5%',2.5,'base',27,'236540','fuente'),('RFSERV4','ReteFuente servicios 4% (declar.)',4,'base',4,'236525','fuente'),('RFSERV6','ReteFuente servicios 6% (no dec.)',6,'base',4,'236525','fuente'),('RFHON10','ReteFuente honorarios 10%',10,'base',0,'236515','fuente'),('RFHON11','ReteFuente honorarios 11%',11,'base',0,'236515','fuente'),('RFARR','ReteFuente arrendamientos 3.5%',3.5,'base',27,'236530','fuente'),('RFAGRO','ReteFuente compras agrícolas/pecuarios 1.5%',1.5,'base',92,'236540','fuente'),('RFCAFE','ReteFuente café pergamino/cereza 0.5%',0.5,'base',160,'236540','fuente'),('RETEIVA','ReteIVA 15% (sobre el IVA)',15,'iva',0,'236701','iva'),('RETEICA','ReteICA (tarifa municipal)',0.7,'base',0,'236805','ica') ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cn_conceptos_plantilla (codigo text PRIMARY KEY, nombre text, naturaleza text, comprobante text, cuenta_base text, cuenta_contrapartida text, tipo_iva_codigo text, tipo_retencion_codigo text, maneja_iva boolean, maneja_retencion boolean, descripcion text);
INSERT INTO public.cn_conceptos_plantilla VALUES ('COMPRA_BIEN_19','Compra de bienes 19% + ReteCompras 2.5%','compra','3','143501','220505','IVA19','RFCOMP',true,true,'Compra gravada de mercancía/insumos.'),('COMPRA_SERV_19','Servicios 19% + ReteServicios 4%','compra','3','513535','220505','IVA19','RFSERV4',true,true,'Servicios gravados.'),('HONORARIOS','Honorarios 19% + Rete 11%','compra','3','511030','220505','IVA19','RFHON11',true,true,'Honorarios profesionales.'),('ARRENDAMIENTO','Arrendamiento 19% + Rete 3.5%','compra','3','512010','220505','IVA19','RFARR',true,true,'Arrendamiento de bienes.'),('COMPRA_AGRICOLA','Compra productos agrícolas/pecuarios (Rete 1.5%, base 92 UVT)','compra','3','143501','220505','IVA0','RFAGRO',false,true,'Productos agrícolas sin proceso industrial.'),('SERV_PUBLICOS','Servicios públicos (sin IVA ni retención)','compra','2','513535','111005','IVA0',NULL,false,false,'Servicios públicos.'),('COMPRA_EXCLUIDA','Compra excluida/exenta','compra','3','143501','220505','IVA0',NULL,false,false,'Compra excluida o exenta.'),('VENTA_19','Venta gravada 19%','venta','5','413501','130505','IVA19V',NULL,true,false,'Venta gravada con IVA generado.') ON CONFLICT (codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cn_terceros_base (nit text PRIMARY KEY, nombre text, tipo_persona char(1), dv text, regimen text);
INSERT INTO public.cn_terceros_base VALUES ('890903938','BANCOLOMBIA S.A.','J','8',NULL),('860002964','BANCO DE BOGOTA','J','4',NULL),('860003020','BANCO BILBAO VIZCAYA ARGENTARIA COLOMBIA S.A.','J','1',NULL),('860007738','BANCO DAVIVIENDA S.A.','J','9',NULL),('800197268','DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES','J','4',NULL) ON CONFLICT (nit) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.cn_directorio_terceros (nit text PRIMARY KEY, dv text, nombre text NOT NULL, tipo_persona char(1), regimen text, departamento text, municipio text);
INSERT INTO public.cn_directorio_terceros (nit,dv,nombre,tipo_persona,regimen,departamento,municipio) VALUES
('800180687','2','FONDO DE INVERSION COLECTIVA ABIERTO FIDUCUENTA','J',NULL,NULL,NULL),
('811001713','1','PROFESIONALES GINECOLOGICOS PROGYNE SAS','J',NULL,NULL,NULL),
('811006789','1','JUAN D. HOYOS DISTRIBUCIONES S.A.S','J',NULL,NULL,NULL),
('811027462','9','CENTRO DE SALUD Y BELLEZA S.A.','J',NULL,NULL,NULL),
('811045607','6','INVERSIONES EURO S.A','J',NULL,NULL,NULL),
('860000018','2','AGENCIA DE VIAJES Y TURISMO AVIATUR S.A.S','J',NULL,NULL,NULL),
('860002964','4','BANCO DE BOGOTA','J',NULL,NULL,NULL),
('860003020','1','BANCO BILBAO VIZCAYA ARGENTARIA COLOMBIA S.A.','J',NULL,NULL,NULL),
('890900608','9','ALMACENES EXITO SA','J',NULL,NULL,NULL),
('890903938','8','BANCOLOMBIA S.A.','J',NULL,NULL,NULL),
('890903939','5','POSTOBON S.A.','J',NULL,NULL,NULL),
('900410098','5','ADMINISTRACION Y NEGOCIOS NUTIBARA S.A.S.','J',NULL,NULL,NULL),
('900425129','0','INSTITUTO DE CULTURA Y PATRIMONIO DE ANTIOQUIA INSTITUTO DE CULTURA Y PATRIMONIO DE ANTIOQUIA INSTITUTO DE CULTURA Y PAT','J',NULL,NULL,NULL),
('900462228','9','CIMENTO INMUEBLES COMERCIALES S.A.S.','J',NULL,NULL,NULL),
('900480569','1','JERONIMO MARTINS COLOMBIA S.A.','J',NULL,NULL,NULL),
('900495853','4','MILAGROS GROUP S.A.S.','J',NULL,NULL,NULL),
('900509570','8','PEDESTAL CONSTRUCTORA SAS','J',NULL,NULL,NULL),
('900522508','4','INVERSIONES SUPERVAQUITA LA 33 S.A.S.','J',NULL,NULL,NULL),
('900626715','1','VM LEGAL S.A.S','J',NULL,NULL,NULL),
('900665107','8','FRUTOS TIPICOS NACIONALES S.A.S','J',NULL,NULL,NULL),
('900843898','9','RAPPI S.A.S.','J',NULL,NULL,NULL),
('901053485','4','LISTO EL POLLO COLOMBIA S.A.S','J',NULL,NULL,NULL),
('901266634','1','PROTEMIX SAS','J',NULL,NULL,NULL),
('901313091','2','ARBA COLOMBIA SAS','J',NULL,NULL,NULL),
('901422482','6','TRAZO T CONSTRUCCIONES SAS','J',NULL,NULL,NULL),
('901800615','0','CIRCULAR FACTORING SAS','J',NULL,NULL,NULL),
('901873256','2','RYU SOLES SAS','J',NULL,NULL,NULL),
('811007547','','CORPORACION INCUBADORA DE EMPR','N',NULL,NULL,NULL),
('860007738','9','BANCO DAVIVIENDA S.A.','J',NULL,NULL,NULL),
('800197268','4','DIRECCION DE IMPUESTOS Y ADUANAS NACIONALES','J',NULL,NULL,NULL)
ON CONFLICT (nit) DO NOTHING;

ALTER TABLE public.cn_plan_cuentas_plantilla ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_plan_cuentas_plantilla_read" ON public.cn_plan_cuentas_plantilla;
CREATE POLICY "cn_plan_cuentas_plantilla_read" ON public.cn_plan_cuentas_plantilla FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_plan_cuentas_plantilla_write" ON public.cn_plan_cuentas_plantilla;
CREATE POLICY "cn_plan_cuentas_plantilla_write" ON public.cn_plan_cuentas_plantilla FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_plan_cuentas_plantilla TO authenticated;
ALTER TABLE public.cn_comprobantes_plantilla ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_comprobantes_plantilla_read" ON public.cn_comprobantes_plantilla;
CREATE POLICY "cn_comprobantes_plantilla_read" ON public.cn_comprobantes_plantilla FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_comprobantes_plantilla_write" ON public.cn_comprobantes_plantilla;
CREATE POLICY "cn_comprobantes_plantilla_write" ON public.cn_comprobantes_plantilla FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_comprobantes_plantilla TO authenticated;
ALTER TABLE public.cn_tipos_iva_plantilla ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_tipos_iva_plantilla_read" ON public.cn_tipos_iva_plantilla;
CREATE POLICY "cn_tipos_iva_plantilla_read" ON public.cn_tipos_iva_plantilla FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_tipos_iva_plantilla_write" ON public.cn_tipos_iva_plantilla;
CREATE POLICY "cn_tipos_iva_plantilla_write" ON public.cn_tipos_iva_plantilla FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_tipos_iva_plantilla TO authenticated;
ALTER TABLE public.cn_tipos_retencion_plantilla ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_tipos_retencion_plantilla_read" ON public.cn_tipos_retencion_plantilla;
CREATE POLICY "cn_tipos_retencion_plantilla_read" ON public.cn_tipos_retencion_plantilla FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_tipos_retencion_plantilla_write" ON public.cn_tipos_retencion_plantilla;
CREATE POLICY "cn_tipos_retencion_plantilla_write" ON public.cn_tipos_retencion_plantilla FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_tipos_retencion_plantilla TO authenticated;
ALTER TABLE public.cn_conceptos_plantilla ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_conceptos_plantilla_read" ON public.cn_conceptos_plantilla;
CREATE POLICY "cn_conceptos_plantilla_read" ON public.cn_conceptos_plantilla FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_conceptos_plantilla_write" ON public.cn_conceptos_plantilla;
CREATE POLICY "cn_conceptos_plantilla_write" ON public.cn_conceptos_plantilla FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_conceptos_plantilla TO authenticated;
ALTER TABLE public.cn_terceros_base ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_terceros_base_read" ON public.cn_terceros_base;
CREATE POLICY "cn_terceros_base_read" ON public.cn_terceros_base FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_terceros_base_write" ON public.cn_terceros_base;
CREATE POLICY "cn_terceros_base_write" ON public.cn_terceros_base FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_terceros_base TO authenticated;
ALTER TABLE public.cn_directorio_terceros ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cn_directorio_terceros_read" ON public.cn_directorio_terceros;
CREATE POLICY "cn_directorio_terceros_read" ON public.cn_directorio_terceros FOR SELECT USING (auth.role() = 'authenticated');
DROP POLICY IF EXISTS "cn_directorio_terceros_write" ON public.cn_directorio_terceros;
CREATE POLICY "cn_directorio_terceros_write" ON public.cn_directorio_terceros FOR ALL USING (public.es_superadmin()) WITH CHECK (public.es_superadmin());
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_directorio_terceros TO authenticated;

-- ============================================================
-- Función que copia las plantillas a una empresa (idempotente)
-- ============================================================
CREATE OR REPLACE FUNCTION public.cn_inicializar_empresa(p_empresa uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  -- PUC (núcleo 014)
  INSERT INTO public.cn_plan_cuentas
      (empresa_id, codigo, nombre, naturaleza, tipo_cuenta, maneja_nit, maneja_cc, maneja_base, nivel)
  SELECT p_empresa, codigo, nombre, naturaleza, tipo_cuenta, maneja_nit, maneja_cc, maneja_base, nivel
  FROM public.cn_plan_cuentas_plantilla
  ON CONFLICT (empresa_id, codigo) DO NOTHING;

  -- Comprobantes (núcleo 014)
  INSERT INTO public.cn_comprobantes (empresa_id, codigo, nombre)
  SELECT p_empresa, codigo, nombre FROM public.cn_comprobantes_plantilla
  ON CONFLICT (empresa_id, codigo) DO NOTHING;

  -- Terceros base (requiere 015). Si no existe la tabla, se omite.
  BEGIN
    INSERT INTO public.cn_terceros (empresa_id, nit, nombre, tipo_persona, dv, regimen)
    SELECT p_empresa, nit, nombre, tipo_persona, dv, regimen FROM public.cn_terceros_base
    ON CONFLICT (empresa_id, nit) DO NOTHING;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  -- Tipos de IVA (requiere 016)
  BEGIN
    INSERT INTO public.cn_tipos_iva (empresa_id, codigo, nombre, tarifa, cuenta, tipo)
    SELECT p_empresa, codigo, nombre, tarifa, cuenta, tipo FROM public.cn_tipos_iva_plantilla
    ON CONFLICT (empresa_id, codigo) DO NOTHING;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  -- Tipos de retención (requiere 016)
  BEGIN
    INSERT INTO public.cn_tipos_retencion (empresa_id, codigo, nombre, tarifa, base_calculo, base_uvt, cuenta, clase)
    SELECT p_empresa, codigo, nombre, tarifa, base_calculo, base_uvt, cuenta, clase FROM public.cn_tipos_retencion_plantilla
    ON CONFLICT (empresa_id, codigo) DO NOTHING;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  -- Conceptos programados (requiere 016)
  BEGIN
    INSERT INTO public.cn_conceptos
        (empresa_id, codigo, nombre, naturaleza, comprobante, cuenta_base, cuenta_contrapartida,
         tipo_iva_codigo, tipo_retencion_codigo, maneja_iva, maneja_retencion, descripcion)
    SELECT p_empresa, codigo, nombre, naturaleza, comprobante, cuenta_base, cuenta_contrapartida,
           tipo_iva_codigo, tipo_retencion_codigo, maneja_iva, maneja_retencion, descripcion
    FROM public.cn_conceptos_plantilla
    ON CONFLICT (empresa_id, codigo) DO NOTHING;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;
END;
$$;

GRANT EXECUTE ON FUNCTION public.cn_inicializar_empresa(uuid) TO authenticated;

-- ============================================================
-- TRIGGER: cada empresa nueva nace con los catálogos por defecto
-- ============================================================
CREATE OR REPLACE FUNCTION public.cn_trg_inicializar_empresa()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  PERFORM public.cn_inicializar_empresa(NEW.id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS cn_after_insert_empresa ON public.empresas;
CREATE TRIGGER cn_after_insert_empresa
  AFTER INSERT ON public.empresas
  FOR EACH ROW EXECUTE FUNCTION public.cn_trg_inicializar_empresa();

-- Vista de actividades económicas (reusa el catálogo CIIU del F350)
CREATE OR REPLACE VIEW public.cn_actividades_ciiu AS
  SELECT DISTINCT codigo, actividad_economica, seccion_ciiu, tarifa_autorretencion
  FROM public.f350_catalogo_ciiu;

-- ============================================================
-- FIN 017
-- ============================================================
