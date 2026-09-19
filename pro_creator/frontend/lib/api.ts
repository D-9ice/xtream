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

export type CharacterVoiceProfile = {
  character_id: string;
  display_name: string;
  voice_profile: string;
  voice_id?: string | null;
};

export type DialogueLine = {
  speaker_id: string;
  text: string;
  pause_ms?: number;
  voice_profile?: string;
  voice_id?: string;
};

export type DialogueSceneRequest = {
  scene_id: number;
  lines: DialogueLine[];
};

export type DialogueRenderResponse = {
  scenes: Array<{
    scene_id: number;
    audio_path: string;
    line_count: number;
  }>;
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
  process.env.NEXT_PUBLIC_API_BASE ?? "/api";

type FetchInput = Parameters<typeof globalThis.fetch>[0];
type FetchInit = Parameters<typeof globalThis.fetch>[1];
type FetchHeaders = Record<string, string> | [string, string][] | Headers;

const migrateAdminTokenToSessionStorage = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  const sessionToken = window.sessionStorage.getItem("pc_admin_access_token");
  if (sessionToken) {
    return sessionToken;
  }
  const legacyToken = window.localStorage.getItem("pc_admin_access_token");
  if (legacyToken) {
    window.sessionStorage.setItem("pc_admin_access_token", legacyToken);
    window.localStorage.removeItem("pc_admin_access_token");
    return legacyToken;
  }
  return null;
};

const getAuthToken = (): string | null => {
  if (typeof window !== "undefined") {
    // The normal API bearer token and the privileged admin-dashboard token are
    // intentionally separate credentials. Never send pc_admin_access_token as
    // Authorization: Bearer for user/workflow APIs.
    return window.localStorage.getItem("pc_token");
  }
  return process.env.NEXT_PUBLIC_API_TOKEN ?? null;
};

