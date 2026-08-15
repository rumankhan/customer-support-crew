export type KbArticle = {
  id: string;
  title: string;
  body: string;
};

/** Parse RFC4180-style CSV (quoted fields, doubled quotes). */
export function parseKbCsv(text: string): KbArticle[] {
  const rows = parseCsvRows(text.replace(/^\uFEFF/, ""));
  if (rows.length < 2) return [];
  const header = rows[0].map((h) => h.trim().toLowerCase());
  const idIdx = header.indexOf("id");
  const titleIdx = header.indexOf("title");
  const bodyIdx = header.indexOf("body");
  if (idIdx < 0 || titleIdx < 0 || bodyIdx < 0) {
    throw new Error("KB CSV must have id,title,body columns");
  }
  const articles: KbArticle[] = [];
  for (const row of rows.slice(1)) {
    if (row.every((cell) => cell.trim() === "")) continue;
    const id = row[idIdx]?.trim() ?? "";
    const title = row[titleIdx]?.trim() ?? "";
    const body = row[bodyIdx]?.trim() ?? "";
    if (!id || !title || !body) continue;
    articles.push({ id, title, body });
  }
  return articles;
}

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next = text[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

let cachedArticles: KbArticle[] | null = null;
let loadPromise: Promise<KbArticle[]> | null = null;

export function getKbArticles(): KbArticle[] {
  return cachedArticles ?? [];
}

export async function loadKbArticles(): Promise<KbArticle[]> {
  if (cachedArticles) return cachedArticles;
  if (!loadPromise) {
    loadPromise = fetch("/api/kb")
      .then(async (res) => {
        if (!res.ok) throw new Error(`KB CSV fetch failed: ${res.status}`);
        return parseKbCsv(await res.text());
      })
      .then((articles) => {
        cachedArticles = articles;
        return articles;
      })
      .finally(() => {
        loadPromise = null;
      });
  }
  return loadPromise;
}

const STOP = new Set([
  "the",
  "and",
  "for",
  "how",
  "do",
  "does",
  "what",
  "your",
  "you",
  "are",
  "can",
  "i",
  "my",
  "a",
  "an",
  "to",
  "of",
  "in",
  "on",
  "is",
  "or",
]);

export const KB_SIMILARITY_FLOOR = 0.35;

function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1 && !STOP.has(w));
}

function overlapScore(query: string, article: KbArticle): number {
  const q = [...new Set(tokens(query))];
  if (q.length === 0) return 0;
  const doc = new Set(tokens(`${article.title} ${article.body}`));
  const hits = q.filter((t) => doc.has(t)).length;
  return hits / q.length;
}

export type KbHit = {
  article: KbArticle;
  score: number;
  snippet: string;
};

export function searchKb(query: string, articles = getKbArticles()): KbHit | null {
  let best: KbHit | null = null;
  for (const article of articles) {
    const score = overlapScore(query, article);
    if (score < KB_SIMILARITY_FLOOR) continue;
    if (!best || score > best.score) {
      const snippet =
        article.body.length > 160 ? `${article.body.slice(0, 157)}…` : article.body;
      best = { article, score, snippet };
    }
  }
  return best;
}
