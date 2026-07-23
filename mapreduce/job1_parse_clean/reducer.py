#!/usr/bin/env python3
"""Preserve sorted Job 1 tagged records for downstream stages."""

import sys


def main():
    for line in sys.stdin:
        line = line.rstrip("\r\n")
        if "\t" in line:
            print(line)


if __name__ == "__main__":
    main()
