"""Regression test for the first real-run bug: Swagger showed the upload field as a text box."""
from app.main import app


def test_upload_field_is_described_as_binary_file():
    schema = app.openapi()["components"]["schemas"]["Body_upload_documents_api_documents_post"]
    assert schema["properties"]["files"]["items"]["format"] == "binary"
