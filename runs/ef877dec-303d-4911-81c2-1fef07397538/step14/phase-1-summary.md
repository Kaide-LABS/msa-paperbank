# Stage 1

## What was built

The groundwork for moving the past-paper bot off Google's cloud. The bot's code was reshaped so that the parts that talk to storage, search, passwords, and the database now go through standard "sockets." Today those sockets still plug into Google, but they're built so a different provider can be slotted in later without rewriting everything. A new round of safety checks was added for this reshaped plumbing, and those checks pass.

## What was decided

Google was kept as the only live provider for now, so nothing users rely on changes while the structure is rebuilt first. The team also chose to hold off rerouting a few remaining pieces to a later step, to keep each change small and reviewable.

## What is uncertain

This stage did not finish — it stopped partway. Several pieces still point directly at Google and need rerouting next: parts of the database, file handling, and password handling. The full set of automated checks could not all be run here because of a setup mismatch on the test machine, so wider confidence is not yet confirmed. The next worker has a written list of exactly what remains.
