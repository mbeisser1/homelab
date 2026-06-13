# Backup

Scheduled backups on NAS-DEV are driven by `/usr/local/bin/cron_backup.sh` (also tracked in the repo at `nas-dev/scripts/cron_backup.sh`). Docker volume snapshots are produced separately by [Backrest](https://github.com/garethgeorge/backrest) on an hourly schedule.

## Overview

| Component | Role |
| --------- | ---- |
| `cron_backup.sh` | Nightly (cron) orchestration: SnapRAID checks, rclone copies, email report |
| Backrest / restic | Hourly Docker volume backups into `/pool/docker_archive/volumes` |
| SnapRAID | Parity sync before off-site copies; aborts backup if unhealthy |
| `rclone-filen` | rclone binary used for Koofr and Filen remotes |
| `koofr-remote` | Koofr cloud storage |
| `filen-remote` | Filen cloud storage (secondary copy) |

On completion (success or failure), the script emails an HTML log to `nas-dev@bitrealm.dev`.

## `/pool` off-site sync (Koofr & Filen)

Each nightly run copies three paths under `/pool` to cloud storage. Koofr and Filen are not mirrors of each other — each path has a specific role on each remote.

| `/pool` path | Koofr | Filen | Notes |
| ------------ | ----- | ----- | ----- |
| `/pool/docs/` | **pull** at start | **push** after SnapRAID | Koofr is the docs source of truth; Filen gets a copy |
| `/pool/archive/` | **push** | **push** | Both remotes receive the same archive tree |
| `/pool/docker_archive/` | **push** (if restic idle) | **push** (if restic idle) | Skipped while Backrest/restic is writing snapshots |

All **push** copies run only after SnapRAID `status` and `sync` succeed. If either fails, every push is skipped.

### Copy order

Operations run in this sequence every night:

```mermaid
flowchart TD
    S1["① koofr-remote:/docs/ → /pool/docs/"]
    S2["② SnapRAID status + sync"]
    S3["③ /pool/archive/ → koofr-remote:/archive/"]
    S4{"restic running?"}
    S5["④ /pool/docker_archive/ → filen-remote:/docker_archive/"]
    S6["⑤ /pool/docker_archive/ → koofr-remote:/docker_archive/"]
    S7["⑥ /pool/docs/ → filen-remote:/docs/"]
    S8["⑦ /pool/archive/ → filen-remote:/archive/"]

    S1 --> S2
    S2 -->|ok| S3
    S2 -->|fail| ABORT[Abort — no pushes]
    S3 --> S4
    S4 -->|no| S5
    S5 --> S6
    S6 --> S7
    S4 -->|yes| SKIP[Skip ④⑤ docker_archive copies]
    SKIP --> S7
    S7 --> S8
```

### Path map

Where each `/pool` tree flows relative to the two remotes:

```mermaid
flowchart LR
    subgraph koofr["koofr-remote"]
        KD["/docs/"]
        KA["/archive/"]
        KDA["/docker_archive/"]
    end

    subgraph pool["/pool"]
        PD["/docs/"]
        PA["/archive/"]
        PDA["/docker_archive/"]
    end

    subgraph filen["filen-remote"]
        FD["/docs/"]
        FA["/archive/"]
        FDA["/docker_archive/"]
    end

    KD -->|"① pull"| PD
    PA -->|"③ push"| KA
    PDA -.->|"⑤ push"| KDA

    PD -->|"⑥ push"| FD
    PA -->|"⑦ push"| FA
    PDA -.->|"④ push"| FDA
```

Solid arrows always run (after SnapRAID passes). Dotted arrows run only when `restic` is **not** running.

### Per-path detail

**`/pool/docs/`** — Koofr pulls down first; Filen receives the result afterward. Docs are never pushed back to Koofr in this script. Any local-only edits on the NAS are overwritten by the Koofr pull.

**`/pool/archive/`** — Pushed to Koofr first, then to Filen. Both remotes should end up with the same content.

**`/pool/docker_archive/`** — Filled hourly by Backrest/restic. Pushed to Filen, then Koofr, but only when no `restic` process is active. Avoids uploading partially-written snapshots.

## Full backup flow

```mermaid
flowchart TD
    START([cron_backup.sh starts]) --> GUARD{rclone-filen already running?}
    GUARD -->|yes| MAIL_BUSY[Email: backup already in progress]
    MAIL_BUSY --> END_BUSY([exit 0])

    GUARD -->|no| RESTORE["koofr-remote:/docs/ → /pool/docs/"]
    RESTORE --> STATUS[SnapRAID status]
    STATUS -->|error| ABORT_STATUS[Email failure, exit 1]
    STATUS -->|ok| SYNC[SnapRAID sync]
    SYNC -->|error| ABORT_SYNC[Email failure, exit 1]
    SYNC -->|ok| K_ARCHIVE["/pool/archive/ → koofr-remote:/archive/"]

    K_ARCHIVE --> RESTIC{restic running?}
    RESTIC -->|yes| SKIP_DOCKER[Skip docker_archive remote copies]
    RESTIC -->|no| F_DOCKER["/pool/docker_archive/ → filen-remote:/docker_archive/"]
    F_DOCKER --> K_DOCKER["/pool/docker_archive/ → koofr-remote:/docker_archive/"]
    K_DOCKER --> F_DOCS
    SKIP_DOCKER --> F_DOCS

    F_DOCS["/pool/docs/ → filen-remote:/docs/"] --> F_ARCHIVE["/pool/archive/ → filen-remote:/archive/"]
    F_ARCHIVE --> MAIL[Email HTML log]
    MAIL --> END([exit with status code])
```

## Upstream: Docker volume backups

Backrest runs restic hourly (`0 * * * *`) and writes repository data under `/pool/docker_archive/volumes`. The cron script comment notes that this is what populates `/pool/docker_archive` before the nightly rclone push.

```mermaid
flowchart LR
    subgraph sources["Docker volumes"]
        dockge[dockge]
        immich[immich-db]
        npm[nginx-proxy-manager]
        xwiki[xwiki]
    end

    subgraph backrest["Backrest (hourly)"]
        restic[restic backup]
    end

    subgraph pool["/pool"]
        da["/pool/docker_archive/volumes"]
    end

    subgraph offsite["Nightly cron_backup.sh"]
        koofr[koofr-remote:/docker_archive/]
        filen[filen-remote:/docker_archive/]
    end

    sources --> restic
    restic --> da
    da -->|"rclone copy (if restic idle)"| koofr
    da -->|"rclone copy (if restic idle)"| filen
```

Backed-up paths (from Backrest config):

- `/mnt/dockge_dockge_data`
- `/mnt/immich_immich-db`
- `/mnt/nginx-proxy-manager_data`
- `/mnt/nginx-proxy-manager_letsencrypt`
- `/mnt/xwiki_mariadb-data`
- `/mnt/xwiki_xwiki-data`

## rclone settings

The script sets these defaults for all copy operations:

- `RCLONE_DISABLE_HTTP2=true`
- `RCLONE_TRANSFERS=16`
- Log level: `INFO`

## Safety gates

| Check | On failure |
| ----- | ---------- |
| Another `rclone-filen` process running | Exit 0, email "backup already in progress" |
| SnapRAID `status` | Exit 1, skip all copies |
| SnapRAID `sync` | Exit 1, skip all copies |
| `restic` running during docker_archive copies | Skip docker_archive copies to Koofr and Filen only |

SnapRAID `scrub` is present in the script but commented out.
