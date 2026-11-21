---
slug: binary-search-index
concept: binary-search-index
reviewed: false
---
## Idea
Binary search finds a position in ordered data by repeatedly cutting the candidate range in half. Each probe at the middle answers a yes-or-no question that rules out one half. Because the range halves each time, the number of probes grows like the logarithm of the size.

## When it applies
Use it when the data is sorted, or when some property is false for every position up to a boundary and true from there on. Then the task is to find the boundary: the first position where the property holds, or the last one where it does not. Variants such as "first occurrence" or "insertion point" are all boundary searches with different questions.

## Common mistakes
- Writing a loop that never terminates because the range does not shrink in some case.
- Mishandling the midpoint when positions are large, or rounding it in the wrong direction for the variant.
- Mixing inclusive and exclusive upper bounds within one routine.
- Returning a position without checking that it is inside the data or that the value matches.
- Searching data that is not actually ordered.

## Socratic questions
- What is true about every position you have ruled out on each side?
- Which question does the middle element answer, and which half does each answer discard?
- Is your upper bound a valid position or one past the end, and does every line agree with that?
- Could the range stay the same size after an iteration?
- What should be returned when nothing matches?

## Tiny illustration
Imagine a row of light switches where the first several are off and all the rest are on, and you want the first one that is on. Check the middle. If it is on, the first on-switch is at the middle or earlier, so keep the left half including the middle. If it is off, the first on-switch is later, so discard the middle and everything before it. When one candidate remains, it is the answer.

## Related concepts
invariants, binary-search-answer, sorting
