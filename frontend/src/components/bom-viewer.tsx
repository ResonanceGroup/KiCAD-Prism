import { useEffect, useMemo, useState } from "react";
import {
    ArrowDown,
    ArrowUp,
    ArrowUpDown,
    Check,
    Copy,
    ExternalLink,
    Search,
    X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

interface BomRow {
    value: string;
    quantity: number;
    references: string[];
    footprints: string[];
    datasheet: string;
    description: string;
    extra_fields: Record<string, string>;
}

interface BomViewerProps {
    projectId: string;
}

type SortDir = "asc" | "desc";
interface SortState { col: string; dir: SortDir }

function naturalSortKey(s: string): (string | number)[] {
    return s.split(/(\d+)/).map(p => /^\d+$/.test(p) ? parseInt(p, 10) : p.toLowerCase());
}

function naturalCompare(a: string, b: string): number {
    const ak = naturalSortKey(a);
    const bk = naturalSortKey(b);
    for (let i = 0; i < Math.max(ak.length, bk.length); i++) {
        const av = ak[i] ?? "";
        const bv = bk[i] ?? "";
        if (typeof av === "number" && typeof bv === "number") {
            if (av !== bv) return av - bv;
        } else {
            const cmp = String(av).localeCompare(String(bv));
            if (cmp !== 0) return cmp;
        }
    }
    return 0;
}

function FootprintCell({ fps }: { fps: string[] }) {
    if (fps.length === 0) return <span className="text-muted-foreground">—</span>;
    const first = fps[0];
    const short = first.includes(":") ? first.split(":")[1] : first;
    return (
        <span title={fps.join("\n")} className="cursor-default">
            {short}
            {fps.length > 1 && (
                <span className="text-muted-foreground ml-1 text-xs">+{fps.length - 1}</span>
            )}
        </span>
    );
}

function DatasheetCell({ url }: { url: string }) {
    if (!url) return <span className="text-muted-foreground">—</span>;
    const href = url.startsWith("www.") ? `https://${url}` : url;
    const isLink = url.startsWith("http") || url.startsWith("www.");
    if (isLink) {
        return (
            <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-700 text-xs"
                title={url}
            >
                <ExternalLink className="h-3 w-3" />
                Link
            </a>
        );
    }
    return (
        <span className="text-xs text-muted-foreground truncate max-w-[120px] block" title={url}>
            {url}
        </span>
    );
}

function SortIcon({ col, sort }: { col: string; sort: SortState }) {
    if (sort.col !== col) return <ArrowUpDown className="h-3 w-3 opacity-40 shrink-0" />;
    return sort.dir === "asc"
        ? <ArrowUp className="h-3 w-3 shrink-0" />
        : <ArrowDown className="h-3 w-3 shrink-0" />;
}

const STANDARD_COLS = [
    { col: "references", label: "Ref Des",     cls: "w-48" },
    { col: "quantity",   label: "Qty",          cls: "w-12 text-right" },
    { col: "value",      label: "Value",        cls: "w-36" },
    { col: "footprint",  label: "Footprint",    cls: "w-52" },
    { col: "datasheet",  label: "DS",           cls: "w-14" },
    { col: "description",label: "Description",  cls: "" },
] as const;

export function BomViewer({ projectId }: BomViewerProps) {
    const [rows, setRows] = useState<BomRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState("");
    const [sort, setSort] = useState<SortState>({ col: "references", dir: "asc" });
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        setLoading(true);
        setError(null);
        fetch(`/api/projects/${projectId}/bom`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: BomRow[]) => setRows(data))
            .catch(err => setError(err.message))
            .finally(() => setLoading(false));
    }, [projectId]);

    // Collect extra field column names in order of first appearance
    const extraFieldCols = useMemo(() => {
        const seen = new Set<string>();
        const cols: string[] = [];
        for (const row of rows) {
            for (const k of Object.keys(row.extra_fields)) {
                if (!seen.has(k)) { seen.add(k); cols.push(k); }
            }
        }
        return cols;
    }, [rows]);

    const filtered = useMemo(() => {
        if (!filter) return rows;
        const q = filter.toLowerCase();
        return rows.filter(r =>
            r.value.toLowerCase().includes(q) ||
            r.description.toLowerCase().includes(q) ||
            r.references.some(ref => ref.toLowerCase().includes(q)) ||
            r.footprints.some(fp => fp.toLowerCase().includes(q)) ||
            Object.values(r.extra_fields).some(v => v.toLowerCase().includes(q))
        );
    }, [rows, filter]);

    const sorted = useMemo(() => {
        const arr = [...filtered];
        const { col, dir } = sort;
        const mul = dir === "asc" ? 1 : -1;
        arr.sort((a, b) => {
            let cmp = 0;
            if (col === "quantity") {
                cmp = a.quantity - b.quantity;
            } else if (col === "value") {
                cmp = a.value.localeCompare(b.value);
            } else if (col === "references") {
                cmp = naturalCompare(a.references[0] ?? "", b.references[0] ?? "");
            } else if (col === "footprint") {
                const afp = a.footprints[0] ?? "";
                const bfp = b.footprints[0] ?? "";
                const as2 = afp.includes(":") ? afp.split(":")[1] : afp;
                const bs2 = bfp.includes(":") ? bfp.split(":")[1] : bfp;
                cmp = as2.localeCompare(bs2);
            } else if (col === "description") {
                cmp = a.description.localeCompare(b.description);
            } else {
                cmp = (a.extra_fields[col] ?? "").localeCompare(b.extra_fields[col] ?? "");
            }
            return cmp * mul;
        });
        return arr;
    }, [filtered, sort]);

    const totalComponents = useMemo(
        () => sorted.reduce((s, r) => s + r.quantity, 0),
        [sorted]
    );

    const handleSortHeader = (col: string) => {
        setSort(s => s.col === col
            ? { col, dir: s.dir === "asc" ? "desc" : "asc" }
            : { col, dir: "asc" });
    };

    const handleCopyCSV = () => {
        const headers = ["Ref Des", "Qty", "Value", "Footprint", "Datasheet", "Description", ...extraFieldCols];
        const lines = [headers.join(",")];
        for (const row of sorted) {
            const cells = [
                `"${row.references.join(", ")}"`,
                row.quantity,
                `"${row.value}"`,
                `"${row.footprints.join("; ")}"`,
                `"${row.datasheet}"`,
                `"${row.description}"`,
                ...extraFieldCols.map(k => `"${row.extra_fields[k] ?? ""}"`),
            ];
            lines.push(cells.join(","));
        }
        navigator.clipboard.writeText(lines.join("\n"));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    if (loading) {
        return (
            <div className="p-4 space-y-2">
                {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-8 w-full" />)}
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-8 text-center text-sm text-destructive">
                Failed to load BOM: {error}
            </div>
        );
    }

    const allCols = [
        ...STANDARD_COLS,
        ...extraFieldCols.map(k => ({ col: k, label: k, cls: "w-32" })),
    ];

    return (
        <div className="flex flex-col h-full p-4 gap-3">
            {/* Toolbar */}
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-sm text-muted-foreground">
                    {sorted.length} line items &middot; {totalComponents} components
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative w-56">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                        <Input
                            placeholder="Filter..."
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
                    <Button size="sm" variant="outline" className="h-8" onClick={handleCopyCSV}>
                        {copied
                            ? <><Check className="h-3.5 w-3.5 mr-1.5" />Copied!</>
                            : <><Copy className="h-3.5 w-3.5 mr-1.5" />Copy CSV</>
                        }
                    </Button>
                </div>
            </div>

            {/* Table */}
            <div className="border rounded-lg overflow-auto flex-1 min-h-0">
                <table className="w-full text-sm border-collapse">
                    <thead>
                        <tr className="bg-muted/60 sticky top-0 z-10">
                            {allCols.map(({ col, label, cls }) => (
                                <th
                                    key={col}
                                    className={`px-3 py-2 text-left font-medium text-xs whitespace-nowrap select-none cursor-pointer hover:bg-muted/90 border-b ${cls}`}
                                    onClick={() => handleSortHeader(col)}
                                >
                                    <span className="flex items-center gap-1">
                                        {label}
                                        <SortIcon col={col} sort={sort} />
                                    </span>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.length === 0 ? (
                            <tr>
                                <td
                                    colSpan={allCols.length}
                                    className="text-center py-12 text-muted-foreground"
                                >
                                    {rows.length === 0 ? "No components found in schematic." : "No matches."}
                                </td>
                            </tr>
                        ) : sorted.map((row, i) => (
                            <tr key={i} className="border-t hover:bg-muted/30 transition-colors">
                                {/* Ref Des */}
                                <td className="px-3 py-2 font-mono text-xs">
                                    {row.references.join(", ")}
                                </td>
                                {/* Qty */}
                                <td className="px-3 py-2 text-right tabular-nums font-medium">
                                    {row.quantity}
                                </td>
                                {/* Value */}
                                <td className="px-3 py-2 font-medium">{row.value}</td>
                                {/* Footprint */}
                                <td className="px-3 py-2 text-xs text-muted-foreground">
                                    <FootprintCell fps={row.footprints} />
                                </td>
                                {/* Datasheet */}
                                <td className="px-3 py-2">
                                    <DatasheetCell url={row.datasheet} />
                                </td>
                                {/* Description */}
                                <td className="px-3 py-2 text-muted-foreground">
                                    {row.description || "—"}
                                </td>
                                {/* Extra fields */}
                                {extraFieldCols.map(k => (
                                    <td key={k} className="px-3 py-2 text-muted-foreground">
                                        {row.extra_fields[k] ?? "—"}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
