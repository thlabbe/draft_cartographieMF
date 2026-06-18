from typing import List
import os
import json
import enum
import shutil
import importlib
import duckdb

from tqdm import tqdm 

class PDS_Type(enum.Enum):
    UNDEFINED = 0
    COBOL = 1
    COPYBOOK = 2
    SQL = 3
    ERROR = 99

class PartitionedSataSet():
    def __init__(self, project, name : str, path: str):
        self.parent = project
        self.name = name
        self.path = path


class ProjectContext:
    def __init__(self, name: str, sources_directories: str, dbfile: str):
        self.name = name
        self.sources_directories = sources_directories
        self.dbfile = dbfile
        self.pds = []
        self.cnx = duckdb.connect(database=self.dbfile, read_only=False)
        self.staging_root = os.path.join(os.path.dirname(self.dbfile), "staging")
        
    def extract_pds(self):
        self._prepare_staging_dirs()
        pds_writer = ParquetBatchWriter(
            output_dir=os.path.join(self.staging_root, "pds"),
            columns=["pds_name", "path"],
        )
        members_writer = ParquetBatchWriter(
            output_dir=os.path.join(self.staging_root, "members"),
            columns=["pds_name", "member_name", "type", "human_reviewed"],
        )
        member_content_writer = ParquetBatchWriter(
            output_dir=os.path.join(self.staging_root, "member_content"),
            columns=["pds_name", "member_name", "line_no", "content"],
            batch_size=20000,
        )

        for subdir in os.listdir(self.sources_directories):
            subdir_path = os.path.join(self.sources_directories, subdir)
            if not os.path.isdir(subdir_path):
                continue

            pds = PartitionedSataSet(project=self, name=subdir, path=subdir_path)
            evaluate_pds_type(
                pds,
                members_writer=members_writer,
                member_content_writer=member_content_writer,
            )

            pds_writer.add_row(
                {
                    "pds_name": pds.name,
                    "path": pds.path,
                }
            )
            self.pds.append(pds)

        pds_writer.flush()
        members_writer.flush()
        member_content_writer.flush()

        self._load_staging_to_db()

    def _prepare_staging_dirs(self):
        if os.path.exists(self.staging_root):
            shutil.rmtree(self.staging_root)
        os.makedirs(os.path.join(self.staging_root, "pds"), exist_ok=True)
        os.makedirs(os.path.join(self.staging_root, "members"), exist_ok=True)
        os.makedirs(os.path.join(self.staging_root, "member_content"), exist_ok=True)

    def _load_staging_to_db(self):
        pds_path = os.path.join(self.staging_root, "pds", "*.parquet").replace("\\", "/")
        members_path = os.path.join(self.staging_root, "members", "*.parquet").replace("\\", "/")
        member_content_path = os.path.join(self.staging_root, "member_content", "*.parquet").replace("\\", "/")

        self.cnx.execute(
            f"""
            INSERT INTO pds (name, path)
            SELECT DISTINCT pds_name, path
            FROM read_parquet('{pds_path}')
            """
        )
        self.cnx.execute(
            f"""
            INSERT INTO members (pds_id, name, type, human_reviewed)
            SELECT p.id, m.member_name, m.type, m.human_reviewed
            FROM read_parquet('{members_path}') m
            JOIN pds p ON p.name = m.pds_name
            """
        )
        self.cnx.execute(
            f"""
            INSERT INTO member_content (member_id, line_no, content)
            SELECT mem.id, c.line_no, c.content
            FROM read_parquet('{member_content_path}') c
            JOIN pds p ON p.name = c.pds_name
            JOIN members mem ON mem.name = c.member_name AND mem.pds_id = p.id
            """
        )
        self.cnx.commit()


class ParquetBatchWriter:
    def __init__(self, output_dir: str, columns: List[str], batch_size: int = 5000):
        try:
            pa = importlib.import_module("pyarrow")
            pq = importlib.import_module("pyarrow.parquet")
        except ImportError as err:
            raise RuntimeError(
                "pyarrow is required for Parquet staging. Install with: pip install pyarrow"
            ) from err

        self.pa = pa
        self.pq = pq
        self.output_dir = output_dir
        self.columns = columns
        self.batch_size = batch_size
        self.rows = []
        self.chunk_index = 0

    def add_row(self, row: dict):
        self.rows.append(row)
        if len(self.rows) >= self.batch_size:
            self._flush_chunk()

    def flush(self):
        if self.rows:
            self._flush_chunk()

    def _flush_chunk(self):
        pa = self.pa
        pq = self.pq

        if "line_no" in self.columns:
            line_numbers = [int(r.get("line_no", 0)) for r in self.rows]
            values = {c: [r.get(c) for r in self.rows] for c in self.columns if c != "line_no"}
            table = pa.table({**values, "line_no": line_numbers})
        else:
            table = pa.Table.from_pylist(self.rows)

        output_file = os.path.join(self.output_dir, f"chunk_{self.chunk_index:06d}.parquet")
        pq.write_table(table, output_file)
        self.rows = []
        self.chunk_index += 1


