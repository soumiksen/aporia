---
slug: topological-sort
concept: topological-sort
reviewed: false
---
## Idea
A topological order lists the nodes of a directed graph so that every edge points from an earlier item to a later one. It exists exactly when the graph has no directed cycle. Think of tasks with prerequisites: the order says what can be done first, and if tasks depend on each other in a loop, no valid order exists.

## When it applies
Use it for scheduling, build ordering, resolving dependencies, and any question asking whether a set of prerequisites can all be satisfied. One approach repeatedly removes nodes with no incoming edges. Another runs depth-first search and lists nodes in reverse order of finishing. Either one also detects a cycle.

## Common mistakes
- Building edges in the wrong direction, so prerequisites and dependents swap.
- Ignoring nodes that have no edges at all, which still belong in the order.
- Not noticing that fewer nodes were output than exist, which signals a cycle.
- Confusing "visited" with "on the current path" in the depth-first version.
- Assuming the order is unique when several orders may be valid.

## Socratic questions
- Which direction should an edge point when one task must happen before another?
- Which nodes can safely come first, and how do you find them?
- When a node is placed, what changes for the nodes that depend on it?
- How would you tell that no valid order exists?
- Does the problem need any valid order, or one with extra properties?

## Tiny illustration
You must wear socks before shoes and underwear before trousers, and trousers before shoes. Count for each item how many things must come before it. Items with count zero can go now. Place one, then reduce the count of everything that depends on it, and repeat. If items remain but none has count zero, there must be a loop of requirements.

## Related concepts
graph-bfs, graph-dfs, union-find
