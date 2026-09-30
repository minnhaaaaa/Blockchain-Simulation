import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "./ApiContext";
import { queryKeys } from "./queryKeys";
import { validateAgentEvents, validateRoomManifest } from "./validators";
import type { ActionDecisionRequest, AgentEvent, ArtifactRef, BlockDetail, Chain, JobCreateRequest, JobDetail, JobProjection, Provider, RoomManifest, RoomSessionRequest, StakeSnapshot, Status, Submission, Tool, Peer, Violation } from "../types/api";

function useRequiredApi() {
  const api = useApi();
  if (!api.client || !api.apiOrigin) throw new Error("Application API is not configured.");
  return { ...api, client: api.client, apiOrigin: api.apiOrigin };
}

export function useStatus(enabled = true) {
  const { client, apiOrigin, pollIntervalMs } = useRequiredApi();
  return useQuery({ queryKey: queryKeys.status(apiOrigin), queryFn: ({ signal }) => client.get<Status>("/api/status", signal), enabled, refetchInterval: pollIntervalMs });
}
export function useProviders() { const { client, apiOrigin } = useRequiredApi(); return useQuery({ queryKey: queryKeys.providers(apiOrigin), queryFn: async ({ signal }) => (await client.get<{items: Provider[]}>("/api/providers", signal)).items }); }
export function useTools() { const { client, apiOrigin } = useRequiredApi(); return useQuery({ queryKey: queryKeys.tools(apiOrigin), queryFn: async ({ signal }) => (await client.get<{items: Tool[]}>("/api/tools", signal)).items }); }
export function usePeers(roomId: string) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); return useQuery({ queryKey: queryKeys.peers(apiOrigin, roomId), queryFn: async ({ signal }) => (await client.get<{items: Peer[]}>("/api/peers", signal)).items, refetchInterval: pollIntervalMs }); }
export function useChain(roomId: string, limit = 50) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); return useQuery({ queryKey: queryKeys.chain(apiOrigin, roomId, limit), queryFn: ({ signal }) => client.get<Chain>(`/api/chain?limit=${limit}`, signal), refetchInterval: pollIntervalMs }); }
export function useBlock(roomId: string, blockId: string | null) { const { client, apiOrigin } = useRequiredApi(); return useQuery({ queryKey: queryKeys.block(apiOrigin, roomId, blockId ?? "none"), queryFn: ({ signal }) => client.get<BlockDetail>(`/api/chain/${encodeURIComponent(blockId ?? "")}`, signal), enabled: Boolean(blockId) }); }
export function useStakes(roomId: string) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); return useQuery({ queryKey: queryKeys.stakes(apiOrigin, roomId), queryFn: ({ signal }) => client.get<StakeSnapshot>("/api/stakes", signal), refetchInterval: pollIntervalMs }); }
export function useJobs(roomId: string, status?: string) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); const query = status ? `?status=${encodeURIComponent(status)}` : ""; return useQuery({ queryKey: queryKeys.jobs(apiOrigin, roomId, status), queryFn: async ({ signal }) => (await client.get<{items: JobProjection[]}>(`/api/jobs${query}`, signal)).items, refetchInterval: pollIntervalMs }); }
export function useJob(roomId: string, jobId: string) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); return useQuery({ queryKey: queryKeys.job(apiOrigin, roomId, jobId), queryFn: async ({ signal }) => { const detail = await client.get<JobDetail>(`/api/jobs/${encodeURIComponent(jobId)}`, signal); return { ...detail, events: validateAgentEvents(detail.events) }; }, refetchInterval: pollIntervalMs }); }
export function useViolations(roomId: string) { const { client, apiOrigin, pollIntervalMs } = useRequiredApi(); return useQuery({ queryKey: queryKeys.violations(apiOrigin, roomId), queryFn: async ({ signal }) => (await client.get<{items: Violation[]}>("/api/violations", signal)).items, refetchInterval: pollIntervalMs }); }

function useInvalidateRoom(roomId: string) {
  const queryClient = useQueryClient(); const { apiOrigin } = useRequiredApi();
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["status", apiOrigin] }),
    queryClient.invalidateQueries({ queryKey: ["jobs", apiOrigin, roomId] }),
    queryClient.invalidateQueries({ queryKey: ["chain", apiOrigin, roomId] }),
    queryClient.invalidateQueries({ queryKey: ["violations", apiOrigin, roomId] })
  ]);
}

export function useConfigureRoom() { const { client } = useRequiredApi(); return useMutation({ mutationFn: async (body: RoomSessionRequest) => validateRoomManifest(await client.post<RoomManifest>("/api/room-session", body)) }); }
export function useUploadArtifact() { const { client } = useRequiredApi(); return useMutation({ mutationFn: (file: File) => client.upload<ArtifactRef>("/api/artifacts", file) }); }
export function useCreateJob(roomId: string) { const { client } = useRequiredApi(); const invalidate = useInvalidateRoom(roomId); return useMutation({ mutationFn: (body: JobCreateRequest) => client.post<Submission>("/api/jobs", body), onSuccess: invalidate }); }
export function useAcceptJob(roomId: string, jobId: string) { const { client, apiOrigin } = useRequiredApi(); const qc = useQueryClient(); return useMutation({ mutationFn: () => client.post<Submission>(`/api/jobs/${encodeURIComponent(jobId)}/accept`), onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.job(apiOrigin, roomId, jobId) }) }); }
export function useRunJob(roomId: string, jobId: string) { const { client, apiOrigin } = useRequiredApi(); const qc = useQueryClient(); return useMutation({ mutationFn: () => client.post<{run_id:string;job_id:string;state:JobProjection["status"]}>(`/api/jobs/${encodeURIComponent(jobId)}/run`), onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.job(apiOrigin, roomId, jobId) }) }); }
export function useDecideAction(roomId: string, jobId: string, actionId: string) { const { client, apiOrigin } = useRequiredApi(); const qc = useQueryClient(); return useMutation({ mutationFn: (body: ActionDecisionRequest) => client.post<Submission>(`/api/jobs/${encodeURIComponent(jobId)}/actions/${encodeURIComponent(actionId)}/decision`, body), onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.job(apiOrigin, roomId, jobId) }) }); }

export type ValidatedJobDetail = Omit<JobDetail, "events"> & { events: AgentEvent[] };

export function useJobCommand<T>(roomId: string, jobId: string, command: string) {
  const { client, apiOrigin } = useRequiredApi(); const qc = useQueryClient();
  return useMutation({ mutationFn: (body: T) => client.post<Submission>(`/api/jobs/${encodeURIComponent(jobId)}/${command}`, body),
    onSuccess: async () => { await Promise.all([qc.invalidateQueries({ queryKey: queryKeys.job(apiOrigin, roomId, jobId) }), qc.invalidateQueries({ queryKey: ["jobs", apiOrigin, roomId] })]); } });
}
