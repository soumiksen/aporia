---
slug: tree-bfs
concept: tree-bfs
reviewed: false
---
## Idea
Breadth-first search on a tree visits nodes level by level: first the root, then all its children, then all grandchildren, and so on. A queue holds the nodes waiting to be visited, which guarantees that nodes closer to the root are always processed before deeper ones.

## When it applies
Use it when the answer depends on levels or on distance from the root: the nodes at each depth, the first node that satisfies a condition when scanning top to bottom, the width of the tree, or the view from one side. It is also the right choice when depth could be very large and you would rather not rely on a deep call stack.

## Common mistakes
- Processing nodes one at a time without noticing where one level ends and the next begins.
- Measuring the length of the queue after nodes were already added to it, so the level size is wrong.
- Adding missing children to the queue and then failing on them.
- Forgetting that an empty tree has no levels.
- Using a plain list and removing from the front at linear cost.

## Socratic questions
- What does the queue contain at the start of each level?
- How can you tell how many nodes belong to the level being processed?
- In what order should the children of a node be added?
- What should the routine return when there is no root?
- Which operations on your queue are cheap, and are you using them?

## Tiny illustration
Imagine a family tree and you want each generation listed separately. Start with the oldest person in the queue. Repeat: note how many people are in the queue, take exactly that many out one by one, and add each person's children behind them. The people you took out form one generation. Counting before you start is what keeps generations apart.

## Related concepts
tree-dfs, graph-bfs, matrix-traversal
