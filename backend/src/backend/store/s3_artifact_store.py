"""
S3-backed artifact store with signed URL downloads.
"""

from __future__ import annotations

import io
import json
import uuid
from typing import Any

import pandas as pd

from ..ports import ArtifactDownload, ArtifactPreview, ArtifactRef, ArtifactStorePort


class S3ArtifactStore(ArtifactStorePort):
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str | None,
        url_expires_in: int,
        preview_rows: int,
        endpoint_url: str | None = None,
        use_path_style: bool = False,
    ) -> None:
        if not bucket:
            raise ValueError("S3 artifact store requires a bucket name.")

        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._url_expires_in = url_expires_in
        self._preview_rows = max(preview_rows, 1)
        self._client = self._build_client(
            region=region,
            endpoint_url=endpoint_url,
            use_path_style=use_path_style,
        )

    @staticmethod
    def _build_client(
        *, region: str | None, endpoint_url: str | None, use_path_style: bool
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for the S3 artifact store.") from exc

        config = None
        if use_path_style:
            config = Config(s3={"addressing_style": "path"})

        return boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=config,
        )

    def _key(self, run_id: str, artifact_id: str, filename: str) -> str:
        base = f"{run_id}/{artifact_id}/{filename}"
        return f"{self._prefix}/{base}" if self._prefix else base

    @staticmethod
    def _serialize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        df_serializable = df.copy()
        for col in df_serializable.columns:
            if pd.api.types.is_datetime64_any_dtype(df_serializable[col]):
                df_serializable[col] = df_serializable[col].astype(str)
        return df_serializable

    def _put_json(self, key: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )

    def _get_json(self, key: str) -> dict[str, Any] | None:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 - map S3 errors to missing
            error = getattr(exc, "response", {}).get("Error", {})
            code = error.get("Code")
            if code in {"NoSuchKey", "404"}:
                return None
            raise
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)

    def store_table(self, run_id: str, df: pd.DataFrame) -> ArtifactRef:
        artifact_id = f"a_{run_id[:8]}_{uuid.uuid4().hex[:8]}"
        df_serializable = self._serialize_dataframe(df)

        preview_df = df_serializable.head(self._preview_rows)
        preview_rows = preview_df.to_dict(orient="records")
        columns = list(df_serializable.columns)

        metadata = {
            "id": artifact_id,
            "type": "table",
            "columns": columns,
            "original_row_count": len(df_serializable),
            "exported_row_count": len(preview_rows),
        }

        csv_buffer = io.StringIO()
        df_serializable.to_csv(csv_buffer, index=False)
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(run_id, artifact_id, "data.csv"),
            Body=csv_buffer.getvalue().encode("utf-8"),
            ContentType="text/csv",
        )

        self._put_json(
            self._key(run_id, artifact_id, "preview.json"),
            {"rows": preview_rows},
        )
        self._put_json(self._key(run_id, artifact_id, "metadata.json"), metadata)

        return ArtifactRef(
            id=artifact_id,
            type="table",
            row_count=len(df_serializable),
        )

    def get_metadata(self, run_id: str, artifact_id: str) -> ArtifactRef | None:
        metadata = self._get_json(self._key(run_id, artifact_id, "metadata.json"))
        if not metadata:
            return None
        return ArtifactRef(
            id=str(metadata.get("id", artifact_id)),
            type=str(metadata.get("type", "table")),
            row_count=int(metadata.get("original_row_count", 0)),
        )

    def get_preview(self, run_id: str, artifact_id: str) -> ArtifactPreview | None:
        metadata = self._get_json(self._key(run_id, artifact_id, "metadata.json"))
        preview = self._get_json(self._key(run_id, artifact_id, "preview.json"))
        if not metadata or not preview:
            return None

        rows = preview.get("rows", [])
        columns = metadata.get("columns", [])
        return ArtifactPreview(
            rows=rows if isinstance(rows, list) else [],
            columns=columns if isinstance(columns, list) else [],
            original_row_count=int(metadata.get("original_row_count", 0)),
            exported_row_count=len(rows) if isinstance(rows, list) else 0,
        )

    def get_download(self, run_id: str, artifact_id: str) -> ArtifactDownload | None:
        key = self._key(run_id, artifact_id, "data.csv")
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._url_expires_in,
        )
        return ArtifactDownload(
            url=url,
            expires_in_seconds=self._url_expires_in,
        )
