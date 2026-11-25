# Stage 6 (final)

## What was built

The tools to actually move the bot off Google and onto the school's own servers now exist, and the bot's own code no longer depends on Google at all. There's a step-by-step moving kit: copy the data across, rebuild the search index on the school's hardware, and check the new search gives the same answers as the old one. All the Google-specific parts have been stripped out, and the bot now defaults to running entirely on the school's own equipment.

## What was decided

The moving tools won't touch the live system until someone signs a go-ahead note, and they only read (never change) the old Google setup — to prevent accidents. By default, nothing runs against the real data until explicitly confirmed, as a safety measure.

## What is uncertain

The moving kit has been written and tested, but **the actual move has not happened yet** — it waits for your sign-off. The full set of checks has only been run in a stand-in testing setup, not yet on a real school server or the real Docker setup. Someone still needs to confirm everything starts up and works cleanly on the school's actual hardware before going live.
