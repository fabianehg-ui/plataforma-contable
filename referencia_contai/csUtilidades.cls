Attribute VB_Name = "csUtilidades"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private Clave_Scr(1 To 254) As String

#If Win64 Then
  Private Declare PtrSafe Sub CopyMemory Lib "kernel32" Alias "RtlMoveMemory" (lpDest As Any, lpSource As Any, ByVal cBytes As Long)
#Else
  Private Declare Sub CopyMemory Lib "kernel32" Alias "RtlMoveMemory" (lpDest As Any, lpSource As Any, ByVal cBytes As Long)
#End If

Public Function Get_Clave_Scr(pIndex As Byte)
  If (pIndex >= 31) And (pIndex <= 245) Then
    Get_Clave_Scr = Clave_Scr(pIndex)
  Else
    Get_Clave_Scr = " "
  End If
End Function

Public Sub PrPreparar_Array()
    Clave_Scr(1) = Chr(245)
    Clave_Scr(2) = Chr(245)
    Clave_Scr(3) = Chr(245)
    Clave_Scr(4) = Chr(245)
    Clave_Scr(5) = Chr(245)
    Clave_Scr(6) = Chr(245)
    Clave_Scr(7) = Chr(245)
    Clave_Scr(8) = Chr(245)
    Clave_Scr(9) = Chr(245)
    Clave_Scr(10) = Chr(245)
    Clave_Scr(11) = Chr(245)
    Clave_Scr(12) = Chr(245)
    Clave_Scr(13) = Chr(245)
    Clave_Scr(14) = Chr(245)
    Clave_Scr(15) = Chr(245)
    Clave_Scr(16) = Chr(245)
    Clave_Scr(17) = Chr(245)
    Clave_Scr(18) = Chr(245)
    Clave_Scr(19) = Chr(245)
    Clave_Scr(20) = Chr(245)
    Clave_Scr(21) = Chr(245)
    Clave_Scr(22) = Chr(245)
    Clave_Scr(23) = Chr(245)
    Clave_Scr(24) = Chr(245)
    Clave_Scr(25) = Chr(245)
    Clave_Scr(26) = Chr(245)
    Clave_Scr(27) = Chr(245)
    Clave_Scr(28) = Chr(245)
    Clave_Scr(29) = Chr(245)
    Clave_Scr(30) = Chr(245)
    Clave_Scr(31) = Chr(244)
    Clave_Scr(32) = Chr(243)
    Clave_Scr(33) = Chr(242)
    Clave_Scr(34) = Chr(241)
    Clave_Scr(35) = Chr(240)
    Clave_Scr(36) = Chr(239)
    Clave_Scr(37) = Chr(238)
    Clave_Scr(38) = Chr(237)
    Clave_Scr(39) = Chr(236)
    Clave_Scr(40) = Chr(235)
    Clave_Scr(41) = Chr(234)
    Clave_Scr(42) = Chr(233)
    Clave_Scr(43) = Chr(232)
    Clave_Scr(44) = Chr(231)
    Clave_Scr(45) = Chr(230)
    Clave_Scr(46) = Chr(229)
    Clave_Scr(47) = Chr(228)
    Clave_Scr(48) = Chr(227)
    Clave_Scr(49) = Chr(226)
    Clave_Scr(50) = Chr(225)
    Clave_Scr(51) = Chr(224)
    Clave_Scr(52) = Chr(223)
    Clave_Scr(53) = Chr(222)
    Clave_Scr(54) = Chr(221)
    Clave_Scr(55) = Chr(220)
    Clave_Scr(56) = Chr(219)
    Clave_Scr(57) = Chr(218)
    Clave_Scr(58) = Chr(217)
    Clave_Scr(59) = Chr(216)
    Clave_Scr(60) = Chr(215)
    Clave_Scr(61) = Chr(214)
    Clave_Scr(62) = Chr(213)
    Clave_Scr(63) = Chr(254)
    Clave_Scr(64) = Chr(253)
    Clave_Scr(65) = Chr(252)
    Clave_Scr(66) = Chr(251)
    Clave_Scr(67) = Chr(250)
    Clave_Scr(68) = Chr(249)
    Clave_Scr(69) = Chr(248)
    Clave_Scr(70) = Chr(247)
    Clave_Scr(71) = Chr(246)
    Clave_Scr(72) = Chr(212)
    Clave_Scr(73) = Chr(211)
    Clave_Scr(74) = Chr(210)
    Clave_Scr(75) = Chr(209)
    Clave_Scr(76) = Chr(208)
    Clave_Scr(77) = Chr(207)
    Clave_Scr(78) = Chr(206)
    Clave_Scr(79) = Chr(205)
    Clave_Scr(80) = Chr(204)
    Clave_Scr(81) = Chr(203)
    Clave_Scr(82) = Chr(202)
    Clave_Scr(83) = Chr(201)
    Clave_Scr(84) = Chr(200)
    Clave_Scr(85) = Chr(100)
    Clave_Scr(86) = Chr(101)
    Clave_Scr(87) = Chr(102)
    Clave_Scr(88) = Chr(103)
    Clave_Scr(89) = Chr(104)
    Clave_Scr(90) = Chr(105)
    Clave_Scr(91) = Chr(106)
    Clave_Scr(92) = Chr(107)
    Clave_Scr(93) = Chr(108)
    Clave_Scr(94) = Chr(109)
    Clave_Scr(95) = Chr(110)
    Clave_Scr(96) = Chr(111)
    Clave_Scr(97) = Chr(112)
    Clave_Scr(98) = Chr(113)
    Clave_Scr(99) = Chr(114)
    Clave_Scr(100) = Chr(115)
    Clave_Scr(101) = Chr(116)
    Clave_Scr(102) = Chr(117)
    Clave_Scr(103) = Chr(118)
    Clave_Scr(104) = Chr(119)
    Clave_Scr(105) = Chr(120)
    Clave_Scr(106) = Chr(121)
    Clave_Scr(107) = Chr(122)
    Clave_Scr(108) = Chr(123)
    Clave_Scr(109) = Chr(124)
    Clave_Scr(110) = Chr(125)
    Clave_Scr(111) = Chr(126)
    Clave_Scr(112) = Chr(127)
    Clave_Scr(113) = Chr(128)
    Clave_Scr(114) = Chr(129)
    Clave_Scr(115) = Chr(130)
    Clave_Scr(116) = Chr(131)
    Clave_Scr(117) = Chr(132)
    Clave_Scr(118) = Chr(133)
    Clave_Scr(119) = Chr(134)
    Clave_Scr(120) = Chr(135)
    Clave_Scr(121) = Chr(136)
    Clave_Scr(122) = Chr(137)
    Clave_Scr(123) = Chr(138)
    Clave_Scr(124) = Chr(139)
    Clave_Scr(125) = Chr(140)
    Clave_Scr(126) = Chr(141)
    Clave_Scr(127) = Chr(142)
    Clave_Scr(128) = Chr(143)
    Clave_Scr(129) = Chr(144)
    Clave_Scr(130) = Chr(145)
    Clave_Scr(131) = Chr(146)
    Clave_Scr(132) = Chr(147)
    Clave_Scr(133) = Chr(148)
    Clave_Scr(134) = Chr(149)
    Clave_Scr(135) = Chr(150)
    Clave_Scr(136) = Chr(151)
    Clave_Scr(137) = Chr(152)
    Clave_Scr(138) = Chr(153)
    Clave_Scr(139) = Chr(154)
    Clave_Scr(140) = Chr(155)
    Clave_Scr(141) = Chr(156)
    Clave_Scr(142) = Chr(157)
    Clave_Scr(143) = Chr(158)
    Clave_Scr(144) = Chr(159)
    Clave_Scr(145) = Chr(160)
    Clave_Scr(146) = Chr(161)
    Clave_Scr(147) = Chr(162)
    Clave_Scr(148) = Chr(163)
    Clave_Scr(149) = Chr(164)
    Clave_Scr(150) = Chr(165)
    Clave_Scr(151) = Chr(166)
    Clave_Scr(152) = Chr(167)
    Clave_Scr(153) = Chr(168)
    Clave_Scr(154) = Chr(79)
    Clave_Scr(155) = Chr(169)
    Clave_Scr(156) = Chr(170)
    Clave_Scr(157) = Chr(171)
    Clave_Scr(158) = Chr(172)
    Clave_Scr(159) = Chr(173)
    Clave_Scr(160) = Chr(174)
    Clave_Scr(161) = Chr(175)
    Clave_Scr(162) = Chr(176)
    Clave_Scr(163) = Chr(177)
    Clave_Scr(164) = Chr(178)
    Clave_Scr(165) = Chr(179)
    Clave_Scr(166) = Chr(180)
    Clave_Scr(167) = Chr(181)
    Clave_Scr(168) = Chr(182)
    Clave_Scr(169) = Chr(183)
    Clave_Scr(170) = Chr(184)
    Clave_Scr(171) = Chr(185)
    Clave_Scr(172) = Chr(186)
    Clave_Scr(173) = Chr(187)
    Clave_Scr(174) = Chr(188)
    Clave_Scr(175) = Chr(189)
    Clave_Scr(176) = Chr(190)
    Clave_Scr(177) = Chr(191)
    Clave_Scr(178) = Chr(192)
    Clave_Scr(179) = Chr(193)
    Clave_Scr(180) = Chr(194)
    Clave_Scr(181) = Chr(195)
    Clave_Scr(182) = Chr(196)
    Clave_Scr(183) = Chr(197)
    Clave_Scr(184) = Chr(198)
    Clave_Scr(185) = Chr(199)
    Clave_Scr(186) = Chr(99)
    Clave_Scr(187) = Chr(98)
    Clave_Scr(188) = Chr(97)
    Clave_Scr(189) = Chr(96)
    Clave_Scr(190) = Chr(95)
    Clave_Scr(191) = Chr(94)
    Clave_Scr(192) = Chr(93)
    Clave_Scr(193) = Chr(92)
    Clave_Scr(194) = Chr(91)
    Clave_Scr(195) = Chr(90)
    Clave_Scr(196) = Chr(89)
    Clave_Scr(197) = Chr(88)
    Clave_Scr(198) = Chr(87)
    Clave_Scr(199) = Chr(86)
    Clave_Scr(200) = Chr(85)
    Clave_Scr(201) = Chr(84)
    Clave_Scr(202) = Chr(83)
    Clave_Scr(203) = Chr(82)
    Clave_Scr(204) = Chr(81)
    Clave_Scr(205) = Chr(80)
    Clave_Scr(206) = Chr(79)
    Clave_Scr(207) = Chr(78)
    Clave_Scr(208) = Chr(77)
    Clave_Scr(209) = Chr(76)
    Clave_Scr(210) = Chr(75)
    Clave_Scr(211) = Chr(74)
    Clave_Scr(212) = Chr(73)
    Clave_Scr(213) = Chr(72)
    Clave_Scr(214) = Chr(71)
    Clave_Scr(215) = Chr(70)
    Clave_Scr(216) = Chr(69)
    Clave_Scr(217) = Chr(68)
    Clave_Scr(218) = Chr(67)
    Clave_Scr(219) = Chr(66)
    Clave_Scr(220) = Chr(65)
    Clave_Scr(221) = Chr(64)
    Clave_Scr(222) = Chr(63)
    Clave_Scr(223) = Chr(62)
    Clave_Scr(224) = Chr(61)
    Clave_Scr(225) = Chr(60)
    Clave_Scr(226) = Chr(59)
    Clave_Scr(227) = Chr(58)
    Clave_Scr(228) = Chr(57)
    Clave_Scr(229) = Chr(56)
    Clave_Scr(230) = Chr(55)
    Clave_Scr(231) = Chr(54)
    Clave_Scr(232) = Chr(53)
    Clave_Scr(233) = Chr(52)
    Clave_Scr(234) = Chr(51)
    Clave_Scr(235) = Chr(50)
    Clave_Scr(236) = Chr(49)
    Clave_Scr(237) = Chr(48)
    Clave_Scr(238) = Chr(47)
    Clave_Scr(239) = Chr(46)
    Clave_Scr(240) = Chr(45)
    Clave_Scr(241) = Chr(44)
    Clave_Scr(242) = Chr(43)
    Clave_Scr(243) = Chr(42)
    Clave_Scr(244) = Chr(41)
    Clave_Scr(245) = Chr(40)
    Clave_Scr(246) = Chr(39)
    Clave_Scr(247) = Chr(38)
    Clave_Scr(248) = Chr(37)
    Clave_Scr(249) = Chr(36)
    Clave_Scr(250) = Chr(35)
    Clave_Scr(251) = Chr(34)
    Clave_Scr(252) = Chr(33)
    Clave_Scr(253) = Chr(32)
    Clave_Scr(254) = Chr(31)
