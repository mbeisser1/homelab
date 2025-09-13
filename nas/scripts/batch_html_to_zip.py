import os
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Set, Tuple


class HTMLBatchExporter:
    def __init__(self, input_dir: str, output_dir: str, max_size_mb: int = 250):
        self.input_dir = Path(input_dir).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.attachments_dir = self.input_dir / "attachments"

    def normalize_path(self, path_str: str) -> Path:
        """Smart path normalization handling URL encoding and separators"""
        # URL decode first
        decoded = urllib.parse.unquote(path_str)

        # Normalize separators
        normalized = decoded.replace("\\", "/")

        # Remove leading ./ or .\
        normalized = re.sub(r"^\.?[\\/]", "", normalized)

        return Path(normalized)

    def extract_attachment_paths(self, html_content: str) -> Set[Path]:
        """Extract and normalize attachment paths from HTML content"""
        attachments = set()

        # Comprehensive regex for src/href attributes
        patterns = [
            r'<[^>]+(?:src|href)\s*=\s*["\']([^"\']+)["\'][^>]*>',
            r'url\(["\']?([^"\']+)["\']?\)',
            r'poster\s*=\s*["\']([^"\']+)["\']',  # for video poster
            r'data-src\s*=\s*["\']([^"\']+)["\']',  # for lazy-loaded images
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                path = self.normalize_path(match)

                # Check if it's a local attachment
                if not self.is_external_url(str(path)):
                    # Resolve against input directory
                    full_path = (self.input_dir / path).resolve()

                    # Check if file exists (try variations)
                    if self.find_existing_file(full_path):
                        attachments.add(path)

        return attachments

    def is_external_url(self, url: str) -> bool:
        """Check if URL is external (http, https, data:, etc.)"""
        return bool(re.match(r"^(https?|data|ftp|mailto):", url, re.IGNORECASE))

    def find_existing_file(self, path: Path) -> bool:
        """Check if file exists, trying case variations"""
        if path.exists():
            return True

        # Try case-insensitive search in parent directory
        parent = path.parent
        if parent.exists():
            name_lower = path.name.lower()
            for item in parent.iterdir():
                if item.name.lower() == name_lower:
                    return True

        return False

    def copy_file_with_structure(self, src_path: Path, dst_base: Path) -> int:
        """Copy file maintaining directory structure"""
        relative_path = src_path.relative_to(self.input_dir)
        dst_path = dst_base / relative_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return dst_path.stat().st_size

    def resolve_attachment_path(self, attachment_path: Path) -> Path:
        """Resolve attachment path to actual file"""
        # Try direct path
        full_path = (self.input_dir / attachment_path).resolve()
        if self.find_existing_file(full_path):
            return full_path

        # Try with different separators
        alt_path = Path(str(attachment_path).replace("/", os.sep))
        full_alt = (self.input_dir / alt_path).resolve()
        if self.find_existing_file(full_alt):
            return full_alt

        # Try case-insensitive in attachments directory
        if self.attachments_dir.exists():
            name = attachment_path.name
            for root, dirs, files in os.walk(self.attachments_dir):
                for file in files:
                    if file.lower() == name.lower():
                        return Path(root) / file

        return None

    def create_zip_archive(self, archive_dir: Path, archive_num: int) -> None:
        """Create zip archive from directory"""
        zip_path = self.output_dir / f"archive_{archive_num:03d}.zip"

        with zipfile.ZipFile(
            zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zipf:
            for file_path in archive_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(archive_dir)
                    zipf.write(file_path, arcname)

        print(f"Created: {zip_path} ({zip_path.stat().st_size / (1024*1024):.1f}MB)")
        shutil.rmtree(archive_dir)

    def process_html_batch(self, html_files: List[Path], start_idx: int) -> int:
        """Process batch with improved path handling"""
        current_archive = 1
        current_size = 0
        current_archive_dir = self.output_dir / f"temp_archive_{current_archive:03d}"

        processed_count = 0
        missing_files = []

        for i, html_file in enumerate(html_files[start_idx:], start=start_idx):
            if current_size > self.max_size_bytes:
                self.create_zip_archive(current_archive_dir, current_archive)
                current_archive += 1
                current_size = 0
                current_archive_dir = (
                    self.output_dir / f"temp_archive_{current_archive:03d}"
                )

            try:
                with open(html_file, "r", encoding="utf-8") as f:
                    html_content = f.read()
            except UnicodeDecodeError:
                with open(html_file, "r", encoding="latin-1") as f:
                    html_content = f.read()

            attachments = self.extract_attachment_paths(html_content)

            # Copy HTML file
            html_size = self.copy_file_with_structure(html_file, current_archive_dir)
            current_size += html_size

            # Copy attachments with improved resolution
            for attachment in attachments:
                resolved_path = self.resolve_attachment_path(attachment)
                if resolved_path:
                    attachment_size = self.copy_file_with_structure(
                        resolved_path, current_archive_dir
                    )
                    current_size += attachment_size
                else:
                    missing_files.append(str(attachment))

            processed_count += 1

            if processed_count % 10 == 0:
                print(
                    f"Processed {processed_count} files, current archive: {current_size / (1024*1024):.1f}MB"
                )

        if missing_files:
            print(f"Warning: {len(missing_files)} attachments not found")

        if current_size > 0:
            self.create_zip_archive(current_archive_dir, current_archive)

        return processed_count

    def run(self):
        """Main execution"""
        print(f"Starting batch export...")
        print(f"Input: {self.input_dir}")
        print(f"Output: {self.output_dir}")
        print(f"Max size: {self.max_size_bytes / (1024*1024):.0f}MB")

        self.output_dir.mkdir(parents=True, exist_ok=True)

        html_files = list(self.input_dir.rglob("*.html"))
        print(f"Found {len(html_files)} HTML files")

        if not html_files:
            print("No HTML files found!")
            return

        processed = self.process_html_batch(html_files, 0)
        print(f"Completed! Processed {processed} files")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch export HTML files and attachments to zip archives"
    )
    parser.add_argument("input_dir", help="Input directory containing HTML files")
    parser.add_argument("output_dir", help="Output directory for zip archives")
    parser.add_argument(
        "--max-size",
        type=int,
        default=250,
        help="Maximum size per archive in MB (default: 250)",
    )

    args = parser.parse_args()

    exporter = HTMLBatchExporter(args.input_dir, args.output_dir, args.max_size)
    exporter.run()


if __name__ == "__main__":
    main()
