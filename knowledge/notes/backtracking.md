---
slug: backtracking
concept: backtracking
reviewed: false
---
## Idea
Backtracking builds a solution one decision at a time. After each choice it explores what follows; when that path is finished or cannot succeed, it undoes the choice and tries the next option. The search forms a tree of partial solutions, and the skill lies in cutting off branches that cannot lead anywhere.

## When it applies
Use it when you must produce every arrangement, selection or sequence that satisfies a rule, such as permutations, subsets, placements or paths, and when no shortcut avoids looking at the possibilities. It becomes practical when constraints let you reject a partial solution early, long before it is complete.

## Common mistakes
- Forgetting to undo a choice before trying the next, so state leaks between branches.
- Saving a reference to the working list rather than a copy when a solution is recorded.
- Generating the same result many times by allowing different orders of the same choices.
- Pruning too late, or not at all.
- Missing the empty or single-item case.

## Socratic questions
- What is a choice at this step, and what are the options?
- What must be true of a partial solution for it to be worth continuing?
- How do you restore the state after exploring an option?
- What counts as a finished solution, and when do you record it?
- How can you make sure the same set is not produced in different orders?

## Tiny illustration
List every way to pick two letters from a, b, c without regard to order. Start with an empty pick. Choose a, then from the letters after a choose b to finish, undo b and choose c to finish, then undo a. Now choose b and, from letters after b, choose c. Only looking forward avoids producing both ab and ba.

## Related concepts
recursion-base-cases, memoization, dp-knapsack
