#!/usr/bin/env python3
"""Bootstrap script to prepare PDB targets for the protein design evaluation harness."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path to import agent modules
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.tools.aidd_prepare_tool import aidd_prepare_handler

async def bootstrap_task(
    task_id: str,
    pdb_id: str,
    chains: list[str],
    output_pdb_path: Path,
) -> bool:
    print(f"--- Bootstrapping {task_id} (PDB: {pdb_id}, Chains: {chains}) ---")
    if output_pdb_path.exists():
        print(f"Target already exists at {output_pdb_path}. Skipping download.")
        return True

    # 1. Download full PDB
    temp_raw_pdb = PROJECT_ROOT / "examples" / "protein_design" / "raw" / f"{pdb_id}.pdb"
    temp_raw_pdb.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Step 1: Downloading PDB {pdb_id} from RCSB...")
    download_res, download_ok = await aidd_prepare_handler(
        {
            "operation": "download_pdb",
            "pdb_id": pdb_id,
            "output_path": str(temp_raw_pdb),
        }
    )
    
    if not download_ok:
        print(f"Failed to download PDB {pdb_id}: {download_res}")
        return False
        
    print(f"Successfully downloaded PDB {pdb_id} to {temp_raw_pdb}")
    
    # 2. Crop structure to only target chain
    output_pdb_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Step 2: Cropping structure to chains {chains}...")
    crop_res, crop_ok = await aidd_prepare_handler(
        {
            "operation": "crop_structure",
            "input_path": str(temp_raw_pdb),
            "chains": chains,
            "output_path": str(output_pdb_path),
        }
    )
    
    if not crop_ok:
        print(f"Failed to crop structure: {crop_res}")
        return False
        
    print(f"Step 3: Verifying final cropped PDB at {output_pdb_path}")
    if output_pdb_path.exists():
        print(f"Success! Prepared PDB target saved at {output_pdb_path}")
        # Clean up temporary raw PDB to prevent clutter (RULE 5: Please don't create too many files)
        try:
            temp_raw_pdb.unlink()
            if not any(temp_raw_pdb.parent.iterdir()):
                temp_raw_pdb.parent.rmdir()
        except Exception as e:
            print(f"Warning: Could not remove temporary raw PDB: {e}")
        return True
    else:
        print("Verification failed: Output PDB does not exist.")
        return False

async def main() -> None:
    targets = [
        {
            "task_id": "il7ra_hotspot",
            "pdb_id": "3DI2",
            "chains": ["A"],
            "output_pdb_path": PROJECT_ROOT / "examples" / "protein_design" / "il7ra.pdb",
        },
        {
            "task_id": "pdl1_hotspot",
            "pdb_id": "4ZQK",
            "chains": ["A"],
            "output_pdb_path": PROJECT_ROOT / "examples" / "protein_design" / "pdl1.pdb",
        }
    ]
    
    success = True
    for t in targets:
        ok = await bootstrap_task(
            task_id=t["task_id"],
            pdb_id=t["pdb_id"],
            chains=t["chains"],
            output_pdb_path=t["output_pdb_path"],
        )
        if not ok:
            success = False
            
    if success:
        print("\nAll evaluation targets bootstrapped successfully!")
        sys.exit(0)
    else:
        print("\nSome evaluation targets failed to bootstrap.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
