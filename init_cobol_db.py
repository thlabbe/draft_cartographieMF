
from cartographie.utils import connect_to_db, load_config


def main():
    """
    creation dans la base de données de la table cobol_copybook_reference
    table cobol_copybook_reference
        - id: integer
        - member_id: integer
        - copybook_id: integer
        - cobol_name: string
        - copybook_name: string
        - reference_type: string
        - data: string
    table cobol_call_pgm_reference
        - id: integer
        - member_id: integer
        - pgm_id: integer
        - cobol_name: string
        - pgm_name: string
        - reference_type: string
        - data: string
    """
    config = load_config()
    conn = connect_to_db(config)
    conn.execute("""
                 DROP SEQUENCE IF EXISTS seq_cobol_copybook_reference_id;
                 DROP TABLE IF EXISTS cobol_copybook_reference;
                 CREATE SEQUENCE IF NOT EXISTS 
                 seq_cobol_copybook_reference_id START 1;
                 

                 CREATE TABLE IF NOT EXISTS cobol_copybook_reference (
                    id INTEGER PRIMARY KEY 
                        default nextval('seq_cobol_copybook_reference_id'),
                    member_id INTEGER references members(id),
                    copybook_id INTEGER references members(id),
                    cobol_name TEXT,
                    copybook_name TEXT,
                    reference_type TEXT,
                    data TEXT );
                 
                 -- DROP SEQUENCE IF EXISTS seq_cobol_call_pgm_reference_id;
                 CREATE SEQUENCE IF NOT EXISTS 
                 seq_cobol_call_pgm_reference_id START 1;
                 DROP TABLE IF EXISTS cobol_call_pgm_reference;

                 CREATE TABLE IF NOT EXISTS cobol_call_pgm_reference (
                    id INTEGER PRIMARY KEY
                        default nextval('seq_cobol_call_pgm_reference_id'),
                    member_id INTEGER references members(id),
                    pgm_id INTEGER references members(id),
                    cobol_name TEXT,
                    pgm_name TEXT,
                    reference_type TEXT,
                    data TEXT );
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()

    
    