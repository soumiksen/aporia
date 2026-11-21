---
slug: tree-dfs
concept: tree-dfs
reviewed: false
---
## Idea
Depth-first search on a tree follows one branch all the way down before trying the next. Because every subtree is itself a tree, the natural way to write it is recursively: handle the current node, ask the same question of each child, and combine what the children report.

## When it applies
Use it for questions about paths, depths, sums along branches, or properties that every subtree must satisfy. The order in which you do work matters. Acting on a node before its children flows information downward from ancestors; acting after the children flows information upward from descendants. Many problems need only one of these directions, and some need both.

## Common mistakes
- Forgetting the base case for a missing child.
- Confusing a path that must end at a leaf with one that may end anywhere.
- Returning a single value when the parent needs more than one fact about the subtree.
- Carrying state in shared variables and not resetting it between branches.
- Hitting the recursion limit on very deep trees without considering an explicit stack.

## Socratic questions
- What should the call return for an empty subtree?
- What does a parent need to know about each child, and is that a single number or several?
- Does information need to travel down from the ancestors, up from the descendants, or both?
- Where in the function should the node's own work happen relative to the recursive calls?
- How deep can the tree get, and what does that mean for the call stack?

## Tiny illustration
To find how tall a tree is, say an empty tree has height zero. For any node, ask each child for its height and take the larger, then add one for the node itself. The answer flows upward from the leaves. No node needs to know anything about its ancestors, which is why the solution is so short.

## Related concepts
recursion-base-cases, tree-bfs, bst-properties
