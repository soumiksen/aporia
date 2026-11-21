---
slug: recursion-base-cases
concept: recursion-base-cases
reviewed: false
---
## Idea
Recursion solves a problem by solving smaller versions of the same problem and combining the results. Every correct recursive solution has two parts: base cases, where the answer is known directly, and a step that reduces the input toward a base case. If the step does not move toward a base case, the recursion never stops.

## When it applies
It fits structures that contain smaller copies of themselves, such as trees and nested data, and choices that repeat at each step. Thinking recursively means trusting that the smaller call returns the right answer, and asking only how to turn that answer into the answer for the current input.

## Common mistakes
- Missing a base case, or a base case that misses a possibility such as empty input.
- A reduction that does not shrink, leading to endless calls and a stack overflow.
- Checking the base case after using the input in a way that fails on it.
- Mutating shared state and forgetting to restore it between calls.
- Recomputing the same subproblems many times without noticing.

## Socratic questions
- What is the smallest input for which you know the answer without any calls?
- How does each call make the problem smaller, and by how much?
- If you trust the smaller call to be right, what is left for the current call to do?
- Can any input skip past every base case?
- Do different calls end up solving the same smaller problem?

## Tiny illustration
To add up a chain of numbers, say the total of an empty chain is zero; that is the base case. For a longer chain, the total is the first number plus the total of the rest. The rest is shorter by one each time, so the calls must reach the empty chain. Writing the base case first makes the stopping rule explicit.

## Related concepts
tree-dfs, memoization, backtracking
