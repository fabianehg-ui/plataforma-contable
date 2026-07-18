Attribute VB_Name = "Funciones"
Public CTI As Object
Private lNumeroRegistros As Integer 'Número de filas de Excel Generadas en el Asistente de Presupuestos
Private lPresupuestadoPor As Integer '0 = Cuenta, 1 = CCostos
Private lNumeroPeriodos As Integer 'Número de valores con su respectivo período de los registros o filas
Function FnPath_Programm() As String
  Dim lLength As Integer
  Dim lFileName As String
  lFileName = Trim(ThisWorkbook.Path)
  lLength = Len(lFileName)
  If Mid(lFileName, lLength, 1) <> "\" Then
    lFileName = lFileName & "\"
  End If
  FnPath_Programm = lFileName
End Function

Function FnFileExists(pFile As String) As Boolean
    On Error GoTo Error
    'get the file attributes, and make sure what
    'is being passed isnt a directory
    FnFileExists = (GetAttr(pFile) And vbArchive) = 0
Error:
    'Return False if an error occurs
    FnFileExists = False
End Function

Function FnLenguaje_Opcion(pOpcion As String) As String
   Dim lngCode As Long
   Dim lLenguaje As String
   Dim lResultado As String
   lLenguaje = "ESPAÑOL"
   lngCode = Application.LanguageSettings.LanguageID(msoLanguageIDUI)
   lResultado = ""
   Select Case lngCode
     Case 1033
         lLenguaje = "INGLES"
     Case 1034
         lLenguaje = "ESPAÑOL"
   End Select
   
   Select Case lLenguaje
     Case "ESPAÑOL"
        If pOpcion = "COMPLEMENTO" Then
            lResultado = "Complemento"
        End If
     Case "INGLES"
        If pOpcion = "COMPLEMENTO" Then
            lResultado = "Add-Ins"
        End If
   End Select
   FnLenguaje_Opcion = lResultado
End Function

Sub PrArmar_Menu_Plus()
 Set MiBarraMenú = CommandBars.ActiveMenuBar
 Set NuevoMenú = MiBarraMenú.Controls.Add(Type:=msoControlPopup, Temporary:=True)
 NuevoMenú.Caption = "Ilimitada S.A."
 Set ctrl1 = NuevoMenú.Controls.Add(Type:=msoControlButton, ID:=1)
 ctrl1.Caption = "Activar compañias"
 ctrl1.TooltipText = "Activa las compañias que al solicitar usuario, se cancelo."
 ctrl1.Style = msoButtonCaption
 ctrl1.OnAction = "PrActivarCias"
 Set ctrl2 = NuevoMenú.Controls.Add(Type:=msoControlButton, ID:=2)
 ctrl2.Caption = "Grabar presupuestos"
 ctrl2.TooltipText = "Graba los presupuestos en la hoja de Excel"
 ctrl2.Style = msoButtonCaption
 ctrl2.OnAction = "PrGrabarPresupuestosExcel"
End Sub

Sub auto_open()
 'CrearMenuImpresion
 PrArmar_Menu_Plus
 On Error GoTo Error_Plus
 Set CTI = CreateObject("Contai.Aplicacion")
 CTI.MostrarExcepciones = True
 CTI.SumarSoloMovto = True
 Exit Sub
Error_Plus:
  MsgBox "El archivo " & FnPath_Programm & "contai.dll" & " no se encuentra registrado. " & Chr(13) & Chr(13) & _
          Str(Err.Number) & "-" & Err.Description & Chr(13) & Chr(13) & _
          "Regístrelo por la opción del menú de Contai " & Chr(13) & Chr(13) & _
          " Ayuda \ Registro Plus", vbCritical
End Sub

Sub auto_Close()
On Error GoTo Salir
  Application.Volatile (True)
  CTI.liberarlicencia
  Set MiBarraMenú = CommandBars.ActiveMenuBar
  MiBarraMenú.Controls("Ilimitada S.A.").Delete
  Exit Sub
Salir:
End Sub

Private Sub PrActivarCias()
  On Error GoTo lError
  Application.Volatile (True)
  CTI.ActivarCias
  Exit Sub
lError:
  MsgBox "El archivo " & FnPath_Programm & "contai.dll" & " no se encuentra registrado. " & Chr(13) & Chr(13) & _
          Str(Err.Number) & "-" & Err.Description & Chr(13) & Chr(13) & _
          "Regístrelo por la opción del menú de Contai " & Chr(13) & Chr(13) & _
          " Ayuda \ Registro Plus", vbCritical
