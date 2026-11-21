---
slug: sliding-window
concept: sliding-window
reviewed: false
---
## Idea
A sliding window is a contiguous stretch of a sequence described by a left edge and a right edge. Instead of examining every possible stretch, you move the right edge forward to take in new items and move the left edge forward to drop old ones, keeping a small summary of what is currently inside so you never recompute it from scratch.

## When it applies
It fits questions about the best contiguous subarray or substring under a condition, particularly when the condition behaves predictably as the window grows or shrinks. If adding an item can only push the window toward violating the rule, and removing items can only repair it, you can grow until the rule breaks and then shrink until it holds again. Fixed-size windows work too, with both edges moving together.

## Common mistakes
- Shrinking too little, so the window stays invalid, or too much, so a valid answer is skipped.
- Updating the answer at the wrong moment, before the window has been repaired.
- Forgetting to remove the leaving item from the summary when the left edge moves.
- Using the technique when the condition does not behave predictably, for example when values can be negative and sums are not monotone.
- Mixing up whether the right edge is inclusive or exclusive.

## Socratic questions
- What exactly is stored in the summary, and what changes when an item enters or leaves?
- What makes the window valid, and which edge do you move to restore validity?
- When is the right time to record a candidate answer?
- If a new item can make the condition worse, can an old item ever make it better?
- Does the condition still behave predictably if the values may be negative?

## Tiny illustration
Find the longest run of letters in a word with no letter repeated. Start with an empty window. Take the next letter in on the right. If it already appears inside, drop letters from the left until it no longer does. After each step the window is valid, so note its length. The left edge never moves backward, so the work is linear overall.

## Related concepts
two-pointers, frequency-counting, monotonic-queue
