from __future__ import annotations

import json
import sys
from pathlib import Path

from openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.ingestion.chunker import chunk_text, count_tokens
from app.ingestion.embedder import embed_chunks
from app.ingestion.html_to_markdown import html_to_markdown
from app.ingestion.writer import ingest_document

_MAX_TOKENS = 512
_OVERLAP_TOKENS = 64


def run_pipeline(manifest_path: Path, downloads_dir: Path) -> None:
    """Read the manifest, process each filing, write to the database."""
    manifest = json.loads(manifest_path.read_text())
    client = OpenAI(api_key=settings.openai_api_key)
    engine = create_engine(settings.database_url)

    total_docs = 0
    total_chunks = 0

    for entry in manifest.get("filings", []):
        local_path = entry.get("local_path", "")
        html_path = downloads_dir / local_path
        if not html_path.exists():
            print(f"[skip] missing local file: {html_path}")
            continue

        accession = entry.get("accession_number", local_path)
        print(f"Processing {entry.get('ticker')} {entry.get('form')} ({accession}) ...", end=" ", flush=True)

        html = html_path.read_text(encoding="utf-8", errors="replace")
        md = html_to_markdown(html)
        chunks = chunk_text(md, max_tokens=_MAX_TOKENS, overlap_tokens=_OVERLAP_TOKENS)
        token_counts = [count_tokens(c) for c in chunks]
        embeddings = embed_chunks(
            chunks,
            client,
            settings.openai_embedding_model,
            settings.openai_embedding_dimensions,
        )

        with Session(engine) as session:
            n = ingest_document(entry, md, chunks, embeddings, token_counts, session)

        if n == 0:
            print("already ingested, skipped.")
        else:
            print(f"{n} chunks written.")
            total_docs += 1
            total_chunks += n

    print(f"\nDone: {total_docs} document(s), {total_chunks} chunk(s) ingested.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest SEC filings into Supabase.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "downloads" / "manifest.json",
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "data" / "downloads",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        print("Run: uv run data/download.py", file=sys.stderr)
        sys.exit(1)

    run_pipeline(args.manifest, args.downloads)