End Sub

Public Function FnInicializarPresupuestos(pDriveDatos, pPresupuestadoPor, pNumRegistros, pNumPeriodos As String)
  gDriveDatos = pDriveDatos
  lPresupuestadoPor = pPresupuestadoPor
  lNumeroRegistros = pNumRegistros
  lNumeroPeriodos = pNumPeriodos
  FnInicializarPresupuestos = ""
End Function

Private Function FnPuedeGrabarPresupuesto() As Boolean
    gFrGrabarPresupuestos.Show
    FnPuedeGrabarPresupuesto = Not gFrGrabarPresupuestos.GetAborto
End Function

Private Function FnAbrirPresupuestos() As Boolean
  FnAbrirPresupuestos = gPresupuesto.FnOpen
End Function

Private Function FnCerrarPresupuestos() As Boolean
  FnCerrarPresupuestos = CTI.Archivos.mCerrarPresupuesto
End Function

Private Function FnExistePresupuesto(pCta, pCC, pPer As String) As Boolean
  FnExistePresupuesto = False
  gPresupuesto.KeyNum = 0
  FnExistePresupuesto = CTI.Archivos.mExistePresupuesto(pPer & Space$(6 - Len(pPer)), pCta & Space$(20 - Len(pCta)), pCC & Space$(20 - Len(pCC)))
End Function

Private Function FnReemplazarPresupuesto(pValorPpto As Double) As Boolean
  FnReemplazarPresupuesto = CTI.Archivos.mActualizarPresupuesto(pValorPpto, False)
End Function

Private Function FnAdicionarPresupuesto(pValorPpto As Double) As Boolean
  FnAdicionarPresupuesto = CTI.Archivos.mActualizarPresupuesto(pValorPpto, True)
End Function

Private Function FnInsertarPresupuesto(pCuenta, pCCostos, pPeriodo As String, pValuePpto As Double)
  FnInsertarPresupuesto = CTI.Archivos.mInsertarPresupuesto(pCuenta, pCCostos, pPeriodo, pValuePpto)
End Function

Private Sub PrGrabarPresupuestosExcel()
  Dim mColExcel As Integer
  Dim mFilExcel As Integer
  Dim mRangoExcel As Integer
  Dim mFilPerExcel As Integer
  Dim mNumReg As Integer
  Dim mCtaAux As String
  Dim mCCAux As String
  Dim mPerAux As String
  Dim mValorAux As Double
  Dim mSigaRecorrido As Boolean
  Dim mTipoAct As Integer
  'Valida si cancela o sigue la grabacion con mensaje de pregunta para Tipo de Actualizacion
  If FnPuedeGrabarPresupuesto Then
    mTipoAct = gFrGrabarPresupuestos.GetTipoActualizacion
    If CTI.Archivos.mAbrirPresupuesto(gDriveDatos) Then 'Abrir Archivo de Presupuestos
      mRangoExcel = 3
      mFilPerExcel = 2
      gFrBarraProgreso.Show
      gFrBarraProgreso.Inicializar (lNumeroRegistros)
      mNumReg = lNumeroRegistros + 2 'Mas los titulos y la fila en blanco
      For mFilExcel = 2 To mNumReg - 1
        Range("A" & Trim(Str$(mRangoExcel)), "A" & Trim(Str$(mRangoExcel))).Select
        mColExcel = 4
        mSigaRecorrido = True
        While (Not gUtilidades.FnVacio(ActiveCell.Value)) And mSigaRecorrido
          If lPresupuestadoPor = 0 Then 'Es por cuenta
            mCtaAux = ActiveCell.Offset(0, 0).Value
            mCCAux = ActiveCell.Offset(0, 2).Value
          Else 'Es centro de costos
            mCtaAux = ActiveCell.Offset(0, 2).Value
            mCCAux = ActiveCell.Offset(0, 0).Value
          End If
          mPerAux = ActiveCell.Offset(-mFilPerExcel, mColExcel).Value
          mValorAux = CDbl(ActiveCell.Offset(0, mColExcel).Value)
          'Validar si existe el Presupuesto
          If FnExistePresupuesto(mCtaAux, mCCAux, mPerAux) Then
            If mTipoAct = 1 Then '1 = Adicionar
              mSigaRecorrido = FnAdicionarPresupuesto(mValorAux) 'Adicionar Valor a Presupuesto existente
            Else '0 = Reemplazar
              mSigaRecorrido = FnReemplazarPresupuesto(mValorAux) 'Reemplazar Valor a Presupuesto existente
            End If
          Else
            mSigaRecorrido = FnInsertarPresupuesto(mCtaAux, mCCAux, mPerAux, mValorAux) 'Inserta Presupuesto nuevo
          End If
          mColExcel = mColExcel + 1
          mSigaRecorrido = mColExcel < (lNumeroPeriodos + 4) 'Mas las 4 columnas diferentes de los Periodos
        Wend
        mRangoExcel = mRangoExcel + 1
        mFilPerExcel = mFilPerExcel + 1
        gFrBarraProgreso.Actualizar (mFilExcel - 1)
      Next mFilExcel
      gFrBarraProgreso.Cerrar
      FnCerrarPresupuestos 'Cerrar Archivo de Presupuestos
      MsgBox ("El proceso terminó con éxito.")
    End If
  End If
