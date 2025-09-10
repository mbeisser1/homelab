#!/bin/bash
# Remove immutability from directories + .zip/.rar files (requires sudo)

if [ $# -lt 1 ]; then
	echo "Usage: $0 <dir1> [dir2 ...]"
	exit 1
fi

for target in "$@"; do
	echo "🔓 Removing immutability: $target"

	# Remove immutable flag from directories
	sudo find "$target" -type d -exec chattr -i {} \;

	# Remove immutable flag from .zip and .rar files
	sudo find "$target" \( -iname "*.zip" -o -iname "*.rar" \) -type f -exec chattr -i {} \;
done

echo "✅ Done. Selected directories and .zip/.rar files are now mutable again."
