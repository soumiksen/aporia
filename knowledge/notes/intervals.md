---
slug: intervals
concept: intervals
reviewed: false
---
## Idea
An interval is a stretch with a start and an end, such as a time slot or a range of positions. Questions about intervals ask how they overlap, merge, fit or cover. Sorting by start (or sometimes end) turns most of these into a single sweep in which only the most recent interval needs to be compared with the next.

## When it applies
Use it for merging overlaps, inserting a new interval into a set, counting how many are active at once, finding gaps, or deciding whether a schedule is possible. A related view treats each start and end as an event and sweeps through events in time order, adjusting a running count.

## Common mistakes
- Not deciding whether touching endpoints count as overlapping.
- Merging without sorting first, so overlaps that are not adjacent are missed.
- Comparing the next interval with the wrong earlier one rather than the most recently merged one.
- Forgetting that the merged end is the larger of the two ends, not just the later one.
- Handling ties between a start and an end at the same time inconsistently.

## Socratic questions
- When do two intervals overlap, and do touching ends count?
- What order should you process intervals in so that comparing neighbours is enough?
- When one interval overlaps the current merged one, how do the merged start and end change?
- What is the right moment to close the current merged interval?
- If you treated starts and ends as events, what would the running count mean?

## Tiny illustration
Take ranges 1 to 3, 2 to 6, 8 to 10 and 9 to 12. Sorted by start they are already in order. Begin with 1 to 3. The next starts at 2, before 3 ends, so merge into 1 to 6. The next starts at 8, after 6, so close the first and begin a new one at 8 to 10. The last overlaps it and merges into 8 to 12.

## Related concepts
sorting, greedy, heap-priority-queue