End Sub

' ********* Plan de Cuentas ********
Public Function CTiCuentaDB(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional Periodo = "", Optional NIIF = "")
Attribute CTiCuentaDB.VB_Description = "Obtiene el total de los DÉBITOS de un rango de CUENTAS (Para efectos de NIIF solo hay que digitar la letra ""S"")"
Attribute CTiCuentaDB.VB_HelpID = 1001
 Application.Volatile (True)
 CTiCuentaDB = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, Periodo, NIIF).Debitos
End Function

Public Function CTiCuentaCR(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional Periodo = "", Optional NIIF = "")
Attribute CTiCuentaCR.VB_Description = "Obtiene el total de los CRÉDITOS de un rango de CUENTAS"
Attribute CTiCuentaCR.VB_HelpID = 1002
 Application.Volatile (True)
 CTiCuentaCR = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, Periodo, NIIF).Creditos
End Function

Public Function CTiCuentaSA(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional Periodo = "", Optional NIIF = "")
Attribute CTiCuentaSA.VB_Description = "Obtiene el SALDO ANTERIOR (Inicial) de un rango de CUENTAS"
Attribute CTiCuentaSA.VB_HelpID = 1003
 Application.Volatile (True)
 CTiCuentaSA = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, Periodo, NIIF).SaldoAnterior
End Function

Public Function CTiCuentaSF(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional Periodo = "", Optional NIIF = "")
Attribute CTiCuentaSF.VB_Description = "Obtiene el SALDO FINAL de un rango de CUENTAS"
Attribute CTiCuentaSF.VB_HelpID = 1004
 Application.Volatile (True)
 CTiCuentaSF = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, Periodo, NIIF).SaldoActual
End Function

Public Function CTiCuentaMO(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional Periodo = "", Optional NIIF = "")
Attribute CTiCuentaMO.VB_Description = "Obtiene la diferencia entre los débitos y los creditos (MOVIMIENTO) de un rango de CUENTAS"
Attribute CTiCuentaMO.VB_HelpID = 1005
 Application.Volatile (True)
 CTiCuentaMO = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, Periodo, NIIF).Movimiento
End Function

Public Function CTiCuentaNO(Compañia, CuentaInicial, Optional CuentaFinal = "", Optional TipoCuenta = "T", Optional NIIF = "")
Attribute CTiCuentaNO.VB_Description = "Obtiene el NOMBRE de una CUENTA"
Attribute CTiCuentaNO.VB_HelpID = 1006
 Application.Volatile (True)
 CTiCuentaNO = CTI.Archivos.Cuenta(Compañia, CuentaInicial, CuentaFinal, TipoCuenta, "", NIIF).Nombre
End Function

' ********* Estadisticos ********
Public Function CTiEstDB(Compañia, CuentaInicial, MesInicial, AñoInicial, Optional CuentaFinal = "", Optional MesFinal = "", Optional AñoFinal = "", Optional TipoCta = "T", Optional NIIF = "")
Attribute CTiEstDB.VB_Description = "Obtiene el total de DÉBITOS de un rango de cuentas en los ESTADÍSTICOS de Contai"
Attribute CTiEstDB.VB_HelpID = 2001
 Application.Volatile (True)
 CTiEstDB = CTI.Archivos.Estadistico(Compañia, CuentaInicial, MesInicial, AñoInicial, CuentaFinal, MesFinal, AñoFinal, TipoCta, NIIF).Debitos
End Function

