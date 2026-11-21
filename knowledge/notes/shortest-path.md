---
slug: shortest-path
concept: shortest-path
reviewed: false
---
## Idea
When edges carry different costs, the route with the fewest edges is not necessarily the cheapest. Dijkstra's method keeps a best-known cost to every node and repeatedly settles the unsettled node with the smallest cost, then checks whether going through it improves its neighbours. It relies on costs never being negative.

## When it applies
Use it to find the minimum cost from a source to one or all nodes in a graph with non-negative weights: travel times, prices, effort. A priority queue chooses the next node quickly. If all edges cost the same, plain breadth-first search is enough. If negative costs exist, a different method is required.

## Common mistakes
- Using the method with negative edge costs, which breaks its guarantee.
- Using a first-in first-out queue instead of one ordered by cost.
- Processing a node again after it has been settled, or failing to skip outdated queue entries.
- Initializing distances to a value that can overflow when added to.
- Reporting a distance for a node that was never reached.

## Socratic questions
- Why can the node with the smallest known cost no longer be improved, given non-negative costs?
- How do you find that node quickly each time?
- What do you do when you pop an entry that is out of date?
- What value should an unreached node have?
- Are all edge costs the same, and if so is a simpler method enough?

## Tiny illustration
From a start town, roads to A cost 4 and to B cost 1, and B to A costs 2. The best known cost to A is 4 at first. Settle B at cost 1, then check its roads: reaching A through B costs 3, better than 4, so update A. Settle A at 3. The direct road was not the cheapest even though it had fewer edges.

## Related concepts
graph-bfs, heap-priority-queue, greedy
