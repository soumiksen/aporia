---
slug: linked-list-manipulation
concept: linked-list-manipulation
reviewed: false
---
## Idea
A linked list is a chain of nodes where each node knows only the next one. You cannot jump to a position; you can only follow links. Manipulating a list therefore means rewiring links carefully, in an order that never loses the part of the chain you have not reached yet.

## When it applies
It comes up when you must insert, delete, reverse, merge or reorder nodes without extra storage. Typical tools are a pointer to the previous node, a pointer to the current node, and a saved reference to the next node taken before any link changes. A placeholder node before the head removes special cases for operations that might change the head.

## Common mistakes
- Overwriting a node's next link before saving it, so the rest of the list is lost.
- Not handling an empty list or a list with one node.
- Forgetting to terminate the new tail, which can leave a cycle behind.
- Returning the old head after an operation that moved the head.
- Dereferencing a missing next node at the end of the chain.

## Socratic questions
- Before you change this link, what do you still need to remember?
- Which nodes does each pointer name after one step of your loop?
- What should happen when the list is empty or has a single node?
- Which node ends up last, and what must its link be?
- Would a placeholder in front of the head simplify the first step?

## Tiny illustration
To reverse a chain, keep a previous pointer starting at nothing and a current pointer at the head. At each step save the current node's next link, then point the current node backward at previous, then advance previous to current and current to the saved node. When current runs out, previous is the new head. Taking the save first is what prevents losing the tail.

## Related concepts
fast-slow-pointers, recursion-base-cases, edge-case-reasoning
