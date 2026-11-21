---
slug: prefix-sums
concept: prefix-sums
reviewed: false
---
## Idea
A prefix sum array stores, at each position, the total of everything before it. Once it exists, the sum of any contiguous range is a difference of two stored values, so a question that would take a scan per query takes constant time per query after a single preparation pass.

## When it applies
It applies when you must answer many range-total questions on data that does not change, or when a condition on a subarray can be rewritten as a relationship between two prefix values. Combined with a map of earlier prefix values, it turns "is there a range whose total equals some target" into "have I seen a prefix equal to the current one minus the target". The same trick works with counts, parities and other quantities that combine by addition.

## Common mistakes
- Indexing off by one: deciding whether the prefix at position i includes the item at i or stops just before it, then mixing the two conventions.
- Forgetting the empty prefix, so ranges that start at the first item go missing.
- Recomputing totals inside a loop and losing the benefit.
- Overflow in languages with fixed-width integers when totals grow large.
- Updating the stored data and then continuing to trust a prefix array built earlier.

## Socratic questions
- What does the value at position i stand for, in plain words, and does it include item i?
- How would you express the total of the items between positions a and b using two stored values?
- What should the prefix be before any item has been read?
- If you only need to know whether a range exists, do you need the whole array or just the values seen so far?
- What happens to your prefix array if one item changes?

## Tiny illustration
For the list 2, 4, 1, 3 build running totals starting from zero: 0, 2, 6, 7, 10. The total of the middle two items is the stored value after them minus the stored value before them, which is 7 minus 2, giving 5. That equals 4 plus 1, as expected. One subtraction replaced a small loop.

## Related concepts
hash-map-lookup, sliding-window, edge-case-reasoning