End Sub

Public Function FnByteArrayToDouble(bArray() As Byte) As Double
   On Error GoTo Salir
   Dim retval As Double
   retval = 0
   If 1 + UBound(bArray) - LBound(bArray) <> Len(retval) Then
       Err.Raise vbObjectError + 512, "Wrong number of bytes"
    Else
     CopyMemory retval, bArray(LBound(bArray)), Len(retval)
    End If
   FnByteArrayToDouble = Round(retval, 2)
   Exit Function
Salir: ByteArrayToDouble = 0
End Function

Public Function FnDoubleToByteArray(pValue As Double) As Byte()
  Dim lEntera As Long
  Dim lResultado() As Byte
  lEntera = Len(pValue)
  ReDim lResultado(1 To lEntera) As Byte
  CopyMemory lResultado(1), pValue, lEntera
  FnDoubleToByteArray = lResultado
End Function

Public Function FnJustW(pValue As String, pOcurry As Integer, pCaracter As String, Optional pJustified As String = "D") As String
  Dim lI As Integer
  Dim lDif As Integer
  Dim lResultado As String
  lResultado = Trim(pValue)
  lDif = Len(lResultado)
  For lI = 1 To (pOcurry - lDif)
    If pJustified = "D" Then
      lResultado = pCaracter + lResultado
    Else
      lResultado = lResultado + pCaracter
    End If
  Next lI
  FnJustW = lResultado
