from cartographie.utils import connect_to_db, load_config

# exporte les références de la table cobol_copybook_reference au format CSV
conf = load_config()

# à coté du répertoire des sources 1.Sources, créer un répertoire 2.XRefs et y exporter les références de la table cobol_copybook_reference au format CSV

conn = connect_to_db(conf)

selection_copybook  = conn.execute("""
    SELECT c.id, c.member_id, c.copybook_id, c.cobol_name, c.copybook_name, c.reference_type, c.data
      FROM cobol_copybook_reference c  
""").fetchall()
# création du repertoire 2.XRefs s'il n'existe pas
import os

xref_path = os.path.join(conf['sources_directories'], "../2.XRefs")
os.makedirs(xref_path, exist_ok=True)

with open(os.path.join(xref_path, "cobol_copybook_reference.csv"), "w") as f:
    f.write("id,member_id,copybook_id,cobol_name,copybook_name,reference_type,data\n")
    for row in selection_copybook:
        f.write(",".join([str(x) for x in row]) + "\n")

selection_call_pgm  = conn.execute("""
    SELECT c.id, c.member_id, c.pgm_id, c.cobol_name, c.pgm_name, c.reference_type, c.data
      FROM cobol_call_pgm_reference c
""").fetchall()
with open(os.path.join(xref_path, "cobol_call_pgm_reference.csv"), "w") as f:
    f.write("id,member_id,pgm_id,cobol_name,pgm_name,reference_type,data\n")
    for row in selection_call_pgm:
        f.write(",".join([str(x) for x in row]) + "\n")
        
