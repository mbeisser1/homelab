# Postfix Relay Setup with Fastmail

This guide explains how to configure Postfix on a Linux server (Debian/Ubuntu) to relay all outgoing mail through **Fastmail SMTP**.

---

## 1. Install dependencies
```bash
sudo apt update
sudo apt install postfix libsasl2-modules
```
- Choose **“Internet Site”** when prompted.
- If not prompted, you can configure hostname later (see below).

---

## 2. Generate an App Password in Fastmail
1. Log in to [Fastmail Settings → Password & Security → App passwords](https://app.fastmail.com/settings/security).
2. Click **Add App password**.
3. Select **Mail (IMAP/SMTP)**.
4. Name it e.g. `lnas-postfix-relay`.
5. Copy the long random password — this will be used in Postfix.

---

## 3. Create the credentials file
```bash
sudo nano /etc/postfix/sasl_passwd
```
Paste (replace with your Fastmail login + app password):
```
[smtp.fastmail.com]:587 mbeisser@fastmail.com:APP_PASSWORD
```

---

## 4. Secure and hash the credentials
```bash
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
```

---

## 5. Configure Postfix main.cf
Use `postconf -e` to inject settings:

```bash
sudo postconf -e "relayhost = [smtp.fastmail.com]:587"
sudo postconf -e "smtp_sasl_auth_enable = yes"
sudo postconf -e "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd"
sudo postconf -e "smtp_sasl_security_options = noanonymous"
sudo postconf -e "smtp_use_tls = yes"
sudo postconf -e "smtp_tls_security_level = encrypt"
sudo postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"
```

---

## 6. Configure system mail name (if needed)
Edit `/etc/postfix/main.cf` and set:
```ini
myhostname = lnas.bitrealm.dev
myorigin = bitrealm.dev
```
Also set `/etc/mailname`:
```bash
echo "bitrealm.dev" | sudo tee /etc/mailname
```

Check values:
```bash
postconf myhostname
postconf myorigin
```

---

## 7. Configure outgoing From address with smtp_generic_maps
To ensure all outgoing mail uses a valid sender (your custom domain), add this to `/etc/postfix/main.cf`:

```ini
smtp_generic_maps = hash:/etc/postfix/generic
```

Create `/etc/postfix/generic`:
```
mbeisser@lnas     snapraid@bitrealm.dev
root@lnas         snapraid@bitrealm.dev
@lnas             snapraid@bitrealm.dev
```

Build the map and restart Postfix:
```bash
sudo postmap /etc/postfix/generic
sudo systemctl restart postfix
```

Now any mail generated on the system will appear to come from `snapraid@bitrealm.dev`.

---

## 8. Restart Postfix
```bash
sudo systemctl restart postfix
```

---

## 9. Test mail delivery
```bash
echo "This is a test from lnas" | mailx -s "Fastmail relay test" mjbeisser@gmail.com
```

Check logs:
```bash
tail -f /var/log/mail.log
```

You should see: `relay=smtp.fastmail.com[...], status=sent`.

---

✅ Done! Postfix now relays mail through Fastmail securely, and all outgoing messages are rewritten to your custom domain sender address (`snapraid@bitrealm.dev`).
