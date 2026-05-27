#!/usr/bin/env python3
"""Write SVG content from a temp file to the target path.

Usage (two-step approach to avoid heredoc):
    Step 1: Cline uses write_to_file to create: <project>/svg_output/_temp_page.svg.txt
    Step 2: Cline runs: python3 skills/ppt-master/scripts/write_svg.py <project>/svg_output/_temp_page.svg.txt <target>.svg

This avoids heredoc entirely — no stdin reading, no shell integration issues.
"""
import sys
import os
import shutil


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 write_svg.py <source_temp_file> <target_svg_path>", file=sys.stderr)
        sys.exit(1)

    source = sys.argv[1]
    target = sys.argv[2]

    if not os.path.exists(source):
        print(f"Error: source file not found: {source}", file=sys.stderr)
        sys.exit(1)

    # Read source
    with open(source, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.strip():
        print("Error: empty SVG content", file=sys.stderr)
        sys.exit(1)

    # Ensure target directory exists
    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)

    # Write to target
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)

    # Remove temp file
    os.remove(source)

    filename = os.path.basename(target)
    size = len(content)
    print(f"Done: {filename} ({size} bytes written successfully)")


if __name__ == "__main__":
    main()
