---
slug: stack
concept: stack
reviewed: false
---
## Idea
A stack is a collection where the last item added is the first one removed. You can only look at, add to, or remove from the top. That restriction matches any situation where the most recent unfinished thing must be handled before older ones, which is also exactly how nested structures and function calls behave.

## When it applies
Use a stack when the input contains pairs that must nest properly, such as brackets or tags, when you need to undo the latest step, or when you are converting a recursive process into an explicit loop. It also helps when you must remember items whose answer depends on something that appears later in the sequence.

## Common mistakes
- Popping from an empty stack because the input had a closing item first.
- Finishing the loop and forgetting to check that the stack is empty.
- Pushing the wrong thing, such as the value when the position was needed.
- Comparing against the top without first checking that there is one.
- Treating the top and the bottom as interchangeable.

## Socratic questions
- What is the most recent unfinished thing at each point in your scan?
- What must be on top of the stack when a closing item arrives?
- What should you store: the item itself, its position, or both?
- What does it mean if the stack is not empty at the end?
- What should happen if you try to remove from an empty stack?

## Tiny illustration
Check whether a string of round and square brackets is balanced. Scan left to right. An opening bracket goes onto the stack. A closing bracket must match the one on top; if it does, remove that top, otherwise the string is broken. At the end the stack must be empty, otherwise some opening bracket was never closed.

## Related concepts
monotonic-stack, recursion-base-cases, tree-dfs
