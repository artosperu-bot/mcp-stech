from pathlib import Path


def test_chatgpt_bridge_migration_sets_filtered_index_session_options():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "013_chatgpt_research_bridge_v1.sql"
    sql = sql_path.read_text(encoding="utf-8").upper()
    create_pos = sql.index("CREATE UNIQUE INDEX UX_PRODUCT_WORK_ITEM_ACTIVE_KEY")
    prefix = sql[:create_pos]

    required = (
        "SET ANSI_NULLS ON;",
        "SET QUOTED_IDENTIFIER ON;",
        "SET ANSI_PADDING ON;",
        "SET ANSI_WARNINGS ON;",
        "SET ARITHABORT ON;",
        "SET CONCAT_NULL_YIELDS_NULL ON;",
        "SET NUMERIC_ROUNDABORT OFF;",
    )

    missing = [statement for statement in required if statement not in prefix]
    assert not missing, f"filtered-index SET options missing before CREATE INDEX: {missing}"
