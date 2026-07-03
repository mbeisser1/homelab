Joplin is now replaced by Obsidian. Jopling was too restricting because it had it's own database and that made koofr / nas documents inherintly separate from other documentation. Obsidian works well because it's vault is nothing more than a view of a directory which in my case is the docs portion of my cloud storage on koofr. Joplin was also limited with displaying html with css and had a lack of plugins. Previously syncing obsidian vault seemed problematic but that's been resovled.

 recently setup obsidian vault with a root of /pool/docs
/pool/docs is 2-way synced via the koofr gui client now insted of using rclone + cron scripts to stync

Several options were tried
- Mounting koofr via rclone - works but doesn't work with syncthing
- Mounting as WebDAV - to slow, limited to one file at a time

but neither of those work with syncthing & VaultSync on the iphone. Transfer rates are abysmal and the iphone client keeps disconnecting ard reconnecting.

I also added syncthing to docker compose. Docker compose uses obsidian-sync.bitrealm.dev
I use that along with ios VaultSync for my iphone. Synchting has config in the obsidian vault root dir, i.e. /pool/docs

.stfolder/
.stignore
  - Current config allows `_resources` to be copied but not `_assets`. _assets is what message vault uses, and other projects will as well.
.stversions/ 

When sharing a folder in SyncThing the Folder Path is the name of the mount IN the docker compse file. So it's not /pool/docs it's -> /obsidian

/pool/docs is served up via nginix now which was recently added to docker_compose - nginix_proxy_manager. nginix is apparently reacheable via host name because of the docker network?
A config dir/file was necessary to add to enable file browsing. not necessary but helpful
 obsidian-assets-conf/default.conf

When configuring Syncthing
- Select folder to share in syncthing webui

On iphone:
- create a vault in obsidian first
- then open Vaultsync
- Add "device:" for vaulsync, this is the NAS

Back on Syncthing webui add the iphone (should auto detect on same network)

Both devices have to add each other in order for sync to work


In order to make sure the obsidian vault stays small for projects like the message vault, I have the urls of the assets in markdown files point to obsidian-assests.bitrealm.dev so the assets logically live in the correct structure but are accessible on any device becasue it's a web link. This is an altenative to r2 cloudflare.

Some notes:
- Koofr and syncthing can't handle directory names changes inby a single upper case -lower case or vice versa well at all. This is a known limitation and shouldn't be done. If it is needed, the best course of action is to STOP syncthing docker, delete the vault on iphone, and resync.

Also if you are going to rename a folder do it on Koofr web: test_dir -> Test_dir and let changes propogate down to disk as opposed to on the nas and going up to koofr.
