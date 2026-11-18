import { createServer, type Server } from "node:http";

export interface RecordedRequest {
  headers: Record<string, string | string[] | undefined>;
  body: { problem: { slug: string }; code: string; language: string; level: number };
}

export interface MockApi {
  url: string;
  requests: RecordedRequest[];
  close: () => Promise<void>;
}

/** Tiny stand-in for the Aporia API: streams a canned SSE hint and records requests. */
export async function startMockApi(port: number): Promise<MockApi> {
  const requests: RecordedRequest[] = [];
  const server: Server = createServer((req, res) => {
    if (req.method !== "POST" || req.url !== "/v1/hint") {
      res.writeHead(404).end();
      return;
    }
    let raw = "";
    req.on("data", (c: Buffer) => (raw += c.toString()));
    req.on("end", () => {
      requests.push({ headers: req.headers, body: JSON.parse(raw) });
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      const tokens = ["What ", "happens ", "with ", "one ", "element?"];
      let i = 0;
      const timer = setInterval(() => {
        if (i < tokens.length) {
          res.write(`event: token\ndata: ${JSON.stringify({ text: tokens[i] })}\n\n`);
          i += 1;
        } else {
          clearInterval(timer);
          res.write(
            `event: done\ndata: ${JSON.stringify({ hint_id: "h-1", level: 1, sources: [] })}\n\n`,
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
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}
