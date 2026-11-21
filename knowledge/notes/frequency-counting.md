---
slug: frequency-counting
concept: frequency-counting
reviewed: false
---
## Idea
Frequency counting records how many times each distinct item occurs. The result is a table from item to count, built in a single pass. Many questions about duplicates, majorities, anagram-like equality or "what is most common" become questions about that table rather than about the original sequence.

## When it applies
Use it when the order of items does not matter but their multiplicities do. Two collections are rearrangements of each other exactly when their count tables are equal. It is also the natural first step when you need the most or least common item, when you must find items occurring a particular number of times, or when a condition on a range depends on how many of each kind it contains.

## Common mistakes
- Reading a count for an item that was never inserted, which crashes in some languages and silently gives zero in others.
- Leaving entries with a count of zero in the table and then comparing table sizes or key sets.
- Rebuilding the whole table from scratch for every window instead of adjusting it as items enter and leave.
- Using a fixed-size array indexed by character without checking what the alphabet really is.
- Counting before deciding whether letter case or whitespace should be treated as distinct.

## Socratic questions
- Does the order of the items matter for the answer, or only how many of each there are?
- What would the table look like for a very small input you can write out by hand?
- When two collections should count as equal, what must be true of their tables?
- If items are added and removed one at a time, which table entries change?
- What should happen to an entry whose count drops to zero?

## Tiny illustration
Take the word "level". Counting letters gives l twice, e twice and v once. A word can be rearranged into a palindrome only if at most one letter has an odd count. Here exactly one letter, v, is odd, so the check passes. Notice the check never looks at positions at all; the table already holds everything the question needs.

## Related concepts
hash-map-lookup, sliding-window, string-manipulation
