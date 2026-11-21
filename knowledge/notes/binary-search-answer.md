---
slug: binary-search-answer
concept: binary-search-answer
reviewed: false
---
## Idea
Sometimes the thing you search for is not a position in given data but a number that could be the answer itself. If you can write a check that tells whether a proposed value is big enough or small enough, and that check flips from no to yes exactly once as the value grows, you can search the range of possible answers with the same halving method.

## When it applies
Look for problems asking for the smallest value that works or the largest value that still works, where a larger budget never hurts. The check is often a simple greedy or counting pass over the input. The cost is the number of probes, which is logarithmic in the range, times the cost of one check.

## Common mistakes
- Choosing bounds that do not contain the true answer.
- Using a check that is not monotone, so the flip happens more than once and the search lands somewhere meaningless.
- Confusing "smallest that works" with "largest that works" and keeping the wrong half.
- Slow checks that ruin the overall running time.
- Dealing with real-valued answers as if they were whole numbers, or the reverse, without deciding on a precision.

## Socratic questions
- If a value works, what can you say about every larger value?
- What are the smallest and largest answers that could possibly make sense?
- How would you test one proposed value by itself, ignoring the search?
- When the check says yes, which half do you keep for the smallest answer, and for the largest?
- How much does one check cost, and how many checks will you run?

## Tiny illustration
You must split a stack of reports among a fixed number of reviewers so that nobody reads more than some number of pages, and you want that number as small as possible. For a trial limit, hand reports out in order and start a new reviewer whenever the next one would exceed the limit; count reviewers. A bigger limit never needs more reviewers, so the limit can be searched by halving.

## Related concepts
binary-search-index, greedy, complexity-analysis
