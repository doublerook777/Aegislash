#!/usr/bin/env python3
"""Aegislash entry point: python main.py --input <input dir> --output <empty output dir>.

The pipeline lives in aegis/io/pipeline.py (owner: io). Never prints personal data or RAKSHA_SECRET.
"""
import sys

from aegis.io.pipeline import main

if __name__ == "__main__":
    sys.exit(main())
