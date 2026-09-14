"""Validate a pinned parser source region without loading JavaScript."""

import hashlib


BUNDLE_SHA256 = "01511e45db7646e2a12890de8d7866caa0754c8799db6407a6345236f4bed0c4"
BUNDLE_BYTES = 2901663
REGION_OFFSET = 545346
REGION_BYTES = 570486
REGION_SHA256 = "d5c94f357a5098056ec075c1cf91bb487f99e7becb5e6448c3f9415de159097c"
START = b"// node_modules/@babel/parser/lib/index.js"
END = b"// node_modules/picocolors/picocolors.js"


def extract_parser_source(bundle):
    """Return exact inert bytes; no adaptation or executable artifact is produced."""
    if type(bundle) is not bytes:
        raise ValueError("bundle must be bytes")
    if len(bundle) != BUNDLE_BYTES:
        raise ValueError("bundle length mismatch")
    if hashlib.sha256(bundle).hexdigest() != BUNDLE_SHA256:
        raise ValueError("bundle hash mismatch")
    if bundle.count(START) != 1 or bundle.count(END) != 1:
        raise ValueError("ambiguous parser boundaries")
    start = bundle.index(START)
    end = bundle.index(END)
    if start != REGION_OFFSET or end - start != REGION_BYTES:
        raise ValueError("parser region mismatch")
    region = bundle[start:end]
    if hashlib.sha256(region).hexdigest() != REGION_SHA256:
        raise ValueError("parser region hash mismatch")
    region.decode("utf-8", errors="strict")
    return region
