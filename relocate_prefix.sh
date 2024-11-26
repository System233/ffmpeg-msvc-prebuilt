#!/bin/bash
# Copyright (c) 2024 System233
#
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

BASE_DIR="$INSTALL_PREFIX"

OLD_PREFIX=$(cygpath.exe -m "$INSTALL_PREFIX")
NEW_PREFIX=$INSTALL_PREFIX
echo Relocate $OLD_PREFIX -\> $NEW_PREFIX
find "$BASE_DIR" \( -name "*.pc" -o -name "*.cmake" \) | while read -r file; do
    if grep -q "$OLD_PREFIX" "$file"; then
        echo "Processing: $file"
        sed -i "s#$OLD_PREFIX#$NEW_PREFIX#g" "$file"
    else
        echo Skip $file
    fi
done

echo "Replacement completed."