const getAdminAccessToken = (): string | null => {
  if (typeof window !== "undefined") {
    return migrateAdminTokenToSessionStorage();
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

export type VisitAnalyticsTopPath = {
  path: string;
  visits: number;
  human_visits: number;
  bot_visits: number;
};

export type VisitAnalyticsBreakdown = {
  label: string;
  visits: number;
  human_visits: number;
  bot_visits: number;
};

export type VisitAnalyticsDailyPoint = {
  day: string;
  visits: number;
  human_visits: number;
  bot_visits: number;
};

export type VisitEvent = {
  visit_id: string;
  path: string;
  referrer?: string | null;
  device_type?: string | null;
  country_code?: string | null;
  page_title?: string | null;
  session_id?: string | null;
  event_type: string;
  is_bot: boolean;
  bot_reason?: string | null;
  created_at: string;
};

export type VisitAnalyticsSummary = {
  total_visits: number;
  human_visits: number;
  bot_visits: number;
  unique_sessions: number;
  unique_paths: number;
  visits_last_24h: number;
  visits_last_7d: number;
  top_paths: VisitAnalyticsTopPath[];
  top_devices: VisitAnalyticsBreakdown[];
  top_countries: VisitAnalyticsBreakdown[];
  recent_visits: VisitEvent[];
  daily_visits: VisitAnalyticsDailyPoint[];
};

export type AutoCreateCharacterInput = {
  name: string;
  role_type: string;
  description?: string;
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
const fetchWithAuth = async (
  input: FetchInput,
  init: FetchInit = {}
): Promise<Response> => {
  const response = await baseFetch(input, {
    ...init,
    headers: withAuthHeaders(init?.headers),
  });
  if (
    response.status === 401 &&
    typeof window !== "undefined" &&
    !window.localStorage.getItem("pc_token")
  ) {
    window.dispatchEvent(new CustomEvent("procreator:subscription-required"));
  }
  return response;
};

const fetch: FetchType = fetchWithAuth as FetchType;

const throwApiError = async (
  response: Response,
  fallback: string
): Promise<never> => {
  const detail = await response.json().catch(() => null);
  if (
    response.status === 401 &&
    typeof window !== "undefined" &&
    !window.localStorage.getItem("pc_token")
  ) {
    throw new Error("Subscribe or sign in to use this feature.");
  }
  const message =
    detail?.detail ??
    (Array.isArray(detail) ? detail?.[0]?.msg : null) ??
    fallback;
  throw new Error(message);
};

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

export type OrchestrationRunnerStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  detail?: string | null;
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
  genre?: string;
  duration_minutes?: number;
  tone?: string;
  voice_text?: string;
  image_prompt?: string;
  export_preset?: string;
  titles?: string[];
  short_description?: string;
  start_credits?: string;
  end_credits?: string;
  publish_message?: string;
}): Promise<OrchestrationQueueItem> {
  const response = await fetch(`${API_BASE}/orchestration/queue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to enqueue job");
  }
  return response.json();
}

export async function enqueueOrchestrationBatch(payload: {
  items: {
    project_id: string;
    kind: string;
    topic?: string;
    genre?: string;
    duration_minutes?: number;
    tone?: string;
    voice_text?: string;
    image_prompt?: string;
    export_preset?: string;
    titles?: string[];
    short_description?: string;
    start_credits?: string;
    end_credits?: string;
    publish_message?: string;
  }[];
}): Promise<{ items: OrchestrationQueueItem[] }> {
  const response = await fetch(`${API_BASE}/orchestration/queue/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to enqueue batch");
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
    await throwApiError(response, "Failed to process queue");
  }
  return response.json();
}

export async function retryOrchestrationJob(jobId: number): Promise<OrchestrationQueueItem> {
  const response = await fetch(`${API_BASE}/orchestration/queue/${jobId}/retry`, {
    method: "POST",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to retry job");
  }
  return response.json();
}

export async function startOrchestrationRunner(payload?: {
  interval_seconds?: number;
}): Promise<OrchestrationRunnerStatus> {
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
    await throwApiError(response, "Failed to start runner");
  }
  return response.json();
}

export async function stopOrchestrationRunner(): Promise<OrchestrationRunnerStatus> {
  const response = await fetch(`${API_BASE}/orchestration/queue/runner/stop`, {
    method: "POST",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to stop runner");
  }
  return response.json();
}

export async function fetchOrchestrationRunnerStatus(): Promise<OrchestrationRunnerStatus> {
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
    await throwApiError(response, "Failed to create schedule");
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
    await throwApiError(response, "Failed to run schedules");
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
  genre?: string;
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

export async function listCharacterVoiceProfiles(
  projectId: string
): Promise<CharacterVoiceProfile[]> {
  const response = await fetch(`${API_BASE}/voice/characters/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load character voice profiles");
  }
  const payload = await response.json();
  return payload.characters ?? [];
}

export async function upsertCharacterVoiceProfile(
  projectId: string,
  payload: CharacterVoiceProfile
): Promise<CharacterVoiceProfile[]> {
  const response = await fetch(`${API_BASE}/voice/characters/${projectId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to save character profile");
  }
  const body = await response.json();
  return body.characters ?? [];
}

export async function deleteCharacterVoiceProfile(
  projectId: string,
  characterId: string
): Promise<CharacterVoiceProfile[]> {
  const response = await fetch(
    `${API_BASE}/voice/characters/${projectId}/${encodeURIComponent(characterId)}`,
    {
      method: "DELETE",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to delete character profile");
  }
  const body = await response.json();
  return body.characters ?? [];
}

export async function renderDialogue(payload: {
  project_id: string;
  scenes: DialogueSceneRequest[];
  write_scene_audio_paths?: boolean;
}): Promise<DialogueRenderResponse> {
  const response = await fetch(`${API_BASE}/voice/dialogue/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to render dialogue");
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
    await throwApiError(response, "Failed to generate image");
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
    await throwApiError(response, "Failed to render video");
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
    await throwApiError(response, "Failed to import video");
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
    await throwApiError(response, "Failed to run feature");
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
    await throwApiError(response, "Failed to export preset");
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
    await throwApiError(response, "Failed to export batch");
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

export type SocialAccountConnection = {
  connection_id: string;
  platform: "youtube" | "instagram" | "facebook" | "x" | "tiktok" | string;
  account_label: string;
  account_identifier?: string | null;
  scopes?: string[];
  metadata?: Record<string, string>;
  enabled: boolean;
  token_expires_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type SocialOAuthStartResponse = {
  authorization_url: string;
  state: string;
};

export type SocialOAuthCompletePayload = {
  platform: SocialAccountConnection["platform"];
  state: string;
  code?: string | null;
  oauth_token?: string | null;
  oauth_verifier?: string | null;
};

export type SocialPublishJob = {
  job_id: string;
  project_id: string;
  connection_id: string;
  platform: string;
  status: string;
  remote_post_id?: string | null;
  published_url?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
};

export async function beginSocialOAuth(
  platform: SocialAccountConnection["platform"]
): Promise<SocialOAuthStartResponse> {
  const response = await fetch(`${API_BASE}/social/oauth/${encodeURIComponent(platform)}/start`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to start social account authorization");
  }
  return response.json();
}

export async function completeSocialOAuth(
  payload: SocialOAuthCompletePayload
): Promise<SocialAccountConnection> {
  const response = await fetch(`${API_BASE}/social/oauth/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to complete social account authorization");
  }
  return response.json();
}

export async function fetchSocialConnections(): Promise<{ items: SocialAccountConnection[] }> {
  const response = await fetch(`${API_BASE}/social/connections`, { cache: "no-store" });
  if (!response.ok) {
    await throwApiError(response, "Failed to load social connections");
  }
  return response.json();
}

export async function fetchAdminSocialConnections(): Promise<{ items: SocialAccountConnection[] }> {
  const response = await fetch(`${API_BASE}/social/admin/connections`, {
    cache: "no-store",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load admin social connections");
  }
  return response.json();
}

export async function saveSocialConnection(payload: {
  connection_id?: string | null;
  platform: SocialAccountConnection["platform"];
  account_label: string;
  account_identifier?: string | null;
  access_token?: string | null;
  access_token_secret?: string | null;
  refresh_token?: string | null;
  client_key?: string | null;
  client_secret?: string | null;
  token_expires_at?: string | null;
  scopes?: string[];
  metadata?: Record<string, string>;
  enabled?: boolean;
}): Promise<SocialAccountConnection> {
  const response = await fetch(`${API_BASE}/social/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to save social connection");
  }
  return response.json();
}

export async function saveAdminSocialConnection(payload: {
  connection_id?: string | null;
  platform: SocialAccountConnection["platform"];
  account_label: string;
  account_identifier?: string | null;
  access_token?: string | null;
  access_token_secret?: string | null;
  refresh_token?: string | null;
  client_key?: string | null;
  client_secret?: string | null;
  token_expires_at?: string | null;
  scopes?: string[];
  metadata?: Record<string, string>;
  enabled?: boolean;
}): Promise<SocialAccountConnection> {
  const response = await fetch(`${API_BASE}/social/admin/connections`, {
    method: "POST",
    headers: withOwnerDashboardHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to save admin social connection");
  }
  return response.json();
}

export async function deleteSocialConnection(connectionId: string): Promise<{ deleted: boolean }> {
  const response = await fetch(`${API_BASE}/social/connections/${encodeURIComponent(connectionId)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to delete social connection");
  }
  return response.json();
}

export async function deleteAdminSocialConnection(connectionId: string): Promise<{ deleted: boolean }> {
  const response = await fetch(`${API_BASE}/social/admin/connections/${encodeURIComponent(connectionId)}`, {
    method: "DELETE",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to delete admin social connection");
  }
  return response.json();
}

export async function fetchSocialPublishJobs(payload?: {
  project_id?: string | null;
}): Promise<{ items: SocialPublishJob[] }> {
  const params = payload?.project_id ? `?project_id=${encodeURIComponent(payload.project_id)}` : "";
  const response = await fetch(`${API_BASE}/social/publish/jobs${params}`, { cache: "no-store" });
  if (!response.ok) {
    await throwApiError(response, "Failed to load publish jobs");
  }
  return response.json();
}

export async function publishSocialVideos(payload: {
  project_id: string;
  connection_ids?: string[];
  message?: string | null;
  title?: string | null;
}): Promise<{ items: SocialPublishJob[] }> {
  const response = await fetch(`${API_BASE}/social/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to publish to social accounts");
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
}): Promise<{ profile_path: string }> {
  const formData = new FormData();
  formData.append("project_id", payload.project_id);
  formData.append("profile_name", payload.profile_name);
  formData.append("sample", payload.file);

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

export type CharacterSlotSummary = {
  base_slots: number;
  extra_slots: number;
  total_slots: number;
  used_slots: number;
  remaining_slots: number;
  addon_pack_size: number;
  addon_pack_cost_credits: number;
  is_full: boolean;
};

export type CreditBalance = {
  email: string;
  plan_name: string;
  status: string;
  credits_balance: number;
  credits_reserved?: number;
  credits_used_total: number;
  renewal_date?: string | null;
  extra_character_slots?: number;
  owner_mode_enabled?: boolean;
  factory_mode_status?: string;
  factory_mode_access?: string;
  factory_mode_renewal_date?: string | null;
  factory_mode_purchased_at?: string | null;
  character_slots: CharacterSlotSummary;
};

export type CreditPlan = {
  id: string;
  name: string;
  kind?: "credits" | "factory_access" | string;
  credits: number;
  price_usd: number;
  base_character_slots: number;
  popular?: boolean;
  stripe_price_id?: string | null;
  checkout_providers?: Array<"stripe" | "paystack">;
  checkout_enabled?: boolean;
  access_mode?: "one_time" | "subscription" | string | null;
  access_days?: number | null;
  description?: string | null;
};

export type BillingReceipt = {
  receipt_id: number;
  created_at: string;
  kind: string;
  action?: string | null;
  amount: number;
  reason?: string | null;
  reference_id?: string | null;
  provider?: string | null;
  balance_after: number;
  reserved_after: number;
  plan_id?: string | null;
  plan_kind?: string | null;
  access_mode?: string | null;
  purchase_label?: string | null;
  metadata: Record<string, unknown>;
};

export type BillingTransactionRecord = {
  record_id: number;
  created_at: string;
  kind: string;
  action?: string | null;
  amount: number;
  reason?: string | null;
  reference_id?: string | null;
  provider?: string | null;
  balance_after: number;
  reserved_after: number;
  metadata: Record<string, unknown>;
};

export type BillingPricingSettings = {
  plans: CreditPlan[];
  owner_mode_enabled: boolean;
  receipts_live_mode: boolean;
  free_base_character_slots: number;
  character_slot_addon_size: number;
  character_slot_addon_cost_credits: number;
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

export async function fetchBillingReceipts(limit = 10): Promise<{ items: BillingReceipt[] }> {
  const response = await fetch(`${API_BASE}/billing/receipts?limit=${encodeURIComponent(limit)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load billing receipts");
  }
  return response.json();
}

export async function fetchBillingTransactionRecords(limit = 50): Promise<{ items: BillingTransactionRecord[] }> {
  const response = await fetch(`${API_BASE}/billing/records?limit=${encodeURIComponent(limit)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to load billing transaction records");
  }
  return response.json();
}

export async function clearBillingTransactionRecords(): Promise<{
  deleted: boolean;
  deleted_count: number;
  deleted_ids: number[];
}> {
  const response = await fetch(`${API_BASE}/billing/records`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to clear transaction records");
  }
  return response.json();
}

export async function deleteBillingReceipt(receiptId: number): Promise<{
  deleted: boolean;
  receipt_id: number;
  deleted_permanently: boolean;
}> {
  const response = await fetch(`${API_BASE}/billing/receipts/${encodeURIComponent(receiptId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to delete receipt");
  }
  return response.json();
}

export async function createStripeCheckoutSession(payload: {
  plan_id: string;
  provider?: "stripe" | "paystack";
}): Promise<{ provider: string; session_id: string; checkout_url: string }> {
  const response = await fetch(`${API_BASE}/billing/purchase/checkout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to start checkout");
  }
  return response.json();
}

export async function recordAnalyticsVisit(payload: {
  path: string;
  referrer?: string | null;
  user_agent?: string | null;
  device_hint?: string | null;
  country_hint?: string | null;
  page_title?: string | null;
  session_id?: string | null;
  event_type?: string;
  bot_hint?: boolean;
}): Promise<VisitEvent> {
  const response = await fetch(`${API_BASE}/analytics/visits`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to record visit");
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
    factory_mode_access?: "none" | "one_time" | "subscription" | string | null;
    factory_mode_renewal_date?: string | null;
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

export async function deleteAdminUser(email: string): Promise<{ deleted: boolean; email: string }> {
  const response = await fetch(`${API_BASE}/billing/admin/users/${encodeURIComponent(email)}`, {
    method: "DELETE",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to delete user");
  }
  return response.json();
}

export async function clearAdminTestPurchases(): Promise<{
  deleted_count: number;
  deleted_emails: string[];
}> {
  const response = await fetch(`${API_BASE}/billing/admin/users/actions/purge-test-purchases`, {
    method: "DELETE",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to clear test purchases");
  }
  return response.json();
}

export async function fetchAdminBillingPricing(): Promise<BillingPricingSettings> {
  const response = await fetch(`${API_BASE}/billing/admin/pricing`, {
    cache: "no-store",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to load billing pricing");
  }
  return response.json();
}

export async function fetchAdminVisitAnalyticsSummary(days = 30): Promise<VisitAnalyticsSummary> {
  const response = await fetch(`${API_BASE}/analytics/summary?days=${encodeURIComponent(days)}`, {
    cache: "no-store",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load visit analytics");
  }
  return response.json();
}

export async function resetAdminVisitAnalytics(): Promise<{
  deleted: boolean;
  deleted_count: number;
}> {
  const response = await fetch(`${API_BASE}/analytics/visits`, {
    method: "DELETE",
    headers: withOwnerDashboardHeaders(undefined),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to reset visitor analytics");
  }
  return response.json();
}

export async function updateAdminBillingPricing(payload: {
  moderate_credits: number;
  moderate_price_usd: number;
  moderate_base_character_slots: number;
  moderate_stripe_price_id?: string | null;
  pro_credits: number;
  pro_price_usd: number;
  pro_base_character_slots: number;
  pro_stripe_price_id?: string | null;
  studio_credits: number;
  studio_price_usd: number;
  studio_base_character_slots: number;
  studio_stripe_price_id?: string | null;
  factory_one_time_price_usd: number;
  factory_one_time_stripe_price_id?: string | null;
  factory_subscription_price_usd: number;
  factory_subscription_stripe_price_id?: string | null;
  owner_mode_enabled: boolean;
  receipts_live_mode: boolean;
  free_base_character_slots: number;
  character_slot_addon_size: number;
  character_slot_addon_cost_credits: number;
}): Promise<BillingPricingSettings> {
  const response = await fetch(`${API_BASE}/billing/admin/pricing`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...normalizeHeaders(withOwnerDashboardHeaders(undefined)),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to update billing pricing");
  }
  return response.json();
}

export async function purchaseCharacterSlotPack(payload?: {
  pack_count?: number;
}): Promise<CreditBalance> {
  const response = await fetch(`${API_BASE}/billing/character-slots/purchase`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pack_count: payload?.pack_count ?? 1 }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to buy more character slots");
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

export type WorkflowState =
  | "draft"
  | "script_generating"
  | "script_generated"
  | "script_approved"
  | "characters_in_progress"
  | "characters_approved"
  | "production_ready"
  | "production_queued"
  | "production_running"
  | "video_completed"
  | "production_failed";

export type WorkflowProject = {
  project_id: string;
  title: string;
  topic: string;
  status: string;
  idea_prompt?: string | null;
  short_description?: string | null;
  genre?: string | null;
  target_duration_minutes?: number | null;
  start_credits?: string | null;
  end_credits?: string | null;
  workflow_state: WorkflowState;
  script_draft?: string | null;
  script_approved?: string | null;
  script_approved_at?: string | null;
  character_package_approved: boolean;
  character_package_approved_at?: string | null;
  selected_character_ids: string[];
  production_job_id?: string | null;
  final_video_url?: string | null;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowCharacter = {
  character_id: string;
  name: string;
  role_type: string;
  description: string;
  visual_prompt_base: string;
  negative_prompt_base: string;
  consistency_seed: string;
  identity_hash: string;
  lock_identity: boolean;
  reference_image_url?: string | null;
  reference_image_urls: string[];
  canonical_image_url?: string | null;
  personality_traits: string[];
  voice_profile?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowCharacterList = {
  library: WorkflowCharacter[];
  selected_character_ids: string[];
  selected: WorkflowCharacter[];
  approved_character_ids: string[];
  approved_at?: string | null;
};

export type WorkflowProductionSummary = {
  project_id: string;
  workflow_state: WorkflowState;
  script_ready: boolean;
  characters_ready: boolean;
  estimated_credits: number;
  current_credit_balance: number;
  target_duration_minutes: number;
  selected_characters: WorkflowCharacter[];
  final_video_url?: string | null;
};

export type WorkflowProductionStatus = {
  project_id: string;
  workflow_state: WorkflowState;
  production_job_id?: string | null;
  queue_status?: string | null;
  queue_attempts: number;
  queue_max_attempts: number;
  last_error?: string | null;
  can_retry: boolean;
  final_video_url?: string | null;
};

export type WorkflowLibrary = {
  characters: WorkflowCharacter[];
  scripts: WorkflowProject[];
  videos: WorkflowProject[];
};

export type CommunityPost = {
  post_id: string;
  subject: string;
  message: string;
  author_label: string;
  author_email: string;
  applause_count: number;
  created_at: string;
};

export type CommunityPostListResponse = {
  items: CommunityPost[];
};

export type WorkflowFeedbackResponse = {
  feedback_id: string;
  subject: string;
  page?: string | null;
  project_id?: string | null;
  email_sent: boolean;
  created_at: string;
};

export type CommunityPostResponse = CommunityPost;

export async function fetchCommunityPosts(): Promise<CommunityPostListResponse> {
  const response = await fetch(`${API_BASE}/community/posts`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load community posts");
  }
  return response.json();
}

export async function createCommunityPost(payload: {
  subject: string;
  message: string;
}): Promise<CommunityPostResponse> {
  const response = await fetch(`${API_BASE}/community/posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to create community post");
  }
  return response.json();
}

export async function applaudCommunityPost(postId: string): Promise<CommunityPostResponse> {
  const response = await fetch(`${API_BASE}/community/posts/${postId}/applaud`, {
    method: "POST",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to applaud community post");
  }
  return response.json();
}

export async function submitWorkflowFeedback(payload: {
  subject: string;
  message: string;
  page?: string | null;
  project_id?: string | null;
}): Promise<WorkflowFeedbackResponse> {
  const response = await fetch(`${API_BASE}/workflow/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to submit workflow feedback");
  }
  return response.json();
}

export async function fetchWorkflowProjects(): Promise<WorkflowProject[]> {
  const response = await fetch(`${API_BASE}/workflow/projects`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load workflow projects");
  }
  return response.json();
}

export async function deleteWorkflowProjects(): Promise<{
  deleted_count: number;
  deleted_ids: string[];
}> {
  const response = await fetch(`${API_BASE}/workflow/projects`, {
    method: "DELETE",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to delete workflow projects");
  }
  return response.json();
}

export async function createWorkflowProject(payload: {
  title: string;
  idea_prompt?: string;
  genre?: string;
  target_duration_minutes?: number;
}): Promise<WorkflowProject> {
  const response = await fetch(`${API_BASE}/workflow/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to create workflow project");
  }
  return response.json();
}

export async function autoCreateWorkflowProject(payload: {
  title: string;
  duration_minutes?: number;
  genre?: string;
  short_description?: string;
  start_credits?: string;
  end_credits?: string;
  custom_characters?: AutoCreateCharacterInput[];
}): Promise<{
  project: WorkflowProject;
  status: WorkflowProductionStatus;
  video_path?: string | null;
  requested_duration_minutes: number;
  applied_duration_minutes: number;
  max_affordable_duration_minutes: number;
  estimated_credits: number;
}> {
  const response = await fetch(`${API_BASE}/workflow/auto-create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to auto-create workflow project");
  }
  return response.json();
}

export async function fetchWorkflowProject(
  projectId: string
): Promise<WorkflowProject> {
  const response = await fetch(`${API_BASE}/workflow/projects/${projectId}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load workflow project");
  }
  return response.json();
}

export async function updateWorkflowProject(
  projectId: string,
  payload: {
    title?: string;
    idea_prompt?: string;
    genre?: string;
    target_duration_minutes?: number;
  }
): Promise<WorkflowProject> {
  const response = await fetch(`${API_BASE}/workflow/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to update workflow project");
  }
  return response.json();
}

export async function archiveWorkflowProject(
  projectId: string
): Promise<WorkflowProject> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/archive`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to archive workflow project");
  }
  return response.json();
}

export async function duplicateWorkflowProject(
  projectId: string
): Promise<WorkflowProject> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/duplicate`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to duplicate workflow project");
  }
  return response.json();
}

export async function generateWorkflowScript(
  projectId: string,
  payload: {
    title: string;
    idea_prompt?: string;
    genre?: string;
    target_duration_minutes?: number;
    tone?: string;
  }
): Promise<WorkflowProject> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/generate-script`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to generate workflow script");
  }
  return response.json();
}

export async function approveWorkflowScript(
  projectId: string
): Promise<WorkflowProject> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/approve-script`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to approve script");
  }
  return response.json();
}

export async function regenerateWorkflowScript(
  projectId: string,
  payload: {
    title: string;
    idea_prompt?: string;
    genre?: string;
    target_duration_minutes?: number;
    tone?: string;
  }
): Promise<WorkflowProject> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/regenerate-script`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to regenerate script");
  }
  return response.json();
}

export async function updateWorkflowScript(
  projectId: string,
  payload: { script: string; update_scenes?: boolean }
): Promise<WorkflowProject> {
  const response = await fetch(`${API_BASE}/workflow/projects/${projectId}/script`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to update script");
  }
  return response.json();
}

export async function fetchWorkflowCharacters(
  projectId: string
): Promise<WorkflowCharacterList> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/characters`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to load characters");
  }
  return response.json();
}

export async function selectWorkflowCharacters(
  projectId: string,
  selected_character_ids: string[]
): Promise<WorkflowCharacterList> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/characters/select`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_character_ids }),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to update character selection");
  }
  return response.json();
}

export async function createWorkflowCharacter(
  projectId: string,
  payload: {
    name: string;
    role_type?: string;
    description: string;
    visual_prompt_base?: string;
    negative_prompt_base?: string;
    personality_traits?: string[];
    voice_profile?: string;
    reference_image_url?: string;
    reference_image_urls?: string[];
    canonical_image_url?: string;
    lock_identity?: boolean;
    select_after_create?: boolean;
  }
): Promise<WorkflowCharacterList> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/characters/create`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to create character");
  }
  return response.json();
}

export async function generateWorkflowCharacter(
  projectId: string,
  payload: {
    name: string;
    role_type?: string;
    description: string;
    personality_traits?: string[];
    voice_profile?: string;
    style?: string;
    lock_identity?: boolean;
    select_after_create?: boolean;
  }
): Promise<WorkflowCharacterList> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/characters/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to generate character");
  }
  return response.json();
}

export async function uploadWorkflowCharacter(
  projectId: string,
  payload: {
    file: File;
    name: string;
    role_type?: string;
    description?: string;
    voice_profile?: string;
    lock_identity?: boolean;
    select_after_create?: boolean;
  }
): Promise<WorkflowCharacterList> {
  const formData = new FormData();
  formData.append("reference", payload.file);
  formData.append("name", payload.name);
  formData.append("role_type", payload.role_type ?? "supporting");
  formData.append("description", payload.description ?? "");
  formData.append("voice_profile", payload.voice_profile ?? "");
  formData.append("lock_identity", String(payload.lock_identity ?? true));
  formData.append(
    "select_after_create",
    String(payload.select_after_create ?? true)
  );

  const response = await fetch(`${API_BASE}/workflow/projects/${projectId}/characters/upload`, {
    method: "POST",
    body: formData,
    headers: withAuthHeaders(),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to upload character reference");
  }
  return response.json();
}

export async function createLibraryCharacter(
  payload: {
    name: string;
    role_type?: string;
    description: string;
    visual_prompt_base?: string;
    negative_prompt_base?: string;
    personality_traits?: string[];
    voice_profile?: string;
    reference_image_url?: string;
    reference_image_urls?: string[];
    canonical_image_url?: string;
    lock_identity?: boolean;
  }
): Promise<WorkflowLibrary> {
  const response = await fetch(`${API_BASE}/workflow/characters/create`, {
    method: "POST",
    headers: withAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to save character profile");
  }
  return response.json();
}

export async function generateLibraryCharacter(
  payload: {
    name: string;
    role_type?: string;
    description: string;
    personality_traits?: string[];
    voice_profile?: string;
    style?: string;
    lock_identity?: boolean;
  }
): Promise<WorkflowLibrary> {
  const response = await fetch(`${API_BASE}/workflow/characters/generate`, {
    method: "POST",
    headers: withAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to generate character");
  }
  return response.json();
}

export async function uploadLibraryCharacter(
  payload: {
    file: File;
    name: string;
    role_type?: string;
    description?: string;
    voice_profile?: string;
    lock_identity?: boolean;
  }
): Promise<WorkflowLibrary> {
  const formData = new FormData();
  formData.append("reference", payload.file);
  formData.append("name", payload.name);
  formData.append("role_type", payload.role_type ?? "supporting");
  formData.append("description", payload.description ?? "");
  formData.append("voice_profile", payload.voice_profile ?? "");
  formData.append("lock_identity", String(payload.lock_identity ?? true));
  const response = await fetch(`${API_BASE}/workflow/characters/upload`, {
    method: "POST",
    headers: withAuthHeaders(),
    body: formData,
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to upload character profile");
  }
  return response.json();
}

export async function approveWorkflowCharacters(
  projectId: string,
  selected_character_ids: string[]
): Promise<WorkflowCharacterList> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/approve-characters`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected_character_ids }),
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to approve characters");
  }
  return response.json();
}

export async function fetchWorkflowProductionSummary(
  projectId: string
): Promise<WorkflowProductionSummary> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/production-summary`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to load production summary");
  }
  return response.json();
}

export async function startWorkflowProduction(
  projectId: string
): Promise<{
  project: WorkflowProject;
  status: WorkflowProductionStatus;
  video_path?: string | null;
}> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/start-production`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to start video production");
  }
  return response.json();
}

export async function fetchWorkflowProductionStatus(
  projectId: string
): Promise<WorkflowProductionStatus> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/production-status`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to load production status");
  }
  return response.json();
}

export async function retryWorkflowProduction(
  projectId: string
): Promise<WorkflowProductionStatus> {
  const response = await fetch(
    `${API_BASE}/workflow/projects/${projectId}/retry-production`,
    {
      method: "POST",
    }
  );
  if (!response.ok) {
    await throwApiError(response, "Failed to retry video production");
  }
  return response.json();
}

export async function fetchWorkflowLibrary(): Promise<WorkflowLibrary> {
  const response = await fetch(`${API_BASE}/workflow/library`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await throwApiError(response, "Failed to load workflow library");
  }
  return response.json();
}
