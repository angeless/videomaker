"""Artifact store — versioned file management for review artifacts.

Handles saving, retrieving, and rolling back render artifacts
(video files, thumbnails, waveforms, etc.) with atomic writes.
"""

import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from typing import Dict, List, Optional

from modules.review_engine.exceptions import ArtifactNotFoundError
from modules.review_engine.review_store import ReviewStore

logger = logging.getLogger(__name__)

# Files larger than this use symlinks instead of copies
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB


class ArtifactStore:
    """Versioned file store for review artifacts.

    Directory layout:
        {project_dir}/artifacts/v{N}/{node_name}/filename.ext
    """

    def __init__(self, project_dir: str, review_store: ReviewStore):
        self._project_dir = project_dir
        self._review_store = review_store
        self._artifacts_root = os.path.join(project_dir, "artifacts")

    def _version_dir(self, session_id: str, version_number: int, node_name: str) -> str:
        return os.path.join(
            self._artifacts_root, session_id, f"v{version_number}", node_name,
        )

    @staticmethod
    def _file_checksum(file_path: str) -> str:
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def save(
        self,
        session_id: str,
        version_number: int,
        node_name: str,
        artifact_type: str,
        source_path: str,
    ) -> str:
        """Save an artifact file with atomic write.

        For large files (>50MB), creates a symlink instead of copying.

        Args:
            session_id: Review session ID.
            version_number: Version number.
            node_name: Pipeline node name (e.g. "transcode", "loudnorm").
            artifact_type: Type (e.g. "video", "thumbnail", "waveform").
            source_path: Path to the source file to store.

        Returns:
            artifact_id (UUID string).

        Raises:
            FileNotFoundError: If source_path doesn't exist.
        """
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")

        dest_dir = self._version_dir(session_id, version_number, node_name)
        os.makedirs(dest_dir, exist_ok=True)

        filename = os.path.basename(source_path)
        dest_path = os.path.join(dest_dir, filename)
        file_size = os.path.getsize(source_path)

        if file_size > LARGE_FILE_THRESHOLD:
            # Large file: symlink instead of copy
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.symlink(os.path.abspath(source_path), dest_path)
        else:
            # Atomic write: write to temp, then os.replace
            tmp_fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
            try:
                os.close(tmp_fd)
                shutil.copy2(source_path, tmp_path)
                os.replace(tmp_path, dest_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

        checksum = self._file_checksum(source_path)
        artifact_id = str(uuid.uuid4())

        # Record in DB — acquire ReviewStore's lock for thread safety
        with self._review_store._lock:
            conn = self._review_store._connect()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO review_artifacts
                       (artifact_id, session_id, version_number, node_name,
                        artifact_type, file_path, file_size_bytes, checksum)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (artifact_id, session_id, version_number, node_name,
                     artifact_type, dest_path, file_size, checksum),
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(
            "Saved artifact %s: %s v%d/%s (%.1f KB)",
            artifact_id, node_name, version_number, filename, file_size / 1024,
        )
        return artifact_id

    def get(
        self,
        session_id: str,
        version_number: int,
        node_name: str,
    ) -> str:
        """Get artifact file path.

        Returns:
            Absolute file path to the artifact.

        Raises:
            ArtifactNotFoundError: If no artifact found for the given params.
        """
        with self._review_store._lock:
            conn = self._review_store._connect()
            try:
                row = conn.execute(
                    """SELECT file_path FROM review_artifacts
                       WHERE session_id = ? AND version_number = ? AND node_name = ?""",
                    (session_id, version_number, node_name),
                ).fetchone()
            finally:
                conn.close()

        if not row:
            raise ArtifactNotFoundError(
                f"No artifact: session={session_id}, v{version_number}, node={node_name}"
            )

        file_path = row["file_path"]
        if not os.path.exists(file_path):
            raise ArtifactNotFoundError(f"Artifact file missing: {file_path}")

        return file_path

    def list_artifacts(
        self,
        session_id: str,
        version_number: Optional[int] = None,
    ) -> List[Dict]:
        """List artifacts for a session, optionally filtered by version."""
        with self._review_store._lock:
            conn = self._review_store._connect()
            try:
                if version_number is not None:
                    rows = conn.execute(
                        """SELECT * FROM review_artifacts
                           WHERE session_id = ? AND version_number = ?
                           ORDER BY node_name""",
                        (session_id, version_number),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM review_artifacts
                           WHERE session_id = ? ORDER BY version_number, node_name""",
                        (session_id,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def rollback_artifacts(
        self,
        session_id: str,
        source_version: int,
        target_version: int,
    ) -> int:
        """Copy artifacts from source_version to target_version.

        Returns:
            Number of artifacts copied.
        """
        artifacts = self.list_artifacts(session_id, source_version)
        copied = 0

        for art in artifacts:
            source_path = art["file_path"]
            if not os.path.exists(source_path):
                logger.warning("Skipping missing artifact: %s", source_path)
                continue

            self.save(
                session_id=session_id,
                version_number=target_version,
                node_name=art["node_name"],
                artifact_type=art["artifact_type"],
                source_path=source_path,
            )
            copied += 1

        logger.info(
            "Rolled back %d artifacts from v%d to v%d",
            copied, source_version, target_version,
        )
        return copied
