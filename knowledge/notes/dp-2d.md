---
slug: dp-2d
concept: dp-2d
reviewed: false
---
## Idea
Two-dimensional dynamic programming uses two indices as the state, so the table is a grid. Typical pairs are positions in two different sequences, a position and a remaining quantity, or the two ends of a range within one sequence. An entry depends on neighbouring entries, usually those above, to the left, or diagonally before it.

## When it applies
Use it when one index is not enough to describe the subproblem. Comparing two strings, such as measuring how alike they are, needs a position in each. Problems over ranges of a single sequence need both endpoints. The time and memory cost is the product of the two dimensions, so it is worth asking whether only the previous row is needed.

## Common mistakes
- Filling in an order that reads cells before they exist, especially for range problems that must be filled by increasing length.
- Off-by-one trouble because the table has an extra row and column for the empty prefix.
- Mixing up which index belongs to which sequence.
- Initializing the first row and column incorrectly.
- Keeping only one row and overwriting a value from the previous row that is still needed.

## Socratic questions
- What does each of the two indices stand for?
- Which neighbouring cells does an entry depend on?
- In what order must the cells be filled so dependencies are ready?
- What do the first row and first column mean, and what values do they hold?
- Do you need the entire grid, or just the previous row?

## Tiny illustration
To find the length of the longest sequence of letters that appears in order in two words, let a cell hold the answer for the first i letters of one word and the first j of the other. If the two newest letters match, the cell is one more than the diagonal cell. Otherwise it is the larger of the cell above and the cell to the left.

## Related concepts
dp-1d, dp-state-definition, string-manipulation
