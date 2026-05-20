from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from agent.core.tools import create_builtin_tools
from agent.tools import aidd_prepare_tool


PDL1_PD1_4ZQK_REAL_PDB_FRAGMENT = """\
HEADER    IMMUNE SYSTEM                           10-MAY-15   4ZQK
TITLE     STRUCTURE OF THE COMPLEX OF HUMAN PROGRAMMED DEATH-1 (PD-1) AND ITS
TITLE    2 LIGAND PD-L1.
ATOM    290  N   TYR A  56      -6.305  50.962 115.345  1.00 35.61           N
ATOM    291  CA  TYR A  56      -6.936  51.319 114.087  1.00 36.44           C
ATOM    292  C   TYR A  56      -7.231  50.060 113.250  1.00 37.26           C
ATOM    293  O   TYR A  56      -6.386  49.166 113.096  1.00 41.18           O
ATOM    294  CB  TYR A  56      -5.962  52.240 113.365  1.00 39.41           C
ATOM    295  CG  TYR A  56      -6.244  52.629 111.929  1.00 39.56           C
ATOM    296  CD1 TYR A  56      -7.340  53.394 111.596  1.00 39.93           C
ATOM    297  CD2 TYR A  56      -5.386  52.251 110.914  1.00 39.68           C
ATOM    298  CE1 TYR A  56      -7.590  53.771 110.281  1.00 41.90           C
ATOM    299  CE2 TYR A  56      -5.645  52.597 109.594  1.00 43.63           C
ATOM    300  CZ  TYR A  56      -6.733  53.370 109.271  1.00 42.68           C
ATOM    301  OH  TYR A  56      -6.956  53.720 107.928  1.00 41.24           O
ATOM    316  N   GLU A  58      -9.052  49.219 109.375  1.00 40.06           N
ATOM    317  CA  GLU A  58      -9.621  49.714 108.138  1.00 45.75           C
ATOM    318  C   GLU A  58      -9.868  48.553 107.202  1.00 42.76           C
ATOM    319  O   GLU A  58      -9.252  47.508 107.325  1.00 42.17           O
ATOM    320  CB  GLU A  58      -8.676  50.722 107.456  1.00 47.11           C
ATOM    321  CG  GLU A  58      -7.294  50.146 107.176  1.00 51.64           C
ATOM    322  CD  GLU A  58      -6.618  50.763 105.965  1.00 62.96           C
ATOM    323  OE1 GLU A  58      -7.321  51.391 105.158  1.00 74.70           O
ATOM    324  OE2 GLU A  58      -5.381  50.634 105.803  1.00 68.40           O
ATOM    727  N   ARG A 113      -7.076  45.673 107.577  1.00 44.69           N
ATOM    728  CA  ARG A 113      -5.786  46.019 108.168  1.00 46.90           C
ATOM    729  C   ARG A 113      -5.990  46.496 109.578  1.00 43.81           C
ATOM    730  O   ARG A 113      -6.912  47.263 109.854  1.00 39.01           O
ATOM    731  CB  ARG A 113      -5.190  47.149 107.390  1.00 56.02           C
ATOM    732  CG  ARG A 113      -3.989  46.801 106.557  1.00 60.75           C
ATOM    733  CD  ARG A 113      -3.934  47.864 105.503  1.00 66.96           C
ATOM    735  CZ  ARG A 113      -2.295  48.912 104.012  1.00 80.29           C
ATOM    736  NH1 ARG A 113      -3.017  50.039 103.918  1.00 73.51           N
ATOM    737  NH2 ARG A 113      -1.146  48.826 103.368  1.00 86.67           N
ATOM    744  N   MET A 115      -3.759  48.214 112.803  1.00 37.69           N
ATOM    745  CA  MET A 115      -2.511  48.853 113.248  1.00 37.10           C
ATOM    746  C   MET A 115      -2.674  49.095 114.722  1.00 36.48           C
ATOM    747  O   MET A 115      -3.731  49.604 115.149  1.00 33.02           O
ATOM    748  CB  MET A 115      -2.280  50.192 112.533  1.00 36.55           C
ATOM    749  CG  MET A 115      -0.971  50.923 112.868  1.00 39.27           C
ATOM    750  SD  MET A 115      -0.873  51.792 114.471  1.00 41.96           S
ATOM    751  CE  MET A 115      -1.976  53.124 114.076  1.00 40.32           C
ATOM    786  N   ALA A 121       5.001  51.111 116.982  1.00 45.22           N
ATOM    787  CA  ALA A 121       3.892  50.636 116.058  1.00 41.12           C
ATOM    788  C   ALA A 121       4.137  49.559 115.026  1.00 38.91           C
ATOM    789  O   ALA A 121       5.228  49.437 114.509  1.00 38.87           O
ATOM    790  CB  ALA A 121       3.302  51.803 115.307  1.00 45.34           C
ATOM    791  N   ASP A 122       3.066  48.847 114.666  1.00 36.79           N
ATOM    792  CA  ASP A 122       3.095  47.831 113.625  1.00 37.99           C
ATOM    793  C   ASP A 122       1.696  47.567 113.098  1.00 39.84           C
ATOM    794  O   ASP A 122       0.697  48.035 113.670  1.00 39.24           O
ATOM    795  CB  ASP A 122       3.664  46.529 114.182  1.00 43.64           C
ATOM    796  CG  ASP A 122       4.123  45.540 113.112  1.00 45.90           C
ATOM    797  OD1 ASP A 122       4.346  45.904 111.919  1.00 44.52           O
ATOM    798  OD2 ASP A 122       4.273  44.372 113.506  1.00 45.92           O
ATOM    799  N   TYR A 123       1.631  46.877 111.954  1.00 40.56           N
ATOM    800  CA  TYR A 123       0.348  46.454 111.365  1.00 40.56           C
ATOM    801  C   TYR A 123       0.423  45.151 110.603  1.00 40.66           C
ATOM    802  O   TYR A 123       1.481  44.726 110.235  1.00 43.74           O
ATOM    803  CB  TYR A 123      -0.192  47.498 110.388  1.00 40.90           C
ATOM    804  CG  TYR A 123       0.659  47.887 109.181  1.00 38.26           C
ATOM    805  CD1 TYR A 123       0.623  47.180 107.995  1.00 38.31           C
ATOM    806  CD2 TYR A 123       1.413  49.042 109.213  1.00 39.90           C
ATOM    807  CE1 TYR A 123       1.337  47.608 106.860  1.00 39.54           C
ATOM    808  CE2 TYR A 123       2.159  49.462 108.122  1.00 43.23           C
ATOM    809  CZ  TYR A 123       2.101  48.745 106.932  1.00 42.91           C
ATOM    810  OH  TYR A 123       2.836  49.235 105.880  1.00 46.43           O
ATOM    811  N   LYS A 124      -0.738  44.588 110.318  1.00 43.09           N
ATOM    812  CA  LYS A 124      -0.904  43.321 109.602  1.00 44.22           C
ATOM    813  C   LYS A 124      -2.181  43.357 108.780  1.00 42.01           C
ATOM    814  O   LYS A 124      -3.056  44.195 109.016  1.00 42.83           O
ATOM    815  CB  LYS A 124      -1.092  42.162 110.595  1.00 46.64           C
ATOM    816  CG  LYS A 124       0.077  41.844 111.501  1.00 47.59           C
ATOM    817  CD  LYS A 124       1.334  41.328 110.797  1.00 47.00           C
ATOM    818  CE  LYS A 124       2.503  42.200 111.245  1.00 50.80           C
ATOM    819  NZ  LYS A 124       3.762  41.477 111.375  1.00 57.92           N
ATOM    820  N   ARG A 125      -2.300  42.409 107.852  1.00 43.21           N
ATOM    821  CA  ARG A 125      -3.472  42.242 106.980  1.00 44.14           C
ATOM    822  C   ARG A 125      -4.168  40.918 107.265  1.00 44.47           C
ATOM    823  O   ARG A 125      -3.518  39.887 107.531  1.00 41.87           O
ATOM    824  CB  ARG A 125      -3.014  42.183 105.495  1.00 53.04           C
ATOM    825  CG  ARG A 125      -2.321  43.439 104.946  1.00 60.72           C
ATOM    826  CD  ARG A 125      -1.659  43.202 103.567  1.00 65.45           C
ATOM   1112  N   ASN B  66       8.248  52.721 109.135  1.00 38.64           N
ATOM   1113  CA  ASN B  66       8.632  51.329 109.311  1.00 41.70           C
ATOM   1114  C   ASN B  66       9.171  50.703 108.007  1.00 45.77           C
ATOM   1115  O   ASN B  66       8.744  51.069 106.878  1.00 45.44           O
ATOM   1116  CB  ASN B  66       7.433  50.523 109.835  1.00 42.28           C
ATOM   1117  CG  ASN B  66       7.200  50.673 111.352  1.00 43.25           C
ATOM   1118  OD1 ASN B  66       7.836  51.468 112.018  1.00 41.18           O
ATOM   1134  N   TYR B  68       9.364  47.141 106.056  1.00 42.78           N
ATOM   1135  CA  TYR B  68       8.704  45.829 105.967  1.00 45.19           C
ATOM   1136  C   TYR B  68       9.319  44.980 104.858  1.00 49.79           C
ATOM   1137  O   TYR B  68       9.836  45.510 103.883  1.00 51.89           O
ATOM   1138  CB  TYR B  68       7.194  45.948 105.724  1.00 43.95           C
ATOM   1139  CG  TYR B  68       6.456  46.437 106.942  1.00 43.30           C
ATOM   1140  CD1 TYR B  68       6.139  45.582 107.987  1.00 47.20           C
ATOM   1141  CD2 TYR B  68       6.098  47.770 107.066  1.00 42.71           C
ATOM   1142  CE1 TYR B  68       5.494  46.048 109.137  1.00 46.27           C
ATOM   1143  CE2 TYR B  68       5.443  48.237 108.180  1.00 41.61           C
ATOM   1144  CZ  TYR B  68       5.160  47.389 109.224  1.00 43.85           C
ATOM   1145  OH  TYR B  68       4.549  47.911 110.347  1.00 42.32           O
ATOM   1186  N   GLN B  75       2.178  38.759 104.036  1.00 59.04           N
ATOM   1187  CA  GLN B  75       2.039  39.418 105.359  1.00 55.79           C
ATOM   1188  C   GLN B  75       3.176  40.420 105.574  1.00 52.37           C
ATOM   1189  O   GLN B  75       4.350  40.140 105.321  1.00 54.46           O
ATOM   1190  CB  GLN B  75       1.893  38.394 106.520  1.00 55.24           C
ATOM   1191  CG  GLN B  75       1.293  38.891 107.843  1.00 54.36           C
ATOM   1192  CD  GLN B  75      -0.060  39.615 107.706  1.00 59.60           C
ATOM   1193  OE1 GLN B  75      -0.128  40.830 107.388  1.00 55.95           O
ATOM   1194  NE2 GLN B  75      -1.143  38.889 107.966  1.00 61.14           N
ATOM   1210  N   LYS B  78       7.584  43.449 110.101  1.00 48.63           N
ATOM   1211  CA  LYS B  78       8.380  44.589 110.414  1.00 47.26           C
ATOM   1212  C   LYS B  78       9.820  44.169 110.603  1.00 51.20           C
ATOM   1213  O   LYS B  78      10.082  43.211 111.299  1.00 58.55           O
ATOM   1214  CB  LYS B  78       7.850  45.241 111.705  1.00 48.80           C
ATOM   1215  CG  LYS B  78       8.565  46.530 112.119  1.00 45.82           C
ATOM   1216  CD  LYS B  78       8.440  46.831 113.595  1.00 45.33           C
ATOM   1217  CE  LYS B  78       7.939  48.197 113.829  1.00 44.38           C
ATOM   1218  NZ  LYS B  78       7.649  48.544 115.226  1.00 46.82           N
ATOM   1546  N   ALA B 132      -5.257  58.387 112.366  1.00 51.39           N
ATOM   1547  CA  ALA B 132      -4.411  57.226 112.184  1.00 48.56           C
ATOM   1548  C   ALA B 132      -4.506  56.760 110.753  1.00 43.20           C
ATOM   1549  O   ALA B 132      -5.577  56.689 110.213  1.00 46.29           O
ATOM   1550  CB  ALA B 132      -4.788  56.117 113.144  1.00 51.81           C
ATOM   1575  N   GLU B 136       1.920  53.349 102.313  1.00 38.91           N
ATOM   1576  CA  GLU B 136       2.935  52.397 101.859  1.00 40.29           C
ATOM   1577  C   GLU B 136       3.520  52.769 100.526  1.00 41.24           C
ATOM   1578  O   GLU B 136       2.821  53.162  99.621  1.00 41.34           O
ATOM   1579  CB  GLU B 136       2.323  50.999 101.675  1.00 40.81           C
ATOM   1580  CG  GLU B 136       2.025  50.297 102.984  1.00 41.00           C
ATOM   1581  CD  GLU B 136       1.528  48.887 102.786  1.00 45.66           C
ATOM   1582  OE1 GLU B 136       0.900  48.619 101.704  1.00 47.83           O
ATOM   1583  OE2 GLU B 136       1.716  48.053 103.728  1.00 49.56           O
TER
END
"""


