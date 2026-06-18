"""
alimentation des tables 
 - cobol_copybook_reference 
 - cobol_call_pgm_reference

"""
import logging
import re
from pprint import pprint

import tqdm

from cartographie.utils import connect_to_db, load_config
from cartographie.types import CBL_to_CPY

LOG_FILE = "cobol_copybook_errors.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

class COBOL():
    def __init__(self, member_id, name, pds_id):
        self.member_id = member_id
        self.name = name
        self.pds_id = pds_id
        self.references = []  
    @property
    def name_without_extension(self):
        return self.name.split('.')[0]

def scan_for_copybook(conn, cobol):
    def code_area(content_line):
        # COBOL fixed format: keep only columns 7-72 (drop sequence numbers in 73-80)
        return content_line[6:72].rstrip()

    def fetch_next_line(member_id, current_line_no):
        next_line = conn.execute(f"""
            SELECT line_no, content  
            FROM member_content
            WHERE member_id = {member_id}
            AND line_no > {current_line_no}
            AND SUBSTRING(content, 7, 1) != '*' 
            AND SUBSTRING(content, 7, 1) != 'D'
            ORDER BY line_no ASC
            LIMIT 1
        """).fetchone()
        return next_line
    content = conn.execute(f"""
        SELECT line_no, content  
        FROM member_content
        WHERE member_id = {cobol.member_id}
        AND SUBSTRING(content, 7, 1) != '*' 
        AND SUBSTRING(content, 7, 1) != 'D'
        
        ORDER BY line_no ASC
    """).fetchall()
    # filter les lignes qui contiennent le mot clef COPY
    references = []
    for line in content:
        line_code = code_area(line[1])
        if line_code.upper().lstrip().startswith("COPY "):
            copy_stmt = line_code
            if not copy_stmt.endswith("."):
                # retrieve next line 
                next_line_no, next_line_content = fetch_next_line(cobol.member_id, line[0])
                if next_line_content:
                    copy_stmt = f"{copy_stmt} {code_area(next_line_content)}".strip()
            reference_type = CBL_to_CPY.REFERENCE_WITH_REPLACING if " REPLACING " in copy_stmt.upper() else CBL_to_CPY.REFERENCE
            references.append({
                'line_no': line[0],
                'content': copy_stmt,
                'reference_type': reference_type
            })

    return references

def scan_for_call_pgm(conn, cobol):
    content = conn.execute(f"""
        SELECT line_no, content  
        FROM member_content
        WHERE member_id = {cobol.member_id}
        AND SUBSTRING(content, 7, 1) != '*' 
        AND SUBSTRING(content, 7, 1) != 'D'
        
        ORDER BY line_no ASC
    """).fetchall()
    # filter les lignes qui contiennent le mot clef CALL
    references = []
    for line in content:
        line_code = line[1][6:72].rstrip()  # COBOL fixed format: keep only columns 7-72 (drop sequence numbers in 73-80)
        if line_code.upper().lstrip().startswith("CALL "):
            call_stmt = line_code
            reference_type = CBL_to_CPY.REFERENCE
            references.append({
                'line_no': line[0],
                'content': call_stmt,
                'reference_type': reference_type
            })
    return references