End Function

Public Function FnDigitoVer(pValue As String) As String
  Dim numero(1 To 15) As Integer
  Dim num_nit(1 To 15) As Integer
  Dim Nit_Aux As String * 15
  Dim Otro    As Long
  Dim Todo    As Long
  Dim Dividan As Long
  Dim Resto   As Long
  Dim Dv      As Long
  Dim lI      As Long
  
    Dv = 0
    Otro = 0
    Todo = 0
    Dividan = 0
    Resto = 0
    numero(1) = 3
    numero(2) = 7
    numero(3) = 13
    numero(4) = 17
    numero(5) = 19
    numero(6) = 23
    numero(7) = 29
    numero(8) = 37
    numero(9) = 41
    numero(10) = 43
    numero(11) = 47
    numero(12) = 53
    numero(13) = 59
    numero(14) = 67
    numero(15) = 71
  
  Nit_Aux = FnJustW(pValue, 15, " ")
  For lI = 1 To 15
    If IsNumeric(Mid(Nit_Aux, lI, 1)) Then
      num_nit(lI) = Int(Mid(Nit_Aux, lI, 1))
    End If
  Next lI
  Todo = 0
  Todo = Todo + (numero(1) * num_nit(15))
  Todo = Todo + (numero(2) * num_nit(14))
  Todo = Todo + (numero(3) * num_nit(13))
  Todo = Todo + (numero(4) * num_nit(12))
  Todo = Todo + (numero(5) * num_nit(11))
  Todo = Todo + (numero(6) * num_nit(10))
  Todo = Todo + (numero(7) * num_nit(9))
  Todo = Todo + (numero(8) * num_nit(8))
  Todo = Todo + (numero(9) * num_nit(7))
  Todo = Todo + (numero(10) * num_nit(6))
  Todo = Todo + (numero(11) * num_nit(5))
  Todo = Todo + (numero(12) * num_nit(4))
  Todo = Todo + (numero(13) * num_nit(3))
  Todo = Todo + (numero(14) * num_nit(2))
  Todo = Todo + (numero(15) * num_nit(1))
  Dividan = (Todo \ 11)
  Resto = (Dividan * 11)
  Otro = (Todo - Resto)
  If Otro = 0 Then
    Dv = 0
  Else
    If Otro = 1 Then
      Dv = 1
    End If
  End If
  If (Otro <> 0) And (Otro <> 1) Then
    Dv = 11 - Otro
  End If
  FnDigitoVer = Str(Dv)
