---
slug: divide-and-conquer
concept: divide-and-conquer
reviewed: false
---
## Idea
Divide and conquer solves a problem by splitting it into smaller independent pieces, solving each piece the same way, and combining the results. When the pieces are about half the size and the combination step is cheap, the total work is often far smaller than handling the whole input at once.

## When it applies
It fits problems where the answer for a whole can be built from answers for parts, such as sorting by merging halves, counting pairs across a split, or finding a best value either inside one half or crossing the middle. The crucial question is what the combine step must handle that neither half alone can see, usually items that straddle the split.

## Common mistakes
- Forgetting the pieces that cross the dividing line.
- Splitting in a way that does not shrink the problem for tiny inputs.
- Doing an expensive combine step that cancels the benefit of splitting.
- Copying large slices at each level and paying extra time and memory.
- Missing the base case for empty or single-item inputs.

## Socratic questions
- What are the smaller pieces, and are they truly independent?
- What does the combine step have to account for that the pieces cannot?
- How expensive is the combine step compared with the size of the input?
- What is the smallest piece you can answer directly?
- Does your split guarantee progress for every input size?

## Tiny illustration
To find the largest value in a list, you could split it in half, find the largest in each half, and take the larger of the two. The combine step is a single comparison. The idea works, though a plain scan is just as fast here; the real payoff appears when the combine step does something clever, as when merging two sorted halves into one.

## Related concepts
recursion-base-cases, sorting, complexity-analysis
