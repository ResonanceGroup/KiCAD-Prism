"use client";

import { useCallback, useRef, useState } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Loader2, UploadCloud, X, FileArchive, FileText } from "lucide-react";
import { toast } from "sonner";
import { fetchApi, readApiError } from "@/lib/api";

interface CreateProjectDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onCreated: () => void;
}

const ACCEPTED_KICAD = [".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_mod", ".kicad_wks", ".kicad_dru"];

export function CreateProjectDialog({ open, onOpenChange, onCreated }: CreateProjectDialogProps) {
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [visibility, setVisibility] = useState<"public" | "private" | "hidden">("private");
    const [files, setFiles] = useState<File[]>([]);
    const [zipFile, setZipFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);

    const kicadInputRef = useRef<HTMLInputElement>(null);
    const zipInputRef = useRef<HTMLInputElement>(null);

    const reset = () => {
        setName("");
        setDescription("");
        setVisibility("private");
        setFiles([]);
        setZipFile(null);
        setUploading(false);
    };

    const handleClose = (open: boolean) => {
        if (!uploading) {
            reset();
            onOpenChange(open);
        }
    };

    const onKicadDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        const dropped = Array.from(e.dataTransfer.files).filter(
            (f) => ACCEPTED_KICAD.some((ext) => f.name.toLowerCase().endsWith(ext))
        );
        if (dropped.length) setFiles((prev) => [...prev, ...dropped]);
    }, []);

    const onZipDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        const dropped = Array.from(e.dataTransfer.files).find(
            (f) => f.name.toLowerCase().endsWith(".zip")
        );
        if (dropped) setZipFile(dropped);
    }, []);

    const removeFile = (idx: number) => setFiles((prev) => prev.filter((_, i) => i !== idx));

    const canSubmit =
        !uploading &&
        name.trim().length > 0 &&
        (files.length > 0 || zipFile !== null);

    const handleSubmit = async () => {
        if (!canSubmit) return;
        setUploading(true);
        try {
            const form = new FormData();
            form.append("name", name.trim());
            form.append("description", description.trim());
            form.append("visibility", visibility);
            if (zipFile) {
                form.append("zip_file", zipFile);
            }
            for (const f of files) {
                form.append("files", f);
            }

            const resp = await fetchApi("/api/projects/create", {
                method: "POST",
                body: form,
            });

            if (!resp.ok) {
                const errMsg = await readApiError(resp, "Project creation failed");
                toast.error(errMsg);
                return;
            }

            toast.success("Project created successfully");
            reset();
            onOpenChange(false);
            onCreated();
        } catch (e) {
            toast.error(e instanceof Error ? e.message : "Project creation failed");
        } finally {
            setUploading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Create New Project</DialogTitle>
                    <DialogDescription>
                        Upload KiCAD files or a ZIP archive to create a new project.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 mt-2">
                    {/* Name */}
                    <div className="space-y-1">
                        <Label htmlFor="cp-name">Project Name *</Label>
                        <Input
                            id="cp-name"
                            placeholder="My PCB Design"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            disabled={uploading}
                        />
                    </div>

                    {/* Description */}
                    <div className="space-y-1">
                        <Label htmlFor="cp-desc">Description</Label>
                        <Textarea
                            id="cp-desc"
                            placeholder="Optional description…"
                            rows={2}
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            disabled={uploading}
                        />
                    </div>

                    {/* Visibility */}
                    <div className="space-y-1">
                        <Label>Visibility</Label>
                        <Select
                            value={visibility}
                            onValueChange={(v) => setVisibility(v as typeof visibility)}
                            disabled={uploading}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="public">
                                    <span className="flex items-center gap-2">
                                        <span className="h-2 w-2 rounded-full bg-green-500 inline-block" />
                                        Public — visible to everyone
                                    </span>
                                </SelectItem>
                                <SelectItem value="private">
                                    <span className="flex items-center gap-2">
                                        <span className="h-2 w-2 rounded-full bg-yellow-500 inline-block" />
                                        Private — visible to members only
                                    </span>
                                </SelectItem>
                                <SelectItem value="hidden">
                                    <span className="flex items-center gap-2">
                                        <span className="h-2 w-2 rounded-full bg-gray-400 inline-block" />
                                        Hidden — unlisted, admin only
                                    </span>
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* ZIP upload */}
                    <div className="space-y-1">
                        <Label>ZIP Archive</Label>
                        <div
                            className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/60 transition-colors"
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={onZipDrop}
                            onClick={() => zipInputRef.current?.click()}
                        >
                            {zipFile ? (
                                <div className="flex items-center justify-center gap-2 text-sm">
                                    <FileArchive className="h-4 w-4 text-blue-500" />
                                    <span className="font-medium">{zipFile.name}</span>
                                    <button
                                        type="button"
                                        className="ml-1 text-muted-foreground hover:text-destructive"
                                        onClick={(e) => { e.stopPropagation(); setZipFile(null); }}
                                    >
                                        <X className="h-3 w-3" />
                                    </button>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center gap-1 text-muted-foreground text-sm">
                                    <UploadCloud className="h-6 w-6" />
                                    <span>Drop a <code>.zip</code> here or click to browse</span>
                                </div>
                            )}
                        </div>
                        <input
                            ref={zipInputRef}
                            type="file"
                            accept=".zip"
                            className="hidden"
                            onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) setZipFile(f);
                                e.target.value = "";
                            }}
                        />
                    </div>

                    {/* Individual KiCAD files */}
                    <div className="space-y-1">
                        <Label>Individual KiCAD Files</Label>
                        <div
                            className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer hover:border-primary/60 transition-colors"
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={onKicadDrop}
                            onClick={() => kicadInputRef.current?.click()}
                        >
                            <div className="flex flex-col items-center gap-1 text-muted-foreground text-sm">
                                <UploadCloud className="h-6 w-6" />
                                <span>Drop <code>.kicad_pro</code>, <code>.kicad_sch</code>, <code>.kicad_pcb</code> files or click</span>
                            </div>
                        </div>
                        <input
                            ref={kicadInputRef}
                            type="file"
                            accept={ACCEPTED_KICAD.join(",")}
                            multiple
                            className="hidden"
                            onChange={(e) => {
                                const picked = Array.from(e.target.files ?? []);
                                if (picked.length) setFiles((prev) => [...prev, ...picked]);
                                e.target.value = "";
                            }}
                        />
                        {files.length > 0 && (
                            <ul className="mt-2 space-y-1">
                                {files.map((f, i) => (
                                    <li key={i} className="flex items-center gap-2 text-sm bg-muted/40 rounded px-2 py-1">
                                        <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                        <span className="flex-1 truncate">{f.name}</span>
                                        <button
                                            type="button"
                                            className="text-muted-foreground hover:text-destructive"
                                            onClick={() => removeFile(i)}
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    {/* Actions */}
                    <div className="flex justify-end gap-2 pt-2">
                        <Button variant="outline" onClick={() => handleClose(false)} disabled={uploading}>
                            Cancel
                        </Button>
                        <Button onClick={handleSubmit} disabled={!canSubmit}>
                            {uploading ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Creating…
                                </>
                            ) : (
                                "Create Project"
                            )}
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
