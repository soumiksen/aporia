---
slug: sorting
concept: sorting
reviewed: false
---
## Idea
Sorting arranges items according to an order. Its value is rarely the sorted list itself; it is the structure that order exposes. Equal items become neighbours, the smallest and largest are at the ends, and many problems can be answered by a single sweep or a binary search once the data is ordered.

## When it applies
Consider sorting when a problem asks about closeness, duplicates, ranges, pairs, or a best arrangement, and when the original positions do not matter or can be remembered separately. Typical comparison sorts cost on the order of n log n, so sorting first is a good trade if it turns a quadratic search into a linear one. A custom comparison or key lets you sort by something other than the raw value.

## Common mistakes
- Sorting when the original order was part of the answer, and losing it.
- Writing a comparison that is not consistent, for example one that disagrees with itself about which of two items comes first.
- Assuming a sort is stable when the tool does not promise it.
- Sorting a copy and a reference and then being surprised that only one changed.
- Counting only the sweep after sorting and forgetting the cost of the sort.

## Socratic questions
- What property would you like neighbouring items to have, and does some ordering produce it?
- Does the answer depend on where items started, and if so how will you keep that information?
- What would a custom key have to compute so that your sweep becomes easy?
- After sorting, what is the cheapest scan that finishes the job?
- What is the total cost once the sorting step is included?

## Tiny illustration
You are given appointment times and want to know whether any two clash. Comparing every pair is slow. Sort the appointments by start time instead. Now a clash can only happen between an appointment and the one immediately after it, so one pass over adjacent pairs decides the question. The sort did the hard thinking.

## Related concepts
two-pointers, intervals, greedy
