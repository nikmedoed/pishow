import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

COLLECTION_ROOT_ID = "/"


@dataclass
class CollectionInfo:
    id: str
    display_name: str
    display_path: str
    depth: int
    files_count: int


def normalize_collection_id(collection_id: str) -> str:
    """
    Normalize a collection identifier.
    - An empty value maps to the root collection.
    - Leading/trailing slashes are stripped except for the root.
    """
    if not collection_id:
        return COLLECTION_ROOT_ID
    cleaned = collection_id.strip().strip("/")
    return COLLECTION_ROOT_ID if cleaned == "" else cleaned


def collection_id_from_relative_path(relative_path: str) -> str:
    """
    Build collection id from a file path relative to the media root.
    Only direct parent folder counts; nested folders are distinct collections.
    """
    parent = Path(relative_path).parent
    if str(parent) in {"", "."}:
        return COLLECTION_ROOT_ID
    return normalize_collection_id(parent.as_posix())


def collection_id_from_dir(media_dir: Path, directory: Path) -> str:
    """Convert an absolute directory to a collection id relative to media_dir."""
    rel = directory.resolve().relative_to(media_dir.resolve())
    if not rel.parts:
        return COLLECTION_ROOT_ID
    return normalize_collection_id(rel.as_posix())


def _is_media_file(path: Path, background_suffix: str) -> bool:
    if any(part.startswith(".") for part in path.parts):
        return False
    if path.name.startswith("."):
        return False
    if background_suffix and str(path).endswith(background_suffix):
        return False
    mime_type, _ = mimetypes.guess_type(str(path))
    return bool(mime_type and (mime_type.startswith("image/") or mime_type.startswith("video/")))


def scan_collections(
    media_dir: Path, background_suffix: str = "", skip_dir: Path | None = None
) -> Tuple[List[CollectionInfo], Dict[str, str]]:
    """
    Walk through media_dir and return collection info (folder tree + file counts).
    Only counts files directly inside each folder. Subfolders are separate collections.
    """
    media_dir = media_dir.resolve()
    skip_dir_resolved = skip_dir.resolve() if skip_dir else None
    collections: List[CollectionInfo] = []

    for root, dirs, files in os.walk(media_dir):
        root_path = Path(root).resolve()

        if skip_dir_resolved:
            if root_path == skip_dir_resolved or root_path.is_relative_to(skip_dir_resolved):
                dirs[:] = []
                continue
            dirs[:] = [
                d
                for d in dirs
                if not (root_path / d).resolve().is_relative_to(skip_dir_resolved)
            ]

        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if any(part.startswith(".") for part in root_path.relative_to(media_dir).parts):
            continue

        rel = root_path.relative_to(media_dir)
        collection_id = COLLECTION_ROOT_ID if not rel.parts else normalize_collection_id(rel.as_posix())
        display_name = COLLECTION_ROOT_ID if collection_id == COLLECTION_ROOT_ID else rel.name
        display_path = COLLECTION_ROOT_ID if collection_id == COLLECTION_ROOT_ID else f"/{collection_id}"

        files_count = 0
        for file_name in files:
            if file_name.startswith("."):
                continue
            file_path = root_path / file_name
            if _is_media_file(file_path, background_suffix):
                files_count += 1

        collections.append(
            CollectionInfo(
                id=collection_id,
                display_name=display_name,
                display_path=display_path,
                depth=len(rel.parts),
                files_count=files_count,
            )
        )

    collections.sort(key=lambda c: c.display_path)
    labels = {item.id: item.display_name for item in collections}
    return collections, labels
