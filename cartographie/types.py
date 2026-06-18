

import enum


class Member_Types(enum.Enum):
    UNDEFINED = 0
    COBOL = 10
    COPYBOOK = 20
    JCL = 30
    JCL_PROCEDURE = 31
    SYSIN = 32
    SYSIN_SORT = 33
    SYSIN_IDCAMS = 34
    SCRIPT = 40
    REXX = 41
    CLIST = 42
    SQL = 50
    SQL_DDL = 51
    SQL_DML = 52
    OTHER = 80
    ERROR = 99

class CBL_to_CPY(enum.Enum):
    REFERENCE = 0
    REFERENCE_WITH_REPLACING = 20
