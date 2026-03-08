import os
from fastapi import APIRouter, Depends, HTTPException
from git import Repo
from typing import List, Dict, Any
from pydantic import BaseModel
import datetime

from app.core.security import require_viewer

router = APIRouter(dependencies=[Depends(require_viewer)])

# Configuration
# Default to sibling directory for development
DEFAULT_REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../JTYU-OBC"))

class CommitInfo(BaseModel):
    hexsha: str
    message: str
    author: str
    date: str


def get_commits_list_filtered(repo_path: str, relative_path: str = None, limit: int = 50):
    """
    Get list of commits from repository, optionally filtered to a subdirectory.
    For Type-2 projects, relative_path scopes commits to the subproject.
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        commits = []

        iter_kwargs = {"max_count": limit}
        if relative_path:
            iter_kwargs["paths"] = relative_path

        for commit in repo.iter_commits(**iter_kwargs):
            commits.append({
                "hash": commit.hexsha[:7],
                "full_hash": commit.hexsha,
                "author": commit.author.name,
                "email": commit.author.email,
                "date": datetime.datetime.fromtimestamp(commit.committed_date).isoformat(),
                "message": commit.message.strip()
            })
            
            if len(commits) >= limit:
                break
                
        return commits
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")


def get_releases_filtered(repo_path: str, relative_path: str = None):
    """
    Get list of Git tags/releases from repository.
    For Type-2 projects, shows file count under relative_path for each tag.
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        releases = []
        for tag in repo.tags:
            commit = tag.commit
            
            # Count files under relative_path if provided
            file_count = None
            if relative_path:
                try:
                    tree = commit.tree
                    target = tree / relative_path
                    if target.type == 'tree':
                        file_count = len(list(target.traverse()))
                except:
                    pass
            
            releases.append({
                "tag": tag.name,
                "commit_hash": commit.hexsha[:7],
                "date": datetime.datetime.fromtimestamp(commit.committed_date).isoformat(),
                "message": commit.message.strip(),
                "subproject_files_changed": file_count
            })
        # Sort by date descending (newest first)
        releases.sort(key=lambda x: x['date'], reverse=True)
        return releases
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")


def get_file_from_commit_with_prefix(repo_path: str, commit_hash: str, file_path: str, relative_prefix: str = None) -> str:
    """
    Get file content from a specific commit.
    For Type-2 projects, relative_prefix is prepended to file_path.
    """
    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_hash)
        
        # Prepend relative_prefix for Type-2 projects
        full_path = file_path
        if relative_prefix:
            full_path = os.path.join(relative_prefix, file_path)
        
        try:
            blob = commit.tree / full_path
            content = blob.data_stream.read()
            return content.decode('utf-8')
        except KeyError:
            raise HTTPException(status_code=404, detail=f"File {file_path} not found in commit")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Binary file cannot be decoded")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")


def file_exists_in_commit_with_prefix(repo_path: str, commit_hash: str, file_path: str, relative_prefix: str = None) -> bool:
    """
    Check if a file exists in a specific commit.
    For Type-2 projects, relative_prefix is prepended to file_path.
    """
    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_hash)
        
        full_path = file_path
        if relative_prefix:
            full_path = os.path.join(relative_prefix, file_path)
        
        try:
            _ = commit.tree / full_path
            return True
        except KeyError:
            return False
    except:
        return False


class FileContentRequest(BaseModel):
    repo_path: str = DEFAULT_REPO_PATH
    commit_sha: str
    file_path: str

@router.get("/commits", response_model=List[CommitInfo])
async def list_commits(repo_path: str = DEFAULT_REPO_PATH, limit: int = 50):
    """
    List commits for a given repository.
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        commits = []
        for commit in repo.iter_commits(max_count=limit):
            commits.append(CommitInfo(
                hexsha=commit.hexsha,
                message=commit.message.strip(),
                author=commit.author.name,
                date=datetime.datetime.fromtimestamp(commit.committed_date).isoformat()
            ))
        return commits
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")

def get_releases(repo_path: str):
    """
    Get list of Git tags/releases from repository.
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        releases = []
        for tag in repo.tags:
            releases.append({
                "tag": tag.name,
                "commit_hash": tag.commit.hexsha[:7],
                "date": datetime.datetime.fromtimestamp(tag.commit.committed_date).isoformat(),
                "message": tag.commit.message.strip()
            })
        # Sort by date descending (newest first)
        releases.sort(key=lambda x: x['date'], reverse=True)
        return releases
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")

