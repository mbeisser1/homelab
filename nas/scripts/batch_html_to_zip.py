import logging
import os
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HTMLBatchExporter:
    def __init__(self, input_dir: str, output_dir: str, max_size_mb: int = 250):
        self.input_dir = Path(input_dir).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.large_asset_threshold = 50 * 1024 * 1024  # 50MB
        self.attachments_dir = self.input_dir / "attachments"
        self.missing_files = []
        self.large_html_files = []  # Track HTML files with large assets

    def normalize_path(self, path_str: str) -> Path:
        decoded = urllib.parse.unquote(path_str)
        normalized = decoded.replace("\\", "/")
        normalized = re.sub(r"^\.?[\\/]", "", normalized)
        return Path(normalized)

    def extract_attachment_paths(self, html_content: str) -> Set[Path]:
        attachments = set()
        patterns = [
            r'<[^>]+(?:src|href)\s*=\s*["\']([^"\']+)["\'][^>]*>',
            r'url\(["\']?([^"\']+)["\']?\)',
            r'poster\s*=\s*["\']([^"\']+)["\']',
            r'data-src\s*=\s*["\']([^"\']+)["\']',
            r'<source[^>]+src\s*=\s*["\']([^"\']+)["\']',
            r'<video[^>]+src\s*=\s*["\']([^"\']+)["\']',
            r'<div[^>]*class[^>]*attachment[^>]*>.*?<(?:img|video|source)[^>]+src\s*=\s*["\']([^"\']+)["\'].*?</div>',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                if isinstance(match, tuple):
                    path_str = match[0] if match else ""
                else:
                    path_str = match

                if self.should_skip_path(path_str):
                    continue

                path = self.normalize_path(path_str)

                if not self.is_external_url(str(path)):
                    media_extensions = {
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".gif",
                        ".mp4",
                        ".mov",
                        ".avi",
                        ".m4v",
                        ".mp3",
                        ".m4a",
                        ".wav",
                        ".pdf",
                    }
                    if (
                        path.suffix.lower() in media_extensions
                        or "attachments" in str(path).lower()
                    ):
                        attachments.add(path)

        return attachments

    def should_skip_path(self, path: str) -> bool:
        skip_patterns = [
            r"^sms:",
            r"^tel:",
            r"^mailto:",
            r"^javascript:",
            r"^#",
            r"^data:",
            r"^about:",
            r"^\s*$",
        ]
        return any(re.match(pattern, path, re.IGNORECASE) for pattern in skip_patterns)

    def is_external_url(self, url: str) -> bool:
        return bool(re.match(r"^(https?|data|ftp):", url, re.IGNORECASE))

    def find_existing_file(self, path: Path) -> Optional[Path]:
        if path.exists():
            return path

        parent = path.parent
        if parent.exists():
            name_lower = path.name.lower()
            for item in parent.iterdir():
                if item.name.lower() == name_lower:
                    return item

        if self.attachments_dir.exists():
            name = path.name
            for root, dirs, files in os.walk(self.attachments_dir):
                for file in files:
                    if file.lower() == name.lower():
                        return Path(root) / file
        return None

    def copy_file_with_structure(self, src_path: Path, dst_base: Path) -> int:
        try:
            if not src_path.exists():
                logger.warning(f"File not found: {src_path}")
                self.missing_files.append(str(src_path))
                return 0

            relative_path = src_path.relative_to(self.input_dir)
            dst_path = dst_base / relative_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_path, dst_path)
            return dst_path.stat().st_size

        except Exception as e:
            logger.warning(f"Failed to copy {src_path}: {e}")
            self.missing_files.append(str(src_path))
            return 0

    def resolve_attachment_path(self, attachment_path: Path) -> Optional[Path]:
        full_path = (self.input_dir / attachment_path).resolve()
        found = self.find_existing_file(full_path)
        if found:
            return found

        alt_path = Path(str(attachment_path).replace("/", os.sep))
        full_alt = (self.input_dir / alt_path).resolve()
        found = self.find_existing_file(full_alt)
        if found:
            return full_alt
        return None

    def calculate_total_asset_size(self, attachments: Set[Path]) -> int:
        """Calculate total size of all attachments in bytes"""
        total_size = 0
        for attachment in attachments:
            resolved_path = self.resolve_attachment_path(attachment)
            if resolved_path and resolved_path.exists():
                total_size += resolved_path.stat().st_size
        return total_size

    def create_individual_archive(
        self, html_file: Path, attachments: Set[Path], archive_num: int
    ) -> None:
        """Create a separate archive for HTML files with large assets"""
        archive_dir = self.output_dir / f"temp_large_{archive_num:03d}"

        # Copy HTML file
        html_size = self.copy_file_with_structure(html_file, archive_dir)

        # Copy all attachments
        total_asset_size = 0
        for attachment in attachments:
            resolved_path = self.resolve_attachment_path(attachment)
            if resolved_path:
                attachment_size = self.copy_file_with_structure(
                    resolved_path, archive_dir
                )
                total_asset_size += attachment_size

        # Create zip
        zip_path = self.output_dir / f"large_assets_{archive_num:03d}.zip"
        with zipfile.ZipFile(
            zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zipf:
            for file_path in archive_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(archive_dir)
                    zipf.write(file_path, arcname)

        logger.info(
            f"Created large archive: {zip_path} ({zip_path.stat().st_size / (1024*1024):.1f}MB)"
        )
        logger.info(f"  - HTML: {html_file.name}")
        logger.info(f"  - Assets: {total_asset_size / (1024*1024):.1f}MB")
        shutil.rmtree(archive_dir)

    def create_zip_archive(self, archive_dir: Path, archive_num: int) -> None:
        zip_path = self.output_dir / f"archive_{archive_num:03d}.zip"

        with zipfile.ZipFile(
            zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zipf:
            for file_path in archive_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(archive_dir)
                    zipf.write(file_path, arcname)

        logger.info(
            f"Created: {zip_path} ({zip_path.stat().st_size / (1024*1024):.1f}MB)"
        )
        shutil.rmtree(archive_dir)

    def process_html_batch(self, html_files: List[Path], start_idx: int) -> int:
        current_archive = 1
        large_archive = 1
        current_size = 0
        current_archive_dir = self.output_dir / f"temp_archive_{current_archive:03d}"

        processed_count = 0

        for i, html_file in enumerate(html_files[start_idx:], start=start_idx):
            try:
                with open(html_file, "r", encoding="utf-8") as f:
                    html_content = f.read()
            except UnicodeDecodeError:
                with open(html_file, "r", encoding="latin-1") as f:
                    html_content = f.read()
            except Exception as e:
                logger.warning(f"Failed to read {html_file}: {e}")
                continue

            attachments = self.extract_attachment_paths(html_content)

            # Calculate total asset size
            total_asset_size = self.calculate_total_asset_size(attachments)

            # Check if this HTML file has large assets (>50MB)
            if total_asset_size > self.large_asset_threshold:
                logger.info(
                    f"Large assets detected in {html_file.name}: {total_asset_size / (1024*1024):.1f}MB"
                )
                self.large_html_files.append((html_file, attachments, total_asset_size))

                # Create individual archive for large assets
                self.create_individual_archive(html_file, attachments, large_archive)
                large_archive += 1
                continue  # Skip regular processing for large files

            # Regular processing for normal files
            if current_size > self.max_size_bytes:
                self.create_zip_archive(current_archive_dir, current_archive)
                current_archive += 1
                current_size = 0
                current_archive_dir = (
                    self.output_dir / f"temp_archive_{current_archive:03d}"
                )

            # Copy HTML file
            html_size = self.copy_file_with_structure(html_file, current_archive_dir)
            current_size += html_size

            # Copy attachments
            for attachment in attachments:
                resolved_path = self.resolve_attachment_path(attachment)
                if resolved_path:
                    attachment_size = self.copy_file_with_structure(
                        resolved_path, current_archive_dir
                    )
                    current_size += attachment_size
                else:
                    logger.warning(
                        f"Attachment not found: {attachment} (referenced in {html_file.name})"
                    )
                    self.missing_files.append(f"{html_file.name} -> {attachment}")

            processed_count += 1

            if processed_count % 10 == 0:
                logger.info(
                    f"Processed {processed_count} files, current archive: {current_size / (1024*1024):.1f}MB"
                )

        if current_size > 0:
            self.create_zip_archive(current_archive_dir, current_archive)

        return processed_count

    def run(self):
        logger.info(f"Starting batch export...")
        logger.info(f"Input: {self.input_dir}")
        logger.info(f"Output: {self.output_dir}")
        logger.info(f"Max size: {self.max_size_bytes / (1024*1024):.0f}MB")
        logger.info(
            f"Large asset threshold: {self.large_asset_threshold / (1024*1024):.0f}MB"
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        html_files = list(self.input_dir.rglob("*.html"))
        logger.info(f"Found {len(html_files)} HTML files")

        if not html_files:
            logger.error("No HTML files found!")
            return

        processed = self.process_html_batch(html_files, 0)

        # Report on large HTML files found
        if self.large_html_files:
            logger.info(f"\nLarge HTML files found: {len(self.large_html_files)}")
            for html_file, attachments, size in sorted(
                self.large_html_files, key=lambda x: x[2], reverse=True
            ):
                logger.info(f"  {html_file.name}: {size / (1024*1024):.1f}MB assets")

        if self.missing_files:
            missing_log = self.output_dir / "missing_files.log"
            with open(missing_log, "w") as f:
                f.write("\n".join(self.missing_files))
            logger.warning(
                f"Logged {len(self.missing_files)} missing files to {missing_log}"
            )

        logger.info(
            f"Completed! Processed {processed} regular files and {len(self.large_html_files)} large files"
        )


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
