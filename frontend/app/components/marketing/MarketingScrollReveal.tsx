"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * Lumina-style scroll reveal: IntersectionObserver adds visible class once (threshold 0.1).
 */
export function MarketingScrollReveal({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    el.classList.add("lk-animate-on-scroll-hidden");

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("lk-animate-on-scroll-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
