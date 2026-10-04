#!/usr/bin/env python3
"""Build a Xiaomi Smart Band 8 watchface .bin from a mibandwatchfaces.com maker project.

The maker exports wfDef.json + images/ + images_aod/, which is meant for Xiaomi's
WatchfacePackTool. This script packs it on Linux with the open-source Mi8WfBinTool
and fixes the things that otherwise produce a face showing only its background:

  * every widge_imagelist needs an imageIndexList (value -> image table);
    missing ones are filled with 0..n-1
  * definition indices must be dense (0..n-1 per table, in order of use);
    Mi8WfBinTool pins indices from image_NNNN / imagelist_NNNN file names,
    so assets are renamed sequentially in a staging copy
  * header bytes are matched to a firmware-accepted Band 8 face
    (0x1E = 4, byte 3 of each face header = 2)

Requires python3 and a JDK (javac/java). Usage:
    tools/build.py [project_dir] [-o dist/pip-boy-mb8.bin] [--id 266210095] [--name "fallout pip-boy"]
"""
import argparse
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PACKER_REPO = "zhy8388608/Mi8WfBinTool"
PACKER_SHA = "5e4195ce91b9d8810a7a2233c96b4cba44184adc"
CACHE = Path(__file__).resolve().parent / ".cache"


def packer_classpath():
    cls = CACHE / "Mi8WfBinTool.class"
    if cls.exists():
        return CACHE
    CACHE.mkdir(exist_ok=True)
    src = CACHE / "Mi8WfBinTool.java"
    url = f"https://raw.githubusercontent.com/{PACKER_REPO}/{PACKER_SHA}/Mi8WfBinTool.java"
    print(f"fetching {url}")
    urllib.request.urlretrieve(url, src)
    subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(CACHE), str(src)], check=True)
    return CACHE


def stage(project, out, face_id, name):
    wf = json.loads((project / "wfDef.json").read_text(encoding="utf-8"))
    if face_id:
        wf["id"] = face_id
    if name:
        wf["name"] = name
    for key, folder in (("elementsNormal", "images"), ("elementsAod", "images_aod")):
        (out / folder).mkdir(parents=True, exist_ok=True)
        singles = lists = 0
        for e in wf.get(key, []):
            if e.get("image"):
                new = f"s{singles:02d}"
                shutil.copy(project / folder / f"{e['image']}.png", out / folder / f"{new}.png")
                e["image"] = new
                singles += 1
            if e.get("imageList"):
                renamed = []
                for j, img in enumerate(e["imageList"]):
                    new = f"l{lists:02d}_{j:02d}"
                    shutil.copy(project / folder / f"{img}.png", out / folder / f"{new}.png")
                    renamed.append(new)
                e["imageList"] = renamed
                lists += 1
                if e["type"] == "widge_imagelist" and not e.get("imageIndexList"):
                    e["imageIndexList"] = list(range(len(renamed)))
    preview = wf.get("previewImg", "preview")
    shutil.copy(project / "images" / f"{preview}.png", out / "images" / f"{preview}.png")
    (out / "wfDef.json").write_text(json.dumps(wf, indent=4, ensure_ascii=False), encoding="utf-8")
    return wf


def patch_and_verify(path, wf):
    b = bytearray(path.read_bytes())
    u32 = lambda o: struct.unpack_from("<I", b, o)[0]
    if b[:4] != bytes.fromhex("5aa53412"):
        sys.exit("bad magic")
    faces = struct.unpack_from("<H", b, 0x1C)[0]
    b[0x1E] = 4
    for f in range(faces):
        b[0xA8 + f * 0x58 + 3] = 2

    problems = 0
    for f, key in enumerate(("elementsNormal", "elementsAod")[:faces]):
        fh = 0xA8 + f * 0x58
        n_single, n_list, list_off = u32(fh + 0x18), u32(fh + 0x20), u32(fh + 0x24)
        widgets = [e for e in wf.get(key, []) if e["type"].startswith("widge")]
        w_off = u32(fh + 0x44)
        for i, e in enumerate(widgets):
            p = u32(w_off + i * 16 + 8)
            li = b[p + 8] | b[p + 9] << 8 | b[p + 10] << 16
            if b[p + 11] == 3 and (li >= n_list or b[u32(list_off + li * 16 + 8) + 1] != len(e["imageList"])):
                problems += 1
                print(f"{key}[{i}] {e.get('dataSrc')}: bad image list reference {li}")
        base_n, base_off = u32(fh + 0x08), u32(fh + 0x0C)
        for i in range(base_n):
            p = u32(base_off + i * 16 + 8)
            idx = b[p] | b[p + 1] << 8 | b[p + 2] << 16
            if b[p + 3] == 2 and idx >= n_single:
                problems += 1
                print(f"{key} element {i}: bad image reference {idx}")
            if b[p + 3] == 4:
                print(f"{key} element {i}: element_anim is not supported on Band 8 firmware")
    if problems:
        sys.exit(f"{problems} broken references, not writing output")
    path.write_bytes(b)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=Path(__file__).resolve().parent.parent, type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("dist/pip-boy-mb8.bin"))
    ap.add_argument("--id", help="9-digit watchface id (default: from wfDef.json)")
    ap.add_argument("--name", help="watchface name (default: from wfDef.json)")
    args = ap.parse_args()

    cp = packer_classpath()
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "project"
        wf = stage(args.project.resolve(), staged, args.id, args.name)
        raw = Path(tmp) / "out.bin"
        subprocess.run(["java", "-cp", str(cp), "Mi8WfBinTool", "pack", str(staged), str(raw), "mi8"], check=True)
        patch_and_verify(raw, wf)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(raw, args.output)
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes, id {wf['id']}, name {wf['name']!r})")


if __name__ == "__main__":
    main()
