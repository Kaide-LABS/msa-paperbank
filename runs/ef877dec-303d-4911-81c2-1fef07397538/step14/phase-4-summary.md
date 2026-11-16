# Stage 4

## What was built

The bot can now run its own search engine on the school's own computers, instead of renting Google's. A new piece reads a question and finds the most relevant past papers using a small program that runs on ordinary hardware. We also built a tool that re-does the search index for every stored paper, and a side-by-side checker that compares the new search results against the old Google ones to confirm people still get the same answers.

## What was decided

We kept the search quality the same size and shape as before, so users notice no difference. We fixed a flaw in the re-indexing tool that would have rebuilt the index incorrectly. We also added an automatic check that scans our own files for leaked passwords or old Google account details, to catch mistakes early.

## What is uncertain

This stage is finished, but a few things need attention. The full set of tests has only been confirmed on a slightly different setup than the school's real one, so it should be re-checked there. More importantly, the bot cannot yet start up on the school's servers without still reaching for Google — fixing that is the next stage's job. One internal log accidentally recorded sensitive-looking text.
