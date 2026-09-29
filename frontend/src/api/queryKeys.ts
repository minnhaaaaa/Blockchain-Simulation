export const queryKeys = {
  status: (origin: string) => ["status", origin] as const,
  providers: (origin: string) => ["providers", origin] as const,
  tools: (origin: string) => ["tools", origin] as const,
  peers: (origin: string, roomId: string) => ["peers", origin, roomId] as const,
  chain: (origin: string, roomId: string, limit: number) => ["chain", origin, roomId, limit] as const,
  block: (origin: string, roomId: string, blockId: string) => ["block", origin, roomId, blockId] as const,
  stakes: (origin: string, roomId: string) => ["stakes", origin, roomId] as const,
  jobs: (origin: string, roomId: string, status?: string) => ["jobs", origin, roomId, status ?? "all"] as const,
  job: (origin: string, roomId: string, jobId: string) => ["job", origin, roomId, jobId] as const,
  violations: (origin: string, roomId: string) => ["violations", origin, roomId] as const
};
