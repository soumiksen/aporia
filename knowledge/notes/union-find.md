---
slug: union-find
concept: union-find
reviewed: false
---
## Idea
Union-find, also called disjoint sets, tracks a collection of items partitioned into groups. It supports two operations: find, which names the group an item belongs to, and union, which merges two groups. Each group is a tree whose root represents it. With two common refinements, path compression and union by size or rank, both operations take almost constant time.

## When it applies
It fits problems about connectivity as links arrive over time: are these two items already connected, how many groups remain, or does adding this link create a cycle. It is especially handy when edges come as a list and you do not need paths, only whether items are joined.

## Common mistakes
- Comparing the items themselves instead of their roots.
- Merging two items that already share a root and double counting a merge.
- Forgetting to update the group count only when a real merge happens.
- Skipping the refinements and letting trees become long chains.
- Using it when the answer needs the route between items, which it does not store.

## Socratic questions
- What does the root of an item's tree stand for?
- When you are given a new link, how do you tell whether it joins two different groups?
- What changes when two groups merge, and what must stay unchanged?
- How could you keep the trees shallow?
- Does the problem need to know whether items are connected, or the path between them?

## Tiny illustration
Start with five separate items. Link 1 and 2: they share a group. Link 3 and 4: another group. Now link 2 and 3: find the roots of 2 and 3, they differ, so merge, leaving two groups in total. Link 1 and 4 next: their roots already match, so this link would close a cycle and changes nothing.

## Related concepts
graph-dfs, graph-bfs, topological-sort
