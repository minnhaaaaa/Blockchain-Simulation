import { AlertCircle, Inbox, RefreshCw, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import { IncompatibleResponseError } from "../api/validators";

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return <div className="skeleton-stack" aria-label="Loading">{Array.from({ length: rows }, (_, index) => <span key={index} className="skeleton-line" />)}</div>;
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <section className="empty-state"><Inbox aria-hidden="true" /><h3>{title}</h3><p>{detail}</p>{action}</section>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  const incompatible = error instanceof IncompatibleResponseError ? error : null;
  const offline = apiError?.status === 0;
  return <section className="error-state" role="alert">
    {offline ? <WifiOff aria-hidden="true" /> : <AlertCircle aria-hidden="true" />}
    <div><h3>{incompatible ? "Incompatible server response" : offline ? "Application API unavailable" : "Request failed"}</h3>
      <p>{error instanceof Error ? error.message : "An unexpected error occurred."}</p>
      {apiError?.requestId && <p className="mono muted">Request ID: {apiError.requestId}</p>}
      {incompatible && <ul>{incompatible.validationErrors.map(item => <li key={item}>{item}</li>)}</ul>}
    </div>
    {onRetry && <button className="button button-secondary" onClick={onRetry}><RefreshCw size={16} />Retry</button>}
  </section>;
}

export function StaleDataBanner({ updatedAt, onRetry }: { updatedAt?: number; onRetry?: () => void }) {
  return <div className="stale-banner" role="status"><WifiOff size={16} /><span>Live refresh failed. Showing the last successful response{updatedAt ? ` from ${new Date(updatedAt).toLocaleTimeString()}` : ""}.</span>{onRetry && <button onClick={onRetry}>Retry</button>}</div>;
}
