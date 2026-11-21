---
slug: matrix-traversal
concept: matrix-traversal
reviewed: false
---
## Idea
A grid can be treated as a graph where each cell is a node and neighbouring cells are connected. Moving around it means choosing which directions are allowed, staying inside the boundaries, and remembering which cells have been seen. Rows and columns are just a coordinate system, and the same searches used on graphs apply directly.

## When it applies
Use it for counting regions, finding shortest routes through open cells, spreading something outward from several starting cells, or filling an area. Some problems instead need a fixed visiting pattern such as walking in a spiral or by diagonals, where careful bookkeeping of boundaries matters more than search.

## Common mistakes
- Swapping rows and columns when indexing.
- Checking boundaries after accessing the cell rather than before.
- Forgetting a direction, or including diagonals when only four directions are allowed.
- Marking cells visited late and processing them twice.
- Modifying the input grid as a marker without deciding whether that is acceptable.

## Socratic questions
- How are the row and column indices ordered in your access, and does every use agree?
- What are the allowed moves, and how can you list them compactly?
- When is a neighbouring cell valid: inside the grid, not blocked, not yet seen?
- Which search suits the question, one that needs fewest steps or one that only needs reachability?
- Can the grid be empty, or have a single row or column?

## Tiny illustration
In a small map of land and water cells, count islands. Scan every cell. When you meet unvisited land, add one to the count and spread from it through the four neighbouring directions, marking each land cell reached. Cells marked during the spread are never counted again, so each island is counted exactly once.

## Related concepts
graph-bfs, graph-dfs, edge-case-reasoning