Public Function CTiEstCR(Compañia, CuentaInicial, MesInicial, AñoInicial, Optional CuentaFinal = "", Optional MesFinal = "", Optional AñoFinal = "", Optional TipoCta = "T", Optional NIIF = "")
Attribute CTiEstCR.VB_Description = "Obtiene el total de CRÉDITOS de un rango de cuentas en los ESTADÍSTICOS de Contai"
Attribute CTiEstCR.VB_HelpID = 2002
 Application.Volatile (True)
 CTiEstCR = CTI.Archivos.Estadistico(Compañia, CuentaInicial, MesInicial, AñoInicial, CuentaFinal, MesFinal, AñoFinal, TipoCta, NIIF).Creditos
End Function

Public Function CTiEstSA(Compañia, CuentaInicial, MesInicial, AñoInicial, Optional CuentaFinal = "", Optional MesFinal = "", Optional AñoFinal = "", Optional TipoCta = "T", Optional NIIF = "")
Attribute CTiEstSA.VB_Description = "Obtiene el SALDO ANTERIOR (Inicial) de un rango de cuentas en los ESTADÍSTICOS de Contai"
Attribute CTiEstSA.VB_HelpID = 2003
 Application.Volatile (True)
 CTiEstSA = CTI.Archivos.Estadistico(Compañia, CuentaInicial, MesInicial, AñoInicial, CuentaFinal, MesFinal, AñoFinal, TipoCta, NIIF).SaldoAnterior
End Function

Public Function CTiEstSF(Compañia, CuentaInicial, MesInicial, AñoInicial, Optional CuentaFinal = "", Optional MesFinal = "", Optional AñoFinal = "", Optional TipoCta = "T", Optional NIIF = "")
Attribute CTiEstSF.VB_Description = "Obtiene el SALDO FINAL de un rango de cuentas en los ESTADÍSTICOS de Contai"
Attribute CTiEstSF.VB_HelpID = 2004
 Application.Volatile (True)
 CTiEstSF = CTI.Archivos.Estadistico(Compañia, CuentaInicial, MesInicial, AñoInicial, CuentaFinal, MesFinal, AñoFinal, TipoCta, NIIF).SaldoActual
End Function

Public Function CTiEstMO(Compañia, CuentaInicial, MesInicial, AñoInicial, Optional CuentaFinal = "", Optional MesFinal = "", Optional AñoFinal = "", Optional TipoCta = "T", Optional NIIF = "")
Attribute CTiEstMO.VB_Description = "Obtiene el MOVIMIENTO neto de un rango de cuentas en los ESTADÍSTICOS de Contai"
Attribute CTiEstMO.VB_HelpID = 2005
 Application.Volatile (True)
 CTiEstMO = CTI.Archivos.Estadistico(Compañia, CuentaInicial, MesInicial, AñoInicial, CuentaFinal, MesFinal, AñoFinal, TipoCta, NIIF).Movimiento
End Function

' ********* Anexos Centro de Costos ********
Public Function CTiCcoDB(Compañia, CuentaInicial, CcostoInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional Periodo = "", Optional NIIF = "", Optional NitInicial = "", Optional NitFinal = "")
Attribute CTiCcoDB.VB_Description = "Obtiene el total de los DÉBITOS de un rango de CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoDB = CTI.Archivos.AnexoCcosto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, Periodo, NIIF, NitInicial, NitFinal).Debitos
End Function

Public Function CTiCcoCR(Compañia, CuentaInicial, CcostoInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional Periodo = "", Optional NIIF = "", Optional NitInicial = "", Optional NitFinal = "")
Attribute CTiCcoCR.VB_Description = "Obtiene el total de los CRÉDITOS de un rango de CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoCR = CTI.Archivos.AnexoCcosto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, Periodo, NIIF, NitInicial, NitFinal).Creditos
End Function

Public Function CTiCcoSA(Compañia, CuentaInicial, CcostoInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional Periodo = "", Optional NIIF = "", Optional NitInicial = "", Optional NitFinal = "")
Attribute CTiCcoSA.VB_Description = "Obtiene el SALDO ANTERIOR (Inicial) de un rango de CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoSA = CTI.Archivos.AnexoCcosto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, Periodo, NIIF, NitInicial, NitFinal).SaldoAnterior
End Function

Public Function CTiCcoSF(Compañia, CuentaInicial, CcostoInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional Periodo = "", Optional NIIF = "", Optional NitInicial = "", Optional NitFinal = "")
Attribute CTiCcoSF.VB_Description = "Obtiene el SALDO FINAL de un rango de CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoSF = CTI.Archivos.AnexoCcosto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, Periodo, NIIF, NitInicial, NitFinal).SaldoActual
End Function

