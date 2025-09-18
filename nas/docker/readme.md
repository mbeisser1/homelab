Docker apps are in:
/pool/repo/<docker app>
          / docker-compose.yml
          / .env       <--- environment variables (and secrets) for
		  / gen_env.sh <--- Create the .env file
		  / gen_dir.sh <--- Create the directory to store the app data
		                    and fix file permissions

Example:
mbeisser@nas:/pool/repo/docker$
drwxrwsr-x 2 mbeisser hosted    6 Sep 10 13:28 .
drwxrwsr-x 3 mbeisser hosted   29 Sep  2 23:53 ..
-rw-rw-r-- 1 mbeisser hosted 3.8K Sep 11 02:33 docker-compose.yml
-rw------- 1 mbeisser hosted  229 Sep 11 01:19 .env
-rwxrwxr-x 1 mbeisser hosted  330 Sep 11 02:25 gen_env.sh

Docker data is stored in.
/pool/hosted/docker/<docker app>

Example:
mbeisser@nas:/pool/hosted/docker$ tree trilium/
trilium/
├── backup
│   ├── backup-daily.db
│   ├── backup-now.db
│   └── backup-weekly.db
├── data
│   ├── backup
│   │   └── backup-daily.db
│   ├── config.ini
│   ├── document.db
│   ├── document.db-shm
│   ├── document.db-wal
│   ├── log
│   │   ├── trilium-2025-09-12.log
│   │   └── trilium-2025-09-17.log
│   ├── session_secret.txt
│   └── tmp

Generally the files in hosted are owned by `root:hosted`
However, databases and some apps seem to need special permissions.
I don't use ACL for permissions nor do I want to.

LLM instructions:
When creating a new docker:
- Create the gen_env.sh script with variables needed for the docker-compose.yml
- Create the gen_dir.sh
- Create / update the docker-compose.yml to use the .env file.