def get_commits_list(repo_path: str, limit: int = 50):
    """
    Get list of commits from repository.
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        commits = []
        for commit in repo.iter_commits(max_count=limit):
            commits.append({
                "hash": commit.hexsha[:7],
                "full_hash": commit.hexsha,
                "author": commit.author.name,
                "email": commit.author.email,
                "date": datetime.datetime.fromtimestamp(commit.committed_date).isoformat(),
                "message": commit.message.strip()
            })
        return commits
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")

@router.get("/content")
async def get_file_content(commit_sha: str, file_path: str, repo_path: str = DEFAULT_REPO_PATH):
    """
    Get file content from a specific commit.
    """
    if not os.path.exists(repo_path):
         raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")

    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_sha)
        
        try:
            target_file = commit.tree / file_path
            # For text files, we decode. For binaries, we might need a different strategy (e.g. base64)
            # For now, let's assume text or try to decode utf-8
            blob = target_file.data_stream.read()
            return {"content": blob.decode('utf-8'), "size": target_file.size}
        except KeyError:
             raise HTTPException(status_code=404, detail=f"File {file_path} not found in commit {commit_sha}")
        except UnicodeDecodeError:
             return {"content": "Binary file (preview not available)", "size": target_file.size, "is_binary": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")

def get_file_from_commit(repo_path: str, commit_hash: str, file_path: str) -> str:
    """
    Get file content from a specific commit.
    Returns file content as string.
    """
    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_hash)
        
        try:
            blob = commit.tree / file_path
            content = blob.data_stream.read()
            return content.decode('utf-8')
        except KeyError:
            raise HTTPException(status_code=404, detail=f"File {file_path} not found in commit")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Binary file cannot be decoded")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Git error: {str(e)}")

def file_exists_in_commit(repo_path: str, commit_hash: str, file_path: str) -> bool:
    """
    Check if a file exists in a specific commit.
    """
    try:
        repo = Repo(repo_path)
        commit = repo.commit(commit_hash)
        try:
            _ = commit.tree / file_path
            return True
        except KeyError:
            return False
    except:
        return False


def sync_with_remote(repo_path: str) -> Dict[str, Any]:
    """
    Sync local repository with remote by performing a git pull.
    
    This fetches and merges the latest changes from the remote tracking branch.
    
    Returns:
        Dict with sync status information including:
        - success: bool
        - previous_commit: str
        - current_commit: str
        - commits_pulled: int
        - message: str
    """
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found at {repo_path}")
    
    try:
        repo = Repo(repo_path)
        
        # Get current HEAD before sync
        previous_commit = repo.head.commit.hexsha
        
        # Perform git pull
        origin = repo.remotes.origin
        
        env = os.environ.copy()
        env['GIT_TERMINAL_PROMPT'] = '0'
        # Trust On First Use (TOFU) for SSH
        env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=accept-new'
        
        pull_info = origin.pull(env=env)
        
        # Get new HEAD after sync
        current_commit = repo.head.commit.hexsha
        
        # Count how many commits were pulled
        commits_pulled = 0
        if previous_commit != current_commit:
            try:
                commits_pulled = len(list(repo.iter_commits(f'{previous_commit}..{current_commit}')))
            except Exception:
                commits_pulled = 1  # At least one if heads differ
        
        return {
            "success": True,
            "previous_commit": previous_commit[:7],
            "current_commit": current_commit[:7],
            "commits_pulled": commits_pulled,
            "message": f"Successfully pulled {commits_pulled} commit(s) from remote."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