Public Function CTiCcoMO(Compañia, CuentaInicial, CcostoInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional Periodo = "", Optional NIIF = "", Optional NitInicial = "", Optional NitFinal = "")
Attribute CTiCcoMO.VB_Description = "Obtiene la diferencia entre los débitos y los créditos (MOVIMIENTO) de un rango de CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoMO = CTI.Archivos.AnexoCcosto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, Periodo, NIIF, NitInicial, NitFinal).Movimiento
End Function

Public Function CTiCcoNom(Compañia, CcostoInicial, Optional CcostoFinal = "", Optional NIIF = "")
Attribute CTiCcoNom.VB_Description = "Obtiene el NOMBRE de un CENTRO DE COSTOS"
 Application.Volatile (True)
 CTiCcoNom = CTI.Archivos.AnexoCcosto(Compañia, "", CcostoInicial, "", CcostoFinal, "", NIIF, "", "").Nombre
End Function

' ********* Presupuestos ********
Public Function CTiPptoValor(Compañia, CuentaInicial, CcostoInicial, MesInicial, Optional CuentaFinal = "", Optional CcostoFinal = "", Optional MesFinal = "", Optional TipoPpto = "P", Optional Año = "", Optional NIIF = "")
Attribute CTiPptoValor.VB_Description = "Obtiene el valor del PRESUPUESTO de un rango de cuentas y centro de costos, tanto el valor Real (R) como el Presupuestado (P)"
 Application.Volatile (True)
 If IsMissing(CcostoInicial) Then
   CcostoInicial = "" 'Optimización plus
 End If
 CTiPptoValor = CTI.Archivos.Ppto(Compañia, CuentaInicial, CcostoInicial, CuentaFinal, CcostoFinal, MesInicial, MesFinal, TipoPpto, Año, NIIF).ValorPpto
End Function

' ********* Anexos por Nit ********
Public Function CTiSNitDB(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitDB.VB_Description = "Obtiene el total de DÉBITOS de un rango de NITS en Contai"
 Application.Volatile (True)
 CTiSNitDB = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).Debitos
End Function

Public Function CTiSNitCR(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitCR.VB_Description = "Obtiene el total de CRÉDITOS de un rango de NITS en Contai"
 Application.Volatile (True)
 CTiSNitCR = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).Creditos
End Function

Public Function CTiSNitMO(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitMO.VB_Description = "Obtiene el MOVIMIENTO de un rango de NITS en Contai"
 Application.Volatile (True)
 CTiSNitMO = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).Movimiento
End Function

Public Function CTiSNitSA(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitSA.VB_Description = "Obtiene el SALDO ANTERIOR (Inicial) de un rango de NITS en Contai"
 Application.Volatile (True)
 CTiSNitSA = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).SaldoAnterior
End Function

Public Function CTiSNitSF(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitSF.VB_Description = "Obtiene el SALDO FINAL de un rango de NITS en Contai"
 Application.Volatile (True)
 CTiSNitSF = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).SaldoActual
End Function

Public Function CTiSNitBaseMes(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitBaseMes.VB_Description = "Obtiene EL VALOR BASE DEL MES de un rango de cuentas y rango de nits (Cuentas de impuestos, tipo ""B"")"
 Application.Volatile (True)
 CTiSNitBaseMes = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).BaseMes
End Function

Public Function CTiSNitBaseAcu(Compañia, CuentaInicial, NitInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSNitBaseAcu.VB_Description = "Obtiene el VALOR BASE ACUMULADO de un rango de cuentas y rango de nits (No incluye la base del mes, Cuentas de impuestos, tipo ""B"")"
 Application.Volatile (True)
 CTiSNitBaseAcu = CTI.Archivos.Pagos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, Periodo, NIIF).BaseAcum
End Function

Public Function CTiNitNom(Compañia, NitInicial, Optional NitFinal = "")
Attribute CTiNitNom.VB_Description = "Obtiene el NOMBRE de un NIT"
 Application.Volatile (True)
 CTiNitNom = CTI.Archivos.Pagos(Compañia, "", NitInicial, "", NitFinal).Nombre
End Function

