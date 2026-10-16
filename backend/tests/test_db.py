from app.config import PipelineConfig, Settings
from app.db import init_db


def test_init_db_is_idempotent(conn):
    init_db(conn)
    init_db(conn)
    names = {r["name"] for r in conn.execute("select name from sqlite_master")}
    assert {"users", "sessions", "documents", "chunks", "chunks_fts"} <= names


def test_fts_tracks_chunk_insert_and_delete(conn, make_user_doc):
    user_id, doc_id = make_user_doc()
    conn.execute(
        "insert into chunks(id,document_id,user_id,ordinal,text,location,char_start,char_end,embedding) "
        "values('c1',?,?,0,'refund policy window','p. 1',0,20,x'00')",
        (doc_id, user_id),
    )
    assert conn.execute("select count(*) from chunks_fts where chunks_fts match 'refund'").fetchone()[0] == 1
    conn.execute("delete from documents where id=?", (doc_id,))
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0
    assert conn.execute("select count(*) from chunks_fts where chunks_fts match 'refund'").fetchone()[0] == 0


def test_settings_pipeline_defaults():
    p = Settings(_env_file=None).pipeline()
    assert p == PipelineConfig()
