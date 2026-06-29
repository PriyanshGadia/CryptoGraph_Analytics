"use client";
import { useRef } from "react";

const MAX_DEG = 6;

export function useTilt<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  const onPointerMove = (e: React.PointerEvent) => {
    if (e.pointerType !== "mouse" || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    ref.current.style.setProperty("--ry", `${px * MAX_DEG * 2}deg`);
    ref.current.style.setProperty("--rx", `${py * -MAX_DEG * 2}deg`);
  };

  const onPointerLeave = () => {
    ref.current?.style.setProperty("--rx", "0deg");
    ref.current?.style.setProperty("--ry", "0deg");
  };

  return { ref, onPointerMove, onPointerLeave };
}
