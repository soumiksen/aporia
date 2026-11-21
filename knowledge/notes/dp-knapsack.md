---
slug: dp-knapsack
concept: dp-knapsack
reviewed: false
---
## Idea
Knapsack-style problems choose from a set of items under a limited budget, such as weight, count or amount. The state records how much of the budget has been used or remains, and sometimes which items have been considered. Each item either contributes or does not, and the table records the best result, or whether the target is reachable, for each budget level.

## When it applies
It appears whenever you must reach exactly or stay within a limit using pieces that cost something: forming a total from available values, splitting a set into two equal groups, or maximizing value under a cap. The key question is whether each item may be used once or any number of times, because it changes the order in which the table is updated.

## Common mistakes
- Updating the budget dimension in the wrong direction, which accidentally allows reuse of an item that may be used only once, or the reverse.
- Starting from the wrong base: reaching zero needs one way, not none.
- Using a greedy choice where only the table is guaranteed to work.
- Treating a budget that may be large as if the table were small.
- Forgetting to cover the case where the target is unreachable.

## Socratic questions
- Can each item be used once or repeatedly, and how does that affect the update order?
- What does an entry for a given budget represent?
- What is the value for a budget of zero?
- How do you tell that the target cannot be reached?
- How large can the budget be, and what does that do to the table size?

## Tiny illustration
With coins of value 2 and 3, ask whether 7 can be formed. Let reachable at zero be true. Walk amounts upward: an amount is reachable if the amount minus 2 or the amount minus 3 is reachable. Then 2, 3, 4 (2+2), 5, 6 and 7 (2+2+3) are reachable, so 7 can be formed, while 1 cannot.

## Related concepts
dp-1d, backtracking, greedy
