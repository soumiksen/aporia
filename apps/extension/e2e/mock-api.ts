import { createServer, type Server } from "node:http";

export interface RecordedRequest {
  headers: Record<string, string | string[] | undefined>;
  body: {
    problem: { slug: string };
    code: string;
    language: string;
    level: number;
    student_message: string | null;
    failed_attempts: number;
  };
}

export interface RecordedRating {
  hintId: string;
  rating: number;
  device: string | string[] | undefined;
}

export interface MockApi {
  url: string;
  requests: RecordedRequest[];
  ratings: RecordedRating[];
  events: { device: string | string[] | undefined; events: Record<string, unknown>[] }[];
  close: () => Promise<void>;
}

/** Tiny stand-in for the Aporia API: streams a canned SSE hint and records requests. */
export async function startMockApi(port: number): Promise<MockApi> {
  const requests: RecordedRequest[] = [];
  const ratings: RecordedRating[] = [];
  const events: MockApi["events"] = [];
  const server: Server = createServer((req, res) => {
    if (req.method === "POST" && req.url === "/v1/events") {
      let raw = "";
      req.on("data", (c: Buffer) => (raw += c.toString()));
      req.on("end", () => {
        events.push({ device: req.headers["x-aporia-device"], events: JSON.parse(raw).events });
        res.writeHead(202, { "content-type": "application/json" }).end('{"accepted":1}');
      });
      return;
    }
    const rating = /^\/v1\/hints?\/([^/]+)\/rating$/.exec(req.url ?? "");
    if (req.method === "POST" && rating) {
      let raw = "";
      req.on("data", (c: Buffer) => (raw += c.toString()));
      req.on("end", () => {
        ratings.push({
          hintId: decodeURIComponent(rating[1] ?? ""),
          rating: JSON.parse(raw).rating,
          device: req.headers["x-aporia-device"],
        });
        res.writeHead(204).end();
      });
      return;
    }
    if (req.method !== "POST" || req.url !== "/v1/hint") {
      res.writeHead(404).end();
      return;
    }
    let raw = "";
    req.on("data", (c: Buffer) => (raw += c.toString()));
    req.on("end", () => {
      const body = JSON.parse(raw) as RecordedRequest["body"];
      requests.push({ headers: req.headers, body });
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      // Level-aware canned hint; problems whose slug contains "anagram" are "unsupported".
      const tokens = [`L${body.level}: `, "What ", "happens ", "with ", "one ", "element?"];
      const supported = !body.problem.slug.includes("anagram");
      let i = 0;
      const timer = setInterval(() => {
        if (i < tokens.length) {
          res.write(`event: token\ndata: ${JSON.stringify({ text: tokens[i] })}\n\n`);
          i += 1;
        } else {
          clearInterval(timer);
          res.write(
            `event: done\ndata: ${JSON.stringify({
              hint_id: `h-${requests.length}`,
              level: body.level,
              sources: [],
              supported,
            })}\n\n`,
          );
          res.end();
        }
      }, 30);
      res.on("close", () => clearInterval(timer));
    });
  });
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${port}`,
    requests,
    ratings,
    events,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}