' ********* Anexos por Documento ********
Public Function CTiSDocDB(Compañia, CuentaInicial, NitInicial, DoctoInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional DoctoFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSDocDB.VB_Description = "Obtiene el total de los DÉBITOS de un rango de cuentas, nits y DOCUMENTOS"
 Application.Volatile (True)
 CTiSDocDB = CTI.Archivos.Doctos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, DoctoInicial, DoctoFinal, Periodo, NIIF).Debitos
End Function

Public Function CTiSDocCR(Compañia, CuentaInicial, NitInicial, DoctoInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional DoctoFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSDocCR.VB_Description = "Obtiene el total de los CRÉDITOS de un rango de cuentas, nits y DOCUMENTOS"
 Application.Volatile (True)
 CTiSDocCR = CTI.Archivos.Doctos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, DoctoInicial, DoctoFinal, Periodo, NIIF).Creditos
End Function

Public Function CTiSDocMO(Compañia, CuentaInicial, NitInicial, DoctoInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional DoctoFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSDocMO.VB_Description = "Obtiene el total del MOVIMIENTO de un rango de cuentas, nits y DOCUMENTOS"
 Application.Volatile (True)
 CTiSDocMO = CTI.Archivos.Doctos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, DoctoInicial, DoctoFinal, Periodo, NIIF).Movimiento
End Function

Public Function CTiSDocSA(Compañia, CuentaInicial, NitInicial, DoctoInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional DoctoFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSDocSA.VB_Description = "Obtiene el SALDO ANTERIOR (Inicial) de un rango de cuentas, nits y DOCUMENTOS"
 Application.Volatile (True)
 CTiSDocSA = CTI.Archivos.Doctos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, DoctoInicial, DoctoFinal, Periodo, NIIF).SaldoAnterior
End Function

Public Function CTiSDocSF(Compañia, CuentaInicial, NitInicial, DoctoInicial, Optional CuentaFinal = "", Optional NitFinal = "", Optional DoctoFinal = "", Optional Periodo = "", Optional NIIF = "")
Attribute CTiSDocSF.VB_Description = "Obtiene el SALDO FINAL de un rango de cuentas, nits y DOCUMENTOS"
 Application.Volatile (True)
 CTiSDocSF = CTI.Archivos.Doctos(Compañia, CuentaInicial, NitInicial, CuentaFinal, NitFinal, DoctoInicial, DoctoFinal, Periodo, NIIF).SaldoActual
End Function

' ********* Nombre y Nit de la Cia ********
Public Function CTiNombreCia(Compañia)
Attribute CTiNombreCia.VB_Description = "Obtiene el NOMBRE DE LA COMPAÑÍA que se encuentra en Soportes / Instalación / Mantenimiento de Compañías"
 Application.Volatile (True)
 CTiNombreCia = CTI.NombreCia(Compañia)
End Function

Public Function CTiNitCia(Compañia)
Attribute CTiNitCia.VB_Description = "Obtiene el NIT de la compañía que se encuentra en Soportes / Instalación / Mantenimiento de Compañías"
 Application.Volatile (True)
 CTiNitCia = CTI.NitCia(Compañia)
End Function

Public Function CTiDigitoVNitCia(Compañia)
Attribute CTiDigitoVNitCia.VB_Description = "Obtiene el DÍGITO DE VERIFICACIÓN del NIT de la compañía que se encuentra en Soportes / Instalación / Mantenimiento de Compañías"
 Application.Volatile (True)
 CTiDigitoVNitCia = CTI.DigitoVNitCia(Compañia)
End Function

Public Function CTiDirCia(Compañia)
Attribute CTiDirCia.VB_Description = "Obtiene la DIRECCIÓN de la compañía que se encuentra en Soportes / Instalación / Mantenimiento de Compañías"
 Application.Volatile (True)
 CTiDirCia = CTI.DirCia(Compañia)
End Function

Public Function CTiTelCia(Compañia)
Attribute CTiTelCia.VB_Description = "Obtiene el TELÉFONO de la compañía que se encuentra en Soportes / Instalación / Mantenimiento de Compañías"
 Application.Volatile (True)
 CTiTelCia = CTI.TelCia(Compañia)
End Function

' ********* Nombre del Comprobante ********
Public Function CTiCbteNom(Compañia, CombteInicial, Optional CombteFinal = "")
Attribute CTiCbteNom.VB_Description = "Obtiene el NOMBRE de un COMPROBANTE"
 Application.Volatile (True)
 CTiCbteNom = CTI.Archivos.Combte(Compañia, CombteInicial, CombteFinal).Nombre
End Function
