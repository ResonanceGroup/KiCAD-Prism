import os
import time
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.services import path_config_service

class FileItem(BaseModel):
    name: str
    path: str  # relative to output folder
    size: int
    modified_date: str
    type: str  # file extension or 'folder'
    is_dir: bool

FILE_LISTING_CACHE_TTL = 2.0
_file_listing_cache: dict[str, dict[str, object]] = {}


def invalidate_file_listing_cache(directory: Optional[str] = None) -> None:
    if directory is None:
        _file_listing_cache.clear()
        return
    _file_listing_cache.pop(os.path.abspath(directory), None)


def _scan_files_recursive(directory: str, base_path: str = "") -> List[FileItem]:
    """
    Recursively list all files in a directory.
    
    Args:
        directory: Absolute path to directory
        base_path: Relative path from output folder root (for recursion)
    """
    items = []
    
    if not os.path.exists(directory):
        return items
    
    try:
        for entry in os.scandir(directory):
            # Skip hidden files and .DS_Store
            if entry.name.startswith('.'):
                continue
                
            rel_path = os.path.join(base_path, entry.name) if base_path else entry.name
            
            if entry.is_dir():
                items.append(FileItem(
                    name=entry.name,
                    path=rel_path,
                    size=0,
                    modified_date=datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                    type="folder",
                    is_dir=True
                ))
                # Recursively add subdirectory contents
                items.extend(_scan_files_recursive(entry.path, rel_path))
            else:
                # Get file extension
                ext = os.path.splitext(entry.name)[1].lstrip('.')
                items.append(FileItem(
                    name=entry.name,
                    path=rel_path,
                    size=entry.stat().st_size,
                    modified_date=datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                    type=ext or "file",
                    is_dir=False
                ))
    except PermissionError:
        pass
        
    return items


def get_files_recursive(directory: str) -> List[FileItem]:
    directory_path = os.path.abspath(directory)
    if not os.path.exists(directory_path):
        return []

    try:
        directory_mtime = os.path.getmtime(directory_path)
    except OSError:
        return []

    now = time.time()
    cached = _file_listing_cache.get(directory_path)
    if (
        cached
        and cached.get("mtime") == directory_mtime
        and (now - float(cached.get("cached_at", 0))) < FILE_LISTING_CACHE_TTL
    ):
        return cached["items"]  # type: ignore[return-value]

    items = _scan_files_recursive(directory_path)
    _file_listing_cache[directory_path] = {
        "items": items,
        "mtime": directory_mtime,
        "cached_at": now,
    }
    return items

def get_project_files(project_path: str, output_type: str) -> List[FileItem]:
    """
    Get files from Design-Outputs or Manufacturing-Outputs.
    
    Args:
        project_path: Absolute path to project root
        output_type: 'design' or 'manufacturing'
    """
    resolved = path_config_service.resolve_paths(project_path)
    
    if output_type == "design":
        output_dir = resolved.design_outputs_dir
    elif output_type == "manufacturing":
        output_dir = resolved.manufacturing_outputs_dir
    else:
        return []
    
    if not output_dir or not os.path.exists(output_dir):
        return []
    
    return get_files_recursive(output_dir)
