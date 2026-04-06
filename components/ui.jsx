"use client";

import { useEffect } from "react";

export function BusyButton({ busy, className = "", children, ...props }) {
  return (
    <button
      {...props}
      className={[className, busy ? "is-busy" : ""].filter(Boolean).join(" ")}
      disabled={busy || props.disabled}
    >
      {children}
    </button>
  );
}

export function Modal({ open, title, message, confirmLabel = "确定", cancelLabel, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        onCancel?.();
      }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onCancel]);

  if (!open) {
    return null;
  }

  return (
    <div className="modal-shell is-open">
      <button type="button" className="modal-backdrop" aria-label="关闭" onClick={onCancel} />
      <div className="modal-card" role="dialog" aria-modal="true">
        <h3>{title}</h3>
        <p className="subtle">{message}</p>
        <div className="modal-actions">
          {cancelLabel ? (
            <button type="button" className="ghost-btn" onClick={onCancel}>
              {cancelLabel}
            </button>
          ) : null}
          <button type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
