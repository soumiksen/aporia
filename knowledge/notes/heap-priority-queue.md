---
slug: heap-priority-queue
concept: heap-priority-queue
reviewed: false
---
## Idea
A priority queue lets you add items and always remove the one with the highest priority. A heap is the usual way to build one. It does not keep everything sorted; it keeps just enough order that the best item is available at the top, and both adding and removing take time logarithmic in the size.

## When it applies
Use it when you repeatedly need the current smallest or largest item while the collection keeps changing: the k largest items of a stream, merging several ordered lists, scheduling the next task, or expanding the cheapest option first in a search. If the data never changes, sorting once is often simpler.

## Common mistakes
- Using a min-heap when a max-heap is needed, or the reverse, and forgetting that some libraries only offer one kind.
- Storing items without the key the heap should order by.
- Keeping a heap of every item when only the best k are needed, wasting time and memory.
- Expecting the heap to be fully sorted when you iterate over its storage.
- Leaving stale entries inside and not deciding how to ignore them.

## Socratic questions
- Which item do you need next, and what makes it the best?
- Do you need the smallest or the largest, and which kind of heap gives it to you directly?
- If you only need the best k, how large does the heap have to be?
- What key orders the items, and how do you break ties?
- Would sorting once be enough, or does the collection change as you go?

## Tiny illustration
You read a long stream of scores and must always know the third highest. Keep a small heap that holds the three largest scores seen, arranged so the smallest of those three sits on top. When a new score exceeds the top, swap it in; otherwise ignore it. The top is always the third highest, and the heap never grows beyond three.

## Related concepts
sorting, shortest-path, greedy
