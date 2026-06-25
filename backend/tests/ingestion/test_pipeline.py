import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ingestion.pipeline import run_pipeline


def _make_manifest(tmp_path: Path, local_path: str = "2024/aapl.htm") -> tuple[Path, Path]:
    downloads = tmp_path / "downloads"
    year_dir = downloads / "2024"
    year_dir.mkdir(parents=True)

    if local_path == "2024/aapl.htm":
        html_file = year_dir / "aapl.htm"
        html_file.write_text("<html><body><h1>AAPL 10-K</h1><p>Revenue grew.</p></body></html>")

    manifest = {
        "filings": [
            {
                "ticker": "AAPL",
                "form": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "accession_number": "0000320193-24-000001",
                "source_url": "https://sec.gov/aapl.htm",
                "local_path": local_path,
            }
        ]
    }
    manifest_path = downloads / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path, downloads


def test_pipeline_calls_embed_and_write_for_each_filing(tmp_path):
    manifest_path, downloads_dir = _make_manifest(tmp_path)

    with (
        patch("app.ingestion.pipeline.OpenAI") as mock_openai_cls,
        patch("app.ingestion.pipeline.create_engine"),
        patch("app.ingestion.pipeline.Session") as mock_session_cls,
        patch("app.ingestion.pipeline.embed_chunks", return_value=[[0.1] * 1536]) as mock_embed,
        patch("app.ingestion.pipeline.ingest_document", return_value=1) as mock_write,
        patch("app.ingestion.pipeline.settings") as mock_settings,
    ):
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_embedding_model = "text-embedding-3-small"
        mock_settings.openai_embedding_dimensions = 1536
        mock_settings.database_url = "postgresql+psycopg://localhost/test"

        mock_session_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        run_pipeline(manifest_path, downloads_dir)

    mock_embed.assert_called_once()
    mock_write.assert_called_once()


def test_pipeline_skips_missing_local_file(tmp_path):
    manifest_path, downloads_dir = _make_manifest(tmp_path, local_path="2024/nonexistent.htm")

    with (
        patch("app.ingestion.pipeline.OpenAI"),
        patch("app.ingestion.pipeline.create_engine"),
        patch("app.ingestion.pipeline.embed_chunks") as mock_embed,
        patch("app.ingestion.pipeline.ingest_document") as mock_write,
        patch("app.ingestion.pipeline.settings") as mock_settings,
    ):
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_embedding_model = "text-embedding-3-small"
        mock_settings.openai_embedding_dimensions = 1536
        mock_settings.database_url = "postgresql+psycopg://localhost/test"

        run_pipeline(manifest_path, downloads_dir)

    mock_embed.assert_not_called()
    mock_write.assert_not_called()
