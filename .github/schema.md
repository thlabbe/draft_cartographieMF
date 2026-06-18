# schema 
## tables 
### pds
 - id: integer
 - name: string
 - path: string
 

### members
 - id: integer
 - pds_id: integer
 - name: string
 - type: string
 - human_reviewed: boolean

### member_content
 - id: integer
 - member_id: integer
 - line_no: integer   
 - content: string

### cobol_copybook_reference
 - id: integer
 - member_id: integer
 - copybook_id: integer
 - cobol_name: string
 - copybook_name: string
 - reference_type: string
 - data: string

### cobol_call_pgm_reference
 - id: integer
 - member_id: integer
 - pgm_id: integer
 - cobol_name: string
 - pgm_name: string
 - reference_type: string
 - data: string
