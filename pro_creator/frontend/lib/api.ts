export type Project = {
  project_id: string;
  title: string;
  topic: string;
  status: string;
  created_at: string;
};

export type Scene = {
  id: number;
  text: string;
  image_path?: string | null;
  audio_path?: string | null;
};

export type ScriptResponse = {
  full_script: string;
  scenes: Scene[];
};

export type VoiceResponse = {
  audio_path: string;
  duration_seconds: number;
};

export type ImageResponse = {
  image_path: string;
};

export type VideoResponse = {
  video_path: string;
};

export type ThumbnailResponse = {
  thumbnail_path: string;
  thumbnail_key: string;
  mode_used: string;
  source_used: string;
  width: number;
  height: number;
  variants?: Array<{
    variant_id: number;
    thumbnail_key: string;
    thumbnail_path: string;
    source_used: string;
    width: number;
    height: number;
  }>;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

type FetchInput = Parameters<typeof globalThis.fetch>[0];
type FetchInit = Parameters<typeof globalThis.fetch>[1];
type FetchHeaders = Record<string, string> | [string, string][] | Headers;

const getAuthToken = (): string | null => {
  if (typeof window !== "undefined") {
    return window.localStorage.getItem("pc_token");
  }
  return process.env.NEXT_PUBLIC_API_TOKEN ?? null;
};

const getAdminAccessToken = (): string | null => {
  if (typeof window !== "undefined") {
    return window.sessionStorage.getItem("pc_admin_access_token");
  }
  return null;
};

const normalizeHeaders = (headers?: FetchHeaders): Record<string, string> => {
  if (!headers) {
    return {};
  }
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return headers;
};

const withAuthHeaders = (headers?: FetchHeaders): FetchHeaders => {
  const token = getAuthToken();
  const normalized = normalizeHeaders(headers);
  if (!token) {
    return normalized;
  }
  return {
    ...normalized,
    Authorization: `Bearer ${token}`,
  };
};

const withOwnerDashboardHeaders = (headers?: FetchHeaders): FetchHeaders => {
  const normalized = normalizeHeaders(headers);
  const adminAccessToken = getAdminAccessToken();
  if (!adminAccessToken) {
    return normalized;
  }
  return {
    ...normalized,
    "X-Admin-Access-Token": adminAccessToken,
  };
};

const baseFetch = globalThis.fetch.bind(globalThis);
type FetchType = typeof globalThis.fetch;
const fetchWithAuth = (
  input: FetchInput,
  init: FetchInit = {}
): ReturnType<FetchType> =>
  baseFetch(input, {
    ...init,
    headers: withAuthHeaders(init?.headers),
  });

const fetch: FetchType = fetchWithAuth as FetchType;

export async function fetchProjects(): Promise<Project[]> {
  const response = await fetch(`${API_BASE}/project/`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load projects");
  }
  return response.json();
}

export async function fetchProject(projectId: string): Promise<Project> {
  const response = await fetch(`${API_BASE}/project/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load project");
  }
  return response.json();
}

export async function deleteProject(projectId: string): Promise<{ deleted: boolean }> {
  const response = await fetch(`${API_BASE}/project/${projectId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail ?? "Failed to delete project";
    throw new Error(message);
  }
  return response.json();
}

export async function deleteAllProjects(): Promise<{
  deleted_count: number;
  deleted_ids: string[];
}> {
  const response = await fetch(`${API_BASE}/project/`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail ?? "Failed to delete all projects";
    throw new Error(message);
  }
  return response.json();
}

export async function purgeStaleProjects(payload: {
  min_age_days: number;
}): Promise<{ deleted_count: number; deleted_ids: string[] }> {
  const response = await fetch(`${API_BASE}/project/purge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail ?? "Failed to purge stale projects";
    throw new Error(message);
  }
  return response.json();
}

export type OrchestrationQueueItem = {
  id: number;
  project_id: string;
  kind: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type OrchestrationScheduleItem = {
  id: number;
  project_id: string;
  cadence_days: number;
  next_run_at: string;
  enabled: boolean;
  last_run_at?: string | null;
  created_at: string;
};

export async function changePassword(payload: {
  current_password: string;
  new_password: string;
}): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail ?? "Failed to change password";
    throw new Error(message);
  }
  return response.json();
}

export type AuthGateStatus = {
  enabled: boolean;
  source: "env" | "db";
};

export async function fetchAuthGateStatus(): Promise<AuthGateStatus> {
  const response = await fetch(`${API_BASE}/auth/gate/status`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load password gate status");
  }
  return response.json();
}

export async function updateAuthGateStatus(enabled: boolean): Promise<AuthGateStatus> {
  const response = await fetch(`${API_BASE}/auth/gate`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = detail?.detail ?? "Failed to update password gate";
    throw new Error(message);
  }
  return response.json();
}

export async function enqueueOrchestrationJob(payload: {
  project_id: string;
  kind: string;
  topic?: string;
  duration_minutes?: number;
  tone?: string;
  voice_text?: string;
  image_prompt?: string;
  export_preset?: string;
}): Promise<OrchestrationQueueItem> {
  const response = await fetch(`${API_BASE}/orchestration/queue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to enqueue job");
  }
  return response.json();
}

export async function enqueueOrchestrationBatch(payload: {
  items: {
    project_id: string;
    kind: string;
    topic?: string;
    duration_minutes?: number;
    tone?: string;
    voice_text?: string;
    image_prompt?: string;
    export_preset?: string;
  }[];
}): Promise<{ items: OrchestrationQueueItem[] }> {
  const response = await fetch(`${API_BASE}/orchestration/queue/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to enqueue batch");
  }
  return response.json();
}

export async function fetchOrchestrationQueue(payload?: {
  status?: string;
}): Promise<{ items: OrchestrationQueueItem[] }> {
  const query = payload?.status
    ? `?status=${encodeURIComponent(payload.status)}`
    : "";
  const response = await fetch(`${API_BASE}/orchestration/queue${query}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load queue");
  }
  return response.json();
}

export async function processOrchestrationQueue(payload?: {
  limit?: number;
}): Promise<{ processed: number; completed: number[]; failed: number[] }> {
  const query = payload?.limit ? `?limit=${payload.limit}` : "";
  const response = await fetch(`${API_BASE}/orchestration/queue/process${query}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to process queue");
  }
  return response.json();
}

export async function retryOrchestrationJob(jobId: number): Promise<OrchestrationQueueItem> {
  const response = await fetch(`${API_BASE}/orchestration/queue/${jobId}/retry`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to retry job");
  }
  return response.json();
}

export async function startOrchestrationRunner(payload?: {
  interval_seconds?: number;
}): Promise<{ running: boolean; interval_seconds: number }> {
  const query = payload?.interval_seconds
    ? `?interval_seconds=${payload.interval_seconds}`
    : "";
  const response = await fetch(
    `${API_BASE}/orchestration/queue/runner/start${query}`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    throw new Error("Failed to start runner");
  }
  return response.json();
}

export async function stopOrchestrationRunner(): Promise<{
  running: boolean;
  interval_seconds: number;
}> {
  const response = await fetch(`${API_BASE}/orchestration/queue/runner/stop`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to stop runner");
  }
  return response.json();
}

export async function fetchOrchestrationRunnerStatus(): Promise<{
  running: boolean;
  interval_seconds: number;
}> {
  const response = await fetch(`${API_BASE}/orchestration/queue/runner/status`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load runner status");
  }
  return response.json();
}

export async function createOrchestrationSchedule(payload: {
  project_id: string;
  cadence_days: number;
}): Promise<OrchestrationScheduleItem> {
  const response = await fetch(`${API_BASE}/orchestration/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to create schedule");
  }
  return response.json();
}

export async function fetchOrchestrationSchedules(): Promise<{
  items: OrchestrationScheduleItem[];
}> {
  const response = await fetch(`${API_BASE}/orchestration/schedules`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load schedules");
  }
  return response.json();
}

export async function runOrchestrationSchedules(): Promise<{
  items: OrchestrationScheduleItem[];
}> {
  const response = await fetch(`${API_BASE}/orchestration/schedules/run`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to run schedules");
  }
  return response.json();
}

export async function fetchProjectScenes(projectId: string): Promise<Scene[]> {
  const response = await fetch(`${API_BASE}/project/${projectId}/scenes`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load scenes");
  }
  return response.json();
}

export async function fetchProjectScript(projectId: string): Promise<string> {
  const response = await fetch(`${API_BASE}/project/${projectId}/script`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load script");
  }
  const data = await response.json();
  return data.script ?? "";
}

export async function createProject(payload: {
  title: string;
  topic: string;
}): Promise<Project> {
  const response = await fetch(`${API_BASE}/project/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to create project");
  }
  return response.json();
}

export async function generateScript(payload: {
  project_id: string;
  topic: string;
  duration_minutes: number;
  tone: string;
}): Promise<ScriptResponse> {
  const response = await fetch(`${API_BASE}/script/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      detail?.detail ??
      (Array.isArray(detail) ? detail?.[0]?.msg : null) ??
      "Failed to generate script";
    throw new Error(message);
  }
  return response.json();
}

export async function importScript(payload: {
  project_id: string;
  script: string;
}): Promise<ScriptResponse> {
  const response = await fetch(`${API_BASE}/script/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to import script");
  }
  return response.json();
}

export async function updateLiveScript(payload: {
  project_id: string;
  script: string;
  update_scenes?: boolean;
}): Promise<ScriptResponse> {
  const response = await fetch(`${API_BASE}/script/live`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to update live script");
  }
  return response.json();
}

export async function clearScript(payload: {
  project_id: string;
}): Promise<ScriptResponse> {
  const response = await fetch(`${API_BASE}/script/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to clear script");
  }
  return response.json();
}

export async function generateVoice(payload: {
  project_id: string;
  text: string;
  voice_profile: string;
  tts_provider?: string;
}): Promise<VoiceResponse> {
  const response = await fetch(`${API_BASE}/voice/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      detail?.detail ??
      (Array.isArray(detail) ? detail?.[0]?.msg : null) ??
      "Failed to generate voice";
    throw new Error(message);
  }
  return response.json();
}

export async function generateImage(payload: {
  project_id: string;
  prompt: string;
  style: string;
}): Promise<ImageResponse> {
  const response = await fetch(`${API_BASE}/image/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to generate image");
  }
  return response.json();
}

export async function renderVideo(payload: {
  project_id: string;
}): Promise<VideoResponse> {
  const response = await fetch(`${API_BASE}/video/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to render video");
  }
  return response.json();
}

export async function generateThumbnail(payload: {
  project_id: string;
  mode?: "classic" | "ai";
  title?: string;
  subtitle?: string;
  ai_prompt?: string;
  style?: string;
  variant_count?: number;
  source?: "auto" | "video" | "image";
  scene_id?: number;
  timestamp_seconds?: number;
  format?: "png" | "jpg";
  width?: number;
  height?: number;
}): Promise<ThumbnailResponse> {
  const response = await fetch(`${API_BASE}/video/thumbnail/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to generate thumbnail");
  }
  return response.json();
}

export async function setPrimaryThumbnail(payload: {
  project_id: string;
  thumbnail_key: string;
}): Promise<ThumbnailResponse> {
  const response = await fetch(`${API_BASE}/video/thumbnail/set-primary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to set primary thumbnail");
  }
  return response.json();
}

export async function importVideoUrl(payload: {
  project_id: string;
  url: string;
}): Promise<VideoResponse> {
  const response = await fetch(`${API_BASE}/video/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to import video");
  }
  return response.json();
}

export async function triggerFeature(payload: {
  path: string;
  project_id?: string;
}): Promise<{ status: string; detail: string }> {
  const query = payload.project_id
    ? `?project_id=${encodeURIComponent(payload.project_id)}`
    : "";
  const response = await fetch(`${API_BASE}${payload.path}${query}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to run feature");
  }
  return response.json();
}

export type ArtifactPayload = {
  project_id: string;
  artifact:
    | "transcript"
    | "clips"
    | "scene-detection"
    | "multitrack"
    | "captions"
    | "lipsync";
};

export async function fetchArtifact(
  payload: ArtifactPayload
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `${API_BASE}/video/artifacts/${payload.project_id}/${payload.artifact}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error("Failed to load artifact");
  }
  return response.json();
}

export async function exportPreset(payload: {
  project_id: string;
  preset: string;
}): Promise<{ export_path: string }> {
  const response = await fetch(`${API_BASE}/video/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to export preset");
  }
  return response.json();
}

export async function exportBatch(payload: {
  project_id: string;
  presets: string[];
}): Promise<{ exports: string[] }> {
  const response = await fetch(`${API_BASE}/video/export/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to export batch");
  }
  return response.json();
}

export type ExportStatusEntry = {
  preset: string;
  status: "queued" | "complete";
  path?: string | null;
  size_bytes?: number | null;
  updated_at?: string | null;
};

export async function fetchExportStatus(payload: {
  project_id: string;
  presets?: string[];
}): Promise<{ project_id: string; exports: ExportStatusEntry[] }> {
  const params = payload.presets?.length
    ? `?${payload.presets.map((preset) => `presets=${preset}`).join("&")}`
    : "";
  const response = await fetch(
    `${API_BASE}/video/export/status/${payload.project_id}${params}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error("Failed to load export status");
  }
  return response.json();
}

export async function editByText(payload: {
  project_id: string;
  remove_ranges: number[][];
}): Promise<{ segments_remaining: number }> {
  const response = await fetch(`${API_BASE}/video/edit-by-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to apply edit-by-text");
  }
  return response.json();
}

export async function uploadVoiceProfile(payload: {
  project_id: string;
  profile_name: string;
  file: File;
  tts_provider?: string;
}): Promise<{ profile_path: string }> {
  const formData = new FormData();
  formData.append("project_id", payload.project_id);
  formData.append("profile_name", payload.profile_name);
  formData.append("sample", payload.file);
  if (payload.tts_provider) {
    formData.append("tts_provider", payload.tts_provider);
  }

  const response = await fetch(`${API_BASE}/voice/clone`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error("Failed to upload voice profile");
  }
  return response.json();
}

export async function fetchVoiceProfiles(
  projectId: string
): Promise<string[]> {
  const response = await fetch(`${API_BASE}/voice/profiles/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load voice profiles");
  }
  const data = await response.json();
  return data.profiles ?? [];
}

export async function deleteVoiceProfile(payload: {
  project_id: string;
  profile_name: string;
}): Promise<boolean> {
  const response = await fetch(
    `${API_BASE}/voice/profiles/${payload.project_id}/${payload.profile_name}`,
    {
      method: "DELETE",
    }
  );
  if (!response.ok) {
    throw new Error("Failed to delete voice profile");
  }
  const data = await response.json();
  return data.deleted ?? false;
}

export type Clip = {
  id: number;
  project_id: string;
  title: string;
  start_time: number;
  end_time: number;
  order_index: number;
  source_url?: string | null;
  notes?: string | null;
  created_at: string;
};

export async function fetchEditorClips(projectId: string): Promise<Clip[]> {
  const response = await fetch(`${API_BASE}/editor/${projectId}/clips`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load clips");
  }
  return response.json();
}

export async function createEditorClip(
  projectId: string,
  payload: {
    title: string;
    start_time: number;
    end_time: number;
    order_index: number;
    source_url?: string | null;
    notes?: string | null;
  }
): Promise<Clip> {
  const response = await fetch(`${API_BASE}/editor/${projectId}/clips`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to create clip");
  }
  return response.json();
}

export async function updateEditorClip(
  projectId: string,
  clipId: number,
  payload: {
    title?: string;
    start_time?: number;
    end_time?: number;
    order_index?: number;
    source_url?: string | null;
    notes?: string | null;
  }
): Promise<Clip> {
  const response = await fetch(`${API_BASE}/editor/${projectId}/clips/${clipId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to update clip");
  }
  return response.json();
}

export async function deleteEditorClip(
  projectId: string,
  clipId: number
): Promise<{ deleted: boolean }> {
  const response = await fetch(`${API_BASE}/editor/${projectId}/clips/${clipId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to delete clip");
  }
  return response.json();
}

export type CreditBalance = {
  email: string;
  plan_name: string;
  status: string;
  credits_balance: number;
  credits_reserved?: number;
  credits_used_total: number;
  renewal_date?: string | null;
};

export type CreditPlan = {
  id: string;
  name: string;
  credits: number;
  price_usd: number;
  popular?: boolean;
  stripe_price_id?: string | null;
  checkout_enabled?: boolean;
};

export async function fetchMyCredits(): Promise<CreditBalance> {
  const response = await fetch(`${API_BASE}/billing/me`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load credits");
  }
  return response.json();
}

export async function fetchCreditPlans(): Promise<{ plans: CreditPlan[] }> {
  const response = await fetch(`${API_BASE}/billing/plans`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Failed to load credit plans");
  }
  return response.json();
}

export async function purchaseCreditsMock(payload: {
  plan_id: string;
}): Promise<CreditBalance> {
  const response = await fetch(`${API_BASE}/billing/purchase/mock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to purchase credits");
  }
  return response.json();
}

export async function createStripeCheckoutSession(payload: {
  plan_id: string;
}): Promise<{ session_id: string; checkout_url: string }> {
  const response = await fetch(`${API_BASE}/billing/purchase/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to start Stripe checkout");
  }
  return response.json();
}

export async function consumeCredits(payload: {
  amount: number;
  reason?: string;
}): Promise<CreditBalance> {
  const response = await fetch(`${API_BASE}/billing/consume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to consume credits");
  }
  return response.json();
}

export async function fetchAdminSubscriptions(): Promise<{ items: CreditBalance[] }> {
  const response = await fetch(`${API_BASE}/billing/admin/users`, {
    cache: "no-store",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to load subscriptions");
  }
  return response.json();
}

export async function updateAdminSubscription(
  email: string,
  payload: {
    plan_name?: string;
    status?: string;
    credits_delta?: number;
    credits_balance?: number;
    renewal_date?: string | null;
  }
): Promise<CreditBalance> {
  const response = await fetch(`${API_BASE}/billing/admin/users/${encodeURIComponent(email)}/update`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...normalizeHeaders(withOwnerDashboardHeaders(undefined)),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to update subscription");
  }
  return response.json();
}

export type Admin2FAStatusResponse = {
  enabled: boolean;
  method: string;
  detail: string;
};

export async function fetchAdmin2FAStatus(): Promise<Admin2FAStatusResponse> {
  const response = await fetch(`${API_BASE}/billing/admin/2fa/status`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to load 2FA status");
  }
  return response.json();
}

export async function verifyAdminAccess(payload: {
  password: string;
  otp_code?: string;
}): Promise<{ access_token: string; expires_in_seconds: number }> {
  const response = await fetch(`${API_BASE}/billing/admin/access/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to verify admin access");
  }
  return response.json();
}
