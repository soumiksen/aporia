---
slug: graph-dfs
concept: graph-dfs
reviewed: false
---
## Idea
Depth-first search explores a graph by following an edge as far as possible, then backing up to try the next. Unlike a tree, a graph can contain cycles and several routes to the same node, so the search must remember which nodes it has already visited to avoid walking in circles.

## When it applies
Use it to find everything reachable from a node, to count or label connected pieces, to detect a cycle, or to explore all paths when the structure needs it. Starting a fresh search from every unvisited node covers graphs that are not connected. It can be written recursively or with an explicit stack.

## Common mistakes
- Marking a node visited too late, so it is pushed or called more than once.
- Forgetting the outer loop that starts a search from each unvisited node.
- Treating an undirected edge as one-way, or a directed edge as two-way.
- Confusing "visited anywhere" with "currently on the path", which matters for cycle detection in directed graphs.
- Recursing so deeply that the call stack runs out.

## Socratic questions
- How does your search avoid visiting the same node twice?
- At which moment do you mark a node, and does that moment prevent duplicates?
- Is the graph directed, and does your neighbour list reflect that?
- What if the graph has several separate pieces?
- Do you need to know about nodes you have seen at all, or only those on the current route?

## Tiny illustration
You have a map of rooms and doors and want to count how many separate groups of connected rooms there are. For each room not yet visited, start a search that marks every room it can reach, then add one to the count. Each room is marked once, and the count of fresh starts equals the number of groups.

## Related concepts
graph-bfs, union-find, topological-sort
