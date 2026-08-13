"use client";

import { useEffect, useRef, useState } from "react";

export default function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  function toggle() {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const w = 224;
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    setPos({ top: r.bottom + 6, left });
    setOpen((o) => !o);
  }

  return (
    <>
      <button
        ref={ref}
        type="button"
        onClick={(e) => { e.stopPropagation(); toggle(); }}
        aria-label="Info"
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-gray-200 text-[10px] font-bold leading-none text-gray-500 transition-colors hover:bg-accent hover:text-white"
      >
        ?
      </button>
      {open && (
        <div
          className="fixed z-50 w-56 whitespace-normal break-words rounded-lg border border-border bg-white p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
          style={{ top: pos.top, left: pos.left }}
        >
          {text}
        </div>
      )}
    </>
  );
}
