---
slug: memoization
concept: memoization
reviewed: false
---
## Idea
Memoization stores the result of a computation the first time it is done, keyed by its inputs, so that asking the same question again returns the stored answer immediately. It is most useful for recursion where different branches reach the same subproblem; without storage the same work is repeated many times, often turning a manageable amount of work into an enormous one.

## When it applies
Look for a recursive solution whose calls take a small set of repeating arguments. If the answer to a call depends only on its arguments and not on anything else that changes, it can be cached. The number of distinct argument combinations, times the work per call, gives the running time. This is the top-down way to do dynamic programming.

## Common mistakes
- Caching results that also depend on state outside the arguments.
- Using a key that does not capture all of the inputs that matter.
- Checking the cache after doing the work instead of before.
- Mutating a shared object that is part of the key.
- Ignoring that a very deep recursion may exceed the call limit.

## Socratic questions
- Which arguments fully determine the answer to a call?
- How many different combinations of those arguments can occur?
- Do two branches of your recursion ever ask the same question?
- What exactly should the cache key include?
- Where in the function does the cache check belong?

## Tiny illustration
Counting the ways to climb a staircase by taking one or two steps at a time, a naive recursion asks about each smaller staircase repeatedly, because ways to reach the top from step n relies on both n minus one and n minus two. Storing each answer once means every smaller staircase is solved a single time, and the total work grows only with the number of steps.

## Related concepts
recursion-base-cases, dp-state-definition, dp-1d
