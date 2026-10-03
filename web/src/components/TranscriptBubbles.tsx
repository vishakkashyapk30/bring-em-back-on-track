import clsx from "clsx";

/** Figma testimonial bubbles reused for call turns; cited turns are highlighted (post-call summary citations). */
export function TranscriptBubbles({ turns, cited = [] }: { turns: { turn_index: number; speaker: string; text: string }[]; cited?: number[] }) {
  return (
    <div className="space-y-3 rounded-[var(--radius-lg)] bg-navy p-6">
      {turns.map((t) => (
        <div key={t.turn_index} id={`turn-${t.turn_index}`} className={clsx("flex", t.speaker === "agent" ? "justify-start" : "justify-end")}>
          <div className={clsx("max-w-[75%] rounded-[var(--radius-lg)] border px-4 py-3 text-white",
            cited.includes(t.turn_index) ? "border-gold bg-white/10" : "border-white/30")}>
            <p className="m-0 text-xs text-white/60">#{t.turn_index} · {t.speaker}</p>
            <p className="m-0">{t.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
