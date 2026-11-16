# Stage 5

## What was built

The bot can now be started on the school's own computers with a single command. Everything it needs to run — the bot, its database, its file storage, and its search brain — now starts up together as one package. The search brain is a small model that runs on the school's own hardware, so the bot no longer depends on Google for searching. There are also new tools to make nightly safety copies of the data and to restore from them if needed, plus written guides for starting it up and keeping it running securely over the internet.

## What was decided

Search was switched to a self-contained model so users get the same results without relying on Google. File storage can use either the plain hard disk or an optional add-on, kept simple by default. Safety copies refuse to run against the live system, to avoid accidents.

## What is uncertain

The stage finished, but some checks still need a real server. Nobody has yet started the full package on an actual school computer to confirm it runs without Google. The complete automated test run also needs confirming on the proper setup. One optional storage add-on may not report itself as "ready" correctly.
