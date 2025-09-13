import argparse
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

STATE_FILE = ".html_zip_state.json"


def save_state(processed: set[str]):
    Path(STATE_FILE).write_text(json.dumps(list(processed)))


def load_state() -> set[str]:
    if Path(STATE_FILE).exists():
        return set(json.loads(Path(STATE_FILE).read_text()))
    return set()


def all_html_files(root: Path):
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(".html"):
                yield Path(dirpath) / f


def collect_assets(html_path: Path, root: Path):
    assets = set()
    content = html_path.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(
        r"""(?:src|href)\s*=\s*["'](.*?)["']""", content, flags=re.I
    ):
        raw = match.group(1)
        raw = raw.replace("\\", "/")  # <-- normalise slashes
        if raw.startswith(("http://", "https://", "data:", "#")):
            continue
        abs_path = (html_path.parent / raw).resolve()
        try:
            assets.add(abs_path.relative_to(root.resolve()))
        except ValueError:
            continue
    return assets


def build_zip(root: Path, html_list: list[Path], assets: set, zip_path: Path):
    temp = Path("_tmp")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()

    def copy(rel: Path):
        src = root / rel
        dst = temp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(src, dst)

    for h in html_list:
        copy(h.relative_to(root))
    for a in assets:
        copy(a)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in temp.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(temp))
    shutil.rmtree(temp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=Path, default=Path.cwd())
    parser.add_argument("-o", "--output", default="trilium_part")
    parser.add_argument("-n", "--count", type=int, default=50)
    args = parser.parse_args()

    root = args.input.resolve()
    done = load_state()
    html_iter = (h for h in all_html_files(root) if str(h) not in done)
    batch = []
    assets = set()

    for html in html_iter:
        batch.append(html)
        assets.update(collect_assets(html, root))
        if len(batch) >= args.count:
            zip_name = Path(f"{args.output}_{len(done)//args.count + 1}.zip")
            build_zip(root, batch, assets, zip_name)
            print(f"Created {zip_name}  ({len(batch)} HTML  {len(assets)} assets)")
            done.update(str(h) for h in batch)
            save_state(done)
            batch.clear()
            assets.clear()

    if batch:
        zip_name = Path(f"{args.output}_{len(done)//args.count + 1}.zip")
        build_zip(root, batch, assets, zip_name)
        print(f"Created final {zip_name}")
        done.update(str(h) for h in batch)
        save_state(done)


if __name__ == "__main__":
    main()
