---
slug: edge-case-reasoning
concept: edge-case-reasoning
reviewed: false
---
## Idea
Most wrong submissions are close to right and fail on a boundary: an empty input, a single item, two equal items, the largest allowed value, or a loop that runs one time too many or too few. Edge-case reasoning is the habit of deliberately checking those boundaries against your method before trusting it.

## When it applies
Apply it every time, and especially after a method passes the given examples but fails somewhere else. List the extremes the constraints allow: smallest and largest sizes, zeros, negatives, duplicates, already ordered or reverse ordered data, and cases where the answer does not exist. Then walk your method through each by hand and note what every variable holds.

## Common mistakes
- Testing only the examples that came with the problem.
- Starting a loop at the wrong index or ending it one early.
- Assuming the input is non-empty, or that there are at least two items.
- Forgetting what to return when no answer exists.
- Fixing a failure by adding a special case without understanding why it failed.

## Socratic questions
- What is the smallest input the constraints permit, and what does your method do with it?
- What if all items are equal, or every item is different?
- Which index does each loop touch first and last?
- What should happen when there is no valid answer?
- Which of your variables could be uninitialized or out of range on that input?

## Tiny illustration
Suppose a routine finds the largest gap between neighbouring values in a list. Walk it with an empty list: there are no neighbours, so what is returned? With one item: still no neighbours. With two equal items: the gap is zero. Each walk-through checks a different assumption, and the first two reveal a question that the problem statement may or may not have answered.

## Related concepts
invariants, complexity-analysis, matrix-traversal
