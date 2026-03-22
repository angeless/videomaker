"""Google Drive integration mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains GDrive folder scanning,
preview, and ingestion methods for both video and image assets.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import gdown
except Exception:
    gdown = None

logger = logging.getLogger(__name__)

# Re-exported from parent module to avoid circular imports
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".hevc", ".flv", ".wmv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
GDOWN_FOLDER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
)


class GDriveMixin:
    """Methods related to Google Drive scanning and ingestion."""

    @staticmethod
    def _is_drive_folder_url(url: str) -> bool:
        return "drive.google.com" in url and ("/folders/" in url or "drive/folders" in url)

    @staticmethod
    def _normalize_priority_keywords(priority_subdirs) -> List[str]:
        if not priority_subdirs:
            return []
        if isinstance(priority_subdirs, str):
            raw = [x.strip() for x in re.split(r"[,\n;，；]+", priority_subdirs) if x.strip()]
        elif isinstance(priority_subdirs, list):
            raw = [str(x).strip() for x in priority_subdirs if str(x).strip()]
        else:
            raw = [str(priority_subdirs).strip()] if str(priority_subdirs).strip() else []
        out = []
        seen = set()
        for item in raw:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    @staticmethod
    def _extract_drive_folder_id(url: str) -> Optional[str]:
        parsed = urlparse(url)
        m = re.search(r"/folders/([a-zA-Z0-9_-]+)", parsed.path or "")
        if m:
            return m.group(1)
        q = parse_qs(parsed.query or "")
        folder_ids = q.get("id") or []
        return folder_ids[0] if folder_ids else None

    @staticmethod
    def _sanitize_drive_name(name: str) -> str:
        s = str(name or "").replace("/", "_").replace("\\", "_").strip()
        return s or "untitled"

    @staticmethod
    def _path_priority_score(path_text: str, priority_keywords: List[str]) -> int:
        if not priority_keywords:
            return 0
        text = (path_text or "").lower()
        return sum(1 for kw in priority_keywords if kw and kw in text)

    def _create_gdrive_folder_session(self):
        gdown_folder_mod = importlib.import_module("gdown.download_folder")
        folder_type = gdown_folder_mod._GoogleDriveFile.TYPE_FOLDER
        sess = gdown_folder_mod._get_session(
            proxy=None,
            use_cookies=False,
            user_agent=GDOWN_FOLDER_USER_AGENT,
        )
        return gdown_folder_mod, folder_type, sess

    def _fetch_gdrive_children(self, gdown_folder_mod, sess, folder_id: str):
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

        def _do_fetch():
            req_url = folder_url + ("&hl=en" if "?" in folder_url else "?hl=en")
            res = sess.get(req_url, verify=True, timeout=(10, 30))
            if res.status_code != 200:
                raise RuntimeError(f"扫描文件夹失败，HTTP {res.status_code}")
            gdrive_file, id_name_type_iter = gdown_folder_mod._parse_google_drive_file(
                url=req_url,
                content=res.text,
            )
            folder_name = self._sanitize_drive_name(gdrive_file.name)
            children = []
            for child_id, child_name, child_type in id_name_type_iter:
                children.append((child_id, self._sanitize_drive_name(child_name), child_type))
            return folder_name, children

        return self._run_with_retry(_do_fetch, attempts=3, base_delay=1.2)

    def _scan_gdrive_videos_priority(
        self,
        url: str,
        target_dir: Path,
        max_videos: int,
        priority_keywords: List[str],
        max_scan_folders: int,
        should_cancel=None,
    ) -> Dict:
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()

        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        candidates = []
        listed_files = 0
        scanned_folders = 0
        folder_budget_hit = False
        cancelled = False

        try:
            while (preferred or normal) and len(candidates) < max_videos:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            cancelled = True
                            break
                    except Exception:
                        cancelled = True
                        break
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    if not self._is_video_file(Path(child_name)):
                        continue

                    candidates.append(
                        {
                            "id": child_id,
                            "path": rel_path,
                            "local_path": str(target_dir / Path(*rel_parts)),
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                    if len(candidates) >= max_videos:
                        break
        finally:
            try:
                sess.close()
            except Exception:
                pass

        candidates.sort(
            key=lambda x: (x.get("priority_score", 0), x.get("path", "")),
            reverse=True,
        )
        is_partial = folder_budget_hit or bool(preferred or normal) or (len(candidates) >= max_videos)
        return {
            "items": candidates[:max_videos],
            "listed_files": listed_files,
            "video_candidates": len(candidates),
            "scanned_folders": scanned_folders,
            "folder_budget_hit": folder_budget_hit,
            "scan_partial": is_partial or cancelled,
            "priority_keywords": priority_keywords,
            "cancelled": cancelled,
        }

    def _scan_gdrive_images_priority(
        self,
        url: str,
        target_dir: Path,
        max_images: int,
        priority_keywords: List[str],
        max_scan_folders: int,
        should_cancel=None,
    ) -> Dict:
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()

        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        candidates = []
        listed_files = 0
        scanned_folders = 0
        folder_budget_hit = False
        cancelled = False

        try:
            while (preferred or normal) and len(candidates) < max_images:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            cancelled = True
                            break
                    except Exception:
                        cancelled = True
                        break
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    if not self._is_image_file(Path(child_name)):
                        continue

                    candidates.append(
                        {
                            "id": child_id,
                            "path": rel_path,
                            "local_path": str(target_dir / Path(*rel_parts)),
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                    if len(candidates) >= max_images:
                        break
        finally:
            try:
                sess.close()
            except Exception:
                pass

        candidates.sort(
            key=lambda x: (x.get("priority_score", 0), x.get("path", "")),
            reverse=True,
        )
        is_partial = folder_budget_hit or bool(preferred or normal) or (len(candidates) >= max_images)
        return {
            "items": candidates[:max_images],
            "listed_files": listed_files,
            "image_candidates": len(candidates),
            "scanned_folders": scanned_folders,
            "folder_budget_hit": folder_budget_hit,
            "scan_partial": is_partial or cancelled,
            "priority_keywords": priority_keywords,
            "cancelled": cancelled,
        }

    def preview_google_drive(
        self,
        url: str,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        max_results: int = 30,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")
        if not self._is_drive_folder_url(url):
            raise RuntimeError("仅支持 Google Drive 文件夹链接预览")

        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)

        try:
            max_results = int(max_results)
        except Exception:
            max_results = 30
        if max_results <= 0:
            max_results = 30
        max_results = min(max_results, 200)

        priority_keywords = self._normalize_priority_keywords(priority_subdirs)
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()
        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        folder_stats = {}
        sample_videos = []
        listed_files = 0
        video_files = 0
        scanned_folders = 0
        folder_budget_hit = False

        try:
            while preferred or normal:
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]
                folder_path = "/".join(current_parts)
                stat = folder_stats.setdefault(
                    folder_path,
                    {"path": folder_path, "total_files": 0, "video_files": 0, "priority_hits": 0},
                )

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    stat["total_files"] += 1
                    if not self._is_video_file(Path(child_name)):
                        continue

                    video_files += 1
                    score = self._path_priority_score(rel_path, priority_keywords)
                    stat["video_files"] += 1
                    stat["priority_hits"] += score
                    if len(sample_videos) < max_results:
                        sample_videos.append(
                            {
                                "path": rel_path,
                                "priority_score": score,
                            }
                        )
        finally:
            try:
                sess.close()
            except Exception:
                pass

        folders = [x for x in folder_stats.values() if x["total_files"] > 0]
        folders.sort(
            key=lambda x: (x["video_files"], x["priority_hits"], x["total_files"], x["path"]),
            reverse=True,
        )

        sample_videos.sort(key=lambda x: (x["priority_score"], x["path"]), reverse=True)
        sample_videos = sample_videos[:max_results]

        return {
            "url": url,
            "priority_subdirs": priority_keywords,
            "max_scan_folders": max_scan_folders,
            "scanned_folders": scanned_folders,
            "listed_files": listed_files,
            "video_files": video_files,
            "scan_partial": folder_budget_hit or bool(preferred or normal),
            "folder_stats": folders[:max_results],
            "sample_videos": sample_videos,
        }

    def preview_google_drive_images(
        self,
        url: str,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        max_results: int = 30,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")
        if not self._is_drive_folder_url(url):
            raise RuntimeError("仅支持 Google Drive 文件夹链接预览")

        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)

        try:
            max_results = int(max_results)
        except Exception:
            max_results = 30
        if max_results <= 0:
            max_results = 30
        max_results = min(max_results, 200)

        priority_keywords = self._normalize_priority_keywords(priority_subdirs)
        folder_id = self._extract_drive_folder_id(url)
        if not folder_id:
            raise RuntimeError("无法从链接解析 Google Drive 文件夹 ID")

        gdown_folder_mod, folder_type, sess = self._create_gdrive_folder_session()
        preferred = deque([(folder_id, [])])
        normal = deque()
        visited = set()
        folder_stats = {}
        sample_images = []
        listed_files = 0
        image_files = 0
        scanned_folders = 0
        folder_budget_hit = False

        try:
            while preferred or normal:
                if scanned_folders >= max_scan_folders:
                    folder_budget_hit = True
                    break

                queue = preferred if preferred else normal
                current_id, parent_parts = queue.popleft()
                if current_id in visited:
                    continue
                visited.add(current_id)

                folder_name, children = self._fetch_gdrive_children(gdown_folder_mod, sess, current_id)
                scanned_folders += 1
                current_parts = parent_parts if parent_parts else [folder_name]
                folder_path = "/".join(current_parts)
                stat = folder_stats.setdefault(
                    folder_path,
                    {"path": folder_path, "total_files": 0, "image_files": 0, "priority_hits": 0},
                )

                for child_id, child_name, child_type in children:
                    rel_parts = current_parts + [child_name]
                    rel_path = "/".join(rel_parts)

                    if child_type == folder_type:
                        entry = (child_id, rel_parts)
                        if self._path_priority_score(rel_path, priority_keywords) > 0:
                            preferred.append(entry)
                        else:
                            normal.append(entry)
                        continue

                    listed_files += 1
                    stat["total_files"] += 1
                    if not self._is_image_file(Path(child_name)):
                        continue

                    image_files += 1
                    score = self._path_priority_score(rel_path, priority_keywords)
                    stat["image_files"] += 1
                    stat["priority_hits"] += score
                    if len(sample_images) < max_results:
                        sample_images.append(
                            {
                                "path": rel_path,
                                "priority_score": score,
                            }
                        )
        finally:
            try:
                sess.close()
            except Exception:
                pass

        folders = [x for x in folder_stats.values() if x["total_files"] > 0]
        folders.sort(
            key=lambda x: (x["image_files"], x["priority_hits"], x["total_files"], x["path"]),
            reverse=True,
        )

        sample_images.sort(key=lambda x: (x["priority_score"], x["path"]), reverse=True)
        sample_images = sample_images[:max_results]

        return {
            "url": url,
            "priority_subdirs": priority_keywords,
            "max_scan_folders": max_scan_folders,
            "scanned_folders": scanned_folders,
            "listed_files": listed_files,
            "image_files": image_files,
            "scan_partial": folder_budget_hit or bool(preferred or normal),
            "folder_stats": folders[:max_results],
            "sample_images": sample_images,
        }

    def ingest_google_drive(
        self,
        url: str,
        refresh: bool = False,
        max_videos: int = 80,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")

        try:
            max_videos = int(max_videos)
        except Exception:
            max_videos = 80
        if max_videos <= 0:
            max_videos = 80
        max_videos = min(max_videos, 500)
        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)
        priority_keywords = self._normalize_priority_keywords(priority_subdirs)

        safe_key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        target_dir = self.cache_dir / safe_key

        if refresh and target_dir.exists():
            shutil.rmtree(target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        if not refresh:
            cached_videos = self._discover_videos(target_dir)
            if cached_videos:
                video_candidates = len(cached_videos)
                if priority_keywords:
                    cached_videos.sort(
                        key=lambda p: self._path_priority_score(
                            str(p.relative_to(target_dir)) if p.is_relative_to(target_dir) else str(p),
                            priority_keywords,
                        ),
                        reverse=True,
                    )
                selected_cached = cached_videos[:max_videos]
                ingest_result = self._ingest_video_paths(
                    selected_cached,
                    source_type="gdrive",
                    source_ref=url,
                    source_display=url,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
                ingest_result["listed_files"] = 0
                ingest_result["video_candidates"] = video_candidates
                ingest_result["downloaded_videos"] = len(selected_cached)
                ingest_result["truncated"] = video_candidates > max_videos
                ingest_result["max_videos"] = max_videos
                ingest_result["download_failed"] = 0
                ingest_result["skipped_non_video"] = 0
                ingest_result["cache_dir"] = str(target_dir)
                ingest_result["used_cache_only"] = True
                ingest_result["scan_mode"] = "cache_only"
                ingest_result["scanned_folders"] = 0
                ingest_result["priority_subdirs"] = priority_keywords
                ingest_result["max_scan_folders"] = max_scan_folders
                return ingest_result

        listed_files = 0
        video_candidates = 0
        downloaded_videos = 0
        truncated = False
        download_failed = 0
        downloaded_paths: List[Path] = []

        if self._is_drive_folder_url(url):
            scan_mode = "priority_fast_scan"
            priority_scan_error = None
            scanned_folders = 0
            try:
                scan_result = self._scan_gdrive_videos_priority(
                    url=url,
                    target_dir=target_dir,
                    max_videos=max_videos,
                    priority_keywords=priority_keywords,
                    max_scan_folders=max_scan_folders,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                scan_result = None
                priority_scan_error = str(exc)

            if scan_result and scan_result.get("items"):
                selected = scan_result["items"]
                listed_files = int(scan_result.get("listed_files", 0))
                video_candidates = int(scan_result.get("video_candidates", len(selected)))
                scanned_folders = int(scan_result.get("scanned_folders", 0))
                truncated = bool(scan_result.get("scan_partial", False))
            else:
                scan_mode = "full_recursive_scan"
                try:
                    listing = self._run_with_retry(
                        lambda: gdown.download_folder(
                            url=url,
                            output=str(target_dir),
                            quiet=True,
                            remaining_ok=True,
                            use_cookies=False,
                            skip_download=True,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception as exc:
                    if priority_scan_error:
                        raise RuntimeError(
                            f"优先扫描失败: {priority_scan_error}; 完整扫描也失败: {exc}"
                        ) from exc
                    raise RuntimeError(f"Google Drive 文件夹扫描失败（已重试 3 次）: {exc}") from exc
                if listing is None:
                    raise RuntimeError("Google Drive 文件夹扫描失败")

                listed_files = len(listing)
                selected = []
                for item in listing:
                    file_id = getattr(item, "id", None)
                    rel_path = str(getattr(item, "path", "") or "")
                    local_path = str(getattr(item, "local_path", "") or "")
                    if not file_id:
                        continue
                    suffix_source = rel_path or local_path
                    if not suffix_source or not self._is_video_file(Path(suffix_source)):
                        continue
                    selected.append(
                        {
                            "id": file_id,
                            "path": rel_path,
                            "local_path": local_path,
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                video_candidates = len(selected)
                if video_candidates > max_videos:
                    truncated = True
                selected = selected[:max_videos]

            for item in selected:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            truncated = True
                            break
                    except Exception:
                        truncated = True
                        break
                item_id = item["id"] if isinstance(item, dict) else getattr(item, "id", None)
                item_local_path = (
                    item["local_path"] if isinstance(item, dict) else str(getattr(item, "local_path", ""))
                )
                if not item_id or not item_local_path:
                    download_failed += 1
                    continue
                out_path = Path(str(item_local_path))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    downloaded = self._run_with_retry(
                        lambda: gdown.download(
                            url=f"https://drive.google.com/uc?id={item_id}",
                            output=str(out_path),
                            quiet=True,
                            use_cookies=False,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception:
                    download_failed += 1
                    continue
                final_path = Path(downloaded) if downloaded else out_path
                if final_path.exists():
                    downloaded_paths.append(final_path.resolve())
                else:
                    download_failed += 1
        else:
            scan_mode = "single_file"
            scanned_folders = 0
            priority_scan_error = None
            try:
                file_out = self._run_with_retry(
                    lambda: gdown.download(
                        url=url,
                        output=str(target_dir),
                        quiet=True,
                        fuzzy=True,
                        use_cookies=False,
                        resume=True,
                    ),
                    attempts=3,
                )
            except Exception as exc:
                raise RuntimeError(f"Google Drive 文件下载失败（已重试 3 次）: {exc}") from exc
            if not file_out:
                raise RuntimeError("Google Drive 文件下载失败")
            downloaded_paths = [Path(file_out).resolve()]
            listed_files = 1
            video_candidates = 1

        downloaded_videos = len(downloaded_paths)
        ingest_input = [p for p in downloaded_paths if self._is_video_file(p)]
        ingest_result = self._ingest_video_paths(
            ingest_input,
            source_type="gdrive",
            source_ref=url,
            source_display=url,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

        ingest_result["listed_files"] = listed_files
        ingest_result["video_candidates"] = video_candidates
        ingest_result["downloaded_videos"] = downloaded_videos
        ingest_result["truncated"] = truncated
        ingest_result["max_videos"] = max_videos
        ingest_result["download_failed"] = download_failed
        skipped_non_video = max(downloaded_videos - len(ingest_input), 0)
        ingest_result["skipped_non_video"] = skipped_non_video
        ingest_result["cache_dir"] = str(target_dir)
        ingest_result["used_cache_only"] = False
        ingest_result["scan_mode"] = scan_mode
        ingest_result["scanned_folders"] = scanned_folders
        ingest_result["priority_subdirs"] = priority_keywords
        ingest_result["max_scan_folders"] = max_scan_folders
        if priority_scan_error:
            ingest_result["priority_scan_error"] = priority_scan_error
        if callable(should_cancel):
            try:
                ingest_result["cancelled"] = bool(should_cancel()) or bool(ingest_result.get("cancelled"))
            except Exception:
                ingest_result["cancelled"] = bool(ingest_result.get("cancelled"))

        # Patch source type/ref for new cache locations.
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE asset_locations
                SET source_type='gdrive', source_ref=?
                WHERE path LIKE ?
                """,
                (url, f"{target_dir}%"),
            )
            conn.execute(
                """
                UPDATE assets
                SET source_type=CASE
                    WHEN source_type='local' THEN source_type
                    ELSE 'gdrive'
                END
                WHERE uid IN (
                    SELECT uid FROM asset_locations WHERE path LIKE ?
                )
                """,
                (f"{target_dir}%",),
            )

        return ingest_result

    def ingest_google_drive_images(
        self,
        url: str,
        refresh: bool = False,
        max_images: int = 200,
        priority_subdirs=None,
        max_scan_folders: int = 120,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        if gdown is None:
            raise RuntimeError("未安装 gdown，无法处理 Google Drive 链接")

        try:
            max_images = int(max_images)
        except Exception:
            max_images = 200
        if max_images <= 0:
            max_images = 200
        max_images = min(max_images, 2000)
        try:
            max_scan_folders = int(max_scan_folders)
        except Exception:
            max_scan_folders = 120
        if max_scan_folders <= 0:
            max_scan_folders = 120
        max_scan_folders = min(max_scan_folders, 2000)
        priority_keywords = self._normalize_priority_keywords(priority_subdirs)

        safe_key = hashlib.sha1(f"{url}|images".encode("utf-8")).hexdigest()[:16]
        target_dir = self.cache_dir / safe_key

        if refresh and target_dir.exists():
            shutil.rmtree(target_dir)

        target_dir.mkdir(parents=True, exist_ok=True)

        if not refresh:
            cached_images = self._discover_images(target_dir)
            if cached_images:
                image_candidates = len(cached_images)
                if priority_keywords:
                    cached_images.sort(
                        key=lambda p: self._path_priority_score(
                            str(p.relative_to(target_dir)) if p.is_relative_to(target_dir) else str(p),
                            priority_keywords,
                        ),
                        reverse=True,
                    )
                selected_cached = cached_images[:max_images]
                ingest_result = self._ingest_image_paths(
                    selected_cached,
                    source_type="gdrive",
                    source_ref=url,
                    source_display=url,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
                ingest_result["listed_files"] = 0
                ingest_result["image_candidates"] = image_candidates
                ingest_result["downloaded_images"] = len(selected_cached)
                ingest_result["truncated"] = image_candidates > max_images
                ingest_result["max_images"] = max_images
                ingest_result["download_failed"] = 0
                ingest_result["skipped_non_image"] = 0
                ingest_result["cache_dir"] = str(target_dir)
                ingest_result["used_cache_only"] = True
                ingest_result["scan_mode"] = "cache_only"
                ingest_result["scanned_folders"] = 0
                ingest_result["priority_subdirs"] = priority_keywords
                ingest_result["max_scan_folders"] = max_scan_folders
                return ingest_result

        listed_files = 0
        image_candidates = 0
        downloaded_images = 0
        truncated = False
        download_failed = 0
        downloaded_paths: List[Path] = []

        if self._is_drive_folder_url(url):
            scan_mode = "priority_fast_scan"
            priority_scan_error = None
            scanned_folders = 0
            try:
                scan_result = self._scan_gdrive_images_priority(
                    url=url,
                    target_dir=target_dir,
                    max_images=max_images,
                    priority_keywords=priority_keywords,
                    max_scan_folders=max_scan_folders,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                scan_result = None
                priority_scan_error = str(exc)

            if scan_result and scan_result.get("items"):
                selected = scan_result["items"]
                listed_files = int(scan_result.get("listed_files", 0))
                image_candidates = int(scan_result.get("image_candidates", len(selected)))
                scanned_folders = int(scan_result.get("scanned_folders", 0))
                truncated = bool(scan_result.get("scan_partial", False))
            else:
                scan_mode = "full_recursive_scan"
                try:
                    listing = self._run_with_retry(
                        lambda: gdown.download_folder(
                            url=url,
                            output=str(target_dir),
                            quiet=True,
                            remaining_ok=True,
                            use_cookies=False,
                            skip_download=True,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception as exc:
                    if priority_scan_error:
                        raise RuntimeError(
                            f"优先扫描失败: {priority_scan_error}; 完整扫描也失败: {exc}"
                        ) from exc
                    raise RuntimeError(f"Google Drive 文件夹扫描失败（已重试 3 次）: {exc}") from exc
                if listing is None:
                    raise RuntimeError("Google Drive 文件夹扫描失败")

                listed_files = len(listing)
                selected = []
                for item in listing:
                    file_id = getattr(item, "id", None)
                    rel_path = str(getattr(item, "path", "") or "")
                    local_path = str(getattr(item, "local_path", "") or "")
                    if not file_id:
                        continue
                    suffix_source = rel_path or local_path
                    if not suffix_source or not self._is_image_file(Path(suffix_source)):
                        continue
                    selected.append(
                        {
                            "id": file_id,
                            "path": rel_path,
                            "local_path": local_path,
                            "priority_score": self._path_priority_score(rel_path, priority_keywords),
                        }
                    )
                image_candidates = len(selected)
                if image_candidates > max_images:
                    truncated = True
                selected = selected[:max_images]

            for item in selected:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            truncated = True
                            break
                    except Exception:
                        truncated = True
                        break
                item_id = item["id"] if isinstance(item, dict) else getattr(item, "id", None)
                item_local_path = (
                    item["local_path"] if isinstance(item, dict) else str(getattr(item, "local_path", ""))
                )
                if not item_id or not item_local_path:
                    download_failed += 1
                    continue
                out_path = Path(str(item_local_path))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    downloaded = self._run_with_retry(
                        lambda: gdown.download(
                            url=f"https://drive.google.com/uc?id={item_id}",
                            output=str(out_path),
                            quiet=True,
                            use_cookies=False,
                            resume=True,
                        ),
                        attempts=3,
                    )
                except Exception:
                    download_failed += 1
                    continue
                final_path = Path(downloaded) if downloaded else out_path
                if final_path.exists():
                    downloaded_paths.append(final_path.resolve())
                else:
                    download_failed += 1
        else:
            scan_mode = "single_file"
            scanned_folders = 0
            priority_scan_error = None
            try:
                file_out = self._run_with_retry(
                    lambda: gdown.download(
                        url=url,
                        output=str(target_dir),
                        quiet=True,
                        fuzzy=True,
                        use_cookies=False,
                        resume=True,
                    ),
                    attempts=3,
                )
            except Exception as exc:
                raise RuntimeError(f"Google Drive 文件下载失败（已重试 3 次）: {exc}") from exc
            if not file_out:
                raise RuntimeError("Google Drive 文件下载失败")
            downloaded_paths = [Path(file_out).resolve()]
            listed_files = 1
            image_candidates = 1

        downloaded_images = len(downloaded_paths)
        ingest_input = [p for p in downloaded_paths if self._is_image_file(p)]
        ingest_result = self._ingest_image_paths(
            ingest_input,
            source_type="gdrive",
            source_ref=url,
            source_display=url,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

        ingest_result["listed_files"] = listed_files
        ingest_result["image_candidates"] = image_candidates
        ingest_result["downloaded_images"] = downloaded_images
        ingest_result["truncated"] = truncated
        ingest_result["max_images"] = max_images
        ingest_result["download_failed"] = download_failed
        skipped_non_image = max(downloaded_images - len(ingest_input), 0)
        ingest_result["skipped_non_image"] = skipped_non_image
        ingest_result["cache_dir"] = str(target_dir)
        ingest_result["used_cache_only"] = False
        ingest_result["scan_mode"] = scan_mode
        ingest_result["scanned_folders"] = scanned_folders
        ingest_result["priority_subdirs"] = priority_keywords
        ingest_result["max_scan_folders"] = max_scan_folders
        if priority_scan_error:
            ingest_result["priority_scan_error"] = priority_scan_error
        if callable(should_cancel):
            try:
                ingest_result["cancelled"] = bool(should_cancel()) or bool(ingest_result.get("cancelled"))
            except Exception:
                ingest_result["cancelled"] = bool(ingest_result.get("cancelled"))

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE asset_locations
                SET source_type='gdrive', source_ref=?
                WHERE path LIKE ?
                """,
                (url, f"{target_dir}%"),
            )
            conn.execute(
                """
                UPDATE assets
                SET source_type=CASE
                    WHEN source_type='local' THEN source_type
                    ELSE 'gdrive'
                END
                WHERE uid IN (
                    SELECT uid FROM asset_locations WHERE path LIKE ?
                )
                """,
                (f"{target_dir}%",),
            )

        return ingest_result

