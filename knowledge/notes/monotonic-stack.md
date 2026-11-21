---
slug: monotonic-stack
concept: monotonic-stack
reviewed: false
---
## Idea
A monotonic stack is a stack whose contents are kept in sorted order, either increasing or decreasing, by removing items that would break the order before adding a new one. Items waiting on the stack are those whose question has not yet been answered, and the moment an item is removed is the moment its answer is discovered.

## When it applies
It suits questions such as "for each item, where is the next larger or smaller item to its right or left" and problems about spans or the largest rectangle under a profile. Whenever each item needs its nearest neighbour with some comparison, the stack lets you answer all of them in one pass, because every item is pushed once and popped at most once.

## Common mistakes
- Using the wrong direction of order, so equal values or strictness are handled incorrectly.
- Storing values when positions are needed to compute distances.
- Forgetting items left on the stack at the end, which have no answer and need a default.
- Popping with a condition that is off by one for equal values.
- Believing the nested loop makes it quadratic instead of counting each item's single push and pop.

## Socratic questions
- What does an item still sitting on the stack tell you about what it is waiting for?
- When a new item arrives, which waiting items does it settle?
- Should equal values settle each other, and does your comparison say so?
- Do you need positions, values, or both on the stack?
- What answer do items remaining at the end receive?

## Tiny illustration
Given daily temperatures, find for each day how many days pass before a warmer one. Walk the days, keeping a stack of days still waiting for a warmer day. When today is warmer than the day on top, that waiting day is answered with the difference in positions; keep removing while today is warmer. Then push today. Each day enters and leaves once.

## Related concepts
stack, monotonic-queue, complexity-analysis
