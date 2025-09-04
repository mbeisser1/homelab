# Copy back
sudo cp -r /pool/repo/homelab/nas/etc/* /etc/

# Ownership & perms in /etc
sudo chown -R root:root /etc/postfix /etc/fail2ban /etc/aliases
sudo chmod 644 /etc/postfix/main.cf /etc/postfix/generic /etc/aliases
sudo chmod 600 /etc/postfix/sasl_passwd 2>/dev/null || true
sudo postmap /etc/postfix/generic 2>/dev/null || true
sudo newaliases
sudo systemctl reload postfix fail2ban
