---
slug: greedy
concept: greedy
reviewed: false
---
## Idea
A greedy method builds an answer by always taking the choice that looks best right now and never reconsidering. It is fast and simple, but it is only correct when a local choice can be shown never to hurt the final result. The proof matters more than the code: without a reason that the choice is safe, a greedy rule is only a guess.

## When it applies
Consider it when the problem has an obvious ordering of choices, such as by deadline, by cost, or by ratio, and when exchanging a different choice for the greedy one can never make the outcome worse. Sorting first is common. If a small example shows a case where the locally best choice leads to a worse total, the problem likely needs dynamic programming instead.

## Common mistakes
- Trusting a rule because it works on the examples, without testing small awkward cases.
- Sorting by the wrong key, or breaking ties in a way that matters.
- Choosing the best now when what is needed is the best overall, as in problems with limited budgets and varied item sizes.
- Forgetting that the greedy answer may be correct for the value but not for a count of steps, or the reverse.
- Stopping the loop before every item was considered.

## Socratic questions
- What choice looks best at each step, and by what measure?
- If you picked something else first, could you swap it for the greedy choice without making things worse?
- Can you build a tiny input where the locally best choice goes wrong?
- Does the order in which you consider choices matter, and how do you establish it?
- What distinguishes this from a problem needing a table of subproblems?

## Tiny illustration
You have several talks, each with a start and end time, and one room. Which talk should you schedule first to fit as many as possible? Choosing the shortest can block two others, and choosing the earliest start can block everything. Choosing the one that ends earliest leaves the most room for the rest, and swapping any other first choice for it never reduces the count.

## Related concepts
sorting, intervals, heap-priority-queue
