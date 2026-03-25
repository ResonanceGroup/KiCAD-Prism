import * as React from "react";
import { useEffect, useRef, useState } from "react";
import { X, Send, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CommentContext, CommentLocation } from "@/types/comments";
import { fetchApi } from "@/lib/api";

interface CommentFormProps {
    /** Whether the form is open */
    isOpen: boolean;
    /** Callback to close the form */
    onClose: () => void;
    /** Callback when comment is submitted */
    onSubmit: (content: string) => void;
    /** Location where the comment will be placed */
    location: CommentLocation | null;
    /** Context (PCB or SCH) */
    context: CommentContext;
    /** Whether submission is in progress */
    isSubmitting?: boolean;
}

/**
 * CommentForm - Modal dialog for adding new design review comments.
 * Shows the location (readonly) and allows entering comment text.
 * Supports @email mention autocomplete.
 */
export function CommentForm({
    isOpen,
    onClose,
    onSubmit,
    location,
    context,
    isSubmitting = false,
}: CommentFormProps) {
    const [content, setContent] = useState("");
    const [mentionSuggestions, setMentionSuggestions] = useState<string[]>([]);
    const [mentionQuery, setMentionQuery] = useState<string | null>(null);
    const [mentionIndex, setMentionIndex] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Detect @-mention trigger while typing
    const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const val = e.target.value;
        setContent(val);

        // Find @mention at/near cursor
        const cursor = e.target.selectionStart ?? val.length;
        const textBefore = val.slice(0, cursor);
        const match = /@([\w.+\-]*)$/.exec(textBefore);
        if (match) {
            const q = match[1];
            setMentionQuery(q);
            setMentionIndex(0);
            // Fetch suggestions
            fetchApi(`/api/auth/users/search?q=${encodeURIComponent(q)}`)
                .then((r) => (r.ok ? r.json() : []))
                .then((data: { email: string }[]) => setMentionSuggestions(data.map((d) => d.email)))
                .catch(() => setMentionSuggestions([]));
        } else {
            setMentionQuery(null);
            setMentionSuggestions([]);
        }
    };

    // Close suggestions when form closes
    useEffect(() => {
        if (!isOpen) {
            setContent("");
            setMentionQuery(null);
            setMentionSuggestions([]);
        }
    }, [isOpen]);

    const insertMention = (email: string) => {
        const cursor = textareaRef.current?.selectionStart ?? content.length;
        const textBefore = content.slice(0, cursor);
        const replaced = textBefore.replace(/@([\w.+\-]*)$/, `@${email} `);
        setContent(replaced + content.slice(cursor));
        setMentionQuery(null);
        setMentionSuggestions([]);
        textareaRef.current?.focus();
    };

    if (!isOpen || !location) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (content.trim()) {
            onSubmit(content.trim());
            setContent("");
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (mentionSuggestions.length > 0) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                setMentionIndex((i) => (i + 1) % mentionSuggestions.length);
                return;
            }
            if (e.key === "ArrowUp") {
                e.preventDefault();
                setMentionIndex((i) => (i - 1 + mentionSuggestions.length) % mentionSuggestions.length);
                return;
            }
            if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                insertMention(mentionSuggestions[mentionIndex]);
                return;
            }
            if (e.key === "Escape") {
                setMentionQuery(null);
                setMentionSuggestions([]);
                return;
            }
        }
        if (e.key === "Escape") {
            onClose();
        }
        if (e.key === "Enter" && e.metaKey) {
            handleSubmit(e);
        }
    };

    return (
        <div
            className="fixed inset-0 z-[120] flex items-center justify-center"
            onClick={onClose}
        >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/50" />

            {/* Modal */}
            <div
                className="relative bg-background border rounded-lg shadow-xl w-full max-w-md mx-4"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b">
                    <h2 className="text-lg font-semibold">Add Comment</h2>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={onClose}
                        className="h-8 w-8"
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                {/* Location info */}
                <div className="px-4 py-3 bg-muted/50 border-b">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <MapPin className="h-4 w-4" />
                        <span>
                            {context} · ({location.x.toFixed(2)}, {location.y.toFixed(2)}) mm
                        </span>
                        {location.layer && (
                            <span className="px-2 py-0.5 bg-background rounded text-xs">
                                {location.layer}
                            </span>
                        )}
                    </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="p-4">
                    <div className="relative">
                        <textarea
                            ref={textareaRef}
                            autoFocus
                            value={content}
                            onChange={handleContentChange}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe the issue or leave a note… use @email to mention someone"
                            className="w-full h-32 p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-ring text-foreground bg-background"
                            disabled={isSubmitting}
                        />
                        {mentionSuggestions.length > 0 && mentionQuery !== null && (
                            <ul className="absolute z-10 left-0 right-0 bg-background border rounded-md shadow-lg max-h-40 overflow-y-auto text-sm">
                                {mentionSuggestions.map((email, i) => (
                                    <li
                                        key={email}
                                        className={`px-3 py-2 cursor-pointer ${i === mentionIndex ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                                        onMouseDown={(e) => { e.preventDefault(); insertMention(email); }}
                                    >
                                        @{email}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>

                    <div className="flex items-center justify-between mt-4">
                        <span className="text-xs text-muted-foreground">
                            ⌘ + Enter to submit
                        </span>
                        <div className="flex gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={onClose}
                                disabled={isSubmitting}
                            >
                                Cancel
                            </Button>
                            <Button
                                type="submit"
                                disabled={!content.trim() || isSubmitting}
                            >
                                {isSubmitting ? (
                                    "Posting..."
                                ) : (
                                    <>
                                        <Send className="h-4 w-4 mr-2" />
                                        Post Comment
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    );
}
