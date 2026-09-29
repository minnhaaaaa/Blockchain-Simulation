export function shortId(value: string | null | undefined, length = 10) {
  if (!value) return "—";
  return value.length <= length ? value : `${value.slice(0, Math.max(4, length - 3))}…`;
}

export function formatTimestamp(value: number | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(value);
}

export function relativeAge(value: number | null | undefined, now = Date.now()) {
  if (!value) return "never";
  const seconds = Math.max(0, Math.round((now - value) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

export function titleCase(value: string) {
  return value.replaceAll("_", " ").replaceAll(".", " · ").replace(/\b\w/g, char => char.toUpperCase());
}