@pytest.mark.asyncio
async def test_aidd_prepare_creates_project_and_research_plan(tmp_path):
    project_dir = tmp_path / "pd_l1_prep"

    print("STEP 1: Creating a local AIDD preparation project")
    text, ok = await aidd_prepare_tool.aidd_prepare_handler(
        {
            "operation": "create_project",
            "target_name": "PD-L1",
            "pdb_id": "4ZQK",
            "target_chains": ["A"],
            "partner_chains": ["B"],
            "project_dir": str(project_dir),
        }
    )
    print(f"STEP 2: create_project output = {text.strip()}")

    assert ok is True
    payload = json.loads(text)
    manifest_path = Path(payload["manifest"])
    research_plan_path = Path(payload["research_plan"])
    assert manifest_path.exists()
    assert research_plan_path.exists()

    print("STEP 3: Checking the four preparation stages are written to manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["required_stages"] == [
        "literature_research",
        "pdb_download",
        "structure_cropping",
        "hotspot_residue_determination",
    ]
    assert "literature_lookup" in research_plan_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_aidd_prepare_downloads_real_pdb_from_rcsb(tmp_path):
    print("STEP 1: Downloading real 4ZQK coordinates through RCSB")
    text, ok = await aidd_prepare_tool.aidd_prepare_handler(
        {
            "operation": "download_pdb",
            "pdb_id": "4ZQK",
            "output_path": str(tmp_path / "4ZQK.pdb"),
        }
    )
    print(f"STEP 2: download_pdb output = {text.strip()}")

    assert ok is True
    payload = json.loads(text)
    assert payload["source"] == "https://files.rcsb.org/download/4ZQK.pdb"
    content = Path(payload["path"]).read_text(encoding="utf-8")
    assert content.startswith("HEADER    IMMUNE SYSTEM")
    assert "4ZQK" in content[:200]
    assert "ATOM" in content


