# Immich — Google Photos import and archive

Immich on NAS-DEV is used as an import and deduplication engine for Google Photos Takeout. The long-term artifact is the on-disk **library** under `/pool/archive/cloud_backups/immich`. After import, XMP sidecars are embedded into media files so RAR archives are self-contained.

Related docs:

- [New user setup](new_user.md) — `hosted` group and pool permissions
- [Router](router.md) — `immich.bitrealm.dev` DNS
- [Backup](backup.md) — off-site archive copies
- [Disks](disks.md) — `/pool` layout

## Table of contents

- [Workflow](#workflow)
- [Immich server](#immich-server)
- [Library layout](#library-layout)
- [Google Takeout import](#google-takeout-import)
  - [Upload path and storage template](#upload-path-and-storage-template)
- [Troubleshooting](#troubleshooting)
- [Embed XMP sidecars](#embed-xmp-sidecars)
- [RAR archival](#rar-archival)

## Workflow

```mermaid
flowchart LR
    takeout[Google Takeout ZIPs]
    immichGo[immich-go upload]
    uploadDir["upload/{user}/"]
    library["library/{user}/"]
    xmp[Embed XMP into media]
    rar[RAR archive]

    takeout --> immichGo
    immichGo -->|"API upload"| uploadDir
    uploadDir -->|"storage template"| library
    library --> xmp
    xmp --> rar
```

| Step | Tool | Output |
| ---- | ---- | ------ |
| Import + dedup | `immich-go upload from-google-photos` | Originals in `library/{username}/` (after storage template migration) |
| Self-contained media | `exiftool` | Metadata embedded in JPEG/HEIC/MP4 |
| Cold storage | `rar` (RAR5, store mode) | Self-contained RAR volumes on `/pool` or off-site |

Immich UI is useful for browsing during and after import. The end goal is a dated library tree plus RAR archives, not running Immich indefinitely.

## Immich server

Live deploy: `~/docker_compose/immich/`

This doc covers **`immich-server` only** — user, storage path, port, and permissions. Database, Redis, and machine-learning containers must be running for import but are not documented here.

| Setting | Value |
| ------- | ----- |
| Compose file | `~/docker_compose/immich/docker-compose.yml` |
| Container | `immich_server` |
| `user` | `1000:20250` (`mbeisser` + `hosted`) |
| Port | `2283:2283` |
| LAN URL | `http://192.168.50.100:2283` |
| DNS | `immich.bitrealm.dev` → `192.168.50.100` ([router](router.md)) |
| `UPLOAD_LOCATION` | `/pool/archive/cloud_backups/immich` |
| Volume | `${UPLOAD_LOCATION}:/data` |

Relevant `docker-compose.yml` excerpt:

```yaml
immich-server:
  container_name: immich_server
  user: "1000:20250"
  volumes:
    - ${UPLOAD_LOCATION}:/data
  ports:
    - '2283:2283'
```

`.env` essentials:

```dotenv
UPLOAD_LOCATION=/pool/archive/cloud_backups/immich
```

Other variables (DB password, Redis, etc.) are required by the full stack but out of scope for this workflow doc.

### Permissions

Files created under `/data` must be readable and writable on the host mergerfs pool. Match the [hosted group policy](new_user.md):

```bash
sudo mkdir -p /pool/archive/cloud_backups/immich
sudo chgrp -R hosted /pool/archive/cloud_backups/immich
sudo chmod -R g+rwX /pool/archive/cloud_backups/immich
```

`user: "1000:20250"` ensures the container writes as `mbeisser` with primary group `hosted`, consistent with Jellyfin, Samba, and other pool services.

### API key

Create in Immich: **Administration → Account Settings → API Keys**. Use the key only on the LAN; do not commit it to git.

## Library layout

Inside `UPLOAD_LOCATION` (`/pool/archive/cloud_backups/immich`), mounted as `/data` in the container:

| Path | Contents | Archive? |
| ---- | -------- | -------- |
| `library/{username}/` | Original photos and videos (final location with storage template) | **Yes** |
| `upload/{user-id}/` | Staging area during API upload; may be empty after migration | No |
| `thumbs/` | Generated thumbnails | No |
| `encoded-video/` | Transcoded video previews | No |
| `profile/` | User profile images | No |
| `backups/` | Database backups | No |

On this server the admin account username is `admin`, so originals end up under:

```text
/pool/archive/cloud_backups/immich/library/admin/
```

During import you may briefly see files under `upload/<user-uuid>/` (e.g. `upload/f8ac6909-281b-407f-ad31-d55b05ffa48e/`). That is normal — see [upload path](#upload-path-and-storage-template) below.

### Storage template

Configure in **Administration → Settings → Storage Template** (must be enabled for dated paths):

```text
{{y}}/{{M}}/{{d}}/{{filename}}.{{ext}}
```

Example on disk after migration:

```text
library/admin/
└── 2023/
    └── 06/
        └── 17/
            ├── IMG_001.jpg
            └── IMG_001.jpg.xmp
```

Immich creates `.xmp` sidecars alongside originals. The [embed step](#embed-xmp-sidecars) folds that metadata into the media files before RAR archival. Run embed/RAR only after storage template migration has finished moving files out of `upload/`.

## Google Takeout import

### Prerequisites

1. Immich stack running (`docker compose up -d` in `~/docker_compose/immich`)
2. Admin account created in the Immich UI
3. API key generated (see above)
4. [immich-go](https://github.com/simulot/immich-go) binary on the host
5. Google Takeout ZIPs downloaded (multi-part `takeout-*.zip` is supported)

### Import command

Place Takeout ZIPs on the pool (or reference their path). Run from a directory containing the archives:

```bash
cd /pool/archive/cloud_backups/immich

./immich-go upload from-google-photos \
  --server=http://192.168.50.100:2283 \
  --api-key=<API_KEY> \
  --include-trashed=false \
  ./takeout-20260617T040256Z-4-00*.zip
```

Files land in `upload/<user-uuid>/` first, then Immich moves them to `library/admin/` (or your username) when the storage template runs. See [upload path and storage template](#upload-path-and-storage-template).

### Deduplication

`immich-go upload` skips assets that already exist on the server, matching by **SHA-1 checksum** (and metadata). Re-running after partial failures is safe — only missing or failed items are uploaded.

### Recommended flags

| Flag | Default | Notes |
| ---- | ------- | ----- |
| `--include-trashed=false` | `false` | Avoids trashed photos that can trigger stack-delete bugs in Immich |
| `--include-unmatched` | `false` | Set only if you want media files without matching Google JSON metadata |
| `--include-archived` | `true` | Imports archived Google Photos items |
| `--include-partner` | `true` | Imports partner-shared photos |

Large takeouts often need several runs. Per-file failures do not require starting over.

### Upload path and storage template

`immich-go upload` sends files through the **Immich API** — the same path as the mobile app or web UI. The server stores files on disk the same way for every upload method.

```text
immich-go → Immich API → upload/{user}/ → library/{username}/…  (if storage template enabled)
```

| Stage | On-disk path | Notes |
| ----- | ------------ | ----- |
| 1. API upload | `upload/{user-id}/` | Staging; folder name is the user’s internal UUID |
| 2. Storage template migration | `library/{username}/{{y}}/{{M}}/{{d}}/…` | Runs after upload when template is enabled |
| No template | stays in `upload/{user-id}/` | Not used in this workflow |

**Example from NAS-DEV:** files appeared first under `upload/f8ac6909-281b-407f-ad31-d55b05ffa48e/`, then Immich created `library/admin/` and moved them into dated subfolders per the storage template.

**Before embed or RAR:** confirm migration is complete — `library/admin/` contains the originals and `upload/<uuid>/` is empty or gone. Embedding or archiving while files are still in `upload/` targets the wrong tree.

### What immich-go does

- Reads Google Takeout ZIPs in place (no need to unzip first)
- Matches each media file to its `.json` metadata (dates, GPS, albums, people tags)
- Uploads via the Immich API into `upload/{user-id}/`, then the server migrates to `library/{username}/` per the storage template
- Skips duplicates on subsequent runs

**Not used in this workflow:** `immich-go archive from-immich` re-downloads from the server and can create `filename~1.jpg` duplicates on re-runs. Import via `upload`, then archive the on-disk `library/{username}/` folder directly.

## Troubleshooting

### Stack / trash deletion (PostgreSQL FK error)

**Symptom:** Emptying trash fails with a foreign key constraint on `stack."primaryAssetId"`.

**Cause:** Known Immich race condition — stack rows reference assets that were deleted first.

**Prevention:** Use `--include-trashed=false` during import.

**Fix** (back up the database first):

```bash
docker exec -it immich_postgres psql -U <DB_USER> -d <DB_NAME>
```

```sql
-- Orphaned stacks: primaryAssetId points to a missing asset
SELECT s.id, s."primaryAssetId"
FROM stack s
LEFT JOIN asset a ON s."primaryAssetId" = a.id
WHERE a.id IS NULL;

DELETE FROM stack
WHERE "primaryAssetId" NOT IN (SELECT id FROM asset);
```

To fix a single failing asset from the error log:

```sql
DELETE FROM stack WHERE "primaryAssetId" = '<asset-uuid>';
```

### Missing attachment metadata on import

If Google Takeout JSON is missing for a file, the photo may import without full metadata. Use `--include-unmatched` only if you accept that trade-off.

## Embed XMP sidecars

Immich writes `.xmp` sidecars next to originals in `library/{username}/` (e.g. `library/admin/`). Sidecars use Immich’s naming convention: `photo.jpg.xmp` (not `photo.xmp`). For cold-storage RAR archives, embed that metadata into the media files so sidecars are not required.

Immich only puts a **subset** of metadata in sidecars ([Immich XMP docs](https://docs.immich.app/features/xmp-sidecars)):

| Field | XMP tags |
| ----- | -------- |
| Description | `dc:description`, `tiff:ImageDescription` |
| Date/time | `exif:DateTimeOriginal`, `photoshop:DateCreated`, etc. |
| GPS | `exif:GPSLatitude`, `exif:GPSLongitude` |
| Rating | `xmp:Rating` |
| Tags | `digiKam:TagsList` |

Google Takeout may also have left GPS/dates in the **embedded** EXIF of JPEG/HEIC. After import, Immich may duplicate that in the sidecar — embedding merges sidecar into the file; it does not add metadata that exists only in Immich’s database (e.g. face names) unless Immich wrote them to the sidecar as tags.

Install ExifTool:

```bash
sudo apt install libimage-exiftool-perl
```

Script: `nas-dev/scripts/embed_immich_xmp.sh` (run on NAS-DEV against `library/admin/` after storage template migration — the tree with `.xmp` sidecars; thumbs and encoded-video have none).

```bash
# Copy or symlink to NAS-DEV, then:
chmod +x ~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh

LIBRARY=/pool/archive/cloud_backups/immich/library/admin

# 1. Count sidecars
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh stats -d "$LIBRARY"

# 2. Dry-run embed (shows exiftool command + counts)
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh embed -n -d "$LIBRARY"

# 3. Embed (photos + videos; LargeFileSupport for files > 2 GB)
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh embed -d "$LIBRARY"

# 4. Spot-check samples per format (JPEG, HEIC, MP4, …)
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh verify -d "$LIBRARY"

# 5. Delete sidecars after verify passes
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh delete -d "$LIBRARY" -y

# Or: embed + verify in one step; add -y to delete sidecars when verify passes
~/repo/homelab/nas-dev/scripts/embed_immich_xmp.sh all -d "$LIBRARY" -y
```

Manual equivalent (Immich sidecar naming: `IMG_001.jpg.xmp`):

```bash
exiftool -api LargeFileSupport=1 -r -ext jpg -ext jpeg -ext heic -ext png -ext mp4 -ext mov \
  -if '$xmpfile' \
  -tagsfromfile '%d%f.%e.xmp' -all:all \
  -overwrite_original \
  "$LIBRARY"
```

Single-file check:

```bash
exiftool -Gps:all -DateTimeOriginal -Description "$LIBRARY/2023/06/17/IMG_001.jpg"
exiftool -a "$LIBRARY/2023/06/17/IMG_001.jpg.xmp"
```

### Format-specific notes

#### Video (MP4 / MOV)

ExifTool **can** write XMP into MP4 and MOV ([supported types](https://exiftool.org/exiftool_pod.html)). It **cannot** write metadata into MKV, AVI, WEBM, or most other containers — those keep sidecars or lose embeddable metadata.

Important behaviors:

- **Full file rewrite** — ExifTool never patches a few bytes in place. It builds a new file and replaces the original ([FAQ #31](https://exiftool.org/faq.html)). A 4 GB video needs ~4 GB free space temporarily and takes roughly as long as a full copy.
- **Large files** — Use `-api LargeFileSupport=1` for files over 2 GB.
- **Limited tag set** — Immich sidecars only carry description, date, GPS, rating, and tags. Do not expect every QuickTime atom or Google Takeout JSON field to transfer.
- **Already embedded metadata** — Phone videos often have capture date in the container already. The sidecar may only add GPS or description; after embed, run `exiftool` on the file and confirm you are not **losing** data before deleting `.xmp`.

**Unsupported video types** in the library: leave the `.xmp` sidecar alongside the file in the RAR archive, or convert to MP4 first.

#### HEIC / HEIF

ExifTool lists HEIC/HEIF as read/write without extra packages — `libimage-exiftool-perl` is enough for metadata operations. **`libheif` is not required for ExifTool**; it is needed by other tools (image viewers, some converters) to **display** HEIC pixels.

Caveats for iPhone/Google libraries:

- **Distro version** — Ubuntu’s packaged ExifTool can lag upstream. If HEIC writes fail, check `exiftool -ver` and compare with [exiftool.org](https://exiftool.org/). A newer standalone install may help.
- **File rewrite** — Like JPEG and video, writing metadata rewrites the whole HEIC file; ensure free space and complete imports first.
- **Live Photos / motion** — Paired HEIC+MOV stacks may only get metadata on one file; verify both if you keep Live Photo pairs.
- **Fallback** — If embed fails for HEIC, keep the `.xmp` in the archive or re-import with immich-go HEIC→JPEG conversion (if enabled) so JPEG embed is used instead.

### General caveats

- Embedding modifies originals **in place** — finish import and verification before running bulk embed.
- ExifTool creates a temp file; `-overwrite_original` skips keeping `*_original` backups. You already have Google Takeout ZIPs as the ultimate backup.
- Do not delete `.xmp` files until photo **and** video samples pass the checks above.

## RAR archival

Archive **`library/admin/` only** — not `upload/`, thumbs, encoded-video, or database files.

Photos and videos are already compressed; use **store mode** (`-m0`) so RAR does not spend time re-compressing them. Recovery record and BLAKE2 checksums still protect the archive.

| Option | Purpose |
| ------ | ------- |
| `-ma5` | RAR5 archive format |
| `-m0` | Store — no compression |
| `-r` | Recurse subdirectories |
| `-v2g` | Split into 2 GB volumes |
| `-rr3%` | 3% recovery record |
| `-htb` | BLAKE2 checksums (RAR5) |

```bash
cd /pool/archive/cloud_backups/immich

rar a -ma5 -m0 -r -v2g -rr3% -htb upload/YYYY-mm-DD-mjbeisser@gmail.com-immich.rar library/admin/

rar t upload/YYYY-mm-DD-mjbeisser@gmail.com-immich.rar
```

Produces `upload/YYYY-mm-DD-mjbeisser@gmail.com-immich.rar` plus `.part2.rar`, `.part3.rar`, etc.

**Before archiving:**

- Confirm import and [XMP embed](#embed-xmp-sidecars) are complete
- Optionally stop Immich if you need a quiescent snapshot (not required after import is finished)
- Copy RAR volumes to off-site storage per [backup.md](backup.md) (`/pool/archive` → Koofr/Filen)
