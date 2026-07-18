Attribute VB_Name = "CsPresupuesto"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private Type TPresupuestos
    Periodo           As String * 6
    filler_cod_cuenta As String * 10
    filler_ccosto     As String * 6
    ValorPpto(1 To 8) As Byte
    ValorReal(1 To 8) As Byte
    Usuario           As String * 3
    AnnoActualizado   As String * 4
    MesActualizado    As String * 2
    DiaActualizado    As String * 2
    cod_cuenta        As String * 20
    CCOSTO            As String * 20
    filler            As String * 200
End Type

Private PosBlk$
Private KeyBuffer$
Public Status As Integer
Public KeyNum As Integer
Private FileName As String
Private FileBuf As FileSpec
Private Registro As TPresupuestos
Private StatFileBuffer As StatFileSpecs
Private Size As Integer
Private DBLen As Integer

Dim lIndexCycle As Integer
Dim lMinConvert As Integer
Dim lMaxConvert As Integer
Dim lConvert() As Byte

Private Const KeyBufLen = KEY_BUF_LEN

Public Function FnOpen() As Boolean
    PosBlk$ = Space$(128)
    FileName = gDriveDatos + Archivo_PRESUPUESTO
    KeyBuffer$ = FileName$
    Size = Len(Registro)
    KeyNum = 0
    Status = BTRCALL(BOPEN, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, BACELERADO)
    FnOpen = Status = 0
End Function

Public Function FnFirst() As Integer
  KeyBuffer$ = Space$(255)
  Status = BTRCALL(BGET_FIRST, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, KeyNum)
  FnFirst = Status
End Function

Public Function FnGe(pValue As String) As Integer
  KeyBuffer$ = pValue + Space$(255 - Len(pValue))
  Status = BTRCALL(BGET_GREATEROREQUAL, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, KeyNum)
  FnGe = Status
End Function

Public Function Get_Periodo() As String
  Get_Periodo = Registro.Periodo
End Function

Public Function Get_Cuenta() As String
  Get_Cuenta = Registro.cod_cuenta
End Function

Public Function Get_Ccostos() As String
  Get_Ccostos = Registro.CCOSTO
End Function

Public Function Get_ValorPpto() As Double
  Get_ValorPpto = gUtilidades.FnByteArrayToDouble(Registro.ValorPpto)
End Function

Public Function Get_ValorReal() As Double
  Get_ValorReal = gUtilidades.FnByteArrayToDouble(Registro.ValorReal)
End Function

Public Function FnNext() As Integer
  KeyBuffer$ = Space$(255)
  Status = BTRCALL(BGET_NEXT, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, KeyNum)
  FnNext = Status
End Function

Public Function FnClose() As Boolean
    KeyBuffer$ = FileName$
    Status = BTRCALL(BCLOSE, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, 0)
    FnClose = Status = 0
End Function

Public Function FnEq(pValue As String) As Boolean
    KeyBuffer$ = pValue + Space$(255 - Len(pValue))
    Status = BTRCALL(BGET_EQUAL, PosBlk$, Registro, Size, ByVal KeyBuffer$, KeyBufLen, KeyNum)
    FnEq = Status = 0
End Function

Public Function FnUpdateValue(pValue As Double) As Boolean
    lConvert = gUtilidades.FnDoubleToByteArray(pValue)
    lMinConvert = LBound(lConvert)
    lMaxConvert = UBound(lConvert)
    For lIndexCycle = lMinConvert To lMaxConvert
      Registro.ValorPpto(lIndexCycle) = lConvert(lIndexCycle)
    Next lIndexCycle
    FnUpdateValue = CTI.Archivos.mInsertarPresupuesto(Registro.ValorPpto)
End Function

Public Function FnInsert(pCuenta, pCCostos, pPeriodo As String, pValuePpto As Double) As Boolean
    Registro.Periodo = pPeriodo
    Registro.cod_cuenta = pCuenta
    Registro.CCOSTO = pCCostos
    lTest = gUtilidades.FnDoubleToByteArray(pValuePpto)
    lMin = LBound(lTest)
    lMax = UBound(lTest)
    For lI = lMin To lMax
      Registro.ValorPpto(lI) = lTest(lI)
    Next lI
    FnInsert = CTI.Archivos.mInsertarPresupuesto(pCuenta, pCCostos, pPeriodo, Registro.ValorPpto)
End Function