@pytest.mark.asyncio
async def test_aidd_prepare_crops_structure_by_chain_and_residue_range(tmp_path):
    raw_pdb = tmp_path / "structures" / "raw" / "4ZQK.pdb"
    raw_pdb.parent.mkdir(parents=True)
    raw_pdb.write_text(PDL1_PD1_4ZQK_REAL_PDB_FRAGMENT, encoding="utf-8")
    cropped_pdb = tmp_path / "structures" / "cropped" / "pd_l1_igv.pdb"

    print("STEP 1: Cropping target chain A to a residue interval")
    text, ok = await aidd_prepare_tool.aidd_prepare_handler(
        {
            "operation": "crop_structure",
            "input_path": str(raw_pdb),
            "chains": ["A"],
            "residue_ranges": "A:56-123",
            "output_path": str(cropped_pdb),
        }
    )
    print(f"STEP 2: crop_structure output = {text.strip()}")

    assert ok is True
    payload = json.loads(text)
    assert payload["selected_residue_count"] == 7
    content = cropped_pdb.read_text(encoding="utf-8")

    print("STEP 3: Checking crop retained requested target residues only")
    assert " TYR A  56" in content
    assert " TYR A 123" in content
    assert " GLY A 140" not in content
    assert " ASN B  66" not in content
    assert content.endswith("TER\nEND\n")


