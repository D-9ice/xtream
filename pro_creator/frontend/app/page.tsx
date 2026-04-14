"use client";

import { Suspense } from "react";

import WorkflowHomePage from "./page.workflow";

export default function HomePage() {
  return (
    <Suspense fallback={<div className="p-6 text-slate-400">Loading...</div>}>
      <WorkflowHomePage />
    </Suspense>
  );
}
