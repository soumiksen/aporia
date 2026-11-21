---
slug: dp-1d
concept: dp-1d
reviewed: false
---
## Idea
One-dimensional dynamic programming uses a single index as the state, such as a position in a sequence or an amount. A table of answers is filled in order, each entry computed from earlier entries by a fixed rule. Because only a few earlier entries are usually consulted, the table can often be replaced by a few variables.

## When it applies
It suits problems where processing items from left to right, or building up amounts from zero, gives a natural order of subproblems: counting ways to reach a position, the best total ending at a position, or whether a prefix can be formed. If the answer to a longer prefix depends on answers to shorter ones, a one-dimensional table is a good first attempt.

## Common mistakes
- Filling the table in an order where an entry is read before it is computed.
- Setting the first entries incorrectly, so every later value is wrong.
- Confusing "ending exactly at i" with "best among the first i".
- Taking the last table entry as the answer when the answer is a maximum over entries.
- Reducing memory to a few variables and then overwriting a value that is still needed.

## Socratic questions
- Which earlier entries does the current one use, and are they already computed?
- What are the values for the first one or two positions?
- Is the final answer a particular entry, or the best over all entries?
- If only a few previous entries matter, which ones can you keep?
- What does the table value mean if the input is empty?

## Tiny illustration
Count the sequences of ones and twos that sum to n. Let ways at n be that count. A sequence ends in a one or a two, so ways at n is ways at n minus one plus ways at n minus two. With ways at zero equal to one and ways at one equal to one, fill upward. Only the last two values are ever needed.

## Related concepts
dp-state-definition, dp-2d, dp-knapsack
