Attribute VB_Name = "APIBtrieve"
Rem **********************************************************************
Rem
Rem Copyright 1994-1997 Pervasive Software Inc. All Rights Reserved
Rem
Rem *********************************************************************

DefInt A-Z
Global Const BNORMAL = 0
Global Const BACELERADO = -1
Global Const BOPEN = 0
Global Const BCLOSE = 1
Global Const BINSERT = 2
Global Const BUPDATE = 3
Global Const BDELETE = 4
Global Const BGET_EQUAL = 5
Global Const BGET_NEXT = 6
Global Const BGET_GREATEROREQUAL = 9
Global Const BGET_FIRST = 12
Global Const BCREATE = 14
Global Const BSTAT = 15
Global Const BSTOP = 25
Global Const BVERSION = 26
Global Const BRESET = 28
Global Const BGET_NEXT_EXTENDED = 36

Global Const KEY_BUF_LEN = 255

Rem  Key Flags
Global Const DUP = 1
Global Const MODIFIABLE = 2
Global Const BIN = 4
Global Const NUL = 8
Global Const SEGMENT = 16
Global Const SEQ = 32
Global Const DEC = 64
Global Const SUP = 128

Rem  Key Types
Global Const EXTTYPE = 256
Global Const MANUAL = 512
Global Const BSTRING = 0
Global Const BINTEGER = 1
Global Const BFLOAT = 2
Global Const BDATE = 3
Global Const BTIME = 4
Global Const BDECIMAL = 5
Global Const BNUMERIC = 8
Global Const BZSTRING = 11
Global Const BAUTOINC = 15

Const pregnebuffersize = 36
Const postgnebuffersize = 3262

#If Win64 Then
  Declare PtrSafe Function BTRCALL Lib "w3btrv7.dll" (ByVal OP, ByVal Pb$, Db As Any, DL As Integer, Kb As Any, ByVal Kl, ByVal Kn) As Integer
  Declare PtrSafe Function BTRCALLID Lib "w3btrv7.dll" (ByVal OP, ByVal Pb$, Db As Any, DL As Long, Kb As Any, ByVal Kl, ByVal Kn, ByVal ID) As Integer
#Else
  Declare Function BTRCALL Lib "w3btrv7.dll" (ByVal OP, ByVal Pb$, Db As Any, DL As Integer, Kb As Any, ByVal Kl, ByVal Kn) As Integer
  Declare Function BTRCALLID Lib "w3btrv7.dll" (ByVal OP, ByVal Pb$, Db As Any, DL As Long, Kb As Any, ByVal Kl, ByVal Kn, ByVal ID) As Integer
#End If

Type TEntero
  Value(1 To 2) As Byte
End Type

Type typ_byte4
    f1(1 To 4) As Byte
End Type
Rem ***************************************************************************

Rem  Btrieve Structures

Type KeySpec
          KeyPos    As Integer
          KeyLen    As Integer
          KeyFlags  As Integer
          KeyTot    As typ_byte4
          KeyType   As String * 1
          Reserved  As String * 5
End Type

Type FileSpec
         recLen             As Integer
         PageSize           As Integer
         IndxCnt            As Integer
         NotUsed            As String * 4
         FileFlags          As Integer
         Reserved           As String * 2
         Allocation         As Integer
         KeyBuf(0 To 1)     As KeySpec
End Type

Type StatFileSpecs
     recLen              As Integer
     PageSize            As Integer
     IndexTot            As Integer
     RecTot              As typ_byte4
     FileFlags           As Integer
     Reserved            As String * 2
     UnusedPages         As Integer
     KeyBuf(0 To 1)      As KeySpec
End Type

Type RecordBuffer
         Number           As Double
         Dummy            As String * 26
End Type

Type VersionBuf
    Version  As Integer
    Revision As Integer
    Tipo     As String * 1
End Type

Type TVersion
  Data(1 To 3) As VersionBuf
End Type

Type typ_PosBlk
    f1(1 To 128) As Byte
End Type

Rem*******Added to Open multiple files
  Public iMaxRuns As Integer
  Public bFilesCreated As Boolean
Rem ************************ For Read Multi Records

Public Type GNE_HEADER
    descriptionLen As Integer
    currencyConst As String * 2
    rejectCount As Integer
    numberTerms As Integer
End Type


Public Type RETRIEVAL_HEADER
    maxRecsToRetrieve As Integer
    noFieldsToRetrieve As Integer
End Type

Public Type FIELD_RETRIEVAL_HEADER
    fieldLen As Integer
    fieldOffset As Integer
End Type

Public Type TERM_06
    fieldType      As Byte
    fieldLen       As Integer
    fieldOffset    As Integer
    comparisonCode As Byte
    connector      As Byte
    Value          As String * 6
End Type

Public Type TERM_11
    fieldType      As Byte
    fieldLen       As Integer
    fieldOffset    As Integer
    comparisonCode As Byte
    connector      As Byte
    Value          As String * 11
End Type

Public Type TERM_20
    fieldType      As Byte
    fieldLen       As Integer
    fieldOffset    As Integer
    comparisonCode As Byte
    connector      As Byte
    Value          As String * 20
End Type

Public Type pregnebuffertype
  buf(1 To pregnebuffersize) As Byte
End Type

Public Type postgnebuffertype
  buf(1 To postgnebuffersize) As Byte
End Type