@pytest.mark.asyncio
async def test_aidd_prepare_identifies_contact_derived_hotspots(tmp_path):
    raw_pdb = tmp_path / "4ZQK.pdb"
    raw_pdb.write_text(PDL1_PD1_4ZQK_REAL_PDB_FRAGMENT, encoding="utf-8")
    hotspot_path = tmp_path / "hotspots.json"

    print("STEP 1: Ranking target-chain hotspot residues from atom contacts")
    text, ok = await aidd_prepare_tool.aidd_prepare_handler(
        {
            "operation": "identify_hotspots",
            "input_path": str(raw_pdb),
            "target_chains": ["A"],
            "partner_chains": ["B"],
            "hotspot_cutoff": 4.5,
            "top_k": 5,
            "output_path": str(hotspot_path),
        }
    )
    print(f"STEP 2: identify_hotspots output = {text.strip()}")

    assert ok is True
    payload = json.loads(text)
    assert hotspot_path.exists()
    assert payload["status"] == "hotspots_identified"
    assert payload["hotspot_count"] >= 3

    print("STEP 3: Checking known PD-L1 interface-like residues rank as candidates")
    residues = [item["residue"] for item in payload["hotspots"]]
    assert "A:TYR123" in residues[:3]
    assert "A:TYR56" in residues
    assert "A:ASP122" in residues
    assert (
        payload["hotspots"][0]["contact_count"]
        >= payload["hotspots"][-1]["contact_count"]
    )
    assert payload["hotspots"][0]["partner_residues"]


