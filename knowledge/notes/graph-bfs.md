---
slug: graph-bfs
concept: graph-bfs
reviewed: false
---
## Idea
Breadth-first search explores a graph in rings around a starting node: everything one edge away, then everything two edges away, and so on. Because rings are completed in order, the first time the search reaches a node it has used the fewest possible edges, so it finds shortest paths when every edge counts the same.

## When it applies
Use it for minimum number of steps, minimum moves, or nearest-of-several targets in a graph where each move has equal cost. Starting with several nodes in the queue at once handles "distance to the nearest source" for every node in one pass. It also underlies level-by-level processing of trees and grids.

## Common mistakes
- Marking nodes visited when they are removed from the queue instead of when they are added, which lets duplicates pile up.
- Applying it to weighted edges, where fewer edges does not mean smaller cost.
- Forgetting to record distance or parent alongside the node.
- Stopping at the first target found without checking that it is the one you wanted.
- Not handling an unreachable target.

## Socratic questions
- When exactly should a node be marked as seen, and what goes wrong if you wait?
- Why does the first arrival at a node give the fewest edges?
- What should be stored with each queued node so you can report a distance?
- Are all moves equally costly in this problem?
- What do you return if the target can never be reached?

## Tiny illustration
In a network of stations where each hop between neighbouring stations counts as one step, find the fewest steps from one station to another. Put the start in a queue with distance zero. Repeatedly take a station, and for each neighbour not yet seen, mark it, record one more than the current distance, and queue it. The first time you reach the destination, its recorded distance is the answer.

## Related concepts
graph-dfs, shortest-path, matrix-traversal
