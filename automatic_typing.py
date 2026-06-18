"""
Ce script se connecte à la base de données DuckDB définie dans le fichier de configuration.

Tente de déterminer automatiquement le type de chaque membre.
Les heuristiques sont déterministes : le flag human_reviewed passe a vrai : innutile de reverifier.


Met à jour la base de données avec les types déterminés.
"""

import re
import tqdm

from cartographie.utils import load_config, connect_to_db
from cartographie.types import Member_Types


def list_review_candidates(conn):
    """
    Liste les candidats pour la révision automatique dans la base de données.

    Args:
        conn (duckdb.DuckDBPyConnection): La connexion à la base de données DuckDB.

    Returns:
        list: Une liste de tuples représentant les candidats pour la révision automatique.
    """

    query = "SELECT * FROM members WHERE human_reviewed = FALSE"
    candidates = conn.execute(query).fetchall()
    return candidates

RE_JCL = re.compile(r"^//[A-Z$#@][A-Z0-9$#@]{0,7}\s+JOB\b")

def isJCL(conn, candidate):
    """
    Détermine si un candidat est de type JCL en fonction de ses caractéristiques.

    Args:
        conn (duckdb.DuckDBPyConnection): La connexion à la base de données DuckDB.
        candidate (tuple): Le candidat à vérifier, représenté par un tuple contenant les informations du membre.

    Returns:
        bool: True si le candidat est de type JCL, False sinon.
    """

    # recuperer la première ligne du contenu du membre
    # si la ligne commence par "//[0-9A-Z]{1,8} JOB " alors c'est un JCL
    query = f"""
    SELECT content 
      FROM member_content 
     WHERE member_id = {candidate[0]}
     ORDER BY line_no ASC
    LIMIT 1;
    """

    # Exemple d'implémentation simple :
    frist_str = conn.execute(query).fetchone()
    # print(f"Candidate {candidate[0]} first line: {frist_str}")
    if frist_str and RE_JCL.match(frist_str[0]):
        update_member_type(conn, candidate[0], Member_Types.JCL)
        return True
    return False

RE_JCL_FIRST_LINE = re.compile(r"^//")
RE_JCL_EXEC = re.compile(r"^//[A-Z$#@][A-Z0-9$#@]{0,7}\s+EXEC\b")
def isJCL_PROCEDURE(conn, candidate):

    content = conn.execute(f"""
    SELECT content
        FROM member_content 
         WHERE member_id = {candidate[0]}
         ORDER BY line_no ASC
        """).fetchall()
    # si la premiere ligne matche RE_JCL_FIRST_LINE et qu'au moins ne ligne matche RE_JCL_EXEC alors c'est un JCL_PROCEDURE

    if content and RE_JCL_FIRST_LINE.match(content[0][0]):
        for line in content:
            if RE_JCL_EXEC.match(line[0]):
                update_member_type(conn, candidate[0], Member_Types.JCL_PROCEDURE)
                return True 
    return False

RE_REXX = re.compile(r"^\s*/\*\s*REXX\b(?:\s*\*/)?", re.IGNORECASE)

def isREXX(conn, candidate):
    content = conn.execute(f"""
    SELECT content
        FROM member_content 
         WHERE member_id = {candidate[0]}
         ORDER BY line_no ASC
        """).fetchall()
    # si la premiere ligne matche RE_REXX alors c'est un REXX

    if content and RE_REXX.match(content[0][0]):
        update_member_type(conn, candidate[0], Member_Types.REXX)
        return True 
    return False

RE_COBOL = re.compile(r"^       IDENTIFICATION\s+DIVISION\b", re.IGNORECASE)

def isCOBOL(conn, candidate):
    """ 
    C'est un cobol si l'une des 5 premieres lignes matche RE_COBOL
    """
    
    content = conn.execute(f"""
    SELECT content
        FROM member_content 
         WHERE member_id = {candidate[0]}
         ORDER BY line_no ASC
         LIMIT 5
        """).fetchall()
    # si l'une des 5 premieres lignes matche RE_COBOL alors c'est un COBOL

    for line in content:
        if RE_COBOL.match(line[0]):
            update_member_type(conn, candidate[0], Member_Types.COBOL)
            return True 
    return False

def isCopybook(conn, candidate):
    """ pour déterminer que c'est un Copybook il faut que :
    - le PDS contient "COPY" dans son nom (ignorecase)
    - le nom du membre contienne l'extension '.CPY' (ignorecase)
    """
    
    pds_name = conn.execute(f"""
    SELECT name
        FROM pds 
         WHERE id = {candidate[1]}
        """).fetchone()[0]

    member_name = candidate[2]

    if "COPY" in pds_name.upper() and member_name.upper().endswith(".CPY"):
        update_member_type(conn, candidate[0], Member_Types.COPYBOOK)
        return True 
    return False

def update_member_type(conn, member_id, member_type):
    """
    Met à jour le type d'un membre dans la base de données.

    Args:
        conn (duckdb.DuckDBPyConnection): La connexion à la base de données DuckDB.
        member_id (int): L'ID du membre à mettre à jour.
        member_type (Member_Types): Le type du membre à définir.
    """

    update_query = f"""UPDATE members SET type = '{member_type.name}'
    , human_reviewed = TRUE 
    WHERE id = {member_id}"""
    conn.execute(update_query)
    
def procede_to_review(conn, candidate):
    """
    Procède à la révision automatique d'un candidat et met à jour la base de données avec le type déterminé.

    Args:
        conn (duckdb.DuckDBPyConnection): La connexion à la base de données DuckDB.
        candidate (tuple): Le candidat à réviser, représenté par un tuple contenant les informations du membre.
    """

    # Implémentez ici la logique pour déterminer le type du membre en fonction de ses caractéristiques.
    # Par exemple, vous pouvez utiliser des heuristiques basées sur le nom, le chemin, etc.
    # Mettez à jour la base de données avec le type déterminé et définissez human_reviewed sur TRUE.
    typed = False
    
    if not typed:
        typed = isCopybook(conn,candidate)
    if not typed:
       typed = isJCL(conn,candidate)
    if not typed:
        typed = isREXX(conn,candidate)
    if not typed:
        typed = isCOBOL(conn,candidate)
    if not typed:
        typed = isJCL_PROCEDURE(conn,candidate)
    
    return typed

def main():
    config = load_config()
    conn = connect_to_db(config)
    candidates = list_review_candidates(conn)

    updates = 0
    
    for candidate in tqdm.tqdm(candidates, desc="Processing candidates"):
        if procede_to_review(conn, candidate): updates += 1
    
    print(f"Total candidates processed: {len(candidates)}")
    print(f"Total updates made: {updates}")

if __name__ == "__main__":
    main()
