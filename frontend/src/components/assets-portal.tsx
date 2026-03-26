import { useEffect, useMemo, useState } from "react";
import { Download, File, FileText, Package, Image as ImageIcon, Folder, ChevronRight, ChevronDown, Eye, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { FileItem, TreeNode, formatBytes, buildFileTree, calculateTotalSize } from "@/lib/file-utils";

interface AssetsPortalProps {
    projectId: string;
}

const PREVIEWABLE_EXTS = new Set(["pdf", "png", "jpg", "jpeg", "webp", "svg", "gif"]);

function getFileIcon(type: string, isDir: boolean) {
    if (isDir) return Folder;
    switch (type.toLowerCase()) {
        case "pdf": return FileText;
        case "zip": case "rar": case "7z": case "gz": case "tar": return Package;
        case "png": case "jpg": case "jpeg": case "webp": case "gif": case "svg": return ImageIcon;
        default: return File;
    }
}

function TreeNodeRow({
    node,
    projectId,
    level,
    filter,
}: {
    node: TreeNode;
    projectId: string;
    level: number;
    filter: string;
}) {
    const [expanded, setExpanded] = useState(false);
    const hasChildren = node.children.length > 0;
    const Icon = getFileIcon(node.type, node.isDir);
    const isPreviewable = !node.isDir && PREVIEWABLE_EXTS.has(node.type.toLowerCase());

    const assetUrl = `/api/projects/${projectId}/asset/${encodeURIComponent(node.path).replace(/%2F/g, "/")}`;
    const downloadUrl = `${assetUrl}?download=true`;

    const childrenMatchFilter = (n: TreeNode): boolean =>
        n.name.toLowerCase().includes(filter.toLowerCase()) ||
        n.children.some(childrenMatchFilter);

    const matchesFilter = !filter || node.name.toLowerCase().includes(filter.toLowerCase());
    const shouldShow = !filter || matchesFilter || (node.isDir && childrenMatchFilter(node));
    const isExpanded = (filter ? node.isDir && childrenMatchFilter(node) : false) || expanded;

    if (!shouldShow) return null;

    return (
        <div>
            <div
                className="flex items-center gap-1.5 py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors group"
                style={{ paddingLeft: `${level * 1.25 + 0.5}rem` }}
            >
                <button
                    className="flex-shrink-0 w-4 h-4 flex items-center justify-center"
                    onClick={() => node.isDir && setExpanded(e => !e)}
                    tabIndex={node.isDir ? 0 : -1}
                >
                    {node.isDir && hasChildren ? (
                        isExpanded
                            ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                            : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    ) : null}
                </button>

                <Icon className={`h-4 w-4 flex-shrink-0 ${node.isDir ? "text-yellow-500" : "text-blue-400"}`} />

                <span className="flex-1 text-sm truncate" title={node.path}>{node.name}</span>

                {!node.isDir && (
                    <span className="text-xs text-muted-foreground mr-2 shrink-0 opacity-60 group-hover:opacity-100">
                        {formatBytes(node.size)}
                    </span>
                )}

                {!node.isDir && (
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        {isPreviewable && (
                            <Button
                                size="sm" variant="ghost"
                                className="h-6 w-6 p-0"
                                title="Preview"
                                onClick={() => window.open(assetUrl, "_blank")}
                            >
                                <Eye className="h-3.5 w-3.5" />
                            </Button>
                        )}
                        <Button
                            size="sm" variant="ghost"
                            className="h-6 w-6 p-0"
                            title="Download"
                            onClick={() => {
                                const a = document.createElement("a");
                                a.href = downloadUrl;
                                a.download = node.name;
                                a.click();
                            }}
                        >
                            <Download className="h-3.5 w-3.5" />
                        </Button>
                    </div>
                )}
            </div>

            {node.isDir && isExpanded && hasChildren && (
                <div>
                    {node.children.map(child => (
                        <TreeNodeRow
                            key={child.path}
                            node={child}
                            projectId={projectId}
                            level={level + 1}
                            filter={filter}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

export function AssetsPortal({ projectId }: AssetsPortalProps) {
    const [files, setFiles] = useState<FileItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState("");

    useEffect(() => {
        setLoading(true);
        setError(null);
        fetch(`/api/projects/${projectId}/files/all`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: FileItem[]) => setFiles(data))
            .catch(err => setError(err.message))
            .finally(() => setLoading(false));
    }, [projectId]);

    const tree = useMemo(() => buildFileTree(files), [files]);
    const totalSize = useMemo(() => calculateTotalSize(files.filter(f => !f.is_dir)), [files]);
    const fileCount = useMemo(() => files.filter(f => !f.is_dir).length, [files]);

    if (loading) {
        return (
            <div className="space-y-2 p-4">
                {[1, 2, 3, 4, 5].map(i => (
                    <Skeleton key={i} className="h-8 w-full" />
                ))}
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-8 text-center text-sm text-destructive">
                Failed to load files: {error}
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between gap-4 mb-3">
                <div className="text-sm text-muted-foreground">
                    {fileCount} files &middot; {formatBytes(totalSize)}
                </div>
                <div className="relative w-56">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                    <Input
                        placeholder="Filter files..."
                        value={filter}
                        onChange={e => setFilter(e.target.value)}
                        className="pl-8 pr-8 h-8 text-sm"
                    />
                    {filter && (
                        <button
                            onClick={() => setFilter("")}
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                            <X className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>
            </div>

            <div className="border rounded-lg overflow-y-auto flex-1 min-h-0 max-h-[65vh]">
                {tree.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-12">No files found in project.</p>
                ) : (
                    <div className="p-2 space-y-0.5">
                        {tree.map(node => (
                            <TreeNodeRow
                                key={node.path}
                                node={node}
                                projectId={projectId}
                                level={0}
                                filter={filter}
                            />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
