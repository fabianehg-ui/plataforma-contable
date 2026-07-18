Attribute VB_Name = "Globales"
Public Const Archivo_USUARIO = "CNINSTAL.USU"
Public Const Archivo_COMPANIA = "CNINSTAL.emp"
Public Const Archivo_DIRECTORIO = "CNINSTAL.DIR"
Public Const Archivo_PRESUPUESTO = "CNPPTOS.BTV"

Public gUtilidades As New csUtilidades
Public gPresupuesto As New CsPresupuesto
Public gFrGrabarPresupuestos As New FrGrabarPresupuestos
Public gFrBarraProgreso As New FrBarraProgreso

Public gDriveDatos As String
Public gCompaniaIni As String
Public gCompaniaFin As String
Public gDrivePrograma As String
Public gUsuario_Actual As String
Public gCompania_Actual As String
