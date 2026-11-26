"""detect module (owner: Member-2). Contract: contracts/detect.md.

The real engine lives in engine.py. mock.py is the old placeholder, kept so the
contract's mock-only error case can still be run by pointing this import at it.
"""
from aegis.detect.engine import detect_file  # noqa: F401
