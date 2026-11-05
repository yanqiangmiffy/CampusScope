"""The chunker of the department's deployed RAG prototype (600 characters, overlap 100), reproduced verbatim.
The chunk baselines search the service notices cut by it (scripts/build_index.py, campusscope_chunks)."""

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100


def chunk(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Fixed-size chunks that prefer to end at a line break, 。 or ；, overlapping by `overlap` characters."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    out = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind("。"), window.rfind("；"))
            if cut > size * 0.5:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out
