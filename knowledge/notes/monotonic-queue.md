---
slug: monotonic-queue
concept: monotonic-queue
reviewed: false
---
## Idea
A monotonic queue is a double-ended queue that keeps its items in sorted order while the front is expired as a window slides forward. The best item for the current window is always at the front, because anything that could never be the best again has already been removed from the back.

## When it applies
Use it when a window moves over a sequence and each step needs the maximum or minimum of the current window. Recomputing from scratch costs the window size each time. The queue lets you answer in constant amortized time by discarding items that are both older and worse than a newer item, since the newer one will outlast them.

## Common mistakes
- Forgetting to remove the front when its position has left the window.
- Storing values instead of positions, which makes expiry impossible to check.
- Removing from the back with a strict comparison when ties should also be removed, or the reverse.
- Reading the answer before the window has reached its full size.
- Using a plain list and paying linear time to remove at the front.

## Socratic questions
- If an older item is worse than a newer one, will the older one ever matter again?
- How will you know when the front item has fallen out of the window?
- What must the queue hold so that expiry can be detected?
- When is the first full window complete, and when may you start recording answers?
- Which end of the queue should be cheap to remove from, and does your structure allow it?

## Tiny illustration
Track the highest reading over every run of three consecutive readings. Keep positions in a queue whose readings decrease from front to back. A new reading first removes any weaker readings from the back, then joins. If the front position is older than the window allows, remove it. The front now names the highest reading in the window. Each position joins once and leaves once.

## Related concepts
sliding-window, monotonic-stack, complexity-analysis
