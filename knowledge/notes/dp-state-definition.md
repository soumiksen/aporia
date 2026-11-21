---
slug: dp-state-definition
concept: dp-state-definition
reviewed: false
---
## Idea
Dynamic programming starts with a precise sentence describing what one table entry means. That sentence is the state. Once it is clear, a recurrence relates an entry to smaller entries, base values anchor the smallest ones, and a final entry or combination of entries holds the answer. Most failed attempts fail at the first step because the meaning of the state was vague.

## When it applies
Use it when a problem asks for a best value, a count or a yes-or-no answer, and the problem contains overlapping smaller versions of itself where only a few quantities describe the situation. Ask what information about the past is truly needed to decide the future. That information, and nothing more, belongs in the state.

## Common mistakes
- Defining a state that does not carry enough information, so the recurrence needs facts that are not in it.
- Carrying more information than needed and making the table huge.
- Mixing two meanings, such as "best using the first i items" and "best ending at item i".
- Wrong base values, especially for the empty case.
- Reading the answer from the wrong cell.

## Socratic questions
- Can you complete the sentence "the value at this entry is the ... of ..." in plain words?
- What does a decision at this point need to know about everything that came before?
- Which smaller entries does this one depend on?
- What is the value for the smallest possible state, and why?
- Which entry holds the final answer?

## Tiny illustration
You want the largest total from a row of numbers when you may not take two neighbours. Define best at position i as the largest total using only the first i numbers. For the next number there are two choices: skip it and keep the previous best, or take it and add the best from two positions earlier. The sentence defining the state made the recurrence nearly obvious.

## Related concepts
memoization, dp-1d, dp-2d
