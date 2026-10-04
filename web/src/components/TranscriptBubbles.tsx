import clsx from "clsx";

/** Call turns as a light, two-sided conversation. Turns the summary cites are outlined in brand red and labelled
 * "cited", so the link is not shown by colour alone. */
export function TranscriptBubbles({ turns, cited = [] }: { turns: { turn_index: number; speaker: string; text: string }[]; cited?: number[] }) {
  return (
    <ol className="m-0 list-none space-y-2.5 p-0">
      {turns.map((t) => {
        const agent = t.speaker === "agent";
        const c = cited.includes(t.turn_index);
        return (
          <li key={t.turn_index} id={`turn-${t.turn_index}`} className={clsx("flex", agent ? "justify-start" : "justify-end")}>
            <div className={clsx("max-w-[80%] rounded-[var(--radius-lg)] border px-3.5 py-2.5 text-[14px]",
              agent ? "border-grey-300/70 bg-grey-100" : "border-grey-300/70 bg-white", c && "border-brand ring-1 ring-brand/30")}>
              <p className="m-0 text-[12px] text-muted">#{t.turn_index} · {agent ? "Agent" : "Customer"}{c && <span className="font-semibold text-brand"> · cited</span>}</p>
              <p className="m-0">{t.text}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
