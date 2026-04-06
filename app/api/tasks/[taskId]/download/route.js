import fs from "node:fs";
import { NextResponse } from "next/server";
import { withErrorBoundary } from "@/src/server/api";
import { requireAuth } from "@/src/server/auth";
import { createTaskArchive } from "@/src/server/tasks";

export async function GET(request, { params }) {
  return withErrorBoundary(async () => {
    requireAuth(request);
    const archivePath = createTaskArchive(Number(params.taskId));
    const data = fs.readFileSync(archivePath);
    return new NextResponse(data, {
      headers: {
        "content-type": "application/zip",
        "content-disposition": `attachment; filename="task-${params.taskId}.zip"`,
      },
    });
  });
}
