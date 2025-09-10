#!/bin/bash
# Make directories + .zip/.rar files immutable (requires sudo)

if [ $# -lt 1 ]; then
	echo "Usage: $0 <dir1> [dir2 ...]"
	exit 1
fi

for target in "$@"; do
	echo "🔒 Making immutable: $target"

	# Make directories immutable
	sudo find "$target" -type d -exec chattr +i {} \;

	# Make .zip and .rar files immutable
	sudo find "$target" \( -iname "*.zip" -o -iname "*.rar" \) -type f -exec chattr +i {} \;
done

echo "✅ Done. Selected directories and .zip/.rar files are now immutable."
