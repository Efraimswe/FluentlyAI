export function LiveInput({ text, listening }: { text: string; listening: boolean }) {
  return (
    <p className="w-full text-center text-xs min-h-6 truncate">
      {text ? (
        <span className="text-slate-200">
          {text}
          <span className="animate-pulse">|</span>
        </span>
      ) : listening ? (
        <span className="text-slate-600">…</span>
      ) : null}
    </p>
  );
}
