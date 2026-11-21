---
slug: two-pointers
concept: two-pointers
reviewed: false
---
## Idea
Two pointers means keeping two positions in a sequence and moving them according to a rule, so that together they visit the data in one pass rather than testing every pair. The positions might start at opposite ends and move toward each other, or both move forward at different moments, as when one position writes results while the other reads.

## When it applies
It is useful when the sequence has an order you can exploit, such as sorted values, and when comparing the current pair tells you which pointer can safely move. If a comparison proves that no answer exists involving the current left item with anything at or beyond the right pointer, that left item can be discarded for good. It also fits in-place rearrangements and merging two ordered sequences.

## Common mistakes
- Moving a pointer without a reason, so a candidate is skipped that might have been the answer.
- Applying the technique to data that is not ordered when the rule depends on order.
- Stopping the loop one step too early or too late, for example comparing a position with itself.
- Not deciding how duplicates should be treated.
- Updating both pointers when only one should move.

## Socratic questions
- What does the current pair of positions tell you about the comparison you just made?
- Which pointer can you move, and why is it safe to give up what it passed over?
- What ordering of the data does your rule rely on, and is that ordering guaranteed?
- When should the loop end, and what are the two pointers pointing to at that moment?
- How do duplicates change the situation?

## Tiny illustration
In a sorted list of numbers, find two that add to a target. Put one pointer at the smallest value and one at the largest. If their sum is too large, the largest value cannot work with anything remaining, because the smallest remaining value already overshoots, so move the right pointer in. If the sum is too small, move the left pointer out. Each step discards one candidate.

## Related concepts
sorting, sliding-window, fast-slow-pointers
