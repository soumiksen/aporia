---
slug: bit-manipulation
concept: bit-manipulation
reviewed: false
---
## Idea
Integers are stored as patterns of bits, and the bitwise operators work on each position separately. With them you can test, set, clear and flip individual bits, shift a pattern left or right, and combine patterns. These operations are very cheap and let a small integer stand for a set of yes-or-no flags.

## When it applies
Use bits when state is naturally a set of independent flags, when you need to count or isolate bits, or when a property of exclusive or can cancel pairs. Exclusive or of a value with itself is zero, and with zero is unchanged, so combining many values can cancel matched pairs and leave the odd one out. Small sets can be encoded as masks to speed up enumeration.

## Common mistakes
- Confusing logical and bitwise operators, or getting operator precedence wrong without brackets.
- Shifting by an amount that is too large or using a signed type where the sign bit matters.
- Assuming a fixed width in a language where integers are unbounded, especially with negative numbers.
- Off-by-one in which bit is position zero.
- Reaching for a bit trick when a plain set would be clearer.

## Socratic questions
- Which positions of the number matter, and how can you isolate them?
- What does applying exclusive or twice with the same value do?
- How would you check, set or clear a specific bit?
- What happens to negative numbers in this language?
- Is the bit approach actually simpler than the straightforward one?

## Tiny illustration
A list contains every number twice except one. Combine all numbers with exclusive or. Each pair cancels to zero because a value exclusive-or itself is zero, and zero combined with the remaining number leaves that number. The order of combining does not matter, so one pass and a single variable suffice.

## Related concepts
frequency-counting, math-number-theory, invariants
