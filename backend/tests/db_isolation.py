from sqlalchemy.engine import make_url
from sqlalchemy import text

TEST_DATABASE = "docintel_test"


def assert_test_database(engine) -> None:
    database = make_url(str(engine.url)).database
    if database != TEST_DATABASE:
        raise RuntimeError(f"Destructive test operation requires database {TEST_DATABASE!r}, got {database!r}")


def truncate_test_database(engine) -> None:
    assert_test_database(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "TRUNCATE documents, pages, extractions, validation_issues, "
            "processing_events, corrections RESTART IDENTITY CASCADE"
        ))
