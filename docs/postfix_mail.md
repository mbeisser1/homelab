## Overview

This document outlines the steps to configure Postfix on Ubuntu 25.04 as a send-only mail relay using Fastmail SMTP for cron job notifications and system alerts.

## System Details

- **System:** Ubuntu 25.04
- **Hostname:** nas-dev
- **Custom Domain:** bitrealm.dev
- **Email Provider:** Fastmail
- **Use Case:** Send-only configuration for cron notifications and system alerts

## Installation

1. Install required packages:
   - `postfix`
   - `libsasl2-modules`

2. During installation, select "Internet Site" and set mail name to custom domain. (Select defaults for remaining options)

## Configuration Files Modified

### Primary Configuration

**`/etc/postfix/main.cf`**
- Configured relay through Fastmail SMTP (`smtp.fastmail.com:587`)
- Enabled SASL authentication for SMTP relay
- Enforced TLS encryption for outgoing mail
- Set network interface to `loopback-only` for security
- Configured local destinations
- Added generic mapping for sender address rewriting

**`/etc/mailname`**
- Set to custom domain (`bitrealm.dev`)

### Authentication

**`/etc/postfix/sasl_passwd`**
- Contains Fastmail SMTP credentials
- **Important:** Must use `@fastmail.com` email address for authentication (not custom domain)
- Must use Fastmail App Password (not regular account password)
- File permissions set to `600` for security
- Must be hashed using `postmap` command

### Address Rewriting

**`/etc/postfix/generic`**
- Maps local sender addresses to custom domain addresses
- Format: `local@hostname` → `user.hostname@domain.com`
- Configured for both root and regular user accounts
- Includes catch-all patterns for the hostname

**`/etc/postfix/aliases`**
- Redirects local system mail to external addresses
- Maps `root` and other system accounts to monitored email addresses

## Database Generation

After modifying configuration files, the following commands were run to build database files:

1. `sudo postmap /etc/postfix/sasl_passwd` - Build authentication database
2. `sudo newaliases` - Build aliases database
3. `sudo postmap /etc/postfix/generic` - Build generic mapping database

## Service Management

- Restarted Postfix after each configuration change: `sudo systemctl restart postfix`
- Enabled Postfix to start on boot: `sudo systemctl enable postfix`

## Testing

Tested configuration using:
- `echo "test message" | mail -s "subject" recipient@domain.com`
- Monitored logs: `sudo tail -f /var/log/mail.log`
- Verified sender address rewriting in received emails
- Confirmed successful SASL authentication and TLS encryption

## Key Troubleshooting Points

1. **Authentication failure:** Fastmail SMTP authentication requires the `@fastmail.com` email address, not the custom domain address
2. **App Password required:** Regular Fastmail account passwords will not work for SMTP authentication
3. **Hostname consistency:** All configuration files must reference the current hostname (`nas-dev`)
4. **Database rebuilding:** Must run `postmap` and `newaliases` after any configuration changes
5. **Service restart:** Postfix must be restarted for changes to take effect

## Security Considerations

- SASL password file secured with `600` permissions (owner read/write only)
- TLS encryption enforced for all outbound mail
- Interface limited to loopback-only for send-only operation
- App Passwords used instead of main account credentials

## Result

Successfully configured Postfix to:
- Send all outgoing mail through Fastmail's SMTP relay
- Rewrite sender addresses to use custom domain format (`user.hostname@bitrealm.dev`)
- Forward local system mail to monitored external addresses
- Enable cron job email notifications
- Provide secure, authenticated email delivery
