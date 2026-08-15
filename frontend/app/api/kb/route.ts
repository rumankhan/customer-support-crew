import { readFile } from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";

/** Mock-only: expose the canonical seed CSV to the browser stub. Not the CrewAI API. */
export async function GET() {
  const filePath = path.join(process.cwd(), "..", "backend", "kb", "articles.csv");
  try {
    const text = await readFile(filePath, "utf8");
    return new NextResponse(text, {
      headers: { "Content-Type": "text/csv; charset=utf-8" },
    });
  } catch {
    return NextResponse.json(
      { error: `Could not read seed KB at ${filePath}` },
      { status: 500 },
    );
  }
}
