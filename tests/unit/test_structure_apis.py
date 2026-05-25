import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Mock the environment to disable Auth dependency before importing backend app
os.environ["OAUTH_CLIENT_ID"] = ""

from backend.main import app  # noqa: E402
from backend.routes.agent import STRUCTURE_CACHE_DIR  # noqa: E402


@pytest.fixture(autouse=True)
def setup_teardown_cache():
    # Clean up structure cache directory before and after tests
    if STRUCTURE_CACHE_DIR.exists():
        shutil.rmtree(STRUCTURE_CACHE_DIR)
    yield
    if STRUCTURE_CACHE_DIR.exists():
        shutil.rmtree(STRUCTURE_CACHE_DIR)


def test_get_pdb_structure_success():
    client = TestClient(app)

    # First fetch (should trigger download and cache)
    pdb_id = "4ZQK"
    response = client.get(f"/api/v3/structure/pdb/{pdb_id}?file_format=pdb")
    assert response.status_code == 200
    assert len(response.content) > 0
    assert b"HEADER" in response.content or b"ATOM" in response.content

    cache_file = STRUCTURE_CACHE_DIR / f"{pdb_id}.pdb"
    assert cache_file.exists()

    # Second fetch (should hit cache)
    response_cached = client.get(
        f"/api/v3/structure/pdb/{pdb_id}?file_format=pdb"
    )
    assert response_cached.status_code == 200
    assert response_cached.content == response.content


def test_get_pdb_structure_invalid_id():
    client = TestClient(app)

    # Invalid length/format ID
    response = client.get("/api/v3/structure/pdb/INVALID_ID")
    assert response.status_code == 400
    assert "Invalid PDB ID" in response.json()["detail"]


def test_get_local_structure_success(tmp_path):
    client = TestClient(app)

    # Resolve workspace root and create a test PDB file in the workspace
    workspace_root = Path(__file__).parent.parent.parent.resolve()
    test_pdb = workspace_root / "test_structure_temp.pdb"

    try:
        test_pdb.write_text("ATOM      1  N   ASP A   1      33.916  18.917  11.524")

        response = client.get(f"/api/v3/structure/local?filepath={test_pdb}")
        assert response.status_code == 200
        assert (
            response.content == b"ATOM      1  N   ASP A   1      33.916  18.917  11.524"
        )
    finally:
        if test_pdb.exists():
            test_pdb.unlink()


def test_get_local_structure_directory_traversal():
    client = TestClient(app)

    # Attempt to access outside the workspace (e.g. /etc/passwd or a temp directory outside workspace)
    with tempfile.NamedTemporaryFile(suffix=".pdb") as tmp:
        outside_path = Path(tmp.name).resolve()
        response = client.get(f"/api/v3/structure/local?filepath={outside_path}")
        assert response.status_code == 403
        assert "Access forbidden" in response.json()["detail"]


def test_get_local_structure_invalid_extension():
    client = TestClient(app)

    workspace_root = Path(__file__).parent.parent.parent.resolve()
    test_txt = workspace_root / "test_structure_temp.txt"

    try:
        test_txt.write_text("Hello World")
        response = client.get(f"/api/v3/structure/local?filepath={test_txt}")
        assert response.status_code == 400
        assert "Forbidden file type" in response.json()["detail"]
    finally:
        if test_txt.exists():
            test_txt.unlink()
