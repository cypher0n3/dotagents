# Lines Adapted From the Karpathy Guidelines

This note is for people reading or forking the skill.
It is deliberately kept out of `SKILL.md`, because everything in that file is loaded into the model's context on every invocation and this history is not something the model needs in order to follow the rules.

## Source

Several lines in `senior-developer` are adapted, reworded, from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) by forrestchang, which its plugin and skill metadata publish under the MIT license.
That project distils [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on the mistakes coding models make.

## What Was Adopted

Most of that guidance was already here, in `senior-developer` and `engineering-principles`, so only the parts that were missing were taken:

- The "Before Coding" section: state assumptions, name competing readings instead of picking one silently, say when a simpler approach exists, and turn a task into a check that can fail.
- The rule that every changed line must trace to the request.
- Cleaning up only what your own change orphaned, and noting pre-existing dead code instead of deleting it.
- Building nothing speculative, and rewriting a result that could be much shorter.
- Handling every error that can actually occur, without guarding states the code already makes impossible.

## What Was Changed

- Questions go through the `grill-me` skill rather than a bare question, following the global `AGENTS.md`.
- The upstream rule to match the existing style even where you would write it differently was not adopted.
  `engineering-principles` keeps its rule to bring old code up to the current standard, now limited to the lines a change touches, so that it agrees with the trace-to-the-request rule.
- The upstream skill was not vendored as its own skill, because it would duplicate `senior-developer` and contradict it on dead code and style with nothing to decide which one wins.
