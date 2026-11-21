---
slug: complexity-analysis
concept: complexity-analysis
reviewed: false
---
## Idea
Complexity analysis describes how the time or memory used by a method grows as the input grows, ignoring constant factors and small details. It lets you compare approaches before you write them and judge whether one will finish within the limits of the problem. The common growth rates, from slowest-growing to fastest, are constant, logarithmic, linear, linearithmic, quadratic and exponential.

## When it applies
Use it constantly: to estimate whether a first idea is fast enough, to find which part of a method dominates, and to decide what to improve. Problem limits give a hint. An input size around a hundred thousand rules out quadratic work, while an input of about twenty may allow exponential search. Also consider extra memory and the cost of operations hidden inside library calls.

## Common mistakes
- Counting only the loop you wrote and ignoring costs inside called functions, such as slicing, searching a list or concatenating strings.
- Multiplying costs that are actually added, or adding costs that are multiplied.
- Calling something linear when each step does work that grows with the input.
- Ignoring the recursion stack when counting memory.
- Treating an average cost as if it were guaranteed in the worst case.

## Socratic questions
- How many times does the innermost step run, as a function of the input size?
- What does each step really cost, including calls to library routines?
- What input size do the limits allow, and what growth rate does that suggest?
- Does an operation happen once per item, or once per pair of items?
- Beyond time, how much extra memory does the method use?

## Tiny illustration
A loop over n items that, for each item, scans the rest of the items does about n times n divided by two comparisons, which grows like n squared. Replacing the inner scan with a lookup in a structure built beforehand makes each step constant, so the whole thing grows like n. The estimate told you where to look before running anything.

## Related concepts
hash-map-lookup, sorting, divide-and-conquer
