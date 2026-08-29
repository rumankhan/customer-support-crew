import { readFile } from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";

/**
 * FE-epic mock loader only. Live chat uses POST {API}/api/chat; crew kb_search
 * owns retrieval. Do not call this route for answers after Integration.
 */
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
