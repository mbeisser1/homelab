# Create the base directory for rustdesk
sudo mkdir -p /pool/hosted/docker/rustdesk/data

# Change ownership to root:hosted
sudo chown -R root:hosted /pool/hosted/docker/rustdesk

# Set permissions with SGID bit so group 'hosted' inherits
sudo chmod -R 2775 /pool/hosted/docker/rustdesk
