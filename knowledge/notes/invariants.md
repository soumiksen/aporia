---
slug: invariants
concept: invariants
reviewed: false
---
## Idea
A loop invariant is a statement that is true before the loop begins, stays true after every pass, and, together with the reason the loop ended, implies the result you want. Naming the invariant turns vague confidence into a checkable argument. It also tells you exactly what each line of the loop must preserve.

## When it applies
Use it whenever a loop maintains a growing result or a shrinking search range, as in searching a sorted list, partitioning, merging, or sweeping with two pointers. If you cannot state what is true at the top of the loop, you probably cannot be sure the loop is right. It is also the best tool for diagnosing off-by-one bugs.

## Common mistakes
- Writing an invariant that holds at the start but is broken partway through a pass and not restored.
- Stating one that is true but too weak to prove the result.
- Forgetting to check that it holds before the first pass.
- Changing the meaning of an index, such as inclusive versus exclusive, partway through.
- Ending the loop on a condition that does not give the invariant the facts it needs.

## Socratic questions
- What do you know to be true about the data you have already processed at the top of each pass?
- Is that statement true before the first pass?
- Which lines of the loop could break it, and where is it restored?
- When the loop ends, what does the invariant plus the exit condition tell you?
- Do all of your indices keep a single meaning throughout?

## Tiny illustration
Moving all zeros to the end of a list while keeping the order of the others, use a write position. The invariant is that everything before the write position is the non-zero items seen so far, in order. Each non-zero item found is placed at the write position and the position advances. When the scan ends, the rest can be filled with zeros.

## Related concepts
binary-search-index, two-pointers, edge-case-reasoning