End Function

Public Function FnDecodificar_Cadena(pCadena As String) As String
  Dim lI As Integer
  Dim lAscII As Byte
  Dim lResultado As String
  lResultado = ""
  gUtilidades.PrPreparar_Array
  For lI = 1 To Len(pCadena)
    lAscII = Asc(Mid(pCadena, lI, 1))
    lResultado = lResultado + gUtilidades.Get_Clave_Scr(lAscII)
  Next lI
  FnDecodificar_Cadena = lResultado
End Function

Public Function Directory_Exist(pPath As String) As Boolean
  Directory_Exist = (Dir$(pPath, vbDirectory) <> "")
End Function

Public Function FnVacio(pValue As String) As Boolean
  FnVacio = Len(Trim(pValue)) <= 0
End Function

Public Function FnDepurar_Caracteres(pValue As String) As String
  Dim lI As Integer
  Dim ltmp As String
  Dim lChar As String
  Dim lResult As String
  lResult = ""
  ltmp = Trim(pValue)
  For lI = 1 To Len(ltmp)
    lChar = Mid(ltmp, lI, 1)
    If ((Asc(lChar) >= 65) And (Asc(lChar) <= 90)) Then
      lResult = lResult + lChar
    End If
    If ((Asc(lChar) >= 97) And (Asc(lChar) <= 122)) Then
      lResult = lResult + lChar
    End If
    If ((Asc(lChar) >= 48) And (Asc(lChar) <= 47)) Then
      lResult = lResult + lChar
    End If
    If ((Asc(lChar) = 92) Or (Asc(lChar) <= 58)) Then
      lResult = lResult + lChar
    End If
  Next lI
  If FnVacio(lResult) Then
    lResult = ltmp
  End If
  FnDepurar_Caracteres = lResult
End Function

Public Function FnAddBacklSlash(pValue As String) As String
  Dim lI As Integer
  Dim ltmp As String
  Dim lResult As String
  lResult = pValue
  If Not FnVacio(lResult) Then
     ltmp = Mid(lResult, Len(lResult) - 1, 1)
     If Asc(ltmp) <> 92 Then
       lResult = lResult + "\"
     End If
  End If
  FnAddBacklSlash = lResult
End Function

