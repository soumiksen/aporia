---
slug: fast-slow-pointers
concept: fast-slow-pointers
reviewed: false
---
## Idea
Two pointers walk the same chain at different speeds, typically one step and two steps at a time. The gap between them grows in a predictable way, which reveals facts about the chain that a single pointer cannot see without extra memory, such as where the middle is or whether the path loops back on itself.

## When it applies
It is useful for linked structures and for sequences defined by repeatedly applying a function. If the faster pointer reaches the end, the chain is finite and the slower one is then about halfway. If the chain contains a loop, the faster pointer eventually laps the slower one inside the loop, so they meet. This detects a loop in constant extra memory.

## Common mistakes
- Dereferencing the fast pointer's next step without checking that the first step exists.
- Starting both pointers in a way that makes them equal immediately and ends the loop too early.
- Returning the wrong middle when the length is even.
- Assuming that a meeting point is where the loop begins; it is not necessarily.
- Using the technique on a structure that cannot loop and gaining nothing over a simple count.

## Socratic questions
- What do you learn when the fast pointer runs off the end?
- Where is the slow pointer at that moment, relative to the whole chain?
- Why must the two pointers meet if there is a loop, and why never if there is not?
- Which checks keep the fast pointer from stepping onto a missing node?
- For an even length, which of the two middle nodes does your loop select?

## Tiny illustration
Picture two runners on a circular track, one twice as fast as the other. Once both are on the track the faster one gains one step per move, so the gap shrinks by one each time and must reach zero, meaning they meet. On a straight path with an end the faster runner simply leaves it. Meeting therefore tells you the path loops.

## Related concepts
linked-list-manipulation, two-pointers, graph-dfs
