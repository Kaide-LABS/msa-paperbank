"""Channel adapters: translate a channel's own wire payload to/from the channel-neutral
`app.inbound.InboundMessage` / `app.schemas.Reply` envelope. The handler core imports none of
these; only the edge (webhook handlers) does."""
