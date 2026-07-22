# Starling Bank Receiver

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)

Receive **Starling Bank personal API V2** webhooks directly in Home Assistant.

This integration deliberately does not ask for a Starling access token. It receives webhook notifications only, creates Home Assistant entities, and fires automation events. Transaction details remain in your own Home Assistant instance.

![Starling Bank Receiver icon](brand/logo.png)

## What it creates

- `sensor.starling_bank_feed_feed` — a dashboard summary such as `💳 • £12.34 • Card payment • Example shop`, with a matching Home Assistant icon. Round-ups are identified separately with a piggy-bank icon. Its attributes keep the full unmodified Starling callback under `latest.raw_payload`, alongside the normalised fields used in automations.
- `sensor.starling_bank_feed_latest_amount` — the latest amount as a signed monetary value: money in is positive and money out is negative. Useful automation fields such as direction, transaction type, counterparty, category, and reference are direct attributes.
- `event.starling_bank_feed` — a Home Assistant event entity for the latest received webhook.
- `starling_bank_receiver.webhook_received` — Home Assistant event bus event for every accepted callback.
- `starling_bank_receiver.feed_item_received` — emitted for `FEED_ITEM` callbacks.

The integration keeps the latest 250 callbacks in Home Assistant's private integration storage and deduplicates deliveries by Starling's `webhookEventUid`.

## Install

1. Install through HACS as a custom repository (category: **Integration**) or copy `custom_components/starling_bank_receiver` to your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant.
3. Add **Starling Bank Receiver** from **Settings → Devices & services → Add integration**.
4. Copy the **Payload URL** shown on `sensor.starling_bank_feed` and paste it into Starling Developer Portal's *Payload URL* field.
5. In Starling, choose **Show public key** for that webhook. Open the integration's **Configure** menu in Home Assistant and paste the complete PEM key. The receiver verifies Starling's raw-payload `X-Hook-Signature` using SHA512withRSA and rejects unsigned callbacks.

## Data retention

The integration persists the latest 250 accepted callbacks using Home Assistant's integration storage. Each saved item contains the complete callback payload plus the friendly GBP summary fields, and is restored after a Home Assistant restart. This is intentionally local to Home Assistant; do not expose the entity's attributes in a public dashboard.

### Important: paste the base URL

Starling appends a callback type such as `/feed-item`, `/standing-order`, or `/standing-order-payment` to the base Payload URL. Paste the URL exactly as shown by the integration; do not add a suffix.

The receiving Home Assistant instance must have a public HTTPS external URL. The callback URL contains an unguessable secret; do not share it or commit it to Git.

## Automation example

```yaml
automation:
  - alias: React to a Starling feed item
    triggers:
      - trigger: event
        event_type: starling_bank_receiver.feed_item_received
    actions:
      - action: logbook.log
        data:
          name: Starling
          message: >-
            {{ trigger.event.data.direction }} {{ trigger.event.data.amount }}
            {{ trigger.event.data.currency }} at {{ trigger.event.data.counterparty_name }}
```

## Privacy and security

- No cloud account, token, analytics, or outbound network connection.
- Webhook IDs, account IDs, references, and counterparties are runtime data only.
- The callback route accepts only Starling's documented callback suffixes and validates the corresponding `webhookType`.
- Replay deliveries are ignored using `webhookEventUid` during the current Home Assistant runtime.

Starling's personal API webhook documentation should remain the source of truth for supported event types and callback semantics.

## Development

```bash
python3 -m compileall custom_components
python3 -m unittest discover -s tests
```

## Disclaimer

This is an independent community integration, not affiliated with, endorsed by, or supported by Starling Bank.
