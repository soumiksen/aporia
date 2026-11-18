import { createParser } from "eventsource-parser";
import { hintEventSchema, type HintEvent, type HintRequest } from "./messages";

export interface StreamHintOptions {
  apiUrl: string;
  deviceId: string;
  request: HintRequest;
  signal?: AbortSignal;
  fetchFn?: typeof fetch;
  onEvent: (event: HintEvent) => void;
}

const HTTP_MESSAGES: Record<number, string> = {
  400: "The request was rejected by the server.",
  413: "Your code or the problem text is too long to send.",
  429: "Too many hint requests. Please wait a minute and try again.",
};

/**
 * POSTs a hint request and relays parsed SSE events. Never throws: failures (network, non-200,
 * truncated stream, malformed events) become a typed `error` event. Abort is silent.
 * Student code is never logged.
 */
export async function streamHint(opts: StreamHintOptions): Promise<void> {
  const { apiUrl, deviceId, request, signal, onEvent } = opts;
  const fetchFn = opts.fetchFn ?? fetch;
  let terminal = false;
  const emit = (event: HintEvent) => {
    if (event.event === "done" || event.event === "error") terminal = true;
    onEvent(event);
  };

  try {
    const res = await fetchFn(`${apiUrl}/v1/hint`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
        "x-aporia-device": deviceId,
      },
      body: JSON.stringify(request),
      signal,
    });
    if (!res.ok) {
      emit({
        event: "error",
        code: `http_${res.status}`,
        message: HTTP_MESSAGES[res.status] ?? `The server returned an error (${res.status}).`,
      });
      return;
    }
    if (!res.body) {
      emit({ event: "error", code: "no_body", message: "The server sent an empty response." });
      return;
    }

    const parser = createParser({
      onEvent(message) {
        try {
          const data: unknown = JSON.parse(message.data);
          const parsed = hintEventSchema.safeParse({
            event: message.event ?? "message",
            ...(typeof data === "object" && data !== null ? data : {}),
          });
          if (parsed.success) emit(parsed.data);
        } catch {
          /* ignore malformed event */
        }
      },
    });

    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(value);
    }
    if (!terminal) {
      emit({
        event: "error",
        code: "stream_ended",
        message: "The hint stream ended unexpectedly.",
      });
    }
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
    emit({
      event: "error",
      code: "network",
      message: "Could not reach the Aporia server. Is it running?",
    });
  }
}