def serialize_call_refs(refs, cobol, cnx):
    for ref in refs:
        cobol_id = cobol.member_id
        cobol_name = cobol.name_without_extension
        line_no = ref.get('line_no')
        ref_content = ref.get('content', '')
        try:
            ref_type = ref['reference_type']

            call_match = re.search(r"\bCALL\s+([^\s.]+)", ref_content, flags=re.IGNORECASE)
            if not call_match:
                logging.error(
                    "Unable to parse CALL reference: cobol_id=%s cobol_name=%s line_no=%s content=%r",
                    cobol_id,
                    cobol_name,
                    line_no,
                    ref_content,
                )
                continue
            pgm_name = call_match.group(1).strip()
        except Exception:
            logging.exception(
                "Exception while serializing reference: cobol_id=%s cobol_name=%s line_no=%s content=%r",
                cobol_id,
                cobol_name,
                line_no,
                ref_content,
            )
            print(f"[ERROR] COBOL={cobol.name} line={line_no} content={ref_content!r}")
            raise

        pgm_rows = cnx.execute("""
            SELECT m.id
              FROM members m
             WHERE m.name LIKE ?
        """, (f"{pgm_name}%",)).fetchall()

        if len(pgm_rows) != 1:
            reason = "not found" if len(pgm_rows) == 0 else "not unique"
            logging.error(
                "PGM lookup %s: cobol_id=%s cobol_name=%s pgm_name=%s line_no=%s matches=%s content=%r",
                reason,
                cobol_id,
                cobol_name,
                pgm_name,
                line_no,
                len(pgm_rows),
                ref_content,
            )
            continue

        data = {'line_no': line_no, 'content': ref_content}
        cnx.execute("""
            INSERT INTO cobol_call_pgm_reference (member_id, pgm_id, cobol_name, pgm_name, reference_type, data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cobol_id, pgm_rows[0][0], cobol_name, pgm_name, ref_type.value, str(data)))

def serialize_copy_refs(refs, cobol, cnx):
    for ref in refs:
        cobol_id = cobol.member_id
        cobol_name = cobol.name_without_extension
        line_no = ref.get('line_no')
        ref_content = ref.get('content', '')
        try:
            ref_type = ref['reference_type']

            copy_match = re.search(r"\bCOPY\s+([^\s.]+)", ref_content, flags=re.IGNORECASE)
            if not copy_match:
                logging.error(
                    "Unable to parse COPY reference: cobol_id=%s cobol_name=%s line_no=%s content=%r",
                    cobol_id,
                    cobol_name,
                    line_no,
                    ref_content,
                )
                continue
            copybook_name = copy_match.group(1).strip()
        except Exception:
            logging.exception(
                "Exception while serializing reference: cobol_id=%s cobol_name=%s line_no=%s content=%r",
                cobol_id,
                cobol_name,
                line_no,
                ref_content,
            )
            print(f"[ERROR] COBOL={cobol.name} line={line_no} content={ref_content!r}")
            raise

        copybook_rows = cnx.execute("""
            SELECT m.id
              FROM members m
             WHERE m.name LIKE ?
        """, (f"{copybook_name}%",)).fetchall()

        if len(copybook_rows) != 1:
            reason = "not found" if len(copybook_rows) == 0 else "not unique"
            logging.error(
                "COPYBOOK lookup %s: cobol_id=%s cobol_name=%s copybook_name=%s line_no=%s matches=%s content=%r",
                reason,
                cobol_id,
                cobol_name,
                copybook_name,
                line_no,
                len(copybook_rows),
                ref_content,
            )
            continue

        data = {'line_no': line_no, 'content': ref_content}
        cnx.execute("""
            INSERT INTO cobol_copybook_reference (member_id, copybook_id, cobol_name, copybook_name, reference_type, data)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cobol_id, copybook_rows[0][0], cobol_name, copybook_name, ref_type.value, str(data)))

        
def main():
    config = load_config()
    conn = connect_to_db(config)
    
    raw_list_cobols = conn.execute("""
        SELECT m.id, m.name, m.pds_id 
        FROM members m 
        WHERE m.type = 'COBOL';
""").fetchall()
    total_refs = 0
    cobol_list = [COBOL(member_id=row[0], name=row[1], pds_id=row[2]) for row in raw_list_cobols]
    for cobol in tqdm.tqdm(cobol_list, desc="Processing COBOL members"):
        refs_copy = scan_for_copybook(conn, cobol)
        total_refs += len(refs_copy)
        serialize_copy_refs(refs_copy, cobol, conn)
        refs_call = scan_for_call_pgm(conn, cobol)
        serialize_call_refs(refs_call, cobol, conn)

        # pprint(f"COBOL member {cobol.name} (ID: {cobol.member_id}) has {len(refs)} copybook references. total so far: {total_refs}")



    pass

if __name__ == "__main__":
    print("start")
    main()
    print("done")