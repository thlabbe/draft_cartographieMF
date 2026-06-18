import json
import duckdb

def connect_to_db(config):
    """
    Connecte à la base de données DuckDB définie dans le fichier de configuration.

    Args:
        config (dict): Le dictionnaire de configuration contenant les informations de connexion à la base de données.

    Returns:
        duckdb.DuckDBPyConnection: La connexion à la base de données DuckDB.
    """

    db_path = config.get("dbfile")
    conn = duckdb.connect(database=db_path, read_only=False)
    return conn

def load_config(file = "cardif.project.json"):

    with open(file, "r") as f:
        config = json.load(f)
    return config
