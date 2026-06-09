import os, sys, argparse, json

sys.path.insert(0, os.path.dirname(__file__))
from sprite_generator import generate_all_assets
from iso_tileset import build_iso_tileset, generate_vfx_sprites

def run(output_root):
    sprites_dir  = os.path.join(output_root,"sprites")
    iso_dir      = os.path.join(sprites_dir,"iso")
    vfx_dir      = os.path.join(sprites_dir,"vfx")
    os.makedirs(sprites_dir, exist_ok=True)
    print("[1/3] Generating character + item sprites...")
    manifest = generate_all_assets(sprites_dir)
    print(f"      Manifest: {manifest}")
    print("[2/3] Generating isometric tiles...")
    iso_keys = build_iso_tileset(iso_dir)
    print(f"      Tiles: {iso_keys}")
    print("[3/3] Generating VFX sprites...")
    generate_vfx_sprites(vfx_dir)
    print("      VFX: hit_0-3.png, magic_0-3.png")
    summary = {
        "sprite_manifest": manifest,
        "iso_tiles": iso_keys,
        "vfx": ["hit","magic"],
        "output_root": output_root
    }
    summary_path = os.path.join(output_root,"pipeline_summary.json")
    with open(summary_path,"w") as f:
        json.dump(summary,f,indent=2)
    print(f"\nDone. Summary: {summary_path}")

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="../../godot/assets", help="Output root dir")
    args = parser.parse_args()
    run(args.out)