@pytest.mark.asyncio
async def test_aidd_prepare_run_preparation_writes_all_artifacts(tmp_path):
    project_dir = tmp_path / "pd_l1_full_prep"
    print("STEP 1: Running the full AIDD preparation pipeline with public APIs")
    text, ok = await aidd_prepare_tool.aidd_prepare_handler(
        {
            "operation": "run_preparation",
            "target_name": "PD-L1",
            "pdb_id": "4ZQK",
            "target_chains": ["A"],
            "partner_chains": ["B"],
            "project_dir": str(project_dir),
            "residue_ranges": "A:56-123",
            "research_query": "PD-L1 PD-1 interface hotspot residues 4ZQK",
            "limit": 2,
        }
    )
    print(f"STEP 2: run_preparation output = {text.strip()}")

    assert ok is True
    payload = json.loads(text)
    manifest = json.loads(Path(payload["manifest"]).read_text(encoding="utf-8"))

    print("STEP 3: Checking all four preparation artifacts exist")
    for artifact in manifest["artifacts"].values():
        assert Path(artifact).exists()
    assert Path(payload["summary"]).exists()
    assert manifest["stage_status"] == {
        "literature_research": "complete",
        "pdb_download": "complete",
        "structure_cropping": "complete",
        "hotspot_residue_determination": "complete",
    }
    assert payload["top_hotspots"]


@pytest.mark.asyncio
async def test_prepare_aidd_cli_reports_steps_and_missing_inputs():
    print("STEP 1: Running prepare CLI helper with missing options")
    output = StringIO()
    exit_code = await aidd_prepare_tool.run_aidd_preparation_cli(
        target_name="PD-L1",
        pdb_id=None,
        target_chains="A",
        partner_chains="B",
        output=output,
    )
    rendered = output.getvalue()
    print(f"STEP 2: CLI helper output = {rendered.strip()}")

    assert exit_code == 2
    assert "Missing required AIDD preparation options" in rendered
    assert "--pdb-id" in rendered


def test_aidd_prepare_is_registered_for_llm():
    print("STEP 1: Creating built-in tool registry")
    tools = create_builtin_tools(local_mode=True)
    specs = {tool.name: tool for tool in tools}

    print("STEP 2: Checking aidd_prepare is visible to the agent")
    assert "aidd_prepare" in specs
    operations = specs["aidd_prepare"].parameters["properties"]["operation"]["enum"]
    assert "run_preparation" in operations
    assert "download_pdb" in operations
    assert "crop_structure" in operations
    assert "identify_hotspots" in operations
