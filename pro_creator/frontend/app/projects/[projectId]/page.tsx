import Link from "next/link";

import {
  fetchProject,
  fetchProjectScenes,
  fetchProjectScript,
} from "../../../lib/api";
import ScriptActions from "../../../components/ScriptActions";

export const dynamic = "force-dynamic";

export default async function ProjectDetail({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  let project: Awaited<ReturnType<typeof fetchProject>> | null = null;
  let script = "";
  let scenes: Awaited<ReturnType<typeof fetchProjectScenes>> = [];
  try {
    project = await fetchProject(projectId);
    [script, scenes] = await Promise.all([
      fetchProjectScript(projectId),
      fetchProjectScenes(projectId),
    ]);
  } catch {
    project = null;
  }
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE ?? "/api";
  const projectsBase =
    process.env.NEXT_PUBLIC_PROJECTS_BASE ?? `${apiBase}/projects`;
  const projectBase = `${projectsBase}/${projectId}`;
  const downloadsHref = `/?nav=downloads&project=${projectId}`;

  if (!project) {
    return (
      <div className="min-h-screen bg-midnight text-slate-100">
        <header className="border-b border-slate-800 bg-slate-950/70">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
            <div>
              <h1 className="text-3xl font-semibold text-white">
                Project not found
              </h1>
            </div>
            <Link
              className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora"
              href="/"
            >
              Back
            </Link>
          </div>
        </header>
        <main className="mx-auto flex max-w-6xl items-center justify-center px-6 py-16">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-8 text-center">
            <p className="text-sm text-slate-300">Unavailable.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-midnight text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div>
            <h1 className="text-3xl font-semibold text-white">
              {project.title}
            </h1>
          </div>
          <Link
            className="rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-xs font-semibold text-aurora"
            href="/"
          >
            Back
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-6 py-10">
        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
            <h2 className="text-xl font-semibold">Script preview</h2>
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200 whitespace-pre-line">
              {script || "No script yet."}
            </div>
            <ScriptActions projectId={projectId} scriptText={script} />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
            <h2 className="text-xl font-semibold">Download</h2>
            <div className="mt-4">
              <Link
                className="inline-flex rounded-full border border-aurora/40 bg-aurora/10 px-4 py-2 text-sm font-semibold text-aurora"
                href={downloadsHref}
              >
                Download
              </Link>
            </div>
            <div className="mt-6 space-y-4">
              <div>
                <audio
                  className="mt-2 w-full"
                  controls
                  src={`${projectBase}/audio/scene_1.wav`}
                />
              </div>
              <div>
                <img
                  className="mt-2 w-full rounded-xl border border-slate-800"
                  src={`${projectBase}/images/scene_1.png`}
                  alt="Generated scene"
                />
              </div>
              <div>
                <video
                  className="mt-2 w-full rounded-xl border border-slate-800"
                  controls
                  src={`${projectBase}/video/final.mp4`}
                />
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6">
          <h2 className="text-xl font-semibold">Scene preview</h2>
          <div className="mt-4 grid gap-4">
            {scenes.length === 0 ? (
              <p className="text-sm text-slate-400">No scenes.</p>
            ) : (
              scenes.map((scene) => (
                <div
                  key={scene.id}
                  className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs uppercase tracking-wide text-slate-400">
                      Scene {scene.id}
                    </p>
                    <div className="flex gap-2">
                      <span
                        className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wide ${
                          scene.image_path
                            ? "bg-aurora/20 text-aurora"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {scene.image_path ? "Image ready" : "Image missing"}
                      </span>
                      <span
                        className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wide ${
                          scene.audio_path
                            ? "bg-aurora/20 text-aurora"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {scene.audio_path ? "Audio ready" : "Audio missing"}
                      </span>
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-slate-100">{scene.text}</p>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">
                        Image
                      </p>
                      <img
                        className="mt-2 w-full rounded-lg border border-slate-800"
                        src={scene.image_path || `${projectBase}/images/scene_1.png`}
                        alt={`Scene ${scene.id}`}
                      />
                    </div>
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">
                        Audio
                      </p>
                      <audio
                        className="mt-2 w-full"
                        controls
                        src={scene.audio_path || `${projectBase}/audio/scene_1.wav`}
                      />
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
