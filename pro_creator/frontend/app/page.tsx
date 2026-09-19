import { connection } from "next/server";

import WorkflowHomePage from "./page.workflow";

export default async function HomePage() {
  await connection();
  return <WorkflowHomePage />;
}
