---
slug: hash-map-lookup
concept: hash-map-lookup
reviewed: false
---
## Idea
A hash map stores key-value pairs and finds the value for a key in constant time on average. It trades memory for speed: instead of scanning a collection each time you need to know whether something has been seen, you record it once and ask the map later. A hash set is the same idea when only membership matters.

## When it applies
Reach for it when a loop repeatedly asks "have I already seen a value with this property?" or "where did that value occur?". If the inner step of a nested loop is only a search, a map can often replace it. It also fits when you need to group items by a shared key, or remember one piece of information per key as you sweep through the input once.

## Common mistakes
- Using a value as a key when two different items can share that value, then overwriting the earlier entry without meaning to.
- Checking the map after inserting the current element, so the element matches itself.
- Forgetting that keys must be hashable, so a list cannot be a key while a tuple of the same items can.
- Assuming iteration order carries meaning beyond what the language promises.
- Quoting constant time without remembering it is an average, and that building keys from large objects costs time too.

## Socratic questions
- What question does your inner loop ask each time it runs, and what do you already know that could answer it without a scan?
- What should the key be, and what should be stored as its value?
- At the moment you look something up, what has been inserted so far, and is that the right moment?
- What happens when two different elements produce the same key?
- What does the extra memory cost you, and is the speedup worth it here?

## Tiny illustration
Suppose you read a list of names and must report the first name that appears twice. Scanning backwards through everything read so far for each new name is slow. Instead keep a set of names seen. For each new name, ask the set first; if the answer is yes, you are done, otherwise add the name and continue. Each name is touched a constant number of times, so the work grows in step with the list length.

## Related concepts
frequency-counting, two-pointers, sorting
