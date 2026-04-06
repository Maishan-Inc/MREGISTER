import fs from "node:fs";
import { NextResponse } from "next/server";
import { withErrorBoundary } from "@/src/server/api";
import { requireApiKey } from "@/src/server/auth";
import { createTaskArchive } from "@/src/server/tasks";

export async function GET(request, { params }) {
  return withErrorBoundary(async () => {
    requireApiKey(request);
    const archivePath = createTaskArchive(Number(params.taskId));
    const data = fs.readFileSync(archivePath);
    return new NextResponse(data, {
      headers: {
        "content-type": "application/zip",
        "content-disposition": `attachment; filename="api-task-${params.taskId}.zip"`,
      },
    });
  });
}