def _read_text_with_fallback(path: str) -> str:
    encodings = ["utf-8", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as file:
                return file.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Unable to decode file: {path}")


def _detect_member_type(content: str) -> PDS_Type:

    return PDS_Type.UNDEFINED


def evaluate_pds_type(
    pds: PartitionedSataSet,
    members_writer: ParquetBatchWriter,
    member_content_writer: ParquetBatchWriter,
):
    """ 
    Pour un PDS donné, il faut scnner les membre pour 
    déterminer les types possibles en pondérant le résultat par un indice de confiance
    """
    results = {}
    members = os.listdir(pds.path)

    # progressbar : pour monter l'avancement du scan des membres 
    # du PDS
    for member in tqdm(members, desc=f"Scanning PDS: {pds.name}"):
        member_path = os.path.join(pds.path, member)
        if os.path.isfile(member_path):
            try:
                content = _read_text_with_fallback(member_path)
            except UnicodeDecodeError as e:
                print(f"Error reading file {member_path}: {e}")
                members_writer.add_row(
                    {
                        "pds_name": pds.name,
                        "member_name": member,
                        "type": PDS_Type.ERROR.name,
                        "human_reviewed": False,
                    }
                )
                continue

            member_type = _detect_member_type(content)
            if member_type != PDS_Type.UNDEFINED:
                results[member_type] = results.get(member_type, 0) + 1

            members_writer.add_row(
                {
                    "pds_name": pds.name,
                    "member_name": member,
                    "type": member_type.name,
                    "human_reviewed": False,
                }
            )
            for line_no, line_content in enumerate(content.splitlines(), start=1):
                member_content_writer.add_row(
                    {
                        "pds_name": pds.name,
                        "member_name": member,
                        "line_no": line_no,
                        "content": line_content,
                    }
                )

    # normaliser les résultats pour obtenir un indice de confiance
    total = sum(results.values())
    if total > 0:
        for key in results:
            results[key] /= total
    return results



def load_json_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)


def main(ctx: ProjectContext):
    ctx.extract_pds()

    print(f"Project: {ctx.name}")
    for p in ctx.pds:
        print(f"Found PDS: {p.name} at {p.path}")
    print("Staging and bulk load completed.")
    

def initialize_database(cnx):
    # Créer les tables nécessaires dans la base de données DuckDB
    cnx.execute("CREATE SEQUENCE IF NOT EXISTS pds_id_seq START 1;")
    cnx.execute("CREATE SEQUENCE IF NOT EXISTS members_id_seq START 1;")
    cnx.execute("CREATE SEQUENCE IF NOT EXISTS member_content_id_seq START 1;")
    
    cnx.execute("""                
        CREATE TABLE IF NOT EXISTS pds (
            id INTEGER PRIMARY KEY default nextval('pds_id_seq'),
            name TEXT,
            path TEXT
        );
                
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY default nextval('members_id_seq'),
            pds_id INTEGER REFERENCES pds(id),
            name TEXT,
            type TEXT default 'UNDEFINED',
            human_reviewed BOOLEAN DEFAULT FALSE
                );

        CREATE TABLE IF NOT EXISTS member_content (
            id INTEGER PRIMARY KEY default nextval('member_content_id_seq'),   
            member_id INTEGER REFERENCES members(id),
                line_no INTEGER,
                content TEXT
                );
    """)
    cnx.commit()
def empty_database_tables(cnx):
    # Supprimer les lignes des tables de la base de données DuckDB . si et seulement sui elle existent déjà.
    cnx.execute("""
        DROP TABLE IF EXISTS member_content;
        DROP TABLE IF EXISTS members;
        DROP TABLE IF EXISTS pds;
    """)
    
    cnx.commit()

if __name__ == "__main__":
    print("Start")

    # charger le contexte à partir de cardif.project.json
    ctx_data = load_json_file("cardif.project.json")
    dbfile = ctx_data.get("dbfile")

    cnx = duckdb.connect(database=dbfile, read_only=False)
    
    empty_database_tables(cnx)
    initialize_database(cnx)


    ctx = ProjectContext(**ctx_data)

    main(ctx)
    print("Done")