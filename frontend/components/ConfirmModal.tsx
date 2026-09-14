"use client";
import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

type Props = {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger = false,
  onConfirm,
  onCancel,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter") onConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onConfirm, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-fade-in"
      onClick={onCancel}
    >
      <div
        className="bg-bg-panel border border-border rounded-lg shadow-2xl w-[420px] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-3">
          {danger && <AlertTriangle className="w-5 h-5 text-accent-red" />}
          <h3 className="font-semibold text-base">{title}</h3>
        </div>

        <div className="text-sm text-text-secondary mb-5 leading-relaxed">
          {message}
        </div>

        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-xs rounded border border-border hover:bg-bg-hover transition"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-xs font-semibold rounded transition ${
              danger
                ? "bg-accent-red hover:bg-accent-red/80 text-white"
                : "bg-accent-blue hover:bg-accent-blue/80 text-white"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}